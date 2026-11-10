from datetime import datetime, timedelta
import json
import os
import re
import sqlite3
import time
from bs4 import BeautifulSoup
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "lotto.db")
OUTPUT_FILE = os.path.join(BASE_DIR, "west_malaysia_10years_4d.json")


def get_latest_draw_date():
  """Finds the most recent draw date recorded in the SQLite database."""
  if not os.path.exists(DB_FILE):
    return datetime(2016, 1, 1)

  try:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(draw_date) FROM draws")
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
      return datetime.strptime(result[0], "%Y-%m-%d")
  except Exception as e:
    print(f"⚠️ Error querying latest date: {e}")
  return datetime(2016, 1, 1)


def save_new_record(record):
  """Stores new updates into database and JSON backup."""
  try:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
            INSERT OR IGNORE INTO draws 
            (company, draw_date, first_prize, second_prize, third_prize, special_prizes, consolation_prizes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["company"],
            record["date"],
            record["prizes"]["first"],
            record["prizes"]["second"],
            record["prizes"]["third"],
            json.dumps(record["prizes"]["special"]),
            json.dumps(record["prizes"]["consolation"]),
        ),
    )
    conn.commit()
    conn.close()

    if os.path.exists(OUTPUT_FILE):
      with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    else:
      data = []

    data.append(record)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
      json.dump(data, f, indent=4, ensure_ascii=False)

    print(
        f"✅ [New Draw Recorded] {record['company']} | Date:"
        f" {record['date']} | 1st: {record['prizes']['first']}"
    )
  except Exception as e:
    print(f"❌ [Error] {e}")


def check_and_update():
  latest_db_date = get_latest_draw_date()
  start_dt = latest_db_date + timedelta(days=1)
  end_dt = datetime.now()

  if start_dt > end_dt:
    print("✨ Database is already fully up to date.")
    return

  missing_dates = []
  curr = start_dt
  while curr <= end_dt:
    if curr.weekday() in [2, 5, 6]:  # Wed, Sat, Sun
      missing_dates.append(curr)
    curr += timedelta(days=1)

  if not missing_dates:
    print("✨ No new draw dates to check.")
    return

  print(
      f"🚀 Checking {len(missing_dates)} potential new draw date(s)..."
  )
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      )
  }

  for d in missing_dates:
    date_str = d.strftime("%Y-%m-%d")
    url = f"https://www.4dmoon.com/past-results/{date_str}"
    try:
      time.sleep(0.3)
      response = requests.get(url, headers=headers, timeout=15)
      if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        for container in soup.find_all(["div", "section", "table"]):
          text_content = container.get_text()
          if any(op in text_content for op in ["Magnum 4D", "Damacai", "SportsToto"]):
            company_name = (
                "Damacai"
                if "Damacai" in text_content
                else ("Magnum 4D" if "Magnum" in text_content else "Sports Toto")
            )
            cells = container.find_all(["td", "div", "span", "p"])
            numbers = [
                c.get_text().strip()
                for c in cells
                if re.fullmatch(r"\d{4}", c.get_text().strip())
            ]
            # Deduplicate while preserving order
            numbers = list(dict.fromkeys(numbers))

            if len(numbers) >= 3:
              record = {
                  "company": company_name,
                  "date": date_str,
                  "prizes": {
                      "first": numbers[0],
                      "second": numbers[1],
                      "third": numbers[2],
                      "special": numbers[3:13]
                      if len(numbers) >= 13
                      else numbers[3:],
                      "consolation": numbers[13:23]
                      if len(numbers) >= 23
                      else [],
                  },
              }
              save_new_record(record)
    except Exception as e:
      print(f"⚠️ Error on {date_str}: {e}")


if __name__ == "__main__":
  check_and_update()