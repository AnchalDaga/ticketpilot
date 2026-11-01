import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import openai

ROOT = Path(__file__).resolve().parent.parent
tmp_db = Path(tempfile.mkdtemp()) / "test.db"
shutil.copy(ROOT / "data" / "ticketpilot.db", tmp_db)
os.environ["TICKETPILOT_DB"] = str(tmp_db)

from app.agent import run_agent  # noqa: E402
from app.db import get_conn  # noqa: E402

gold = json.loads((ROOT / "eval" / "gold_tickets.json").read_text())
args = sys.argv[1:]
provider = args.pop(0) if args and args[0] in ("groq", "gemini") else None

if args:
    picks = [next(g for g in gold if g["gold_id"] == a) for a in args]
else:
    picks = [next(g for g in gold if g["scenario"] == s)
             for s in ("damaged_photo_low", "damaged_high_value", "shipping_question")]

for g in picks:
    print("=" * 70)
    print(f"{g['gold_id']} | {g['scenario']} | expected: {g['expected_action']} {g['expected_policies']}")
    print(f"TICKET: {g['text']}\n")
    try:
        res = run_agent(int(g["gold_id"][1:]), provider=provider)
    except openai.RateLimitError:
        print("Rate limit hit. Wait a minute (or until tomorrow if it is the daily limit) and rerun.")
        break
    print(f"DECISION: {res['decision']}   (expected {g['expected_action']})")
    print(f"TOOLS: {' -> '.join(res['tools_used']) or 'none'}")
    print(f"REFUND REQUEST: {res['refund_amount']}")
    print(f"POLICIES CITED: {res['policies_cited']}")
    print(f"REASONING: {res['reasoning']}")
    print(f"REPLY: {res['reply']}")
    print(f"llm calls={res['llm_calls']} fresh={res['fresh_calls']} "
          f"tokens in/out={res['prompt_tokens']}/{res['completion_tokens']} {res['seconds']}s")
    if res["decision_mismatch"]:
        print("NOTE: the model's stated decision did not match what it actually did")
    conn = get_conn()
    for row in conn.execute("SELECT step, detail FROM traces WHERE ticket_id = ? AND kind = 'error'", (int(g["gold_id"][1:]),)):
        print(f"ERROR at step {row['step']}: {row['detail']}")
    conn.close()