import json
import re
import sys

from app.db import ROOT

CLAIM = re.compile(
    r"\b(we(?:[’']ve| have) (?:\w+ )?(?:processed|issued|approved|refunded|cancel+ed|updated|changed|reset)"
    r"|(?:has|have) been (?:\w+ )?(?:processed|issued|approved|refunded|cancel+ed|updated|changed|reset)"
    r"|(?:is|are) being (?:processed|issued|refunded|cancel+ed|updated)"
    r"|i(?:[’']ve| have) (?:\w+ )?(?:processed|issued|approved|refunded|cancel+ed|updated|changed|reset))\b",
    re.I,
)
TIMELINE = re.compile(r"\b\d+\s*(?:-|–|to)\s*\d+\s*(?:business\s+)?days\b|\bwithin\s+\d+\s*(?:business\s+)?(?:days|hours)\b", re.I)
STOP_USING = re.compile(r"unplug|stop using|disconnect|power (?:it )?off", re.I)

for tag in sys.argv[1:]:
    path = ROOT / "eval" / "runs" / f"{tag}.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    claims = [r for r in rows if CLAIM.search(r["reply"])]
    timelines = [r for r in rows if TIMELINE.search(r["reply"])]
    safety = [r for r in rows if r["flags"].get("safety_issue")]
    told = [r for r in safety if STOP_USING.search(r["reply"])]
    print(f"== {tag} ({len(rows)} replies)")
    print(f"   claim an action was done: {len(claims)}")
    print(f"   state a day-count timeline: {len(timelines)}")
    print(f"   safety replies telling customer to stop using the product: {len(told)}/{len(safety)}")
    for r in claims[:6]:
        m = CLAIM.search(r["reply"])
        print(f"   - {r['gold_id']} {r['scenario']}: ...{r['reply'][max(0, m.start() - 40): m.end() + 60]}...".replace("\n", " "))