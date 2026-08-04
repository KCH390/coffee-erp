"""
Continuous live simulator -- generates one simulated day of orders at a
time, immediately checking each order against current stock (consume,
substitute, or lose the sale, same rules as inventory_engine.py), then
sleeps --tick-seconds before moving to the next simulated day. Runs
until stopped (Ctrl+C) or --days is reached.

Meant to run alongside `streamlit run src/dashboard.py` in another
terminal -- turn on the dashboard's auto-refresh (sidebar) and watch
orders, inventory, and working capital move in real time.

Unlike simulate_orders.py + inventory_engine.py (which regenerate/
reprocess the ENTIRE history every run), this script advances state
incrementally and is meant to be left running: reorders become real
`purchase_orders` rows (not an in-memory heap) so state survives a
restart, and on-hand inventory is only ever read once at startup, then
kept in memory and written back to the DB after each simulated day.

Usage:
    python src/live_sim.py --tick-seconds 3
    python src/live_sim.py --tick-seconds 3 --days 30   # stop after 30 sim-days
    python src/live_sim.py --start-date 2026-01-01       # override start date
"""

import argparse
import random
import sqlite3
import time
from datetime import datetime, timedelta

from inventory_engine import load_bom_explosion, pick_substitute, SUBSTITUTION_PROBABILITY
from simulate_orders import (
    ITEM_POPULARITY,
    DAY_OF_WEEK_MULTIPLIER,
    HOUR_WEIGHTS,
    WEEKEND_FRAPPE_BOOST,
    NUM_LOYALTY_CUSTOMERS,
    NUM_WHOLESALE_CUSTOMERS,
    WALKIN_ORDER_SHARE,
    WHOLESALE_ORDER_SHARE,
    pick_hour,
    pick_items,
)


def get_or_create_customers(conn, rng):
    cur = conn.cursor()
    row = cur.execute("SELECT customer_id FROM customers WHERE segment='walk_in' LIMIT 1").fetchone()
    if row:
        walkin_id = row[0]
        loyalty_ids = [r[0] for r in cur.execute("SELECT customer_id FROM customers WHERE segment='loyalty'")]
        wholesale_ids = [r[0] for r in cur.execute("SELECT customer_id FROM customers WHERE segment='wholesale'")]
        return walkin_id, loyalty_ids, wholesale_ids

    cur.execute("INSERT INTO customers (customer_name, segment) VALUES ('Walk-in', 'walk_in')")
    walkin_id = cur.lastrowid

    loyalty_ids = []
    for i in range(1, NUM_LOYALTY_CUSTOMERS + 1):
        cur.execute("INSERT INTO customers (customer_name, segment) VALUES (?, 'loyalty')", (f"Loyalty Customer {i}",))
        loyalty_ids.append(cur.lastrowid)

    wholesale_ids = []
    for i in range(1, NUM_WHOLESALE_CUSTOMERS + 1):
        cur.execute("INSERT INTO customers (customer_name, segment) VALUES (?, 'wholesale')", (f"Wholesale Account {i}",))
        wholesale_ids.append(cur.lastrowid)

    conn.commit()
    return walkin_id, loyalty_ids, wholesale_ids


def next_simulation_date(conn, override_start_date):
    if override_start_date:
        return datetime.strptime(override_start_date, "%Y-%m-%d").date()
    cur = conn.cursor()
    row = cur.execute("SELECT MAX(order_date) FROM orders").fetchone()
    if row and row[0]:
        last_date = datetime.strptime(row[0].split(" ")[0], "%Y-%m-%d").date()
        return last_date + timedelta(days=1)
    return datetime.now().date()


def apply_due_purchase_orders(conn, as_of_dt, on_hand, standard_cost, new_txns):
    cur = conn.cursor()
    as_of_str = as_of_dt.strftime("%Y-%m-%d %H:%M:%S")
    due = cur.execute(
        "SELECT po_id, item_id, quantity FROM purchase_orders WHERE status='pending' AND expected_arrival <= ?",
        (as_of_str,),
    ).fetchall()
    received_ids = []
    for po_id, item_id, qty in due:
        on_hand[item_id] += qty
        new_txns.append((item_id, "receipt", qty, standard_cost.get(item_id, 0), as_of_str, f"PO-{po_id}"))
        received_ids.append(po_id)
    if received_ids:
        cur.executemany("UPDATE purchase_orders SET status='received' WHERE po_id=?", [(i,) for i in received_ids])
    return len(received_ids)


def has_open_po(conn, item_id):
    cur = conn.cursor()
    row = cur.execute(
        "SELECT 1 FROM purchase_orders WHERE item_id=? AND status='pending' LIMIT 1", (item_id,)
    ).fetchone()
    return row is not None


def maybe_place_purchase_order(conn, rm_id, on_hand, reorder_point, reorder_qty, lead_time_days, order_dt):
    if on_hand[rm_id] <= reorder_point[rm_id] and not has_open_po(conn, rm_id):
        arrival = order_dt + timedelta(days=lead_time_days[rm_id])
        conn.execute(
            "INSERT INTO purchase_orders (item_id, order_date, expected_arrival, quantity, status) "
            "VALUES (?, ?, ?, ?, 'pending')",
            (rm_id, order_dt.strftime("%Y-%m-%d %H:%M:%S"), arrival.strftime("%Y-%m-%d %H:%M:%S"), reorder_qty[rm_id]),
        )
        return True
    return False


def simulate_and_fulfill_day(conn, rng, sim_date, avg_daily_orders, state):
    cur = conn.cursor()

    (on_hand, reorder_point, reorder_qty, lead_time_days, standard_cost,
     bom_explosion, item_id_by_code, item_code_by_id, price_by_code,
     fg_codes, walkin_id, loyalty_ids, wholesale_ids) = state

    dow_mult = DAY_OF_WEEK_MULTIPLIER[sim_date.weekday()]
    is_weekend = sim_date.weekday() >= 5
    expected_orders = avg_daily_orders * dow_mult
    num_orders = max(0, round(rng.gauss(expected_orders, expected_orders * 0.1)))

    # build this day's order timestamps up front, then process chronologically
    day_events = []
    for _ in range(num_orders):
        hour = pick_hour(rng)
        minute = rng.randint(0, 59)
        dt = datetime.combine(sim_date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)

        roll = rng.random()
        if roll < WHOLESALE_ORDER_SHARE:
            customer_id = rng.choice(wholesale_ids)
            n_lines, qty_range = rng.randint(3, 6), (4, 12)
        elif roll < WHOLESALE_ORDER_SHARE + (1 - WALKIN_ORDER_SHARE - WHOLESALE_ORDER_SHARE):
            customer_id = rng.choice(loyalty_ids)
            n_lines, qty_range = (1 if rng.random() < 0.85 else 2), (1, 1)
        else:
            customer_id = walkin_id
            n_lines, qty_range = (1 if rng.random() < 0.9 else 2), (1, 1)

        chosen_codes = pick_items(rng, fg_codes, ITEM_POPULARITY, is_weekend, n_lines)
        lines = [(code, rng.randint(*qty_range)) for code in chosen_codes]
        day_events.append((dt, customer_id, lines))

    day_events.sort(key=lambda e: e[0])

    new_txns = []
    day_revenue = 0.0
    day_orders = 0
    day_lines_fulfilled = 0
    day_lines_substituted = 0
    day_lines_stockout = 0
    pos_placed = 0
    pos_received = 0

    for dt, customer_id, lines in day_events:
        pos_received += apply_due_purchase_orders(conn, dt, on_hand, standard_cost, new_txns)

        cur.execute(
            "INSERT INTO orders (customer_id, order_date, status) VALUES (?, ?, 'completed')",
            (customer_id, dt.strftime("%Y-%m-%d %H:%M:%S")),
        )
        order_id = cur.lastrowid
        day_orders += 1
        line_fulfilled_flags = []

        for fg_code, qty in lines:
            fg_id = item_id_by_code[fg_code]
            explosion = bom_explosion.get(fg_id, {})
            required = {rm: q * qty for rm, q in explosion.items()}
            can_fulfill = all(on_hand[rm] >= need for rm, need in required.items())

            if can_fulfill:
                for rm, need in required.items():
                    on_hand[rm] -= need
                    new_txns.append((rm, "consumption", -need, standard_cost.get(rm, 0),
                                      dt.strftime("%Y-%m-%d %H:%M:%S"), f"Order {order_id}"))
                    if maybe_place_purchase_order(conn, rm, on_hand, reorder_point, reorder_qty, lead_time_days, dt):
                        pos_placed += 1
                cur.execute(
                    "INSERT INTO order_lines (order_id, item_id, quantity, unit_price, fulfilled) VALUES (?, ?, ?, ?, 1)",
                    (order_id, fg_id, qty, price_by_code[fg_code]),
                )
                day_revenue += qty * price_by_code[fg_code]
                day_lines_fulfilled += 1
                line_fulfilled_flags.append(1)
                continue

            for rm in required:
                if maybe_place_purchase_order(conn, rm, on_hand, reorder_point, reorder_qty, lead_time_days, dt):
                    pos_placed += 1

            if rng.random() >= SUBSTITUTION_PROBABILITY:
                cur.execute(
                    "INSERT INTO order_lines (order_id, item_id, quantity, unit_price, fulfilled) VALUES (?, ?, ?, ?, 0)",
                    (order_id, fg_id, qty, price_by_code[fg_code]),
                )
                day_lines_stockout += 1
                line_fulfilled_flags.append(0)
                continue

            sub_code = pick_substitute(rng, fg_code, fg_codes, ITEM_POPULARITY)
            sub_id = item_id_by_code[sub_code]
            sub_explosion = bom_explosion.get(sub_id, {})
            sub_required = {rm: q * qty for rm, q in sub_explosion.items()}
            sub_can_fulfill = all(on_hand[rm] >= need for rm, need in sub_required.items())

            if sub_can_fulfill:
                for rm, need in sub_required.items():
                    on_hand[rm] -= need
                    new_txns.append((rm, "consumption", -need, standard_cost.get(rm, 0),
                                      dt.strftime("%Y-%m-%d %H:%M:%S"), f"Order {order_id}"))
                    if maybe_place_purchase_order(conn, rm, on_hand, reorder_point, reorder_qty, lead_time_days, dt):
                        pos_placed += 1
                cur.execute(
                    "INSERT INTO order_lines (order_id, item_id, quantity, unit_price, fulfilled, original_item_id) "
                    "VALUES (?, ?, ?, ?, 1, ?)",
                    (order_id, sub_id, qty, price_by_code[sub_code], fg_id),
                )
                day_revenue += qty * price_by_code[sub_code]
                day_lines_substituted += 1
                line_fulfilled_flags.append(1)
            else:
                for rm in sub_required:
                    if maybe_place_purchase_order(conn, rm, on_hand, reorder_point, reorder_qty, lead_time_days, dt):
                        pos_placed += 1
                cur.execute(
                    "INSERT INTO order_lines (order_id, item_id, quantity, unit_price, fulfilled) VALUES (?, ?, ?, ?, 0)",
                    (order_id, fg_id, qty, price_by_code[fg_code]),
                )
                day_lines_stockout += 1
                line_fulfilled_flags.append(0)

        status = "completed" if all(line_fulfilled_flags) else ("stockout" if not any(line_fulfilled_flags) else "partial")
        cur.execute("UPDATE orders SET status=? WHERE order_id=?", (status, order_id))

    if new_txns:
        cur.executemany(
            "INSERT INTO inventory_transactions (item_id, txn_type, quantity, unit_cost, txn_date, reference) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            new_txns,
        )
    cur.executemany(
        "UPDATE inventory SET on_hand_qty=?, last_updated=datetime('now') WHERE item_id=?",
        [(qty, item_id) for item_id, qty in on_hand.items()],
    )
    conn.commit()

    negative = [item_code_by_id[i] for i, q in on_hand.items() if q < -1e-9]

    print(
        f"[{sim_date}] orders={day_orders:<4} fulfilled={day_lines_fulfilled:<4} "
        f"substituted={day_lines_substituted:<3} stockout={day_lines_stockout:<3} "
        f"revenue=${day_revenue:>8,.2f}  POs placed={pos_placed} received={pos_received}"
        + (f"  !! NEGATIVE: {negative}" if negative else "")
    )


def main():
    parser = argparse.ArgumentParser(description="Continuously simulate one day of orders + inventory at a time.")
    parser.add_argument("--db", default="data/coffee_shop.db")
    parser.add_argument("--tick-seconds", type=float, default=3.0, help="Real seconds between simulated days")
    parser.add_argument("--avg-daily-orders", type=float, default=120)
    parser.add_argument("--days", type=int, default=None, help="Stop after this many simulated days (default: run forever)")
    parser.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD; default is the day after existing history, or today")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # better concurrent reads while the dashboard polls this file

    rng = random.Random(args.seed)

    walkin_id, loyalty_ids, wholesale_ids = get_or_create_customers(conn, rng)

    cur = conn.cursor()
    fg_rows = cur.execute("SELECT item_id, item_code, sale_price FROM items WHERE item_type='finished_good'").fetchall()
    item_id_by_code = {code: item_id for item_id, code, _ in fg_rows}
    item_code_by_id_fg = {item_id: code for item_id, code, _ in fg_rows}
    price_by_code = {code: price for _, code, price in fg_rows}
    fg_codes = list(price_by_code.keys())

    item_code_by_id = {i: c for i, c in cur.execute("SELECT item_id, item_code FROM items")}
    standard_cost = {i: c for i, c in cur.execute("SELECT item_id, standard_cost FROM items")}

    inv_rows = cur.execute(
        "SELECT item_id, on_hand_qty, reorder_point, reorder_qty, lead_time_days FROM inventory"
    ).fetchall()
    on_hand = {r[0]: r[1] for r in inv_rows}
    reorder_point = {r[0]: r[2] for r in inv_rows}
    reorder_qty = {r[0]: r[3] for r in inv_rows}
    lead_time_days = {r[0]: r[4] for r in inv_rows}

    bom_explosion = load_bom_explosion(conn)

    state = (on_hand, reorder_point, reorder_qty, lead_time_days, standard_cost,
             bom_explosion, item_id_by_code, item_code_by_id, price_by_code,
             fg_codes, walkin_id, loyalty_ids, wholesale_ids)

    sim_date = next_simulation_date(conn, args.start_date)

    print(f"Starting live simulation at {sim_date}, ticking every {args.tick_seconds}s "
          f"({'forever' if args.days is None else f'{args.days} days'}). Ctrl+C to stop.")

    day_count = 0
    try:
        while args.days is None or day_count < args.days:
            simulate_and_fulfill_day(conn, rng, sim_date, args.avg_daily_orders, state)
            sim_date += timedelta(days=1)
            day_count += 1
            time.sleep(args.tick_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
