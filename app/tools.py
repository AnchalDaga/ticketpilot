import json
from datetime import date, timedelta

from app.db import get_conn
from app.retrieval import search

REFUND_LIMIT = 100.0      # refunds above this need a human (KB-08)
HISTORY_DAYS = 30         # look-back window for repeat customers (KB-16)
HISTORY_LIMIT = 3         # this many earlier tickets in the window means a human takes over
RETURN_WINDOW = 30
GOLD_RETURN_WINDOW = 45   # gold members, returns only (KB-14)
RETRIEVAL_MODE = "hybrid"
REASONS = ("return", "damaged", "wrong_item", "missing")
TEAMS = ("support", "billing", "warranty", "privacy", "safety", "legal")
REQUEST_KINDS = ("return_label", "replacement", "carrier_investigation", "password_reset_link")


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_of(conn) -> date:
    row = conn.execute("SELECT value FROM meta WHERE key = 'as_of'").fetchone()
    if row is None:
        raise RuntimeError("No reference date found. Run: python -m scripts.load_tickets")
    return date.fromisoformat(row["value"])


def _event(conn, ctx, order_id, action, detail):
    conn.execute(
        "INSERT INTO order_events (ticket_id, order_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (ctx["ticket_id"], order_id, action, json.dumps(detail), _as_of(conn).isoformat()),
    )


def search_policy(ctx, query):
    results = search(str(query), k=3, mode=RETRIEVAL_MODE)
    return {"results": [{"id": r["id"], "title": r["title"], "text": r["text"]} for r in results]}


def get_order(ctx, order_id):
    oid = _to_int(order_id)
    if oid is None:
        return {"found": False, "error": "order_id must be a whole number"}
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM orders WHERE id = ? AND customer_id = ?", (oid, ctx["customer_id"])
        ).fetchone()
        if row is None:
            return {"found": False, "error": f"No order {oid} found for this customer"}
        days = None
        if row["delivered_date"]:
            days = (_as_of(conn) - date.fromisoformat(row["delivered_date"])).days
        tier = conn.execute("SELECT tier FROM customers WHERE id = ?", (ctx["customer_id"],)).fetchone()["tier"]
        return {
            "found": True, "order_id": row["id"], "item": row["item_name"], "category": row["category"],
            "total_amount": row["total_amount"], "status": row["status"], "order_date": row["order_date"],
            "delivered_date": row["delivered_date"], "days_since_delivery": days, "customer_tier": tier,
            "shipping_address": row["shipping_address"],
        }
    finally:
        conn.close()


def list_customer_orders(ctx):
    conn = get_conn()
    try:
        as_of = _as_of(conn)
        rows = conn.execute(
            "SELECT id, item_name, total_amount, status, order_date, delivered_date FROM orders "
            "WHERE customer_id = ? ORDER BY order_date DESC, id DESC LIMIT 10",
            (ctx["customer_id"],),
        ).fetchall()
        orders = []
        for r in rows:
            days = (as_of - date.fromisoformat(r["delivered_date"])).days if r["delivered_date"] else None
            orders.append({
                "order_id": r["id"], "item": r["item_name"], "total_amount": r["total_amount"],
                "status": r["status"], "order_date": r["order_date"],
                "delivered_date": r["delivered_date"], "days_since_delivery": days,
            })
        return {"orders": orders}
    finally:
        conn.close()


def get_customer_history(ctx):
    conn = get_conn()
    try:
        today = _as_of(conn)
        current = conn.execute("SELECT created_at FROM tickets WHERE id = ?", (ctx["ticket_id"],)).fetchone()
        cutoff = (today - timedelta(days=HISTORY_DAYS)).isoformat()
        n = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE customer_id = ? AND id != ? AND created_at < ? AND created_at >= ?",
            (ctx["customer_id"], ctx["ticket_id"], current["created_at"], cutoff),
        ).fetchone()[0]
        tier = conn.execute("SELECT tier FROM customers WHERE id = ?", (ctx["customer_id"],)).fetchone()["tier"]
        return {"customer_tier": tier, "earlier_tickets_last_30_days": n, "repeat_customer": n >= HISTORY_LIMIT}
    finally:
        conn.close()


def check_refund_eligibility(ctx, order_id, reason):
    if reason not in REASONS:
        return {"error": f"reason must be one of {list(REASONS)}"}
    order = get_order(ctx, order_id)
    if not order["found"]:
        return order
    window = GOLD_RETURN_WINDOW if (order["customer_tier"] == "gold" and reason == "return") else RETURN_WINDOW
    days = order["days_since_delivery"]
    total = round(order["total_amount"], 2)
    blockers = []
    if order["status"] != "delivered":
        blockers.append(f"order status is '{order['status']}'; only delivered orders can be refunded")
    elif days is None or days > window:
        blockers.append(f"delivered {days} days ago, outside the {window}-day window")
    if total > REFUND_LIMIT:
        blockers.append(f"order total ${total:.2f} is above the ${REFUND_LIMIT:.0f} limit, so a human must approve")
    return {
        "order_id": order["order_id"], "reason": reason, "status": order["status"],
        "days_since_delivery": days, "window_days": window, "order_total": total,
        "can_approve_without_human": not blockers, "blockers": blockers,
    }


def create_refund_request(ctx, order_id, amount):
    try:
        amount = round(float(amount), 2)
    except (TypeError, ValueError):
        return {"ok": False, "error": "amount must be a number"}
    order = get_order(ctx, order_id)
    if not order["found"]:
        return {"ok": False, "error": order["error"]}
    if order["status"] != "delivered":
        return {"ok": False, "error": f"order status is '{order['status']}', not delivered"}
    if amount <= 0 or amount > round(order["total_amount"], 2):
        return {"ok": False, "error": "amount must be above 0 and no more than the order total"}
    if amount > REFUND_LIMIT:
        return {"ok": False, "error": f"refunds above ${REFUND_LIMIT:.0f} need human approval; escalate instead"}
    conn = get_conn()
    try:
        dup = conn.execute(
            "SELECT 1 FROM refund_requests WHERE order_id = ? AND status IN ('pending', 'approved')",
            (order["order_id"],),
        ).fetchone()
        if dup:
            return {"ok": False, "error": "a refund request already exists for this order"}
        as_of = _as_of(conn).isoformat()
        cur = conn.execute(
            "INSERT INTO refund_requests (ticket_id, order_id, amount, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
            (ctx["ticket_id"], order["order_id"], amount, as_of),
        )
        conn.commit()
        return {"ok": True, "refund_request_id": cur.lastrowid, "amount": amount, "status": "pending",
                "note": "Pending approval. No refund has been issued. Do not tell the customer it is processed."}
    finally:
        conn.close()


def cancel_order(ctx, order_id):
    order = get_order(ctx, order_id)
    if not order["found"]:
        return {"ok": False, "error": order["error"]}
    if order["status"] == "cancelled":
        return {"ok": False, "error": "this order is already cancelled"}
    if order["status"] != "placed":
        return {"ok": False, "error": (
            f"order status is '{order['status']}'; only orders in 'placed' status can be cancelled (KB-06)")}
    conn = get_conn()
    try:
        conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order["order_id"],))
        _event(conn, ctx, order["order_id"], "cancel", {"old_status": "placed"})
        conn.commit()
        return {"ok": True, "order_id": order["order_id"], "status": "cancelled",
                "note": "Cancelled orders are refunded in full within 3 to 5 business days (KB-06)."}
    finally:
        conn.close()


def update_shipping_address(ctx, order_id, new_address):
    order = get_order(ctx, order_id)
    if not order["found"]:
        return {"ok": False, "error": order["error"]}
    if order["status"] != "placed":
        return {"ok": False, "error": (
            f"order status is '{order['status']}'; the address can be changed only while the order is 'placed' (KB-12)")}
    addr = " ".join(str(new_address or "").split())
    if len(addr) < 10 or len(addr) > 200:
        return {"ok": False, "error": "new_address must be a full street address (10 to 200 characters)"}
    conn = get_conn()
    try:
        conn.execute("UPDATE orders SET shipping_address = ? WHERE id = ?", (addr, order["order_id"]))
        _event(conn, ctx, order["order_id"], "address",
               {"old_address": order["shipping_address"], "new_address": addr})
        conn.commit()
        return {"ok": True, "order_id": order["order_id"], "new_address": addr}
    finally:
        conn.close()


def submit_request(ctx, kind, order_id=None, details=""):
    if kind not in REQUEST_KINDS:
        return {"ok": False, "error": f"kind must be one of {list(REQUEST_KINDS)}"}
    oid = None
    if kind != "password_reset_link":
        order = get_order(ctx, order_id)
        if not order["found"]:
            return {"ok": False, "error": order["error"]}
        oid = order["order_id"]
        days = order["days_since_delivery"]
        if order["status"] != "delivered":
            return {"ok": False, "error": f"order status is '{order['status']}'; this request needs a delivered order"}
        if kind == "carrier_investigation":
            if days is None or days < 2:
                return {"ok": False, "error": "wait 48 hours after the delivered scan before an investigation (KB-04)"}
        else:
            window = GOLD_RETURN_WINDOW if (order["customer_tier"] == "gold" and kind == "return_label") else RETURN_WINDOW
            if days is None or days > window:
                return {"ok": False, "error": f"delivered {days} days ago, outside the {window}-day window"}
            if order["total_amount"] > REFUND_LIMIT:
                return {"ok": False, "error": f"orders above ${REFUND_LIMIT:.0f} need human approval (KB-08); escalate instead"}
    conn = get_conn()
    try:
        dup = conn.execute(
            "SELECT 1 FROM requests WHERE customer_id = ? AND kind = ? AND status = 'pending' "
            "AND COALESCE(order_id, 0) = COALESCE(?, 0)",
            (ctx["customer_id"], kind, oid),
        ).fetchone()
        if dup:
            return {"ok": False, "error": "a pending request of this kind already exists"}
        cur = conn.execute(
            "INSERT INTO requests (ticket_id, customer_id, order_id, kind, details, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (ctx["ticket_id"], ctx["customer_id"], oid, kind, str(details or "")[:300], _as_of(conn).isoformat()),
        )
        conn.commit()
        return {"ok": True, "request_id": cur.lastrowid, "kind": kind, "status": "pending",
                "note": "Pending: someone else completes it. Say it was submitted, never that it is done."}
    finally:
        conn.close()


def escalate(ctx, reason, team="support"):
    if team not in TEAMS:
        return {"ok": False, "error": f"team must be one of {list(TEAMS)}"}
    reason = str(reason or "").strip()
    if not reason:
        return {"ok": False, "error": "a reason is required"}
    conn = get_conn()
    try:
        conn.execute("UPDATE tickets SET status = 'escalated' WHERE id = ?", (ctx["ticket_id"],))
        conn.commit()
        return {"ok": True, "team": team, "reason": reason}
    finally:
        conn.close()


TOOLS = {
    "search_policy": search_policy,
    "get_order": get_order,
    "list_customer_orders": list_customer_orders,
    "get_customer_history": get_customer_history,
    "check_refund_eligibility": check_refund_eligibility,
    "create_refund_request": create_refund_request,
    "cancel_order": cancel_order,
    "update_shipping_address": update_shipping_address,
    "submit_request": submit_request,
    "escalate": escalate,
}


def _spec(name, description, properties, required):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required}}}


TOOL_SPECS = [
    _spec("search_policy", "Search the company policy documents. Use a short description of the customer's problem.",
          {"query": {"type": "string"}}, ["query"]),
    _spec("get_order", "Look up one of this customer's orders: item, price, status, delivery date, days since delivery.",
          {"order_id": {"type": "integer"}}, ["order_id"]),
    _spec("list_customer_orders", "List this customer's 10 most recent orders. Use it when the ticket names no order number.",
          {}, []),
    _spec("get_customer_history", "Get this customer's tier and how many earlier tickets they opened in the last 30 days.",
          {}, []),
    _spec("check_refund_eligibility",
          "Check whether a refund can be approved without a human, by order and reason. Returns blockers if not.",
          {"order_id": {"type": "integer"}, "reason": {"type": "string", "enum": list(REASONS)}},
          ["order_id", "reason"]),
    _spec("create_refund_request", "Create a pending refund request. Refused above the approval limit.",
          {"order_id": {"type": "integer"}, "amount": {"type": "number"}}, ["order_id", "amount"]),
    _spec("cancel_order", "Cancel one of this customer's orders. Only works while the order status is 'placed'.",
          {"order_id": {"type": "integer"}}, ["order_id"]),
    _spec("update_shipping_address",
          "Change the shipping address of one of this customer's orders. Only works while the status is 'placed'.",
          {"order_id": {"type": "integer"}, "new_address": {"type": "string"}}, ["order_id", "new_address"]),
    _spec("submit_request",
          "File a pending request that someone else completes. kind is return_label, replacement, "
          "carrier_investigation, or password_reset_link. order_id is required except for password_reset_link.",
          {"kind": {"type": "string", "enum": list(REQUEST_KINDS)}, "order_id": {"type": "integer"},
           "details": {"type": "string"}}, ["kind"]),
    _spec("escalate", "Hand the ticket to a human team with a short reason.",
          {"reason": {"type": "string"}, "team": {"type": "string", "enum": list(TEAMS)}}, ["reason", "team"]),
]


def run_tool(name, args, ctx) -> str:
    fn = TOOLS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool '{name}'"})
    try:
        return json.dumps(fn(ctx, **(args or {})), default=str)
    except TypeError as e:
        return json.dumps({"error": f"bad arguments for {name}: {e}"})
    except Exception as e:
        return json.dumps({"error": f"{name} failed: {e}"})