import random
from datetime import date, timedelta

from faker import Faker

from app.db import DB_PATH, get_conn, init_db

SEED = 42
N_CUSTOMERS = 200
N_ORDERS = 500

# (item, category, min price, max price)
PRODUCTS = [
    ("Wireless Headphones", "electronics", 40, 220),
    ("Bluetooth Speaker", "electronics", 25, 150),
    ("Laptop Stand", "accessories", 20, 90),
    ("Phone Case", "accessories", 8, 35),
    ("Running Shoes", "apparel", 45, 160),
    ("Winter Jacket", "apparel", 70, 300),
    ("Coffee Maker", "home", 35, 180),
    ("Desk Lamp", "home", 18, 75),
    ("Air Fryer", "home", 50, 200),
    ("4K Monitor", "electronics", 180, 700),
    ("Gaming Laptop", "electronics", 700, 1800),
    ("Office Chair", "home", 90, 450),
]
STATUSES = ["delivered", "shipped", "placed", "cancelled", "refunded"]
STATUS_WEIGHTS = [0.70, 0.12, 0.08, 0.06, 0.04]


def main() -> None:
    random.seed(SEED)
    Faker.seed(SEED)
    fake = Faker()

    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    today = date.today()

    conn = get_conn()
    for cid in range(1, N_CUSTOMERS + 1):
        created = today - timedelta(days=random.randint(90, 900))
        tier = random.choices(["standard", "gold"], weights=[0.85, 0.15])[0]
        conn.execute(
            "INSERT INTO customers (id, name, email, tier, created_at) VALUES (?, ?, ?, ?, ?)",
            (cid, fake.name(), f"user{cid}@example.com", tier, created.isoformat()),
        )

    for oid in range(1, N_ORDERS + 1):
        cid = random.randint(1, N_CUSTOMERS)
        item, category, lo, hi = random.choice(PRODUCTS)
        total = round(random.uniform(lo, hi), 2)
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        order_date = today - timedelta(days=random.randint(1, 90))
        delivered = None
        if status in ("delivered", "refunded"):
            delivered = min(order_date + timedelta(days=random.randint(2, 7)), today).isoformat()
        conn.execute(
            "INSERT INTO orders (id, customer_id, item_name, category, total_amount, status, order_date, delivered_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (oid, cid, item, category, total, status, order_date.isoformat(), delivered),
        )

    conn.commit()
    conn.close()
    print(f"Created {DB_PATH} with {N_CUSTOMERS} customers and {N_ORDERS} orders")


if __name__ == "__main__":
    main()