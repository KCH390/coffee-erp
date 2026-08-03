"""
Generates synthetic customers, orders, and order_lines for the coffee
shop ERP, with:

  - a small pool of repeat "loyalty" customers plus a generic "Walk-in"
    customer used for the majority of orders (realistic for a coffee
    shop -- most transactions aren't tied to an identified customer),
    and a couple of "wholesale" accounts that place fewer, larger orders
  - day-of-week seasonality (weekends busier)
  - hour-of-day seasonality (morning rush, midday lull, smaller
    afternoon bump)
  - per-item popularity weights, so Latte Standard sells a lot more
    than, say, plain Brewed Coffee -- matching a typical shop's mix

This REPLACES existing customers/orders/order_lines each run (clears
those three tables first) so it's safe to re-run repeatedly while
you're tuning parameters.

Usage:
    python src/simulate_orders.py --days 60 --avg-daily-orders 120 --seed 42
"""

import argparse
import random
import sqlite3
from datetime import datetime, timedelta

# ---------------------------------------------------------------------
# Tunable assumptions -- adjust these to reshape the simulated business
# ---------------------------------------------------------------------

# Relative popularity of each FG item (weights, not percentages -- they
# get normalized). Roughly reflects a typical coffee shop's mix: lattes
# dominate, plain brewed coffee and americano are common budget picks,
# frappes are a smaller treat-occasion category, cold brew has a loyal
# niche.
ITEM_POPULARITY = {
    "FG-LATTE-STD": 25,
    "FG-LATTE-SPICED": 8,
    "FG-LATTE-MOCHA": 12,
    "FG-BREWED": 15,
    "FG-AMERICANO": 12,
    "FG-FRAPPE-CARAMEL": 10,
    "FG-FRAPPE-MOCHA": 7,
    "FG-COLDBREW": 11,
}

# Multiplier on FRAPPE items specifically for weekend days (treat-occasion
# items skew weekend); applied on top of the general weekend volume bump.
WEEKEND_FRAPPE_BOOST = 1.4

# Day-of-week volume multiplier (Mon=0 ... Sun=6)
DAY_OF_WEEK_MULTIPLIER = {
    0: 0.90,  # Mon
    1: 0.92,  # Tue
    2: 0.95,  # Wed
    3: 1.00,  # Thu
    4: 1.10,  # Fri
    5: 1.35,  # Sat
    6: 1.15,  # Sun
}

# Hour-of-day weights (only hours with weight > 0 are open/operating hours)
HOUR_WEIGHTS = {
    6: 3, 7: 10, 8: 14, 9: 10, 10: 6, 11: 6, 12: 8, 13: 6,
    14: 4, 15: 4, 16: 3, 17: 3, 18: 2,
}

NUM_LOYALTY_CUSTOMERS = 30
NUM_WHOLESALE_CUSTOMERS = 3
WALKIN_ORDER_SHARE = 0.80      # share of orders with no identified customer
WHOLESALE_ORDER_SHARE = 0.02   # share of orders that are wholesale (larger qty)


def reset_transactional_tables(conn):
    conn.execute("DELETE FROM order_lines")
    conn.execute("DELETE FROM orders")
    conn.execute("DELETE FROM customers")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('order_lines','orders','customers')")


def seed_customers(conn, rng):
    cur = conn.cursor()
    cur.execute("INSERT INTO customers (customer_name, segment) VALUES ('Walk-in', 'walk_in')")
    walkin_id = cur.lastrowid

    loyalty_ids = []
    for i in range(1, NUM_LOYALTY_CUSTOMERS + 1):
        cur.execute(
            "INSERT INTO customers (customer_name, segment) VALUES (?, 'loyalty')",
            (f"Loyalty Customer {i}",),
        )
        loyalty_ids.append(cur.lastrowid)

    wholesale_ids = []
    for i in range(1, NUM_WHOLESALE_CUSTOMERS + 1):
        cur.execute(
            "INSERT INTO customers (customer_name, segment) VALUES (?, 'wholesale')",
            (f"Wholesale Account {i}",),
        )
        wholesale_ids.append(cur.lastrowid)

    return walkin_id, loyalty_ids, wholesale_ids


def pick_hour(rng):
    hours, weights = zip(*HOUR_WEIGHTS.items())
    return rng.choices(hours, weights=weights, k=1)[0]


def pick_items(rng, fg_items, weights, is_weekend, n):
    """Pick n item_codes weighted by popularity, boosting frappes on weekends."""
    adj_weights = []
    for code in fg_items:
        w = weights[code]
        if is_weekend and "FRAPPE" in code:
            w *= WEEKEND_FRAPPE_BOOST
        adj_weights.append(w)
    return rng.choices(fg_items, weights=adj_weights, k=n)


def simulate(conn, days, avg_daily_orders, seed=None):
    rng = random.Random(seed)

    cur = conn.cursor()
    fg_rows = cur.execute(
        "SELECT item_id, item_code, sale_price FROM items WHERE item_type='finished_good'"
    ).fetchall()
    price_by_code = {code: price for _, code, price in fg_rows}
    item_id_by_code = {code: item_id for item_id, code, _ in fg_rows}
    fg_items = list(price_by_code.keys())

    missing = set(ITEM_POPULARITY) - set(fg_items)
    if missing:
        raise ValueError(f"ITEM_POPULARITY references item_codes not found in items table: {missing}")

    reset_transactional_tables(conn)
    walkin_id, loyalty_ids, wholesale_ids = seed_customers(conn, rng)

    start_date = datetime.now().date() - timedelta(days=days)

    order_rows = []   # (customer_id, order_date)
    line_rows = []    # (order_index, item_id, quantity, unit_price)

    for day_offset in range(days):
        current_date = start_date + timedelta(days=day_offset)
        dow_mult = DAY_OF_WEEK_MULTIPLIER[current_date.weekday()]
        is_weekend = current_date.weekday() >= 5

        expected_orders = avg_daily_orders * dow_mult
        num_orders = max(0, round(rng.gauss(expected_orders, expected_orders * 0.1)))

        for _ in range(num_orders):
            hour = pick_hour(rng)
            minute = rng.randint(0, 59)
            order_dt = datetime.combine(current_date, datetime.min.time()) + timedelta(
                hours=hour, minutes=minute
            )

            roll = rng.random()
            if roll < WHOLESALE_ORDER_SHARE:
                customer_id = rng.choice(wholesale_ids)
                n_lines = rng.randint(3, 6)
                qty_range = (4, 12)
            elif roll < WHOLESALE_ORDER_SHARE + (1 - WALKIN_ORDER_SHARE - WHOLESALE_ORDER_SHARE):
                customer_id = rng.choice(loyalty_ids)
                n_lines = 1 if rng.random() < 0.85 else 2
                qty_range = (1, 1)
            else:
                customer_id = walkin_id
                n_lines = 1 if rng.random() < 0.9 else 2
                qty_range = (1, 1)

            chosen_codes = pick_items(rng, fg_items, ITEM_POPULARITY, is_weekend, n_lines)

            order_index = len(order_rows)
            order_rows.append((customer_id, order_dt.strftime("%Y-%m-%d %H:%M:%S")))

            for code in chosen_codes:
                qty = rng.randint(*qty_range)
                line_rows.append((order_index, item_id_by_code[code], qty, price_by_code[code]))

    cur.executemany(
        "INSERT INTO orders (customer_id, order_date, status) VALUES (?, ?, 'completed')",
        order_rows,
    )

    # map our 0-based order_index back to real order_id (SQLite autoincrement
    # ids are assigned in insertion order starting from the first id used)
    first_order_id = cur.execute(
        "SELECT MIN(order_id) FROM orders"
    ).fetchone()[0]

    resolved_lines = [
        (first_order_id + order_index, item_id, qty, unit_price)
        for order_index, item_id, qty, unit_price in line_rows
    ]
    cur.executemany(
        "INSERT INTO order_lines (order_id, item_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
        resolved_lines,
    )

    conn.commit()
    return len(order_rows), len(resolved_lines)


def main():
    parser = argparse.ArgumentParser(description="Simulate customer orders for the coffee shop ERP.")
    parser.add_argument("--db", default="data/coffee_shop.db", help="Path to the SQLite database")
    parser.add_argument("--days", type=int, default=60, help="Number of days of history to generate")
    parser.add_argument("--avg-daily-orders", type=float, default=120, help="Average orders per day")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")

    n_orders, n_lines = simulate(conn, args.days, args.avg_daily_orders, seed=args.seed)
    print(f"Generated {n_orders} orders ({n_lines} order lines) over {args.days} days.")

    conn.close()


if __name__ == "__main__":
    main()
