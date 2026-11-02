"""Create a deterministic synthetic retail dataset for local development."""
from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

CATEGORIES = ["Electronics", "Home", "Books", "Sports", "Beauty", "Clothing"]
PRODUCT_NAMES = {
    "Electronics": ["Wireless Mouse", "USB-C Hub", "Bluetooth Speaker", "Webcam", "Keyboard", "Power Bank"],
    "Home": ["Desk Lamp", "Water Bottle", "Storage Box", "Coffee Mug", "Bedside Organizer"],
    "Books": ["Python Basics", "Data Science Handbook", "Machine Learning Guide", "SQL Cookbook", "AI Engineering"],
    "Sports": ["Yoga Mat", "Resistance Bands", "Running Bottle", "Training Gloves", "Fitness Tracker"],
    "Beauty": ["Face Cleanser", "Moisturizer", "Sunscreen", "Hair Brush", "Hand Cream"],
    "Clothing": ["Cotton T-Shirt", "Hoodie", "Running Socks", "Canvas Tote", "Baseball Cap"],
}
CITIES = ["Singapore", "Kuala Lumpur", "Jakarta", "Bangkok", "Manila", "Ho Chi Minh City"]
SEGMENTS = ["Consumer", "Small Business", "Enterprise"]
STATUSES = ["delivered", "processing", "cancelled", "returned"]


def initialize_database(db_path: Path | str | None = None, force: bool = False) -> Path:
    """Create the sample SQLite database. Existing DBs are preserved unless force=True."""
    if db_path is None:
        from app.core.config import get_db_path
        path = get_db_path()
    else:
        path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not force:
        return path

    if path.exists():
        path.unlink()

    rng = random.Random(42)
    conn = sqlite3.connect(path)
    try:
        conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            customer_name TEXT NOT NULL,
            email TEXT NOT NULL,
            city TEXT NOT NULL,
            segment TEXT NOT NULL,
            signup_date TEXT NOT NULL
        );
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            unit_price REAL NOT NULL
        );
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            order_date TEXT NOT NULL,
            status TEXT NOT NULL,
            total_amount REAL NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );
        CREATE TABLE order_items (
            item_id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );
        CREATE INDEX idx_orders_date ON orders(order_date);
        CREATE INDEX idx_orders_customer ON orders(customer_id);
        CREATE INDEX idx_order_items_order ON order_items(order_id);
        """)

        start = date(2024, 1, 1)
        customers = []
        for i in range(1, 251):
            signup = start + timedelta(days=rng.randint(0, 700))
            customers.append((
                i, f"Customer {i:03d}", f"customer{i:03d}@example.com",
                rng.choice(CITIES), rng.choice(SEGMENTS), signup.isoformat()
            ))
        conn.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?)", customers
        )

        products = []
        product_id = 1
        for category, names in PRODUCT_NAMES.items():
            for name in names:
                price = round(rng.uniform(8, 280), 2)
                products.append((product_id, name, category, price))
                product_id += 1
        conn.executemany(
            "INSERT INTO products VALUES (?, ?, ?, ?)", products
        )

        orders = []
        order_items = []
        order_id = 1
        item_id = 1
        total_days = 730
        for _ in range(900):
            customer_id = rng.randint(1, 250)
            order_date = start + timedelta(days=rng.randint(0, total_days - 1))
            status = rng.choices(STATUSES, weights=[0.82, 0.08, 0.06, 0.04])[0]
            item_count = rng.randint(1, 4)
            order_total = 0.0
            selected_products = rng.sample(products, item_count)
            for product in selected_products:
                pid, _, _, base_price = product
                quantity = rng.randint(1, 4)
                unit_price = round(base_price * rng.uniform(0.90, 1.10), 2)
                order_total += quantity * unit_price
                order_items.append((item_id, order_id, pid, quantity, unit_price))
                item_id += 1
            orders.append((
                order_id, customer_id, order_date.isoformat(), status,
                round(order_total, 2)
            ))
            order_id += 1

        conn.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders
        )
        conn.executemany(
            "INSERT INTO order_items VALUES (?, ?, ?, ?, ?)", order_items
        )
        conn.commit()
    finally:
        conn.close()
    return path
