import json
import random
import re
import sys
import time

import openai

from app.db import ROOT
from app.llm import chat

SCENARIOS = ROOT / "eval" / "gold_scenarios.json"
OUT = ROOT / "eval" / "gold_tickets.json"
REVIEW = ROOT / "eval" / "gold_review.md"
SEED = 44

STYLES = [
    "short and blunt, one or two sentences",
    "polite and detailed, a short paragraph",
    "informal, all lowercase, hardly any punctuation",
    "annoyed and a bit rambling",
    "calm and businesslike",
    "confused, not sure what to ask for",
    "friendly, with a small typo or two",
]

SYSTEM = """You write realistic customer support messages for testing a support system.
You will get a description of a situation. Write the message the customer would send.
Rules:
- Write only the customer's message text: no subject line, no quotes around it, no explanation.
- Write in first person, as the customer.
- If the description gives an order number, mention it naturally (for example "order #123" or "my order 123"). If it gives none, do not invent one.
- Include only facts from the description. Do not invent amounts, dates, or other order numbers.
- Never mention policies, categories, or internal systems.
- Follow the requested style."""

FLAG_WORDS = {
    "legal_threat": r"lawyer|attorney|\bsue\b|suing|legal|chargeback|court",
    "safety_issue": r"smok|overheat|\bhot\b|burn|spark|fire|melt",
    "asks_for_human": r"person|human|agent|manager|someone|representative",
    "injection": r"ignore|disregard|override|instruction|rules|system",
}


def clean(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^subject:.*\n+", "", t, flags=re.I)
    return t.strip().strip('"').strip("\u201c\u201d").strip()


def valid(g: dict, text: str) -> bool:
    if len(text) < 15:
        return False
    if g["order_id"] is not None and str(g["order_id"]) not in text:
        return False
    if g["order_id"] is None and re.search(r"#\s*\d+|order\s*(number|no\.?)?\s*\d+", text, re.I):
        return False
    for flag, pattern in FLAG_WORDS.items():
        if g["flags"].get(flag) and not re.search(pattern, text, re.I):
            return False
    return True


def main() -> None:
    provider = sys.argv[1] if len(sys.argv) > 1 else None
    rng = random.Random(SEED)
    scenarios = json.loads(SCENARIOS.read_text())

    done, failed = [], []
    tokens = fresh_calls = 0
    for g in scenarios:
        style = rng.choice(STYLES)  # drawn first so styles stay the same on reruns
        text = None
        for attempt in (1, 2):
            note = f"\nThe message MUST contain the order number {g['order_id']}." if attempt == 2 and g["order_id"] else ""
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Situation: {g['brief']}\nStyle: {style}{note}\nWrite the customer's message."},
            ]
            try:
                r = chat(messages, provider=provider, temperature=0.8)
            except openai.RateLimitError:
                print(f"\nRate limit hit after {len(done)} tickets. Wait a minute (or until tomorrow if it is the daily limit)")
                print("and run the same command again. Finished tickets are cached and cost nothing.")
                sys.exit(1)
            except openai.OpenAIError as e:
                print(f"{g['gold_id']}: API error: {e}")
                break
            tokens += r["prompt_tokens"] + r["completion_tokens"]
            if not r["cached"]:
                fresh_calls += 1
                time.sleep(2.2)  # stay under the per-minute request limit
            candidate = clean(r["content"])
            if valid(g, candidate):
                text = candidate
                break
        if text is None:
            failed.append(g["gold_id"])
            continue
        done.append({**g, "style": style, "text": text})

    OUT.write_text(json.dumps(done, indent=2))
    lines = ["# Gold ticket review", "", "Read each ticket and check that the expected action makes sense.", ""]
    for g in sorted(done, key=lambda x: x["gold_id"]):
        lines.append(f"## {g['gold_id']} | {g['scenario']} | expected: {g['expected_action']} | policies: {', '.join(g['expected_policies'])}")
        lines.append("")
        lines.append(g["text"])
        lines.append("")
    REVIEW.write_text("\n".join(lines))

    print(f"Wrote {len(done)} tickets to {OUT}")
    print(f"Fresh API calls: {fresh_calls} | tokens counted this run: {tokens}")
    print(f"Failed validation: {failed if failed else 'none'}")


if __name__ == "__main__":
    main()