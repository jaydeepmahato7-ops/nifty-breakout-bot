import concurrent.futures
import datetime
import io
import json
import os
import pandas as pd
import requests
import schedule
import time
import yfinance as yf

# ==================== CONFIGURATION ====================
TELEGRAM_TOKEN = "8663109611:AAEgppVnCtd3l0Yv5B_zieiw-NquXMKyP1I"
CHAT_ID = "@tFreeCryptoNSEAlert"
ALERT_RECORD_FILE = "sent_alerts.json"
# =======================================================

# Global control variables
IS_SCANNING = False

# Create a secure session with browser headers to bypass Yahoo 401/Crumb error
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
})


def load_sent_alerts():
  """आज भेजे गए अलर्ट्स का JSON फाइल से रिकॉर्ड लोड करना"""
  if os.path.exists(ALERT_RECORD_FILE):
    try:
      with open(ALERT_RECORD_FILE, "r") as f:
        return json.load(f)
    except:
      return {}
  return {}


def save_sent_alert(ticker, today_str):
  """स्टॉक के अलर्ट को JSON फाइल में परमानेंट सेव करना"""
  data = load_sent_alerts()
  if today_str not in data:
    data[today_str] = []
  if ticker not in data[today_str]:
    data[today_str].append(ticker)
  with open(ALERT_RECORD_FILE, "w") as f:
    json.dump(data, f)


def is_already_sent(ticker, today_str):
  """चेक करना कि क्या आज यह अलर्ट पहले ही भेजा जा चुका है"""
  data = load_sent_alerts()
  if today_str in data and ticker in data[today_str]:
    return True
  return False


def send_telegram_message(message):
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
  payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
  try:
    response = requests.post(url, json=payload, timeout=10)
    if response.status_code != 200:
      print(f"Telegram Error: {response.text}")
  except Exception as e:
    print(f"Telegram Exception: {e}")


def get_nifty_total_market_symbols():
  """Nifty Total Market (Nifty 500 + Midcap 150 + Smallcap 250) की पूरी लिस्ट प्राप्त करना"""
  index_urls = [
      "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
      "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
      "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
  ]
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "en-US,en;q=0.9",
  }

  all_symbols = set()
  for url in index_urls:
    try:
      response = requests.get(url, headers=headers, timeout=10)
      if response.status_code == 200:
        df = pd.read_csv(io.StringIO(response.text))
        if "Symbol" in df.columns:
          for sym in df["Symbol"].dropna():
            all_symbols.add(str(sym).strip().upper() + ".NS")
    except Exception:
      pass

  if all_symbols:
    print(
        f"✅ Total Market Watchlist Loaded: {len(all_symbols)} Stocks Found!"
    )
    return list(all_symbols)

  return [
      "RELIANCE.NS",
      "TCS.NS",
      "INFY.NS",
      "ICICIBANK.NS",
      "SBIN.NS",
      "TATAMOTORS.NS",
      "AXISBANK.NS",
      "ITC.NS",
  ]


def get_earnings_date(ticker):
  try:
    tk = yf.Ticker(ticker, session=session)
    info = tk.info
    for key in [
        "earningsTimestamp",
        "earningsTimestampStart",
        "earningsTimestampEnd",
    ]:
      ts = info.get(key)
      if ts and isinstance(ts, (int, float)) and ts > 0:
        return datetime.datetime.fromtimestamp(ts).strftime("%d-%m-%Y")
  except Exception:
    pass
  return "N/A"


def analyze_stock(ticker, nifty_return_20d, nifty_df):
  try:
    df = yf.download(
        ticker, period="3mo", interval="1d", progress=False, session=session
    )
    if df is None or len(df) < 60:
      return None
    if isinstance(df.columns, pd.MultiIndex):
      df.columns = df.columns.get_level_values(0)

    close = df["Close"]
    open_p = df["Open"]
    high = df["High"]
    low = df["Low"]
    vol = df["Volume"]

    current_close = float(close.iloc[-1])
    current_open = float(open_p.iloc[-1])
    current_high = float(high.iloc[-1])
    current_low = float(low.iloc[-1])
    current_volume = float(vol.iloc[-1])
    prev_close = float(close.iloc[-2])

    # 1. NEWS & PANIC FILTER (Gap Down Check)
    if current_open < (prev_close * 0.98):
      return None

    # 2. LIQUIDITY & TURNOVER FILTER (Minimum ₹5 Crore Daily Turnover)
    avg_price = close.rolling(window=20).mean()
    avg_vol = vol.rolling(window=20).mean()
    avg_turnover = (avg_price * avg_vol).iloc[-1]
    if avg_turnover < 50000000:
      return None

    # 3. TREND ALIGNMENT (50-EMA Filter)
    ema50 = close.rolling(window=50).mean()
    if current_close < ema50.iloc[-1]:
      return None

    # 4. RELATIVE STRENGTH (RS) FILTER
    stock_return_20d = (
        (current_close - float(close.iloc[-20])) / float(close.iloc[-20])
    ) * 100
    if stock_return_20d < (nifty_return_20d + 3.0):
      return None

    # 5. FRESH SUPPORT (VIRGIN SUPPORT) CHECK
    past_data = df.iloc[-30:-5]
    support_level = float(past_data["Low"].min())
    support_zone = support_level * 1.005
    previous_touches = len(past_data[past_data["Low"] <= support_zone])
    if previous_touches > 1:
      return None

    # 6. SOLID BULLISH CANDLE ANATOMY FILTER
    total_range = current_high - current_low
    if total_range == 0:
      return None

    body_size = current_close - current_open
    upper_wick = current_high - current_close

    is_green = current_close > current_open
    is_solid_body = body_size >= (0.50 * total_range)
    is_small_upper_wick = upper_wick <= (0.35 * total_range)

    if not (is_green and is_solid_body and is_small_upper_wick):
      return None

    # 7. SECTOR & VOLUME VALIDATION
    try:
      ticker_info = yf.Ticker(ticker, session=session).info
      sector = ticker_info.get("sector", "Unknown")
    except Exception:
      sector = "Unknown"

    is_at_support = (current_low <= support_level * 1.03) and (
        current_low >= support_level * 0.97
    )
    is_volume_supported = current_volume >= (float(avg_vol.iloc[-1]) * 1.05)

    if is_at_support and is_volume_supported:
      stock_name = ticker.replace(".NS", "")

      # Dynamic ATR Risk Management (1:3 Risk-Reward)
      tr = high - low
      atr = float(tr.rolling(window=14).mean().iloc[-1])
      stop_loss = round(current_close - (1.5 * atr), 1)
      target = round(current_close + (3 * (1.5 * atr)), 1)

      # Multi-Factor Scoring
      vol_ratio = current_volume / float(avg_vol.iloc[-1])
      rs_score = stock_return_20d - nifty_return_20d
      score = round((vol_ratio * 30) + (rs_score * 20), 1)

      earnings_date = get_earnings_date(ticker)

      return {
          "stock": stock_name,
          "price": round(current_close, 1),
          "sector": sector,
          "sl": stop_loss,
          "target": target,
          "score": score,
          "earnings": earnings_date,
      }
  except Exception:
    pass
  return None


def run_continuous_scan():
  current_date = datetime.date.today()
  today_str = current_date.strftime("%Y-%m-%d")

  print(
      f"\n[Running Total Market Scan] Time:"
      f" {datetime.datetime.now().strftime('%H:%M:%S')}"
  )

  try:
    nifty_df = yf.download(
        "^NSEI", period="3mo", interval="1d", progress=False, session=session
    )
    if isinstance(nifty_df.columns, pd.MultiIndex):
      nifty_df.columns = nifty_df.columns.get_level_values(0)
    nifty_return_20d = (
        (
            float(nifty_df["Close"].iloc[-1])
            - float(nifty_df["Close"].iloc[-20])
        )
        / float(nifty_df["Close"].iloc[-20])
    ) * 100
  except Exception:
    nifty_return_20d = 0.0
    nifty_df = None

  watchlist = get_nifty_total_market_symbols()
  results_list = []

  # Thread pool with strict timeout handling per task to prevent hanging
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    futures = {
        executor.submit(
            analyze_stock, ticker, nifty_return_20d, nifty_df
        ): ticker
        for ticker in watchlist
    }
    for future in concurrent.futures.as_completed(futures):
      try:
        # 6 seconds timeout per stock thread so it never hangs indefinitely
        res = future.result(timeout=6)
        if res:
          if not is_already_sent(res["stock"], today_str):
            results_list.append(res)
      except concurrent.futures.TimeoutError:
        pass  # Skip stuck stocks safely
      except Exception:
        pass

  if results_list:
    results_list.sort(key=lambda x: x["score"], reverse=True)

    table_rows = []
    table_rows.append(
        f"{'Rk':<2} | {'Stock':<9} | {'Price':<6} | {'SL':<6} | {'Tgt':<6} |"
        f" {'Earn':<10} | {'Scr':<5}"
    )
    table_rows.append("-" * 60)

    for idx, item in enumerate(results_list, start=1):
      row = (
          f"{idx:<2} | {item['stock']:<9} | {item['price']:<6.1f} |"
          f" {item['sl']:<6.1f} | {item['target']:<6.1f} |"
          f" {item['earnings']:<10} | {item['score']:<5}"
      )
      table_rows.append(row)
      save_sent_alert(item["stock"], today_str)

    table_content = "\n".join(table_rows)
    final_message = (
        "🔥 *Nifty Total Market Outperformer Bot* 🔥\n```text\n"
        f"{table_content}\n```"
    )
    send_telegram_message(final_message)
    print(f"Alert sent for {len(results_list)} setups!")
  else:
    print("No setups matched current conditions.")


def safe_run_scanner():
  global IS_SCANNING
  if IS_SCANNING:
    print("Previous scan still active, skipping cycle...")
    return

  IS_SCANNING = True
  try:
    run_continuous_scan()
  finally:
    IS_SCANNING = False


# Schedule scan every 5 minutes
schedule.every(5).minutes.do(safe_run_scanner)

print("🤖 Nifty Total Market Outperformer Scanner is Active with Timeout Protection!")
print(
    "Scanning Total Market for 50-EMA & Relative Strength setups every 5"
    " minutes..."
)

# Run once immediately on startup
safe_run_scanner()

while True:
  schedule.run_pending()
  time.sleep(10)