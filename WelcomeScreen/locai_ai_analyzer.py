import os
import re
import sqlite3
import ollama

# ==========================================
# CONFIGURATION & SETUP
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "lotto.db")
LOCAL_MODEL = "llama3.2"

print(f"[*] Initializing Local AI Analyzer...")
print(f"[*] Database Path: {DB_FILE}")


def get_db_connection():
    """Establishes a connection to the SQLite database."""
    if not os.path.exists(DB_FILE):
        print(f"[!] Warning: Database file not found at {DB_FILE}.")
        return None
    return sqlite3.connect(DB_FILE)


def search_dictionary_and_draws(query_text):
    """Performs precise SQL lookups on dictionary terms and draw results

    based on tokens found in the user prompt.
    """
    conn = get_db_connection()
    if not conn:
        return {"dictionary": [], "draws": []}

    cursor = conn.cursor()
    tokens = [t.lower() for t in re.findall(r"\w+", query_text) if len(t) > 2]
    dict_results = []
    draw_results = []

    # 1. Search dictionary table for semantic matches
    for token in tokens:
        cursor.execute(
            "SELECT term, number FROM dictionary WHERE LOWER(term) LIKE ?",
            (f"%{token}%",),
        )
        for row in cursor.fetchall():
            if row not in dict_results:
                dict_results.append(row)

    # 2. Check if a specific date was requested (YYYY-MM-DD)
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", query_text)
    if date_match:
        target_date = date_match.group(0)
        cursor.execute(
            "SELECT company, draw_date, first_prize, second_prize, third_prize FROM draws WHERE draw_date = ?",
            (target_date,),
        )
        draw_results = cursor.fetchall()
    else:
        # Fetch recent draws as context
        cursor.execute(
            "SELECT company, draw_date, first_prize FROM draws ORDER BY draw_date DESC LIMIT 3"
        )
        draw_results = cursor.fetchall()

    conn.close()
    return {"dictionary": dict_results, "draws": draw_results}


def query_local_ai_with_context(user_query):
    """Gathers local DB context and queries the local Ollama AI model."""
    print(f"\nUser Query: '{user_query}'")
    print("-" * 60)

    # Retrieve factual data from SQLite database first
    db_data = search_dictionary_and_draws(user_query)

    # Strict context prompt to prevent hallucinations
    context_prompt = f"""
[DATA CONTEXT]
- Dictionary Match Results (Term & Numbers): {db_data['dictionary']}
- Draw Records Results (Company, Date, Prizes): {db_data['draws']}

[USER REQUEST]
{user_query}

[INSTRUCTIONS]
1. Answer the user request strictly using the provided [DATA CONTEXT] above.
2. If the [DATA CONTEXT] is empty or does not contain the answer, explicitly state: "No matching records found in the local database."
3. Do not invent, assume, or hallucinate lottery numbers or dictionary mappings that are not present in the data context.
4. Keep the response concise, factual, and direct (under 75 words).
"""

    try:
        response = ollama.chat(
            model=LOCAL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise data-retrieval assistant. You never "
                        "hallucinate facts and rely solely on the provided database context."
                    ),
                },
                {"role": "user", "content": context_prompt},
            ],
            options={"temperature": 0.1},
        )

        print("[Local AI Response]:")
        print(response["message"]["content"].strip())

    except Exception as e:
        print(
            f"[!] Error communicating with local Ollama service. Ensure `ollama serve` is running. Details: {e}"
        )


# ==========================================
# DUAL MODE INTERFACE
# ==========================================
def run_test_mode():
    """Runs a pre-defined batch of standard test questions."""
    print("\n=== RUNNING TEST MODE (Pre-defined Questions) ===")
    test_queries = [
        "Can you check the lottery result for 2016-04-02?",
        "I dreamed about a big snake last night, what numbers match that?",
        "Show me the latest draw results.",
    ]

    for i, query in enumerate(test_queries, 1):
        print(f"\n[Test Case {i}]")
        query_local_ai_with_context(query)
        print("=" * 60)


def run_client_mode():
    """Allows users to input their own questions interactively."""
    print("\n=== RUNNING CLIENT MODE (Interactive) ===")
    print("Type your questions below. Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            user_input = input("Client Query > ").strip()
            if user_input.lower() in ["exit", "quit"]:
                print("Exiting client mode. Goodbye!")
                break
            if not user_input:
                continue

            query_local_ai_with_context(user_input)
            print("=" * 60)
        except KeyboardInterrupt:
            print("\nExiting client mode.")
            break


if __name__ == "__main__":
    print("\nSelect Mode:")
    print("1. Test Mode (Run preset evaluation questions)")
    print("2. Client Mode (Write your own questions interactively)")

    choice = input("Enter choice (1 or 2): ").strip()

    if choice == "1":
        run_test_mode()
    elif choice == "2":
        run_client_mode()
    else:
        print("Invalid choice. Defaulting to Test Mode.")
        run_test_mode()