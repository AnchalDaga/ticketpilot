import json

from app.db import ROOT, get_conn

gold = json.loads((ROOT / "eval" / "gold_tickets.json").read_text())
conn = get_conn()
history_customers = {r[0] for r in conn.execute("SELECT DISTINCT customer_id FROM tickets WHERE id > 1000")}
conn.close()

problems = [
    (g["gold_id"], g["customer_id"], g["scenario"], g["expected_action"])
    for g in gold
    if g["customer_id"] in history_customers and g["flags"].get("needs_history", 0) == 0
]
print("Gold tickets that share a customer with a repeat-customer case:", problems if problems else "none")