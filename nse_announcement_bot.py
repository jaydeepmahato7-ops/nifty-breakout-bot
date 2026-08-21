from datetime import datetime, timedelta, timezone
import io
import pandas as pd
import requests
import time

TELEGRAM_TOKEN = "8663109611:AAEgppVnCtd3l0Yv5B_zieiw-NquXMKyP1I"
CHAT_ID = "@tFreeCryptoNSEAlert"


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


IST = timezone(timedelta(hours=5, minutes=30))
sent_announcements = set()


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
            all_symbols.add(str(sym).strip().upper())
    except Exception:
      pass

  if all_symbols:
    return all_symbols
  return {"RELIANCE", "TCS", "INFY", "ICICIBANK", "SBIN"}


def fetch_nse_announcements():
  session = requests.Session()
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept": "application/json, text/javascript, */*; q=0.01",
      "Accept-Language": "en-US,en;q=0.9",
      "Referer": (
          "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
      ),
      "X-Requested-With": "XMLHttpRequest",
  }
  try:
    session.get(
        "https://www.nseindia.com",
        headers={"User-Agent": headers["User-Agent"]},
        timeout=10,
    )
    time.sleep(2)
    response = session.get(
        "https://www.nseindia.com/api/corporate-announcements?index=equities",
        headers=headers,
        timeout=10,
    )
    if response.status_code == 200:
      return response.json()
  except Exception as e:
    print(f"API Fetch Error: {e}")
  return None


if __name__ == "__main__":
  print("🤖 Announcements Bot शुरू हो गया है...")
  nifty_total_market_symbols = get_nifty_total_market_symbols()

  t_str = datetime.now(IST).strftime("%d-%m-%Y | %H:%M:%S IST")
  print(f"[{t_str}] Corporate Announcements चेक किए जा रहे हैं...")

  announcements = fetch_nse_announcements()

  if announcements and isinstance(announcements, list):
    for item in announcements:
      symbol = str(item.get("symbol", "N/A")).strip().upper()
      if symbol not in nifty_total_market_symbols:
        continue

      ann_id = item.get("id", str(item.get("desc")) + str(item.get("dt")))
      sub = str(item.get("subject", "")).lower()
      desc = str(item.get("desc", "")).lower()
      comp_name = item.get("sm_name", symbol)
      broadcast_date = item.get("an_dt", "")
      att_url = item.get("attchmntFile", "")

      keywords = [
          "result",
          "financial",
          "profit",
          "loss",
          "audited",
          "unaudited",
          "quarterly",
          "performance",
      ]
      is_financial = any(kw in sub or kw in desc for kw in keywords)

      if is_financial and ann_id not in sent_announcements:
        sent_announcements.add(ann_id)
        msg = (
            f"📢 *Nifty Total Market Financial Alert* 📢\n\n"
            f"• *Company:* `{comp_name} ({symbol})`\n"
            f"• *Subject:* {item.get('subject')}\n"
            f"• *Date/Time:* `{broadcast_date}`\n"
        )
        if att_url:
          full_pdf_url = (
              f"https://www1.nseindia.com{att_url}"
              if not att_url.startswith("http")
              else att_url
          )
          msg += f"• *PDF Document:* [Download PDF]({full_pdf_url})"

        send_telegram(msg)
        print(f"✅ अलर्ट भेजा गया: {symbol} - {item.get('subject')}")
  else:
    print("कोई नया अनाउंसमेंट नहीं मिला।")
