from datetime import datetime, timedelta
import json
import os
import re
import sqlite3
import time
from bs4 import BeautifulSoup
import requests

# ==========================================
# SETUP & ABSOLUTE PATH CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "west_malaysia_10years_4d.json")
DB_FILE = os.path.join(BASE_DIR, "lotto.db")

print(f"📁 Target Output File Path: {OUTPUT_FILE}")
print(f"🗄️ Target Database Path: {DB_FILE}")


def init_db():
  """Initializes the SQLite database and creates the draws table if missing."""
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS draws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            draw_date TEXT NOT NULL,
            first_prize TEXT,
            second_prize TEXT,
            third_prize TEXT,
            special_prizes TEXT,      -- Stored as a JSON string array
            consolation_prizes TEXT,  -- Stored as a JSON string array
            UNIQUE(company, draw_date)
        )
    """)
  conn.commit()
  conn.close()


def get_already_processed_dates():
  """Reads the SQLite database to check for existing entries and avoid duplicates."""
  init_db()
  processed = set()
  try:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT draw_date, company FROM draws")
    rows = cursor.fetchall()
    for row in rows:
      processed.add(f"{row[0]}_{row[1]}")
    conn.close()
    print(
        f"🔄 Resuming... Found {len(processed)} existing entries in the database."
    )
  except Exception as e:
    print(f"⚠️ Error reading database cache: {e}")
  return processed


def save_to_database(record):
  """Saves a single record directly to the SQLite database safely."""
  try:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    company = record["company"]
    date = record["date"]
    first = record["prizes"]["first"]
    second = record["prizes"]["second"]
    third = record["prizes"]["third"]
    special = json.dumps(record["prizes"]["special"])
    consolation = json.dumps(record["prizes"]["consolation"])

    cursor.execute(
        """
            INSERT OR IGNORE INTO draws 
            (company, draw_date, first_prize, second_prize, third_prize, special_prizes, consolation_prizes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (company, date, first, second, third, special, consolation),
    )
    conn.commit()
    conn.close()
  except Exception as e:
    print(f"❌ [DB Error] {e}")


def save_locally_safe(record):
  """Safe sequential write function for both JSON backup and SQLite database."""
  try:
    # 1. Save to JSON backup file
    if os.path.exists(OUTPUT_FILE):
      with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        try:
          data = json.load(f)
        except json.JSONDecodeError:
          data = []
    else:
      data = []

    data.append(record)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
      json.dump(data, f, indent=4, ensure_ascii=False)

    # 2. Save directly to SQLite Database
    save_to_database(record)

    print(
        f"✅ [Saved] {record['company']} | Date: {record['date']} | 1st:"
        f" {record['prizes']['first']} | Special: "
        f"{len(record['prizes']['special'])} | Consolation:"
        f" {len(record['prizes']['consolation'])}"
    )
  except Exception as e:
    print(f"❌ [Save Error] {e}")


def crawl_4dmoon_date(current_date, processed_set):
  """Crawls past draw results sequentially with built-in delays for complete data."""
  date_str = current_date.strftime("%Y-%m-%d")
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "Accept-Language": "en-US,en;q=0.9",
  }

  url = f"https://www.4dmoon.com/past-results/{date_str}"

  try:
    # Polite delay to prevent server throttling or packet drops
    time.sleep(0.3)

    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code == 200:
      soup = BeautifulSoup(response.text, "html.parser")
      containers = soup.find_all(["div", "section", "table"])

      for container in containers:
        text_content = container.get_text()

        target_operators = ["Magnum 4D", "Damacai", "SportsToto"]
        matched_op = next(
            (op for op in target_operators if op in text_content), None
        )

        if matched_op:
          company_name = (
              "Damacai"
              if "Damacai" in matched_op
              else ("Magnum 4D" if "Magnum" in matched_op else "Sports Toto")
          )

          # Check if this specific company and date were already logged
          record_key = f"{date_str}_{company_name}"
          if record_key in processed_set:
            continue

          all_cells = container.find_all(["td", "div", "span", "p"])
          numbers = []
          for cell in all_cells:
            val = cell.get_text().strip()
            if re.fullmatch(r"\d{4}", val):
              if val not in numbers:
                numbers.append(val)

          if len(numbers) >= 3:
            special_prizes = numbers[3:13] if len(numbers) >= 13 else numbers[3:]
            consolation_prizes = numbers[13:23] if len(numbers) >= 23 else []

            # Safety check: if extraction missed numbers due to layout glitches, skip empty
            if len(special_prizes) == 0 or len(consolation_prizes) == 0:
              continue

            record = {
                "company": company_name,
                "date": date_str,
                "prizes": {
                    "first": numbers[0],
                    "second": numbers[1],
                    "third": numbers[2],
                    "special": special_prizes,
                    "consolation": consolation_prizes,
                },
            }
            save_locally_safe(record)
            processed_set.add(record_key)
  except Exception as e:
    print(f"⚠️ Error fetching {date_str}: {e}")


def run_crawler():
  start_dt = datetime(2016, 1, 1)
  end_dt = datetime.now()

  processed_set = get_already_processed_dates()

  date_list = []
  curr = start_dt
  while curr <= end_dt:
    if curr.weekday() in [2, 5, 6]:  # Wed, Sat, Sun
      date_list.append(curr)
    curr += timedelta(days=1)

  print(
      f"🚀 Starting reliable sequential crawler for {len(date_list)} total draw"
      " dates..."
  )

  completed = 0
  for d in date_list:
    completed += 1
    if completed % 50 == 0:
      print(f"📊 Progress: Checked {completed}/{len(date_list)} draw dates...")
    crawl_4dmoon_date(d, processed_set)


if __name__ == "__main__":
  start_time = time.time()
  run_crawler()
  print(f"✨ Crawling finished! Data saved to SQLite DB: {DB_FILE}")
  print(f"⏱️ Total time taken: {time.time() - start_time:.2f} seconds.")