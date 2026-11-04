import json
import shutil

from app.db import ROOT

EVAL = ROOT / "eval"
RELABEL = {"damaged_outside_window", "return_outside_window"}
NEW = "auto_resolve"
backup = EVAL / "backup_before_relabel"

if not backup.exists():
    backup.mkdir()
    for name in ("gold_scenarios.json", "gold_tickets.json"):
        shutil.copy(EVAL / name, backup / name)
    shutil.copytree(EVAL / "runs", backup / "runs")
    print(f"Backed up the old labels and runs to {backup}")


def fix(rows):
    n = 0
    for r in rows:
        if r["scenario"] in RELABEL and r["expected_action"] != NEW:
            r["expected_action"] = NEW
            n += 1
    return n


for name in ("gold_scenarios.json", "gold_tickets.json"):
    path = EVAL / name
    rows = json.loads(path.read_text())
    n = fix(rows)
    path.write_text(json.dumps(rows, indent=2))
    print(f"{name}: relabeled {n}")

for path in sorted((EVAL / "runs").glob("*.jsonl")):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    n = fix(rows)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"runs/{path.name}: relabeled {n}")

gold = json.loads((EVAL / "gold_tickets.json").read_text())
lines = ["# Gold ticket review", "", "Read each ticket and check that the expected action makes sense.", ""]
for g in sorted(gold, key=lambda x: x["gold_id"]):
    lines.append(f"## {g['gold_id']} | {g['scenario']} | expected: {g['expected_action']} | policies: {', '.join(g['expected_policies'])}")
    lines.append("")
    lines.append(g["text"])
    lines.append("")
(EVAL / "gold_review.md").write_text("\n".join(lines))
print("Review file rewritten")