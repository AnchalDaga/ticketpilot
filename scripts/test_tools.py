import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp_db = Path(tempfile.mkdtemp()) / "test.db"
shutil.copy(ROOT / "data" / "ticketpilot.db", tmp_db)
os.environ["TICKETPILOT_DB"] = str(tmp_db)

from app import tools  # noqa: E402

gold = json.loads((ROOT / "eval" / "gold_tickets.json").read_text())
passed = failed = 0


def pick(scenario):
    return next(g for g in gold if g["scenario"] == scenario)


def ctx_for(g):
    return {"ticket_id": int(g["gold_id"][1:]), "customer_id": g["customer_id"]}


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}  {detail}")


low = pick("damaged_photo_low")
high = pick("damaged_high_value")
late = pick("return_outside_window")
gold_ext = pick("gold_extended_return")
repeat = pick("repeat_customer")

r = tools.check_refund_eligibility(ctx_for(low), low["order_id"], "damaged")
check("low-value damaged order can be approved", r["can_approve_without_human"], r)

r = tools.check_refund_eligibility(ctx_for(high), high["order_id"], "damaged")
check("order over $100 is blocked, limit mentioned", not r["can_approve_without_human"] and "limit" in str(r["blockers"]), r)

r = tools.check_refund_eligibility(ctx_for(late), late["order_id"], "return")
check("return outside the 30-day window is blocked", not r["can_approve_without_human"], r)

r = tools.check_refund_eligibility(ctx_for(gold_ext), gold_ext["order_id"], "return")
check("gold member gets the 45-day return window", r["can_approve_without_human"], r)

r = tools.check_refund_eligibility(ctx_for(gold_ext), gold_ext["order_id"], "damaged")
check("gold extension does not apply to damaged items", not r["can_approve_without_human"], r)

r = tools.get_customer_history(ctx_for(repeat))
check("repeat customer is detected", r["repeat_customer"], r)

r = tools.get_customer_history(ctx_for(low))
check("normal customer is not flagged", not r["repeat_customer"], r)

other = next(g for g in gold if g["order_id"] and g["customer_id"] != low["customer_id"])
r = tools.get_order(ctx_for(low), other["order_id"])
check("another customer's order is hidden", r["found"] is False, r)

r = tools.create_refund_request(ctx_for(high), high["order_id"], high["context"]["total"])
check("refund over $100 is refused", r["ok"] is False, r)
conn = tools.get_conn()
n = conn.execute("SELECT COUNT(*) FROM refund_requests WHERE order_id = ?", (high["order_id"],)).fetchone()[0]
conn.close()
check("refused refund wrote no row", n == 0, n)

r = tools.create_refund_request(ctx_for(low), low["order_id"], low["context"]["total"])
check("refund within the limit creates a pending request", r["ok"] is True, r)

r = tools.create_refund_request(ctx_for(low), low["order_id"], low["context"]["total"])
check("duplicate refund request is refused", r["ok"] is False, r)

r = tools.escalate(ctx_for(repeat), "repeat customer", "support")
conn = tools.get_conn()
status = conn.execute("SELECT status FROM tickets WHERE id = ?", (ctx_for(repeat)["ticket_id"],)).fetchone()[0]
conn.close()
check("escalate marks the ticket", r["ok"] and status == "escalated", (r, status))

r = tools.escalate(ctx_for(repeat), "x", "marketing")
check("escalate rejects an unknown team", r["ok"] is False, r)

ids = [x["id"] for x in tools.search_policy({}, "my headphones arrived with a cracked case")["results"]]
check("policy search finds KB-02 in the top 3", "KB-02" in ids, ids)

r = json.loads(tools.run_tool("delete_everything", {}, ctx_for(low)))
check("unknown tool returns an error", "error" in r, r)

r1 = json.loads(tools.run_tool("get_order", {"order_id": "abc"}, ctx_for(low)))
r2 = json.loads(tools.run_tool("get_order", {"bogus": 1}, ctx_for(low)))
check("bad arguments return errors instead of crashing", "error" in r1 and "error" in r2, (r1, r2))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)