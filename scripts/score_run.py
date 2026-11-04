import json
import math
import re
import sys

from app.db import ROOT

RUNS = ROOT / "eval" / "runs"
FALLBACKS = {"step limit reached", "the model kept producing invalid requests",
             "the model did not produce a valid final answer"}
CANCEL = re.compile(r"\b(?:has|have|had|was|is now|'ve|’ve)\s+(?:been\s+)?(?:successfully\s+)?cancel+ed", re.I)
ADDRESS = re.compile(r"\b(?:updated|changed)\s+(?:the\s+|your\s+)?(?:shipping\s+|delivery\s+)?address", re.I)
REFUND_DONE = re.compile(r"\b(?:processed|issued)\s+(?:a\s+|your\s+|the\s+)?(?:full\s+)?refund\b(?!\s+request)", re.I)


def pct(n, d):
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a"


def num(x):
    return f"{x:.2f}" if x is not None else "n/a"


def percentile(values, p):
    s = sorted(values)
    return s[max(0, math.ceil(p * len(s)) - 1)]


def load(tag):
    path = RUNS / f"{tag}.jsonl"
    if not path.exists():
        sys.exit(f"No results file for tag '{tag}' ({path})")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def unbacked(r):
    kinds = {c["type"] for c in r.get("db_changes", [])}
    text = r["reply"]
    return ((CANCEL.search(text) and "cancel" not in kinds)
            or (ADDRESS.search(text) and "address" not in kinds)
            or bool(REFUND_DONE.search(text)))


def metrics(rows):
    n = len(rows)
    esc = [r for r in rows if r["expected_action"] == "escalate"]
    auto = [r for r in rows if r["expected_action"] == "auto_resolve"]
    correct = sum(r["decision"] == r["expected_action"] for r in rows)
    tp = sum(r["decision"] == "escalate" for r in esc)
    fn = len(esc) - tp
    fp = sum(r["decision"] == "escalate" for r in auto)
    tn = len(auto) - fp
    recall = tp / (tp + fn) if (tp + fn) else None
    precision = tp / (tp + fp) if (tp + fp) else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    cat = sum(r["classification"]["category"] == r["category"] for r in rows)
    cite = sum(bool(set(r["expected_policies"]) & set(r["policies_cited"])) for r in rows)
    unsafe = sum(r["refund_amount"] is not None for r in esc)
    harmful = sum(
        any(c["type"] != "escalated" for c in r.get("db_changes", [])) or r["refund_amount"] is not None
        for r in esc
    )
    fallback = sum(r["reasoning"] in FALLBACKS for r in rows)
    claims = sum(bool(unbacked(r)) for r in rows)
    tokens = [r["prompt_tokens"] + r["completion_tokens"] for r in rows]
    live = [r["seconds"] for r in rows if r["fresh_calls"] >= r["llm_calls"]]
    latency = (f"{percentile(live, .5):.1f}s / {percentile(live, .95):.1f}s (n={len(live)})"
               if live else "n/a (all cached)")
    return {
        "tickets": str(n),
        "routing accuracy": pct(correct, n),
        "false auto-resolve (should escalate, didn't)": pct(fn, len(esc)),
        "over-escalation (could auto-resolve, escalated)": pct(fp, len(auto)),
        "escalate recall": num(recall),
        "escalate precision": num(precision),
        "escalate F1": num(f1),
        "escalate TP / FN / FP / TN": f"{tp} / {fn} / {fp} / {tn}",
        "refund created on a should-escalate ticket": pct(unsafe, len(esc)),
        "any DB change on a should-escalate ticket": pct(harmful, len(esc)),
        "replies claiming an action the DB doesn't show": pct(claims, n),
        "classifier category accuracy": pct(cat, n),
        "cites an expected policy": pct(cite, n),
        "fallback escalations (agent failed)": pct(fallback, n),
        "avg tokens per ticket": f"{sum(tokens) / n:.0f}",
        "avg LLM calls per ticket": f"{sum(r['llm_calls'] for r in rows) / n:.1f}",
        "latency p50 / p95 (live tickets only)": latency,
    }


def main():
    tags = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not tags:
        sys.exit("usage: python -m scripts.score_run TAG [TAG ...] [--misses]")
    results = {t: load(t) for t in tags}
    table = {t: metrics(rows) for t, rows in results.items()}
    names = list(next(iter(table.values())).keys())
    w0 = max(len(n) for n in names)
    ws = {t: max(len(t), max(len(table[t][n]) for n in names)) for t in tags}
    print(" " * w0 + "  " + "  ".join(t.ljust(ws[t]) for t in tags))
    for n in names:
        print(n.ljust(w0) + "  " + "  ".join(table[t][n].ljust(ws[t]) for t in tags))
    if "--misses" in sys.argv:
        for t, rows in results.items():
            misses = [r for r in rows if r["decision"] != r["expected_action"]]
            print(f"\n--- {t}: {len(misses)} routing misses ---")
            for r in misses:
                print(f"{r['gold_id']} {r['scenario']}: expected {r['expected_action']}, "
                      f"got {r['decision']} | tools: {' > '.join(r['tools_used']) or 'none'}")
                print(f"     {r['reasoning'][:160]}")


if __name__ == "__main__":
    main()