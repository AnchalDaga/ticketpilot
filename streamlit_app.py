import hashlib
import hmac
import json
import os
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

SOURCE_DB = ROOT / "data" / "ticketpilot.db"
DEMO_DB = ROOT / "data" / "demo.db"
USAGE = ROOT / "data" / "demo_usage.json"
if not DEMO_DB.exists():
    shutil.copy(SOURCE_DB, DEMO_DB)
os.environ["TICKETPILOT_DB"] = str(DEMO_DB)  # the demo never touches the real database

import openai  # noqa: E402
import streamlit as st  # noqa: E402
from faker import Faker  # noqa: E402

from app.db import get_conn  # noqa: E402

LIVE = os.getenv("DEMO_LIVE", "0") == "1"
ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "")
PER_VISITOR = int(os.getenv("DEMO_PER_VISITOR", "3"))
DAILY_TOTAL = int(os.getenv("DEMO_DAILY_TOTAL", "10"))
HASH_ITERATIONS = 600_000
MAX_FAILS = 5

st.set_page_config(page_title="TicketPilot", layout="wide")

RUN_COLUMNS = {"tools_used": "TEXT", "policies": "TEXT", "tokens": "INTEGER", "seconds": "REAL"}

# (item, category, price, status, ordered N days ago, delivered N days ago)
SAMPLE_ORDERS = [
    ("Bluetooth Speaker", "electronics", 59.90, "placed", 1, None),
    ("Running Shoes", "apparel", 84.50, "shipped", 4, None),
    ("Phone Case", "accessories", 19.99, "delivered", 9, 4),
    ("Coffee Maker", "home", 74.00, "delivered", 50, 45),
    ("4K Monitor", "electronics", 329.00, "delivered", 10, 6),
]


# ---------- database helpers ----------

def ensure_tables():
    conn = get_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS demo_runs (ticket_id INTEGER PRIMARY KEY, decision TEXT, "
                 "reply TEXT, reasoning TEXT, final_reply TEXT)")
    have = {r["name"] for r in conn.execute("PRAGMA table_info(demo_runs)")}
    for col, typ in RUN_COLUMNS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE demo_runs ADD COLUMN {col} {typ}")
    conn.execute("CREATE TABLE IF NOT EXISTS accounts (email TEXT PRIMARY KEY, "
                 "customer_id INTEGER NOT NULL REFERENCES customers(id), salt BLOB NOT NULL, "
                 "password_hash BLOB NOT NULL, created_at TEXT NOT NULL)")
    conn.commit()
    conn.close()


def as_of():
    conn = get_conn()
    value = conn.execute("SELECT value FROM meta WHERE key = 'as_of'").fetchone()[0]
    conn.close()
    return value


def customer_info(customer_id):
    conn = get_conn()
    row = conn.execute("SELECT name, tier FROM customers WHERE id = ?", (customer_id,)).fetchone()
    conn.close()
    return (row["name"], row["tier"]) if row else ("unknown", "")


def orders_of(customer_id):
    conn = get_conn()
    rows = conn.execute("SELECT id AS order_id, item_name AS item, total_amount AS total, status, "
                        "order_date, delivered_date FROM orders WHERE customer_id = ? "
                        "ORDER BY order_date DESC, id DESC", (customer_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_ticket(customer_id, text):
    today = as_of()
    conn = get_conn()
    ticket_id = max(2000, (conn.execute("SELECT MAX(id) FROM tickets").fetchone()[0] or 0) + 1)
    conn.execute("INSERT INTO tickets (id, customer_id, order_id, body, status, created_at) "
                 "VALUES (?, ?, NULL, ?, 'open', ?)", (ticket_id, customer_id, text, today))
    conn.commit()
    conn.close()
    return ticket_id


def save_run(ticket_id, res):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO demo_runs (ticket_id, decision, reply, reasoning, final_reply, tools_used, "
        "policies, tokens, seconds) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?)",
        (ticket_id, res["decision"], res["reply"], res["reasoning"], json.dumps(res["tools_used"]),
         json.dumps(res["policies_cited"]), res["prompt_tokens"] + res["completion_tokens"], res["seconds"]))
    conn.commit()
    conn.close()


def get_traces(ticket_id):
    conn = get_conn()
    rows = conn.execute("SELECT step, kind, detail FROM traces WHERE ticket_id = ? ORDER BY id",
                        (ticket_id,)).fetchall()
    conn.close()
    return rows


def ticket_changes(ticket_id):
    conn = get_conn()
    out = []
    for r in conn.execute("SELECT action, order_id, detail FROM order_events WHERE ticket_id = ? ORDER BY id",
                          (ticket_id,)):
        out.append({"type": r["action"], "order_id": r["order_id"], "detail": json.loads(r["detail"])})
    for r in conn.execute("SELECT kind, order_id, status FROM requests WHERE ticket_id = ? ORDER BY id", (ticket_id,)):
        out.append({"type": "request:" + r["kind"], "order_id": r["order_id"], "status": r["status"]})
    for r in conn.execute("SELECT order_id, amount, status FROM refund_requests WHERE ticket_id = ?", (ticket_id,)):
        out.append({"type": "refund_request", "order_id": r["order_id"], "amount": r["amount"],
                    "status": r["status"]})
    conn.close()
    return out


# ---------- accounts ----------

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, HASH_ITERATIONS)


def create_account(name, email, password):
    """Returns (customer_id, error_message). Creates the customer, 5 sample orders and the login."""
    email = email.strip().lower()
    conn = get_conn()
    try:
        if (conn.execute("SELECT 1 FROM accounts WHERE email = ?", (email,)).fetchone()
                or conn.execute("SELECT 1 FROM customers WHERE lower(email) = ?", (email,)).fetchone()):
            return None, "An account with this email already exists."
        today = as_of()
        d0 = date.fromisoformat(today)
        cid = (conn.execute("SELECT MAX(id) FROM customers").fetchone()[0] or 0) + 1
        conn.execute("INSERT INTO customers (id, name, email, tier, created_at) VALUES (?, ?, ?, 'standard', ?)",
                     (cid, name, email, today))
        oid = (conn.execute("SELECT MAX(id) FROM orders").fetchone()[0] or 0) + 1
        fake = Faker()
        for item, category, price, status, ordered_ago, delivered_ago in SAMPLE_ORDERS:
            address = f"{fake.street_address()}, {fake.city()}, {fake.state_abbr()} {fake.postcode()}"
            delivered = (d0 - timedelta(days=delivered_ago)).isoformat() if delivered_ago is not None else None
            conn.execute(
                "INSERT INTO orders (id, customer_id, item_name, category, total_amount, status, order_date, "
                "delivered_date, shipping_address) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (oid, cid, item, category, price, status, (d0 - timedelta(days=ordered_ago)).isoformat(),
                 delivered, address))
            oid += 1
        salt = os.urandom(16)
        conn.execute("INSERT INTO accounts (email, customer_id, salt, password_hash, created_at) "
                     "VALUES (?, ?, ?, ?, ?)", (email, cid, salt, hash_password(password, salt), today))
        conn.commit()
        return cid, ""
    finally:
        conn.close()


def verify_login(email, password):
    email = email.strip().lower()
    conn = get_conn()
    row = conn.execute("SELECT customer_id, salt, password_hash FROM accounts WHERE email = ?", (email,)).fetchone()
    conn.close()
    digest = hash_password(password, row["salt"] if row else b"\0" * 16)  # same work either way
    if row and hmac.compare_digest(digest, row["password_hash"]):
        return row["customer_id"]
    return None


# ---------- live-run limits ----------

def visitor_id():
    try:
        ip = (st.context.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if ip:
            return ip
    except Exception:
        pass
    if "sid" not in st.session_state:
        st.session_state["sid"] = os.urandom(4).hex()
    return "session-" + st.session_state["sid"]


def load_usage():
    today = date.today().isoformat()
    try:
        usage = json.loads(USAGE.read_text())
        if usage.get("date") == today:
            return usage
    except Exception:
        pass
    return {"date": today, "total": 0, "visitors": {}}


def can_run_live(vid):
    if not LIVE:
        return False, "Live mode is turned off on this server."
    usage = load_usage()
    if usage["total"] >= DAILY_TOTAL:
        return False, "The demo's live quota for today is used up."
    if usage["visitors"].get(vid, 0) >= PER_VISITOR:
        return False, "You have used your live tickets for today."
    return True, ""


def record_live(vid):
    usage = load_usage()
    usage["total"] += 1
    usage["visitors"][vid] = usage["visitors"].get(vid, 0) + 1
    USAGE.write_text(json.dumps(usage))


def run_ticket(customer_id, text):
    """Create a ticket, run the agent, save the result. Returns the result dict or None on failure."""
    record_live(visitor_id())
    tid = create_ticket(customer_id, text)
    try:
        from app.agent import run_agent
        res = run_agent(tid)
        save_run(tid, res)
        return res
    except openai.RateLimitError:
        st.warning("The free LLM quota is used up right now. Please try again later.")
    except Exception as e:
        st.error(f"Something went wrong: {e}")
    return None


# ---------- replay samples (admin only) ----------

@st.cache_data(ttl=60)
def load_samples():
    gold = {g["gold_id"]: g for g in json.loads((ROOT / "eval" / "gold_tickets.json").read_text())}
    out = []
    for tag in ("dev_v2_on", "held_v2_on"):
        path = ROOT / "eval" / "runs" / f"{tag}.jsonl"
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    if "db_changes" in r and r["gold_id"] in gold:
                        r["text"] = gold[r["gold_id"]]["text"]
                        r["run"] = tag
                        out.append(r)
    return out


def render_replay(r):
    if r["decision"] == "escalate":
        st.warning("Escalated to a human.")
    else:
        st.success("Handled by the agent.")
    with st.chat_message("assistant"):
        st.write(r["reply"])
    c1, c2 = st.columns(2)
    c1.metric("Agent LLM calls", r["llm_calls"])
    c2.metric("Tokens (all calls)", r["prompt_tokens"] + r["completion_tokens"])
    with st.expander("Why the agent decided this", expanded=True):
        st.write(r["reasoning"] or "No reasoning recorded.")
        st.write("**Policies cited:** " + (", ".join(r["policies_cited"]) or "none"))
        st.write("**Tools used, in order:** " + (" → ".join(r["tools_used"]) or "none (rule or direct answer)"))
        st.write("**Database changes:**")
        if r["db_changes"]:
            st.json(r["db_changes"])
        else:
            st.write("none")


# ---------- sign-in ----------

def logout():
    for key in ("role", "cid", "email", "last"):
        st.session_state.pop(key, None)
    st.rerun()


def login_screen():
    st.title("TicketPilot")
    st.caption("An AI agent that triages support tickets for a fictional store. All data is mock. "
               "Demo-grade accounts only: please use a throwaway password.")
    tab_login, tab_signup, tab_admin = st.tabs(["Customer log in", "Create account", "Admin"])

    with tab_login:
        with st.form("customer_login"):
            email = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            go = st.form_submit_button("Log in", type="primary")
        if go:
            if st.session_state.get("fails_customer", 0) >= MAX_FAILS:
                st.error("Too many failed attempts in this session. Reload the page to try again.")
            else:
                cid = verify_login(email, pw)
                if cid is None:
                    st.session_state["fails_customer"] = st.session_state.get("fails_customer", 0) + 1
                    st.error("Wrong email or password.")
                else:
                    st.session_state.update(role="customer", cid=cid, email=email.strip().lower(), fails_customer=0)
                    st.rerun()

    with tab_signup:
        st.caption("A new account comes with 5 sample orders (placed, shipped and delivered) so you can try the agent.")
        with st.form("customer_signup"):
            name = st.text_input("Name")
            email = st.text_input("Email", key="signup_email")
            pw1 = st.text_input("Password (at least 8 characters)", type="password", key="signup_pw1")
            pw2 = st.text_input("Confirm password", type="password", key="signup_pw2")
            go = st.form_submit_button("Create account", type="primary")
        if go:
            email_clean = email.strip().lower()
            if not 2 <= len(name.strip()) <= 60:
                st.error("Please enter a name (2 to 60 characters).")
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_clean):
                st.error("Please enter a valid email address.")
            elif len(pw1) < 8:
                st.error("The password must be at least 8 characters.")
            elif pw1 != pw2:
                st.error("The two passwords do not match.")
            else:
                cid, err = create_account(name.strip(), email_clean, pw1)
                if err:
                    st.error(err)
                else:
                    st.session_state.update(role="customer", cid=cid, email=email_clean)
                    st.rerun()

    with tab_admin:
        if not ADMIN_PASSWORD:
            st.warning("No admin password is set. Add a line DEMO_ADMIN_PASSWORD=... to your .env file "
                       "and restart the app.")
        with st.form("admin_login"):
            pw = st.text_input("Admin password", type="password")
            go = st.form_submit_button("Log in as admin", disabled=not ADMIN_PASSWORD)
        if go:
            if st.session_state.get("fails_admin", 0) >= MAX_FAILS:
                st.error("Too many failed attempts in this session. Reload the page to try again.")
            elif hmac.compare_digest(pw.encode(), ADMIN_PASSWORD.encode()):
                st.session_state.update(role="admin", fails_admin=0)
                st.rerun()
            else:
                st.session_state["fails_admin"] = st.session_state.get("fails_admin", 0) + 1
                st.error("Wrong password.")


# ---------- customer view ----------

def status_label(row):
    if row["decision"] is None:
        return "Not processed"
    if row["final_reply"]:
        return "Answered by our team"
    if row["status"] == "escalated":
        return "With our team"
    if row["status"] == "closed":
        return "Closed"
    return "Answered"


def customer_view(cid):
    name, tier = customer_info(cid)
    with st.sidebar:
        st.title("TicketPilot")
        st.write(f"Signed in as **{name}** ({tier})")
        st.caption(st.session_state.get("email", ""))
        page = st.radio("Menu", ["New ticket", "My tickets"])
        if st.button("Sign out"):
            logout()

    if page == "New ticket":
        st.header("How can we help?")
        st.caption("Your orders")
        st.dataframe(orders_of(cid), hide_index=True)
        text = st.text_area("Describe your problem", max_chars=800, height=120,
                            placeholder="e.g. My order #123 arrived damaged, I attached photos.")
        ok, why = can_run_live(visitor_id())
        if not ok:
            st.info(why)
        if st.button("Send", disabled=(not ok or not text.strip()), type="primary"):
            st.session_state.pop("last", None)
            with st.spinner("Our assistant is looking into it. This can take up to a minute..."):
                res = run_ticket(cid, text.strip())
            if res:
                st.session_state["last"] = {"text": text.strip(), "reply": res["reply"], "decision": res["decision"]}
        last = st.session_state.get("last")
        if last:
            with st.chat_message("user"):
                st.write(last["text"])
            with st.chat_message("assistant"):
                st.write(last["reply"])
            if last["decision"] == "escalate":
                st.info("Your ticket has been passed to our team. You will see their reply under My tickets.")
    else:
        st.header("My tickets")
        conn = get_conn()
        rows = conn.execute(
            "SELECT t.id, t.body, t.status, r.decision, r.reply, r.final_reply FROM tickets t "
            "LEFT JOIN demo_runs r ON r.ticket_id = t.id WHERE t.customer_id = ? AND t.id >= 2000 "
            "ORDER BY t.id DESC", (cid,)).fetchall()
        conn.close()
        if not rows:
            st.caption("You have no tickets yet.")
        for t in rows:
            with st.container(border=True):
                st.caption(f"Ticket #{t['id']} · {status_label(t)}")
                st.write(t["body"])
                with st.chat_message("assistant"):
                    st.write(t["reply"] or "No reply yet.")
                if t["final_reply"]:
                    st.markdown("**Reply from our team:**")
                    st.write(t["final_reply"])


# ---------- admin view ----------

def admin_queue():
    conn = get_conn()
    esc = conn.execute("SELECT t.id, t.customer_id, t.body, r.reply, r.reasoning FROM tickets t "
                       "JOIN demo_runs r ON r.ticket_id = t.id WHERE t.status = 'escalated' "
                       "ORDER BY t.id DESC").fetchall()
    refunds = conn.execute("SELECT rr.id, rr.ticket_id, rr.order_id, rr.amount, o.item_name FROM refund_requests rr "
                           "JOIN orders o ON o.id = rr.order_id WHERE rr.status = 'pending' "
                           "ORDER BY rr.id DESC").fetchall()
    reqs = conn.execute("SELECT id, ticket_id, order_id, kind, details FROM requests WHERE status = 'pending' "
                        "ORDER BY id DESC").fetchall()
    conn.close()

    st.subheader(f"Escalated tickets ({len(esc)})")
    if not esc:
        st.caption("Nothing waiting. Tickets the agent hands off will appear here.")
    for e in esc:
        with st.container(border=True):
            name, _ = customer_info(e["customer_id"])
            st.markdown(f"**Ticket #{e['id']}** from {name} (#{e['customer_id']})")
            st.write(e["body"])
            st.caption("Why the agent escalated: " + (e["reasoning"] or ""))
            draft = st.text_area("Reply to send", value=e["reply"], key=f"draft{e['id']}", height=100)
            if st.button("Send reply (mock) and close", key=f"send{e['id']}"):
                conn = get_conn()
                conn.execute("UPDATE demo_runs SET final_reply = ? WHERE ticket_id = ?", (draft, e["id"]))
                conn.execute("UPDATE tickets SET status = 'closed' WHERE id = ?", (e["id"],))
                conn.commit()
                conn.close()
                st.rerun()

    st.subheader(f"Pending refund requests ({len(refunds)})")
    st.caption("Approving only changes a status in the mock database. No money moves.")
    for rf in refunds:
        with st.container(border=True):
            st.write(f"Request #{rf['id']}: ${rf['amount']:.2f} for order #{rf['order_id']} "
                     f"({rf['item_name']}), from ticket #{rf['ticket_id']}")
            c1, c2 = st.columns(2)
            for col, label, status in ((c1, "Approve", "approved"), (c2, "Reject", "rejected")):
                if col.button(label, key=f"refund{status}{rf['id']}"):
                    conn = get_conn()
                    conn.execute("UPDATE refund_requests SET status = ? WHERE id = ?", (status, rf["id"]))
                    conn.commit()
                    conn.close()
                    st.rerun()

    st.subheader(f"Other pending requests ({len(reqs)})")
    for rq in reqs:
        with st.container(border=True):
            st.write(f"Request #{rq['id']}: {rq['kind'].replace('_', ' ')} for order #{rq['order_id']} "
                     f"(ticket #{rq['ticket_id']}). {rq['details'] or ''}")
            c1, c2 = st.columns(2)
            for col, label, status in ((c1, "Mark completed", "completed"), (c2, "Reject", "rejected")):
                if col.button(label, key=f"req{status}{rq['id']}"):
                    conn = get_conn()
                    conn.execute("UPDATE requests SET status = ? WHERE id = ?", (status, rq["id"]))
                    conn.commit()
                    conn.close()
                    st.rerun()


def admin_all_tickets():
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.id, t.customer_id, t.body, t.status, r.decision, r.reply, r.reasoning, r.final_reply, "
        "r.tools_used, r.policies, r.tokens, r.seconds FROM tickets t "
        "LEFT JOIN demo_runs r ON r.ticket_id = t.id WHERE t.id >= 2000 ORDER BY t.id DESC").fetchall()
    conn.close()
    st.subheader(f"All live tickets ({len(rows)})")
    if not rows:
        st.caption("No live tickets yet. Tickets sent through the customer view show up here with their full trace.")
    for t in rows:
        name, _ = customer_info(t["customer_id"])
        with st.expander(f"#{t['id']} · {name} · {t['decision'] or 'not processed'} · {t['status']}"):
            st.write("**Ticket:** " + t["body"])
            st.write("**Agent reply:** " + (t["reply"] or "none"))
            if t["final_reply"]:
                st.write("**Team reply:** " + t["final_reply"])
            st.write("**Reasoning:** " + (t["reasoning"] or "none"))
            tools = json.loads(t["tools_used"]) if t["tools_used"] else []
            policies = json.loads(t["policies"]) if t["policies"] else []
            st.write("**Tools used:** " + (" → ".join(tools) or "none"))
            st.write("**Policies cited:** " + (", ".join(policies) or "none"))
            st.write(f"**Tokens:** {t['tokens'] or 0} · **Seconds:** {t['seconds'] or 0}")
            changes = ticket_changes(t["id"])
            st.write("**Database changes:**")
            if changes:
                st.json(changes)
            else:
                st.write("none")
            st.write("**Step-by-step trace:**")
            for tr in get_traces(t["id"]):
                st.markdown(f"{tr['kind']} (step {tr['step']})")
                st.code(tr["detail"][:1500], language="json")


def admin_replay():
    samples = load_samples()
    st.subheader("Replay samples")
    if not samples:
        st.info("No recorded runs found in eval/runs.")
        return
    names = {i: f"{r['gold_id']} · {r['scenario'].replace('_', ' ')}" for i, r in enumerate(samples)}
    i = st.selectbox("Pick a recorded ticket", list(names), format_func=names.get)
    r = samples[i]
    st.info(r["text"])
    render_replay(r)
    matched = r["decision"] == r["expected_action"]
    st.caption(f"Gold label: {r['expected_action']} ({'agent matched' if matched else 'agent differed'}). "
               f"Recorded in run {r['run']}.")


def admin_view():
    with st.sidebar:
        st.title("TicketPilot admin")
        st.caption(("Live mode: on. " if LIVE else "Live mode: off. ")
                   + f"Limits: {PER_VISITOR} per visitor, {DAILY_TOTAL} per day.")
        page = st.radio("Menu", ["Review queue", "All tickets", "Replay samples"])
        with st.expander("Maintenance"):
            st.caption("Resets the demo database to the original data. Deletes all live tickets, requests "
                       "and customer accounts.")
            sure = st.checkbox("I am sure")
            if st.button("Reset demo data", disabled=not sure):
                shutil.copy(SOURCE_DB, DEMO_DB)
                ensure_tables()
                st.rerun()
        if st.button("Sign out"):
            logout()
    if page == "Review queue":
        admin_queue()
    elif page == "All tickets":
        admin_all_tickets()
    else:
        admin_replay()


# ---------- main ----------

ensure_tables()
role = st.session_state.get("role")
if role == "customer" and st.session_state.get("cid"):
    customer_view(st.session_state["cid"])
elif role == "admin":
    admin_view()
else:
    login_screen()