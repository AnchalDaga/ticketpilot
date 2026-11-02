import json

from app.db import ROOT
from app.retrieval import search

gold = json.loads((ROOT / "eval" / "gold_tickets.json").read_text())
GUARD = {"legal_threat", "safety", "asks_for_human", "repeat_customer"}


def run(rows, mode):
    h1 = h3 = 0
    for g in rows:
        ids = [r["id"] for r in search(g["text"], k=3, mode=mode)]
        exp = set(g["expected_policies"])
        h1 += ids[0] in exp
        h3 += bool(exp & set(ids))
    return h1, h3


for label, rows in (("all tickets", gold),
                    ("excluding guardrail scenarios", [g for g in gold if g["scenario"] not in GUARD])):
    n = len(rows)
    print(f"{label} (n={n})")
    for mode in ("bm25", "embed", "hybrid"):
        h1, h3 = run(rows, mode)
        print(f"  {mode:7s} hit@1={h1}/{n} ({100 * h1 / n:.0f}%)  hit@3={h3}/{n} ({100 * h3 / n:.0f}%)")