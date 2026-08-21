# -------------------------------------------------------------------------
# CAR + DMAs + 8 Advanced Filters (Chakravyuh) Breakout Scanner (Clean & Safe)
# -------------------------------------------------------------------------
from datetime import datetime
import gc
import json
import logging
import os
import time
import warnings
import pandas as pd
import requests
import yfinance as yf

# --- टेलीग्राम क्रेडेंशियल्स ---
TELEGRAM_TOKEN = "8663109611:AAEgppVnCtd3l0Yv5B_zieiw-NquXMKyP1I"
CHAT_ID = "@tFreeCryptoNSEAlert"

# अलर्ट रिकॉर्ड फाइल का नाम
ALERT_RECORD_FILE = "sent_alerts.json"

# Yahoo Finance ब्लॉक से बचने के लिए Secure Session सेटअप
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
  try:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    response = requests.post(url, json=payload, timeout=10)
    if response.status_code != 200:
      print(f"Telegram Alert Error: {response.text}")
  except Exception as e:
    print(f"Telegram Connection Error: {e}")


logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")


def advanced_stock_scanner(ticker_list):
  results = []
  today_date = datetime.now().strftime("%d-%m-%Y")
  print("🔄 मार्केट हेल्थ (Nifty Breadth) चेक की जा रही है...")

  nifty_ret_20 = 0
  try:
    nifty_df = yf.download(
        "^NSEI", period="6mo", interval="1d", progress=False, session=session
    )
    if not nifty_df.empty:
      if isinstance(nifty_df.columns, pd.MultiIndex):
        nifty_close = nifty_df["Close"].iloc[:, 0].squeeze()
      else:
        nifty_close = nifty_df["Close"].squeeze()
      nifty_cmp = nifty_close.iloc[-1]
      nifty_ema50 = nifty_close.ewm(span=50, adjust=False).mean().iloc[-1]

      if nifty_cmp < nifty_ema50:
        print(
            "⚠️ [Market Warning] निफ्टी 50-EMA से नीचे है, लेकिन स्कैनर चालू रहेगा!"
        )
      else:
        print("✅ मार्केट ब्रेड्थ पॉजिटिव है।")

      try:
        nifty_ret_20 = (
            (nifty_close.iloc[-1] - nifty_close.iloc[-20])
            / nifty_close.iloc[-20]
        ) * 100
      except:
        nifty_ret_20 = 0
  except Exception as e:
    print(f"Market Check Notice: {e}")

  print("🚀 सभी शेयरों की स्कैनिंग शुरू हो रही है...\n")

  for idx, ticker in enumerate(ticker_list):
    print(f"[{idx+1}/{len(ticker_list)}] चेक हो रहा है: {ticker}")
    try:
      time.sleep(0.3)
      data = yf.download(
          ticker, period="2y", interval="1d", progress=False, session=session
      )
      if data.empty or len(data) < 200:
        continue

      if isinstance(data.columns, pd.MultiIndex):
        close_prices = data["Close"].iloc[:, 0]
        open_prices = data["Open"].iloc[:, 0]
        high_prices = data["High"].iloc[:, 0]
        low_prices = data["Low"].iloc[:, 0]
        volume_data = data["Volume"].iloc[:, 0]
      else:
        close_prices = data["Close"]
        open_prices = data["Open"]
        high_prices = data["High"]
        low_prices = data["Low"]
        volume_data = data["Volume"]

      close_prices = close_prices.squeeze()
      open_prices = open_prices.squeeze()
      high_prices = high_prices.squeeze()
      low_prices = low_prices.squeeze()
      volume_data = volume_data.squeeze()

      if (
          isinstance(close_prices, pd.DataFrame)
          or close_prices.empty
          or len(close_prices) < 200
      ):
        continue

      cmp = float(close_prices.iloc[-1])
      opn = float(open_prices.iloc[-1])
      high_today = float(high_prices.iloc[-1])
      low_today = float(low_prices.iloc[-1])
      current_vol = float(volume_data.iloc[-1])

      # --- फ़िल्टर 1: ₹5 करोड़+ टर्नओवर चेक ---
      turnover = cmp * current_vol
      if turnover < 50_000_000:
        continue

      # --- फ़िल्टर 2: 50-EMA Uptrend चेक ---
      ema_50_series = close_prices.ewm(span=50, adjust=False).mean()
      ema_50_current = float(ema_50_series.iloc[-1])
      ema_50_prev = float(ema_50_series.iloc[-5])

      if not (cmp > ema_50_current and ema_50_current > ema_50_prev):
        continue

      # --- फ़िल्टर 3: Relative Strength (+4% vs Nifty) चेक ---
      stock_ret_20 = (
          (float(close_prices.iloc[-1]) - float(close_prices.iloc[-20]))
          / float(close_prices.iloc[-20])
      ) * 100
      relative_strength_diff = stock_ret_20 - nifty_ret_20
      if relative_strength_diff < 4.0:
        continue

      # --- फ़िल्टर 4: Virgin Support / Low Bounce चेक ---
      low_20 = float(close_prices.tail(20).min())
      price_bounce_pct = ((cmp - low_20) / low_20) * 100
      if not (2.0 <= price_bounce_pct <= 20.0):
        continue

      # --- फ़िल्टर 5: Solid Green Candle + Small Upper Wick चेक ---
      candle_body = cmp - opn
      total_candle_range = high_today - low_today
      upper_wick = high_today - max(cmp, opn)

      is_solid_green = (
          (cmp > opn)
          and (total_candle_range > 0)
          and (candle_body >= 0.4 * total_candle_range)
          and (upper_wick <= 0.3 * total_candle_range)
      )
      if not is_solid_green:
        continue

      # --- फ़िल्टर 6: No Overhead Resistance (52-Week High Check) ---
      high_52w = float(high_prices.tail(252).max())
      if cmp < 0.90 * high_52w:
        continue

      # --- फ़िल्टर 7: Volume Spike (>= 1.1x) चेक ---
      vol_20_avg = float(volume_data.rolling(window=20).mean().iloc[-1])
      volume_ratio = current_vol / vol_20_avg if vol_20_avg > 0 else 1
      if volume_ratio < 1.1:
        continue

      # CAR और ट्रेंड कैलकुलेशन
      last_1y_data = high_prices.tail(252)
      if last_1y_data.empty:
        continue
      high_date = last_1y_data.idxmax()

      car_data = close_prices.loc[high_date:]
      if len(car_data) < 10:
        continue
      car_values = car_data.expanding().mean()
      last_10_car = car_values.tail(10)

      car_status = (
          "Positive" if last_10_car.is_monotonic_increasing else "Negative"
      )
      if car_status != "Positive":
        continue

      # स्कोरिंग फॉर्मूला
      score = int(volume_ratio * price_bounce_pct * 100)
      if score < 1000:
        continue

      # ट्रेड लेवल्स (SL और Target)
      stop_loss = round(low_20, 2)
      risk = cmp - stop_loss
      target_1 = round(cmp + (risk * 2), 2)
      watch_price = round(high_today, 2)

      clean_ticker = ticker.replace(".NS", "")

      results.append({
          "Date": today_date,
          "Stock": clean_ticker,
          "CMP": round(cmp, 2),
          "Score": score,
          "Turnover (Cr)": round(turnover / 10000000, 2),
          "Volume Ratio": round(volume_ratio, 2),
          "RS vs Nifty (%)": round(relative_strength_diff, 2),
          "Trigger Price": watch_price,
          "Stop Loss": stop_loss,
          "Target (1:2)": target_1,
      })

      # टेलीग्राम अलर्ट भेजना
      if not is_already_sent(clean_ticker, today_date):
        msg = (
            f"🤖 *[CHAKRAVYUH SCANNER: 8 FILTERS PASSED]* 🤖\n"
            f"🚨 *SUPER INSTITUTIONAL BREAKOUT!* 🚨\n\n"
            f"📈 *Stock:* `{clean_ticker}`\n"
            f"💰 *CMP:* ₹{round(cmp, 2)}\n"
            f"⭐ *Score:* *{score}* (>=1000)\n"
            f"💸 *Turnover:* ₹{round(turnover/10000000, 2)} Cr\n"
            f"📊 *Volume Ratio:* {round(volume_ratio, 2)}x\n"
            f"💪 *Relative Strength:* +{round(relative_strength_diff, 2)}%"
            f" vs Nifty\n\n"
            f"🎯 *TRADE SETUP:*\n"
            f"👀 *Trigger Price:* ₹{watch_price}\n"
            f"🛑 *Stop Loss:* ₹{stop_loss}\n"
            f"🎯 *Target (1:2):* ₹{target_1}\n\n"
            f"📍 *Date:* {today_date}"
        )
        send_telegram_message(msg)
        save_sent_alert(clean_ticker, today_date)

    except Exception as e:
      continue

    if idx % 10 == 0:
      gc.collect()

  df_positive = pd.DataFrame(results)
  if not df_positive.empty:
    df_positive = df_positive.sort_values(by="Score", ascending=False)
  return df_positive


# -------------------------------------------------------------------------
# कोड रन करने का हिस्सा (Clean Ticker List)
# -------------------------------------------------------------------------
my_stocks = [
    "360ONE.NS",
    "ABB.NS",
    "APLAPOLLO.NS",
    "AUBANK.NS",
    "ADANIENSOL.NS",
    "ADANIENT.NS",
    "ADANIGREEN.NS",
    "ADANIPORTS.NS",
    "ADANIPOWER.NS",
    "ABCAPITAL.NS",
    "ALKEM.NS",
    "AMBER.NS",
    "AMBUJACEM.NS",
    "ANGELONE.NS",
    "APOLLOHOSP.NS",
    "ASHOKLEY.NS",
    "ASIANPAINT.NS",
    "ASTRAL.NS",
    "AUROPHARMA.NS",
    "DMART.NS",
    "AXISBANK.NS",
    "BSE.NS",
    "BAJAJ-AUTO.NS",
    "BAJFINANCE.NS",
    "BAJAJFINSV.NS",
    "BAJAJHLDNG.NS",
    "BANDHANBNK.NS",
    "BANKBARODA.NS",
    "BANKINDIA.NS",
    "BDL.NS",
    "BEL.NS",
    "BHARATFORG.NS",
    "BHEL.NS",
    "BPCL.NS",
    "BHARTIARTL.NS",
    "BIOCON.NS",
    "BLUESTARCO.NS",
    "BOSCHLTD.NS",
    "BRITANNIA.NS",
    "CGPOWER.NS",
    "CANBK.NS",
    "CDSL.NS",
    "CHOLAFIN.NS",
    "CIPLA.NS",
    "COALINDIA.NS",
    "COCHINSHIP.NS",
    "COFORGE.NS",
    "COLPAL.NS",
    "CAMS.NS",
    "CONCOR.NS",
    "CROMPTON.NS",
    "CUMMINSIND.NS",
    "DLF.NS",
    "DABUR.NS",
    "DALBHARAT.NS",
    "DELHIVERY.NS",
    "DIVISLAB.NS",
    "DIXON.NS",
    "DRREDDY.NS",
    "ETERNAL.NS",
    "EICHERMOT.NS",
    "EXIDEIND.NS",
    "FORCEMOT.NS",
    "NYKAA.NS",
    "FORTIS.NS",
    "GAIL.NS",
    "GVT&D.NS",
    "GMRAIRPORT.NS",
    "GLENMARK.NS",
    "GODFRYPHLP.NS",
    "GODREJCP.NS",
    "GODREJPROP.NS",
    "GRASIM.NS",
    "HCLTECH.NS",
    "HDFCAMC.NS",
    "HDFCBANK.NS",
    "HDFCLIFE.NS",
    "HAVELLS.NS",
    "HEROMOTOCO.NS",
    "HINDALCO.NS",
    "HAL.NS",
    "HINDPETRO.NS",
    "HINDUNILVR.NS",
    "HINDZINC.NS",
    "POWERINDIA.NS",
    "HYUNDAI.NS",
    "ICICIBANK.NS",
    "ICICIGI.NS",
    "ICICIPRULI.NS",
    "IDFCFIRSTB.NS",
    "ITC.NS",
    "INDIANB.NS",
    "IEX.NS",
    "IOC.NS",
    "IRFC.NS",
    "IREDA.NS",
    "INDUSTOWER.NS",
    "INDUSINDBK.NS",
    "NAUKRI.NS",
    "INFY.NS",
    "INOXWIND.NS",
    "INDIGO.NS",
    "JINDALSTEL.NS",
    "JSWENERGY.NS",
    "JSWSTEEL.NS",
    "JIOFIN.NS",
    "JUBLFOOD.NS",
    "KEI.NS",
    "KPITTECH.NS",
    "KALYANKJIL.NS",
    "KAYNES.NS",
    "KFINTECH.NS",
    "KOTAKBANK.NS",
    "LTF.NS",
    "LICHSGFIN.NS",
    "LTM.NS",
    "LT.NS",
    "LAURUSLABS.NS",
    "LICI.NS",
    "LODHA.NS",
    "LUPIN.NS",
    "M&M.NS",
    "MANAPPURAM.NS",
    "MANKIND.NS",
    "MARICO.NS",
    "MARUTI.NS",
    "MFSL.NS",
    "MAXHEALTH.NS",
    "MAZDOCK.NS",
    "MOTILALOFS.NS",
    "MPHASIS.NS",
    "MCX.NS",
    "MUTHOOTFIN.NS",
    "NBCC.NS",
    "NHPC.NS",
    "NMDC.NS",
    "NTPC.NS",
    "NATIONALUM.NS",
    "NESTLEIND.NS",
    "NAM-INDIA.NS",
    "NUVAMA.NS",
    "OBEROIRLTY.NS",
    "ONGC.NS",
    "OIL.NS",
    "PAYTM.NS",
    "OFSS.NS",
    "POLICYBZR.NS",
    "PGEL.NS",
    "PIIND.NS",
    "PNBHOUSING.NS",
    "PAGEIND.NS",
    "PATANJALI.NS",
    "PERSISTENT.NS",
    "PETRONET.NS",
    "PIDILITIND.NS",
    "POLYCAB.NS",
    "PFC.NS",
    "POWERGRID.NS",
    "PREMIERENE.NS",
    "PRESTIGE.NS",
    "PNB.NS",
    "RBLBANK.NS",
    "RECLTD.NS",
    "RADICO.NS",
    "RVNL.NS",
    "RELIANCE.NS",
    "SBICARD.NS",
    "SBILIFE.NS",
    "SHREECEM.NS",
    "SRF.NS",
    "MOTHERSON.NS",
    "SHRIRAMFIN.NS",
    "SIEMENS.NS",
    "SOLARINDS.NS",
    "SONACOMS.NS",
    "SBIN.NS",
    "SAIL.NS",
    "SUNPHARMA.NS",
    "SUPREMEIND.NS",
    "SUZLON.NS",
    "SWIGGY.NS",
    "TATACONSUM.NS",
    "TVSMOTOR.NS",
    "TCS.NS",
    "TATAELXSI.NS",
    "TMPV.NS",
    "TATAPOWER.NS",
    "TATASTEEL.NS",
    "TECHM.NS",
    "FEDERALBNK.NS",
    "INDHOTEL.NS",
    "PHOENIXLTD.NS",
    "TITAN.NS",
    "TORNTPHARM.NS",
    "TRENT.NS",
    "TIINDIA.NS",
    "UNOMINDA.NS",
    "UPL.NS",
    "ULTRACEMCO.NS",
    "UNIONBANK.NS",
    "UNITDSPR.NS",
    "VBL.NS",
    "VEDL.NS",
    "VMM.NS",
    "IDEA.NS",
    "VOLTAS.NS",
    "WAAREEENER.NS",
    "WIPRO.NS",
    "YESBANK.NS",
    "ZYDUSLIFE.NS",
]

positive_breakout_data = advanced_stock_scanner(my_stocks)

print("\n" + "=" * 70)
print("🎯 8 चक्रव्यूह पार करने वाले सुपर मजबूत शेयर (Score >= 1000)")
print("=" * 70)

if positive_breakout_data.empty:
  print("❌ आज 8 कड़े फिल्टर्स की वजह से कोई भी शेयर पास नहीं हुआ।")
else:
  for index, row in positive_breakout_data.iterrows():
    print(
        f"✅ स्टॉक: {row['Stock']} | टर्नओवर: ₹{row['Turnover (Cr)']}Cr | RS:"
        f" +{row['RS vs Nifty (%)']}% | Trigger: ₹{row['Trigger Price']}"
    )

  print("=" * 70)
  excel_file = "Chakravyuh_Verified_Breakouts.xlsx"
  positive_breakout_data.to_excel(excel_file, index=False)
  print(
      f"\n📁 फ़िल्टर की गई फाईनल लिस्ट '{excel_file}' आपके फोल्डर में सेव हो गई है!"
  )

  try:
    from google.colab import files

    files.download(excel_file)
  except ImportError:
    pass