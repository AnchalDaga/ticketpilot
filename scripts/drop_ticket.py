import json

from app.db import ROOT, get_conn

DROP = "G026"

for name in ("gold_scenarios.json", "gold_tickets.json"):
    path = ROOT / "eval" / name
    data = json.loads(path.read_text())
    kept = [g for g in data if g["gold_id"] != DROP]
    path.write_text(json.dumps(kept, indent=2))
    print(f"{name}: {len(data)} -> {len(kept)}")

conn = get_conn()
conn.execute("DELETE FROM tickets WHERE id = ?", (int(DROP[1:]),))
conn.commit()
conn.close()

gold = json.loads((ROOT / "eval" / "gold_tickets.json").read_text())
lines = ["# Gold ticket review", "", "Read each ticket and check that the expected action makes sense.", ""]
for g in sorted(gold, key=lambda x: x["gold_id"]):
    lines.append(f"## {g['gold_id']} | {g['scenario']} | expected: {g['expected_action']} | policies: {', '.join(g['expected_policies'])}")
    lines.append("")
    lines.append(g["text"])
    lines.append("")
(ROOT / "eval" / "gold_review.md").write_text("\n".join(lines))
print("Review file rewritten")