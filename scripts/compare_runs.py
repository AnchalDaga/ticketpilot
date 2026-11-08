import json
import math
import sys
from itertools import combinations
from math import comb

from app.db import ROOT

RUNS = ROOT / "eval" / "runs"


def load(tag):
    path = RUNS / f"{tag}.jsonl"
    return {r["gold_id"]: r for r in (json.loads(l) for l in path.read_text().splitlines() if l.strip())}


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def fmt(k, n):
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.0f}% ({k}/{n}), 95% interval {100 * lo:.0f} to {100 * hi:.0f}%"


tags = sys.argv[1:]
runs = {t: load(t) for t in tags}
ids = sorted(set.intersection(*[set(r) for r in runs.values()]))
print(f"{len(ids)} tickets in common\n")
right = {}
for t, r in runs.items():
    right[t] = {i: r[i]["decision"] == r[i]["expected_action"] for i in ids}
    esc = [i for i in ids if r[i]["expected_action"] == "escalate"]
    missed = sum(r[i]["decision"] == "auto_resolve" for i in esc)
    print(t)
    print("  routing accuracy:  ", fmt(sum(right[t].values()), len(ids)))
    print("  false auto-resolve:", fmt(missed, len(esc)))
print()
for a, b in combinations(tags, 2):
    only_a = sum(right[a][i] and not right[b][i] for i in ids)
    only_b = sum(right[b][i] and not right[a][i] for i in ids)
    n, k = only_a + only_b, min(only_a, only_b)
    p = min(1.0, 2 * sum(comb(n, j) for j in range(k + 1)) / 2 ** n) if n else 1.0
    print(f"{a} vs {b}: right only in {a}: {only_a}, right only in {b}: {only_b}, exact paired p = {p:.3f}")