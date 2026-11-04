import argparse
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL_DB = ROOT / "data" / "eval.db"
shutil.copy(ROOT / "data" / "ticketpilot.db", EVAL_DB)  # evals never touch the real database
os.environ["TICKETPILOT_DB"] = str(EVAL_DB)

import openai  # noqa: E402

from app.agent import run_agent  # noqa: E402
from app.baseline import run_baseline  # noqa: E402

RUNS = ROOT / "eval" / "runs"


class DailyLimit(Exception):
    pass


def dev_ids(gold, size=30, seed=45):
    rng = random.Random(seed)
    ordered = sorted(gold, key=lambda g: g["gold_id"])
    by_scenario = {}
    for g in ordered:
        by_scenario.setdefault(g["scenario"], []).append(g)
    picks = [rng.choice(items) for _, items in sorted(by_scenario.items())]
    rest = [g for g in ordered if g not in picks]
    picks += rng.sample(rest, max(0, size - len(picks)))
    return {g["gold_id"] for g in picks}


def run_one(ticket_id, provider, guardrails, system):
    for attempt in range(4):
        try:
            if system == "agent":
                return run_agent(ticket_id, provider=provider, guardrails=guardrails)
            return run_baseline(ticket_id, system, provider=provider)
        except openai.RateLimitError as e:
            text = str(e)
            if "per day" in text.lower() or attempt == 3:
                raise DailyLimit(text[:300])
            print(f"   per-minute limit hit, waiting 65 seconds (attempt {attempt + 1}/3)...")
            time.sleep(65)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--set", default="dev", help="dev, full, or a comma-separated list of gold ids")
    ap.add_argument("--system", default="agent", choices=["agent", "llm_only", "rag"])
    ap.add_argument("--provider", default=None, choices=["groq", "gemini"])
    ap.add_argument("--guardrails", default="on", choices=["on", "off"])
    ap.add_argument("--limit", type=int, default=None, help="max NEW tickets to run this session")
    a = ap.parse_args()
    guardrails = a.guardrails == "on" and a.system == "agent"
    provider_name = a.provider or os.getenv("LLM_PROVIDER", "groq")

    gold = json.loads((ROOT / "eval" / "gold_tickets.json").read_text())
    if a.set == "dev":
        wanted = dev_ids(gold)
    elif a.set == "heldout":
        wanted = {g["gold_id"] for g in gold} - dev_ids(gold)
    elif a.set == "full":
        wanted = {g["gold_id"] for g in gold}
    else:
        wanted = set(a.set.split(","))
    todo_all = [g for g in sorted(gold, key=lambda g: g["gold_id"]) if g["gold_id"] in wanted]
    if not todo_all:
        sys.exit("No tickets matched --set")

    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / f"{a.tag}.jsonl"
    done = {}
    if out.exists():
        for line in out.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["gold_id"]] = row
        for row in done.values():
            if (row["guardrails"] != guardrails or row["provider"] != provider_name
                    or row.get("system", "agent") != a.system):
                sys.exit(f"Tag '{a.tag}' already holds results with different settings. Use a new --tag.")

    todo = [g for g in todo_all if g["gold_id"] not in done]
    print(f"{len(todo_all)} tickets in set, {len(done)} already done, {len(todo)} to go")
    ran = 0
    try:
        for g in todo:
            if a.limit is not None and ran >= a.limit:
                print(f"Reached --limit {a.limit} for this session.")
                break
            res = run_one(int(g["gold_id"][1:]), a.provider, guardrails, a.system)
            row = {"gold_id": g["gold_id"], "scenario": g["scenario"], "category": g["category"],
                   "expected_action": g["expected_action"], "expected_policies": g["expected_policies"],
                   "flags": g["flags"], "guardrails": guardrails, "system": a.system,
                   "provider": provider_name, **res}
            with out.open("a") as f:
                f.write(json.dumps(row) + "\n")
            ran += 1
            ok = "ok  " if res["decision"] == g["expected_action"] else "MISS"
            print(f"[{len(done) + ran}/{len(todo_all)}] {ok} {g['gold_id']} {g['scenario']}: "
                  f"expected {g['expected_action']}, got {res['decision']} | "
                  f"tokens {res['prompt_tokens'] + res['completion_tokens']} | fresh calls {res['fresh_calls']}")
    except DailyLimit as e:
        print("\nStopped: daily rate limit reached. Everything finished so far is saved.")
        print("Run the same command again later (tomorrow, or with --provider gemini). Details:", e)
    remaining = len(todo_all) - len(done) - ran
    print(f"\nDone this session: {ran}. Still to go: {remaining}. Results: {out}")


if __name__ == "__main__":
    main()