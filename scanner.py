import datetime
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import sys
import pandas as pd
import requests
import warnings
import yfinance as yf

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

# --- टेलीग्राम क्रेडेंशियल्स ---
TELEGRAM_TOKEN = "8663109611:AAEgppVnCtd3l0Yv5B_zieiw-NquXMKyP1I"
CHAT_ID = "@tFreeCryptoNSEAlert"
ALERT_RECORD_FILE = "sent_crypto_alerts.json"


def send_telegram(msg):
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
  try:
    requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=5,
    )
  except Exception as e:
    print(f"Telegram Error: {e}")


def load_sent_alerts():
  if os.path.exists(ALERT_RECORD_FILE):
    try:
      with open(ALERT_RECORD_FILE, "r") as f:
        return json.load(f)
    except:
      return {}
  return {}


def save_sent_alert(alert_key, today_str):
  data = load_sent_alerts()
  if today_str not in data:
    data[today_str] = []
  if alert_key not in data[today_str]:
    data[today_str].append(alert_key)
  with open(ALERT_RECORD_FILE, "w") as f:
    json.dump(data, f)


def is_already_sent(alert_key, today_str):
  data = load_sent_alerts()
  if today_str in data and alert_key in data[today_str]:
    return True
  return False


IST = timezone(timedelta(hours=5, minutes=30))

coindcx_cryptos = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "BNB-USD",
    "XRP-USD",
    "DOGE-USD",
    "ADA-USD",
    "AVAX-USD",
    "LINK-USD",
    "DOT-USD",
    "POL-USD",
    "NEAR-USD",
    "UNI-USD",
    "LTC-USD",
    "BCH-USD",
    "ATOM-USD",
    "XLM-USD",
    "ICP-USD",
    "APT-USD",
    "SUI-USD",
    "RENDER-USD",
    "FET-USD",
    "INJ-USD",
    "ARB-USD",
    "OP-USD",
    "TIA-USD",
    "SEI-USD",
    "FTM-USD",
    "SAND-USD",
    "MANA-USD",
    "PEPE-USD",
    "SHIB-USD",
]


def calculate_rsi(series, period=14):
  delta = series.diff()
  gain = delta.where(delta > 0, 0).rolling(window=period).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
  rs = gain / loss
  return 100 - (100 / (1 + rs))


def analyze_crypto_market(ticker_list, today_str):
  signals_5_13 = []
  signals_12_21 = []
  signals_probabilistic = []
  signals_prebreakout = []

  for ticker in ticker_list:
    try:
      old_stderr = sys.stderr
      sys.stderr = open(os.devnull, "w")
      data = yf.download(ticker, period="60d", interval="1h", progress=False)
      sys.stderr.close()
      sys.stderr = old_stderr

      if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

      if data.empty or len(data) < 200:
        continue

      close = data["Close"].squeeze()
      high = data["High"].squeeze()
      low = data["Low"].squeeze()
      vol = data["Volume"].squeeze()

      if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
      if isinstance(high, pd.DataFrame):
        high = high.iloc[:, 0]
      if isinstance(low, pd.DataFrame):
        low = low.iloc[:, 0]
      if isinstance(vol, pd.DataFrame):
        vol = vol.iloc[:, 0]

      cmp = float(close.iloc[-1])
      coin_name = ticker.replace("-USD", "")

      recent_high = float(high.tail(10).max())
      recent_low = float(low.tail(10).min())
      range_spread = (
          (recent_high - recent_low) / cmp if cmp > 0 else 0.001
      )
      avg_vol = float(vol.tail(20).mean())
      cur_vol = float(vol.iloc[-1])

      squeeze_score = round(
          (1 / range_spread) * (cur_vol / avg_vol if avg_vol > 0 else 1), 2
      )

      if squeeze_score > 1000:
        # STRATEGY 1: Fast 5/13 EMA Scalping
        ema_5 = close.ewm(span=5, adjust=False).mean()
        ema_13 = close.ewm(span=13, adjust=False).mean()
        p5, c5 = float(ema_5.iloc[-2]), float(ema_5.iloc[-1])
        p13, c13 = float(ema_13.iloc[-2]), float(ema_13.iloc[-1])

        if p5 <= p13 and c5 > c13:
          alert_key = f"{coin_name}_5_13_BUY"
          if not is_already_sent(alert_key, today_str):
            signals_5_13.append(
                f"🟢 `[5/13 BUY]` *{coin_name}* | Score: `{squeeze_score}` |"
                f" CMP: `{cmp}`"
            )
            save_sent_alert(alert_key, today_str)
        elif p5 >= p13 and c5 < c13:
          alert_key = f"{coin_name}_5_13_SELL"
          if not is_already_sent(alert_key, today_str):
            signals_5_13.append(
                f"🔴 `[5/13 SELL]` *{coin_name}* | Score: `{squeeze_score}` |"
                f" CMP: `{cmp}`"
            )
            save_sent_alert(alert_key, today_str)

        # STRATEGY 2: Research Paper EMA 12/21 Crossover
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_21 = close.ewm(span=21, adjust=False).mean()
        p12, c12 = float(ema_12.iloc[-2]), float(ema_12.iloc[-1])
        p21, c21 = float(ema_21.iloc[-2]), float(ema_21.iloc[-1])

        if p12 <= p21 and c12 > c21:
          alert_key = f"{coin_name}_12_21_BUY"
          if not is_already_sent(alert_key, today_str):
            signals_12_21.append(
                f"🟢 `[12/21 BUY]` *{coin_name}* | Score: `{squeeze_score}` |"
                f" CMP: `{cmp}`"
            )
            save_sent_alert(alert_key, today_str)
        elif p12 >= p21 and c12 < c21:
          alert_key = f"{coin_name}_12_21_SELL"
          if not is_already_sent(alert_key, today_str):
            signals_12_21.append(
                f"🔴 `[12/21 SELL]` *{coin_name}* | Score: `{squeeze_score}` |"
                f" CMP: `{cmp}`"
            )
            save_sent_alert(alert_key, today_str)

        # STRATEGY 3: Probabilistic Extrema
        if cmp <= recent_low * 1.01:
          alert_key = f"{coin_name}_PROB_MIN_BUY"
          if not is_already_sent(alert_key, today_str):
            signals_probabilistic.append(
                f"🟢 `[Prob. Minima BUY]` *{coin_name}* | Score:"
                f" `{squeeze_score}`"
            )
            save_sent_alert(alert_key, today_str)
        elif cmp >= recent_high * 0.99:
          alert_key = f"{coin_name}_PROB_MAX_SELL"
          if not is_already_sent(alert_key, today_str):
            signals_probabilistic.append(
                f"🔴 `[Prob. Maxima SELL]` *{coin_name}* | Score:"
                f" `{squeeze_score}`"
            )
            save_sent_alert(alert_key, today_str)

        # STRATEGY 4: Pre-Breakout
        ema_30 = close.ewm(span=30, adjust=False).mean()
        ema_50 = close.ewm(span=50, adjust=False).mean()
        ema_100 = close.ewm(span=100, adjust=False).mean()
        ema_200 = close.ewm(span=200, adjust=False).mean()
        rsi = calculate_rsi(close, period=14)

        c30, c50, c100, c200 = (
            float(ema_30.iloc[-1]),
            float(ema_50.iloc[-1]),
            float(ema_100.iloc[-1]),
            float(ema_200.iloc[-1]),
        )
        curr_rsi = float(rsi.iloc[-1])

        is_uptrend = (c30 > c50) and (c50 > c100)
        is_downtrend = (c30 < c50) and (c50 < c100)

        if (
            is_uptrend
            and (48 <= curr_rsi <= 60)
            and (abs(cmp - c30) / c30 < 0.015)
            and (range_spread < 0.05)
        ):
          alert_key = f"{coin_name}_PRE_BREAKOUT_BUY"
          if not is_already_sent(alert_key, today_str):
            sl = round(c200, 4)
            if sl >= cmp:
              sl = round(cmp * 0.985, 4)
            risk = cmp - sl
            target = round(cmp + (risk * 3), 4)
            signals_prebreakout.append(
                f"🚀 `[Pre-Breakout BUY]` *{coin_name}* | Score:"
                f" `{squeeze_score}` | Target: `{target}`"
            )
            save_sent_alert(alert_key, today_str)
        elif (
            is_downtrend
            and (40 <= curr_rsi <= 52)
            and (abs(cmp - c30) / c30 < 0.015)
            and (range_spread < 0.05)
        ):
          alert_key = f"{coin_name}_PRE_BREAKOUT_SELL"
          if not is_already_sent(alert_key, today_str):
            sl = round(c200, 4)
            if sl <= cmp:
              sl = round(cmp * 1.015, 4)
            risk = sl - cmp
            target = round(cmp - (risk * 3), 4)
            signals_prebreakout.append(
                f"🔻 `[Pre-Breakout SELL]` *{coin_name}* | Score:"
                f" `{squeeze_score}` | Target: `{target}`"
            )
            save_sent_alert(alert_key, today_str)

    except Exception:
      pass

  return (
      signals_5_13,
      signals_12_21,
      signals_probabilistic,
      signals_prebreakout,
  )


print("🚀 4-Strategy Crypto Bot शुरू हो गया है...")
t_obj = datetime.now(IST)
t_str = t_obj.strftime("%d-%m-%Y | %H:%M:%S IST")
today_date_str = t_obj.strftime("%Y-%m-%d")

s5_13, s12_21, s_prob, s_pre = analyze_crypto_market(
    coindcx_cryptos, today_date_str
)

if s5_13 or s12_21 or s_prob or s_pre:
  msg_lines = [
      (
          "⚡ *4-STRATEGY HIGH-SCORE ALERTS (Score > 1000)* ⚡\n*Time:*"
          f" `{t_str}`\n"
      )
  ]
  if s5_13:
    msg_lines.append("⚡ *--- 1. Fast 5/13 EMA Scalping ---*")
    msg_lines.extend(s5_13[:3])
    msg_lines.append("")
  if s12_21:
    msg_lines.append("📚 *--- 2. Research Paper 12/21 EMA ---*")
    msg_lines.extend(s12_21[:3])
    msg_lines.append("")
  if s_prob:
    msg_lines.append("📊 *--- 3. Probabilistic Extrema & Rolling ---*")
    msg_lines.extend(s_prob[:3])
    msg_lines.append("")
  if s_pre:
    msg_lines.append("📈 *--- 4. Pre-Breakout (30/50/100 EMA) ---*")
    msg_lines.extend(s_pre[:3])

  send_telegram("\n".join(msg_lines))
  print("✅ सिग्नल्स टेलीग्राम पर भेज दिए गए हैं!")
else:
  print("⏳ नए सिग्नल्स नहीं मिले हैं।")
