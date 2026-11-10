import json
import sqlite3
from fastapi import FastAPI, HTTPException
import re

app = FastAPI(
    title="West Malaysia 4D History API",
    version="1.0",
    description=(
        "Query historical 4D draw results and search for specific winning"
        " numbers."
    ),
)

DB_FILE = "lotto.db"


def get_db():
  conn = sqlite3.connect(DB_FILE)
  conn.row_factory = sqlite3.Row
  return conn


@app.get("/draws", summary="Get Historical Draws")
def get_draws(company: str = None, limit: int = 10):
  """Fetch records with optional filtering by operator company (Magnum 4D, Damacai, Sports Toto)."""
  conn = get_db()
  cursor = conn.cursor()

  if company:
    cursor.execute(
        "SELECT * FROM draws WHERE company = ? ORDER BY draw_date DESC LIMIT"
        " ?",
        (company, limit),
    )
  else:
    cursor.execute("SELECT * FROM draws ORDER BY draw_date DESC LIMIT ?", (limit,))

  rows = cursor.fetchall()
  conn.close()

  results = []
  for row in rows:
    results.append({
        "company": row["company"],
        "date": row["draw_date"],
        "first": row["first_prize"],
        "second": row["second_prize"],
        "third": row["third_prize"],
        "special": json.loads(row["special_prizes"]),
        "consolation": json.loads(row["consolation_prizes"]),
    })
  return results


@app.get("/search/{number}", summary="Search 4D Number History")
def search_number(number: str):
  """Check all historical draws to see when a specific 4-digit number appeared."""
  if not re.fullmatch(r"\d{4}", number):
    raise HTTPException(
        status_code=400, detail="Invalid format. Must be strictly 4 digits."
    )

  conn = get_db()
  cursor = conn.cursor()
  cursor.execute(
      """
        SELECT * FROM draws 
        WHERE first_prize = ? OR second_prize = ? OR third_prize = ? 
        OR special_prizes LIKE ? OR consolation_prizes LIKE ?
        ORDER BY draw_date DESC
    """,
      (number, number, number, f"%{number}%", f"%{number}%"),
  )
  rows = cursor.fetchall()
  conn.close()

  if not rows:
    raise HTTPException(
        status_code=404, detail=f"Number {number} not found in records."
    )

  matches = [{"company": r["company"], "date": r["draw_date"]} for r in rows]
  return {"number": number, "total_hits": len(matches), "matches": matches}