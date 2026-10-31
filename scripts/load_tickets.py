import json
from datetime import date, timedelta

from app.db import ROOT, get_conn

TICKETS = ROOT / "eval" / "gold_tickets.json"
HISTORY_BASE_ID = 1000
HISTORY_BODIES = [
    "Quick question about my recent order.",
    "Following up on my earlier message, I have not heard back.",
    "I need help with a delivery.",
]


def main() -> None:
    gold = json.loads(TICKETS.read_text())
    conn = get_conn()

    # Work out the day the labels were computed on, from the data itself.
    refs = set()
    for g in gold:
        days = g["context"].get("days_since_delivery")
        if g["order_id"] is not None and days is not None:
            row = conn.execute("SELECT delivered_date FROM orders WHERE id = ?", (g["order_id"],)).fetchone()
            refs.add(date.fromisoformat(row["delivered_date"]) + timedelta(days=days))
    if len(refs) != 1:
        raise SystemExit(f"Could not find one consistent reference date, got: {sorted(refs)}")
    as_of = refs.pop()

    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('as_of', ?)", (as_of.isoformat(),))

    # Reload from scratch so reruns are safe.
    conn.execute("DELETE FROM traces")
    conn.execute("DELETE FROM refund_requests")
    conn.execute("DELETE FROM tickets")

    for g in gold:
        conn.execute(
            "INSERT INTO tickets (id, customer_id, order_id, body, status, created_at) VALUES (?, ?, ?, ?, 'open', ?)",
            (int(g["gold_id"][1:]), g["customer_id"], g["order_id"], g["text"], as_of.isoformat()),
        )

    history_n = 0
    repeat_customers = set()
    for g in gold:
        need = g["flags"].get("needs_history", 0)
        if need:
            repeat_customers.add(g["customer_id"])
        for k in range(need):
            history_n += 1
            conn.execute(
                "INSERT INTO tickets (id, customer_id, order_id, body, status, created_at) VALUES (?, ?, NULL, ?, 'closed', ?)",
                (HISTORY_BASE_ID + history_n, g["customer_id"], HISTORY_BODIES[k % len(HISTORY_BODIES)],
                 (as_of - timedelta(days=3 + 7 * k)).isoformat()),
            )
    conn.commit()

    # Warn if a non-repeat customer would accidentally trip the "3 or more tickets" rule.
    rows = conn.execute("SELECT customer_id, COUNT(*) AS n FROM tickets GROUP BY customer_id HAVING n >= 3").fetchall()
    stray = [(r["customer_id"], r["n"]) for r in rows if r["customer_id"] not in repeat_customers]
    conn.close()

    print(f"Reference date (as_of): {as_of}")
    print(f"Loaded {len(gold)} gold tickets and {history_n} earlier tickets for repeat customers")
    print(f"Unexpected customers with 3+ tickets: {stray if stray else 'none'}")


if __name__ == "__main__":
    main()