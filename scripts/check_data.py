from app.db import get_conn

conn = get_conn()
for table in ["customers", "orders", "tickets", "refund_requests", "traces"]:
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table}: {n}")
print("orders by status:", [tuple(r) for r in conn.execute("SELECT status, COUNT(*) FROM orders GROUP BY status")])
print("orders over $500:", conn.execute("SELECT COUNT(*) FROM orders WHERE total_amount > 500").fetchone()[0])
print("sample order:", dict(conn.execute("SELECT * FROM orders WHERE id = 1").fetchone()))