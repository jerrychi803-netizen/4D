import json
import os
import re
import sqlite3
import time
from bs4 import BeautifulSoup
import requests

# ==========================================
# SETUP & CONFIGURATION
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_OUTPUT = os.path.join(BASE_DIR, "4d_dictionary.json")
DB_FILE = os.path.join(BASE_DIR, "lotto.db")

print(f"📁 Target Dictionary JSON: {JSON_OUTPUT}")
print(f"🗄️ Target Database: {DB_FILE}")


def init_dictionary_db():
  """Initializes the SQLite database table for the 4D dictionary."""
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS dictionary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT NOT NULL,
            number TEXT NOT NULL,
            UNIQUE(term, number)
        )
    """)
  conn.commit()
  conn.close()


def save_dictionary_record(term, number):
  """Saves a single dictionary term and its 4D number to SQLite and JSON."""
  try:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
            INSERT OR IGNORE INTO dictionary (term, number)
            VALUES (?, ?)
        """,
        (term, number),
    )
    conn.commit()
    conn.close()
    return cursor.rowcount > 0
  except Exception as e:
    print(f"❌ [DB Error] {e}")
    return False


def scrape_all_via_load_more():
  init_dictionary_db()

  url = "https://4d.today/wp-admin/admin-ajax.php"
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/122.0.0.0 Safari/537.36"
      ),
      "X-Requested-With": "XMLHttpRequest",
  }

  offset = 0
  step = 20  # Usually loads batches of 20 or 60 per request
  total_new_saved = 0
  seen_entries = set()

  print("🚀 Starting complete dictionary crawl using 'Load More' offsets...")

  while True:
    payload = {
        "action": "load_more_dictionary_entries_4ddictionary",
        "offset": offset,
    }

    try:
      time.sleep(0.25)  # Polite delay to avoid hammering the server
      response = requests.post(url, data=payload, headers=headers, timeout=20)

      if response.status_code != 200:
        print(f"⚠️ Received status code {response.status_code} at offset {offset}")
        break

      resp_text = response.text.strip()
      # If the server returns empty text or whitespace, we've hit the end of the database
      if not resp_text or resp_text == "0":
        print(f"✨ Reached the end of dictionary records at offset {offset}.")
        break

      soup = BeautifulSoup(resp_text, "html.parser")
      cards = soup.find_all(
          ["div", "article", "li", "section"], class_=True
      ) or soup.find_all("div")

      if not cards or len(cards) == 0:
        print(f"✨ No more cards returned at offset {offset}. Crawl complete.")
        break

      found_on_this_page = 0
      for card in cards:
        text = card.get_text(separator=" | ", strip=True)
        match = re.search(r"\b(\d{3,4})\b", text)
        if match:
          number = match.group(1)
          term = text.replace(number, "").strip(" |.-")
          term = re.sub(r"\s+", " ", term)

          if (
              len(term) > 2
              and "Copyright" not in term
              and "4D Today" not in term
          ):
            identifier = (term, number)
            if identifier not in seen_entries:
              seen_entries.add(identifier)
              if save_dictionary_record(term, number):
                total_new_saved += 1
                found_on_this_page += 1

      print(
          f"📦 Offset {offset}: Processed batch. Newly saved so far:"
          f" {total_new_saved}"
      )

      # If a batch returns items, increment offset. Let's dynamically detect step size or default to 20/60
      # If cards returned fewer than expected or 0 new items multiple times, it will safely terminate next loop.
      offset += step

      # Safety guard to prevent infinite loops (adjust upwards if dictionary has more than 15,000 items)
      if offset > 15000:
        print("⚠️ Reached safety offset limit.")
        break

    except Exception as e:
      print(f"⚠️ Error at offset {offset}: {e}")
      break

  print(
      f"\n✨ Full dictionary scraping complete! Total unique entries saved:"
      f" {total_new_saved}"
  )

  # Check final count in SQLite database
  conn = sqlite3.connect(DB_FILE)
  total_count = conn.execute("SELECT COUNT(*) FROM dictionary").fetchone()[0]
  conn.close()
  print(f"🗄️ Total unique entries now in 'lotto.db': {total_count}")


if __name__ == "__main__":
  scrape_all_via_load_more()