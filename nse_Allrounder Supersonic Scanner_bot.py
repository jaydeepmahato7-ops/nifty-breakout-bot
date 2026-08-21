import concurrent.futures
import datetime
import io
import json
import os
import pandas as pd
import requests
import time
import yfinance as yf

# ==================== CONFIGURATION ====================
TELEGRAM_TOKEN = "8663109611:AAEgppVnCtd3l0Yv5B_zieiw-NquXMKyP1I"
CHAT_ID = "@tFreeCryptoNSEAlert"
ALERT_RECORD_FILE = "sent_alerts.json"
# =======================================================

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
})


def load_sent_alerts():
  if os.path.exists(ALERT_RECORD_FILE):
    try:
      with open(ALERT_RECORD_FILE, "r") as f:
        return json.load(f)
    except:
      return {}
  return {}


def save_sent_alert(ticker, today_str):
  data = load_sent_alerts()
  if today_str not in data:
    data[today_str] = []
  if ticker not in data[today_str]:
    data[today_str].append(ticker)
  with open(ALERT_RECORD_FILE, "w") as f:
    json.dump(data, f)


def is_already_sent(ticker, today_str):
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
    return list(all_symbols)
  return ["RELIANCE.NS", "TCS.NS", "INFY.NS", "ICICIBANK.NS", "SBIN.NS"]


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

    close, open_p, high, low, vol = (
        df["Close"],
        df["Open"],
        df["High"],
        df["Low"],
        df["Volume"],
    )
    current_close = float(close.iloc[-1])
    current_open = float(open_p.iloc[-1])
    current_high = float(high.iloc[-1])
    current_low = float(low.iloc[-1])
    current_volume = float(vol.iloc[-1])
    prev_close = float(close.iloc[-2])

    if current_open < (prev_close * 0.98):
      return None

    avg_price = close.rolling(window=20).mean()
    avg_vol = vol.rolling(window=20).mean()
    if (avg_price * avg_vol).iloc[-1] < 50000000:
      return None

    ema50 = close.rolling(window=50).mean()
    if current_close < ema50.iloc[-1]:
      return None

    stock_return_20d = (
        (current_close - float(close.iloc[-20])) / float(close.iloc[-20])
    ) * 100
    if stock_return_20d < (nifty_return_20d + 3.0):
      return None

    total_range = current_high - current_low
    if total_range == 0:
      return None

    body_size = current_close - current_open
    upper_wick = current_high - current_close
    if not (
        current_close > current_open
        and body_size >= (0.50 * total_range)
        and upper_wick <= (0.35 * total_range)
    ):
      return None

    try:
      sector = yf.Ticker(ticker, session=session).info.get(
          "sector", "Unknown"
      )
    except Exception:
      sector = "Unknown"

    past_data = df.iloc[-30:-5]
    support_level = float(past_data["Low"].min())

    if (current_low <= support_level * 1.03) and (
        current_volume >= (float(avg_vol.iloc[-1]) * 1.05)
    ):
      stock_name = ticker.replace(".NS", "")
      tr = high - low
      atr = float(tr.rolling(window=14).mean().iloc[-1])
      stop_loss = round(current_close - (1.5 * atr), 1)
      target = round(current_close + (3 * (1.5 * atr)), 1)
      vol_ratio = current_volume / float(avg_vol.iloc[-1])
      score = round((vol_ratio * 30) + ((stock_return_20d - nifty_return_20d) * 20), 1)

      return {
          "stock": stock_name,
          "price": round(current_close, 1),
          "sector": sector,
          "sl": stop_loss,
          "target": target,
          "score": score,
          "earnings": get_earnings_date(ticker),
      }
  except Exception:
    pass
  return None


def run_scan():
  today_str = datetime.date.today().strftime("%Y-%m-%d")
  print(f"\n[Running Total Market Scan] Time: {datetime.datetime.now()}")

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

  watchlist = get_nifty_total_market_symbols()
  results_list = []

  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    futures = {
        executor.submit(
            analyze_stock, ticker, nifty_return_20d, None
        ): ticker
        for ticker in watchlist
    }
    for future in concurrent.futures.as_completed(futures):
      try:
        res = future.result(timeout=6)
        if res and not is_already_sent(res["stock"], today_str):
          results_list.append(res)
      except Exception:
        pass

  if results_list:
    results_list.sort(key=lambda x: x["score"], reverse=True)
    table_rows = [
        f"{'Rk':<2} | {'Stock':<9} | {'Price':<6} | {'SL':<6} | {'Tgt':<6} |"
        f" {'Earn':<10} | {'Scr':<5}",
        "-" * 60,
    ]
    for idx, item in enumerate(results_list, start=1):
      table_rows.append(
          f"{idx:<2} | {item['stock']:<9} | {item['price']:<6.1f} |"
          f" {item['sl']:<6.1f} | {item['target']:<6.1f} |"
          f" {item['earnings']:<10} | {item['score']:<5}"
      )
      save_sent_alert(item["stock"], today_str)

    final_message = (
        "🔥 *Nifty Total Market Outperformer Bot* 🔥\n```text\n"
        + "\n".join(table_rows)
        + "\n```"
    )
    send_telegram_message(final_message)
    print(f"Alert sent for {len(results_list)} setups!")
  else:
    print("No setups matched current conditions.")


if __name__ == "__main__":
  run_scan()
