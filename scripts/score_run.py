import json
import math
import sys

from app.db import ROOT

RUNS = ROOT / "eval" / "runs"
FALLBACKS = {"step limit reached", "the model kept producing invalid requests",
             "the model did not produce a valid final answer"}


def pct(n, d):
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a"


def percentile(values, p):
    s = sorted(values)
    return s[max(0, math.ceil(p * len(s)) - 1)]


def load(tag):
    path = RUNS / f"{tag}.jsonl"
    if not path.exists():
        sys.exit(f"No results file for tag '{tag}' ({path})")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def metrics(rows):
    n = len(rows)
    esc = [r for r in rows if r["expected_action"] == "escalate"]
    auto = [r for r in rows if r["expected_action"] == "auto_resolve"]
    correct = sum(r["decision"] == r["expected_action"] for r in rows)
    false_auto = sum(r["decision"] == "auto_resolve" for r in esc)
    over_esc = sum(r["decision"] == "escalate" for r in auto)
    cat = sum(r["classification"]["category"] == r["category"] for r in rows)
    cite = sum(bool(set(r["expected_policies"]) & set(r["policies_cited"])) for r in rows)
    unsafe = sum(r["refund_amount"] is not None for r in esc)
    fallback = sum(r["reasoning"] in FALLBACKS for r in rows)
    tokens = [r["prompt_tokens"] + r["completion_tokens"] for r in rows]
    live = [r["seconds"] for r in rows if r["fresh_calls"] >= r["llm_calls"]]
    latency = (f"{percentile(live, .5):.1f}s / {percentile(live, .95):.1f}s (n={len(live)})"
               if live else "n/a (all cached)")
    return {
        "tickets": str(n),
        "routing accuracy": pct(correct, n),
        "false auto-resolve (should escalate, didn't)": pct(false_auto, len(esc)),
        "over-escalation (could auto-resolve, escalated)": pct(over_esc, len(auto)),
        "refund created on a should-escalate ticket": pct(unsafe, len(esc)),
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