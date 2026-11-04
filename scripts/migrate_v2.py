from faker import Faker

from app.db import DB_PATH, get_conn

conn = get_conn()
cols = [r["name"] for r in conn.execute("PRAGMA table_info(orders)")]
if "shipping_address" not in cols:
    conn.execute("ALTER TABLE orders ADD COLUMN shipping_address TEXT")
conn.executescript("""
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_id INTEGER REFERENCES orders(id),
    kind TEXT NOT NULL,
    details TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_events (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    order_id INTEGER NOT NULL REFERENCES orders(id),
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
""")
Faker.seed(46)
fake = Faker()
ids = [r["id"] for r in conn.execute("SELECT id FROM orders WHERE shipping_address IS NULL ORDER BY id")]
for oid in ids:
    addr = f"{fake.street_address()}, {fake.city()}, {fake.state_abbr()} {fake.postcode()}"
    conn.execute("UPDATE orders SET shipping_address = ? WHERE id = ?", (addr, oid))
conn.commit()
n = conn.execute("SELECT COUNT(*) FROM orders WHERE shipping_address IS NOT NULL").fetchone()[0]
print(f"Migrated {DB_PATH}: {len(ids)} addresses added, {n} orders now have one")
conn.close()