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


def db_one(sql, args=()):
    conn = tools.get_conn()
    row = conn.execute(sql, args).fetchone()
    conn.close()
    return row[0]


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}  {detail}")


placed, shipped = pick("cancel_placed"), pick("cancel_shipped")
addr_p, addr_s = pick("address_placed"), pick("address_shipped")
missing, high, low, login = pick("missing_package_low"), pick("damaged_high_value"), pick("damaged_photo_low"), pick("login_help")
events = "SELECT COUNT(*) FROM order_events WHERE order_id = ? AND action = 'cancel'"

r = tools.cancel_order(ctx_for(placed), placed["order_id"])
check("cancel works on a placed order",
      r["ok"] and db_one("SELECT status FROM orders WHERE id = ?", (placed["order_id"],)) == "cancelled", r)
check("cancel wrote one event", db_one(events, (placed["order_id"],)) == 1)
detail = json.loads(db_one("SELECT detail FROM order_events WHERE order_id = ? AND action = 'cancel'", (placed["order_id"],)))
check("cancel event stores the old status", detail["old_status"] == "placed", detail)
r = tools.cancel_order(ctx_for(placed), placed["order_id"])
check("second cancel sees the first", r["ok"] is False and "already" in r["error"], r)
check("second cancel wrote no new event", db_one(events, (placed["order_id"],)) == 1)
r = tools.cancel_order(ctx_for(shipped), shipped["order_id"])
check("cancel on a shipped order is refused",
      r["ok"] is False and db_one("SELECT status FROM orders WHERE id = ?", (shipped["order_id"],)) == "shipped", r)
other = next(g for g in gold if g["scenario"] == "address_placed" and g["customer_id"] != shipped["customer_id"])
r = tools.cancel_order(ctx_for(shipped), other["order_id"])
check("cannot cancel another customer's order",
      r["ok"] is False and db_one("SELECT status FROM orders WHERE id = ?", (other["order_id"],)) == "placed", r)

new = "42 Maple Avenue, Springfield, IL 62704"
r = tools.update_shipping_address(ctx_for(addr_p), addr_p["order_id"], new)
check("address change works on a placed order",
      r["ok"] and db_one("SELECT shipping_address FROM orders WHERE id = ?", (addr_p["order_id"],)) == new, r)
before = db_one("SELECT shipping_address FROM orders WHERE id = ?", (addr_s["order_id"],))
r = tools.update_shipping_address(ctx_for(addr_s), addr_s["order_id"], new)
check("address change on a shipped order is refused and unchanged",
      r["ok"] is False and db_one("SELECT shipping_address FROM orders WHERE id = ?", (addr_s["order_id"],)) == before, r)
r = tools.update_shipping_address(ctx_for(addr_p), addr_p["order_id"], "x")
check("too-short address is refused", r["ok"] is False, r)

r = tools.list_customer_orders(ctx_for(low))
ids = [o["order_id"] for o in r["orders"]]
check("list_customer_orders returns only this customer's orders",
      0 < len(ids) <= 10 and all(db_one("SELECT customer_id FROM orders WHERE id = ?", (i,)) == low["customer_id"] for i in ids), r)

r = tools.submit_request(ctx_for(missing), "carrier_investigation", missing["order_id"], "tracking says delivered")
check("carrier investigation is filed for a delivered order", r["ok"] and r["status"] == "pending", r)
r = tools.submit_request(ctx_for(missing), "carrier_investigation", missing["order_id"])
check("duplicate request is refused", r["ok"] is False, r)
r = tools.submit_request(ctx_for(addr_p), "carrier_investigation", addr_p["order_id"])
check("request on a not-yet-delivered order is refused", r["ok"] is False, r)
r = tools.submit_request(ctx_for(high), "return_label", high["order_id"])
check("return label for an order over $100 is refused", r["ok"] is False and "human" in r["error"], r)
r = tools.submit_request(ctx_for(high), "replacement", high["order_id"])
check("replacement for an order over $100 is refused", r["ok"] is False and "human" in r["error"], r)
r = tools.submit_request(ctx_for(low), "return_label", low["order_id"])
check("return label is filed for a low-value delivered order", r["ok"] is True, r)
r = tools.submit_request(ctx_for(low), "teleport", low["order_id"])
check("unknown request kind is refused", r["ok"] is False, r)
r = tools.submit_request(ctx_for(login), "password_reset_link")
check("password reset link is filed without an order", r["ok"] is True, r)
r = tools.submit_request(ctx_for(login), "password_reset_link")
check("duplicate password reset is refused", r["ok"] is False, r)

r = json.loads(tools.run_tool("list_customer_orders", {}, ctx_for(low)))
check("run_tool dispatches list_customer_orders", "orders" in r, r)
r = json.loads(tools.run_tool("cancel_order", {"order_id": "abc"}, ctx_for(low)))
check("bad arguments to a new tool return an error", "error" in r, r)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)