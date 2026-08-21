import concurrent.futures
from datetime import datetime
import io
import json
import os
import threading
import pandas as pd
import requests
import yfinance as yf

# ================= CONFIGURATION =================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID", "@tFreeCryptoNSEAlert")
ALERT_RECORD_FILE = "sent_alerts.json"
CSV_FILE = "trade_log.csv"
# =================================================

# Yahoo Finance API के लिए सिक्योर सेशन और यूजर-एजेंट हेडर
session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
})

file_lock = threading.Lock()

def load_sent_alerts():
  """आज भेजे गए अलर्ट्स का रिकॉर्ड लोड करना"""
  if os.path.exists(ALERT_RECORD_FILE):
    try:
      with open(ALERT_RECORD_FILE, "r") as f:
        return json.load(f)
    except:
      return {}
  return {}

def save_sent_alert(ticker, today_str):
  """स्टॉक के अलर्ट को सुरक्षित तरीके से सेव करना ताकि बार-बार रिपीट न हो"""
  with file_lock:
    data = load_sent_alerts()
    if today_str not in data:
      data[today_str] = []
    if ticker not in data[today_str]:
      data[today_str].append(ticker)
    with open(ALERT_RECORD_FILE, "w") as f:
      json.dump(data, f)

def is_already_sent(ticker, today_str):
  """चेक करना कि क्या आज यह अलर्ट भेजा जा चुका है"""
  with file_lock:
    data = load_sent_alerts()
    if today_str in data and ticker in data[today_str]:
      return True
    return False

def log_to_csv(date_str, time_str, symbol, price, trigger, vol_ratio):
    """Excel/CSV फाइल में ऑटोमैटिक ट्रेड लॉग जोड़ना"""
    with file_lock:
        file_exists = os.path.exists(CSV_FILE)
        with open(CSV_FILE, "a") as f:
            if not file_exists or os.path.getsize(CSV_FILE) == 0:
                f.write("Date,Time,Stock,Current Price,Trigger Price,Volume Spike,Trend Status\n")
            f.write(f"{date_str},{time_str},{symbol},{price:.2f},{trigger:.2f},{vol_ratio:.2f}x,Strong Uptrend ✅\n")

def send_telegram_alert(message):
  """Telegram पर अलर्ट भेजने का फंक्शन"""
  if not TELEGRAM_BOT_TOKEN:
      return
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
  try:
    requests.post(url, json=payload, timeout=10)
  except Exception as e:
    print(f"Telegram Error: {e}")

def get_nifty_total_market_symbols():
  """Nifty Total Market (500+ Stocks) की लिस्ट डाउनलोड करना"""
  index_urls = [
      "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
      "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
      "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
  ]
  headers = {"User-Agent": "Mozilla/5.0"}
  all_symbols = set()
  for url in index_urls:
    try:
      response = requests.get(url, headers=headers, timeout=10)
      if response.status_code == 200:
        df = pd.read_csv(io.BytesIO(response.content))
        if "Symbol" in df.columns:
          for sym in df["Symbol"].dropna():
            all_symbols.add(str(sym).strip())
    except Exception:
      pass
  if all_symbols:
    print(f"Total Unique Stocks Found: {len(all_symbols)}")
    return list(all_symbols)
  return ["RELIANCE", "TCS", "INFY", "ICICIBANK"]

def get_daily_data(symbol):
  ticker = symbol + ".NS"
  try:
    df = yf.download(ticker, period="1y", interval="1d", progress=False, session=session)
    if df.empty or len(df) < 200:
      return None
    if isinstance(df.columns, pd.MultiIndex):
      df.columns = df.columns.droplevel(1)
    return df
  except Exception:
    return None

def check_high_probability_breakout(symbol):
  df = get_daily_data(symbol)
  if df is None or df.empty or len(df) < 200:
    return

  dma_50 = df["Close"].rolling(window=50).mean().iloc[-1]
  dma_200 = df["Close"].rolling(window=200).mean().iloc[-1]
  df["Vol_SMA20"] = df["Volume"].rolling(window=20).mean()

  prev_df = df.iloc[:-1]
  high_20 = prev_df["High"].iloc[-20:].max()

  current_candle = df.iloc[-1]
  close_price = current_candle["Close"]
  current_vol = current_candle["Volume"]
  avg_vol_20 = current_candle["Vol_SMA20"]
  
  today_date = datetime.now().strftime("%Y-%m-%d")
  current_time = datetime.now().strftime("%H:%M:%S")

  vol_ratio = current_vol / avg_vol_20 if avg_vol_20 > 0 else 0

  # High Conviction Setup Logic
  if (
      (close_price > dma_50)
      and (close_price > dma_200)
      and (vol_ratio >= 1.5)
      and ((high_20 * 0.995) <= close_price <= high_20)
  ):
    # डुप्लीकेट चेक (ताकि दिन में एक ही बार अलर्ट आए)
    if not is_already_sent(symbol, today_date):
      msg = (
          f"🔥 *Nifty Total Market Breakout Alert!* 🔥\n\n"
          f"📌 *Stock:* `{symbol}`\n"
          f"💰 *Current Price:* `{close_price:.2f}`\n"
          f"🎯 *Trigger / Buy Price (20-Day High):* `{high_20:.2f}`\n"
          f"📊 *Volume Spike:* `{vol_ratio:.2f}x` (Massive Buying 🟢)\n"
          f"📈 *Trend Status:* Strong (Strong Uptrend Above 50 & 200 DMA) ✅\n"
          f"💡 *Action:* Is trigger price par order lagakar tayaar rahein!\n"
          f"⏰ *Time:* `{today_date} {current_time}`"
      )
      print(f"Alert Triggered: {symbol}")
      send_telegram_alert(msg)
      # Telegram के साथ-साथ CSV फाइल में भी एंट्री सेव करें
      log_to_csv(today_date, current_time, symbol, close_price, high_20, vol_ratio)
      save_sent_alert(symbol, today_date)

def main():
  print("🚀 Starting Nifty Total Market Scan & CSV Log...")
  symbols = get_nifty_total_market_symbols()
  if not symbols:
    print("❌ No symbols found.")
    return

  print(f"Scanning {len(symbols)} stocks with Multi-threading...")
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    futures = {executor.submit(check_high_probability_breakout, stock): stock for stock in symbols}
    for future in concurrent.futures.as_completed(futures):
      try:
        future.result(timeout=6)
      except Exception:
        pass
  print("✅ Scan Completed Successfully.")

if __name__ == "__main__":
  main()
