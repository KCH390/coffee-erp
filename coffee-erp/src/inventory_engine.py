"""
Phase 3 -- Inventory & Transaction Engine.

Walks the simulated order history (orders + order_lines) in chronological
order. For each order line, explodes the finished good through the full
BOM to raw materials and checks whether EVERY required raw material has
enough on-hand stock to cover it.

  - If yes: consume all of them (atomically -- a line never partially
    consumes its recipe) and log a 'consumption' transaction per raw
    material.
  - If no (a stockout on the originally requested item): the customer
    reacts one of two ways --
        85% (SUBSTITUTION_PROBABILITY): tries a different item, chosen
            by the same popularity weighting used in simulate_orders.py.
            If THAT item is in stock, the sale happens under the new
            item (order_lines.item_id/unit_price updated, original_item_id
            records what they originally wanted). If the substitute is
            ALSO out of stock, no sale happens.
        15%: leaves without ordering. No sale happens.
    Either way, on_hand can never go negative as a result of this engine.

After processing, each order's status is rolled up from its lines:
'completed' if every line was fulfilled, 'stockout' if none were,
'partial' if some were and some weren't.

Reorder-point logic is unchanged: whenever a raw material's on-hand
quantity drops to or below its reorder_point and it doesn't already have
an outstanding order, a purchase is triggered that arrives (a 'receipt'
transaction, replenishing stock) lead_time_days later.

This does NOT touch the opening-balance transactions already loaded by
seed_inventory.sql -- it starts from current inventory.on_hand_qty and
adds new transactions on top, so it's safe to run after db.py +
simulate_orders.py without re-seeding. Re-running it first restores any
previously-substituted lines back to their original item and resets
fulfilled flags, so re-running after re-simulating orders is safe --
but note it does NOT reset on_hand back to opening balance, so running
it twice in a row without rebuilding the DB in between will double-count
consumption. Rebuild (db.py) between simulate/engine cycles.

Usage:
    python src/inventory_engine.py --db data/coffee_shop.db --seed 7
"""

import argparse
import heapq
import random
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from simulate_orders import ITEM_POPULARITY

SUBSTITUTION_PROBABILITY = 0.85  # chance a customer facing a stockout tries something else
# (the remaining 1 - SUBSTITUTION_PROBABILITY is the chance they just leave)


def load_bom_explosion(conn):
    """
    For each finished_good item, precompute {raw_material_item_id: qty_per_unit},
    fully exploded through any intermediate tiers (handles arbitrary BOM depth,
    same approach used for costing).
    """
    cur = conn.cursor()
    item_type = {i: t for i, t in cur.execute("SELECT item_id, item_type FROM items")}
    formula = defaultdict(list)
    for p, c, q, s in cur.execute("SELECT parent_item_id, component_item_id, quantity, scrap_pct FROM formulas"):
        formula[p].append((c, q, s))

    def explode(item_id, multiplier=1.0):
        result = defaultdict(float)
        for comp_id, qty, scrap in formula.get(item_id, []):
            total_qty = qty * (1 + scrap) * multiplier
            if item_type[comp_id] == "raw_material":
                result[comp_id] += total_qty
            else:
                for rm_id, rm_qty in explode(comp_id, total_qty).items():
                    result[rm_id] += rm_qty
        return result

    fg_ids = [i for i, t in item_type.items() if t == "finished_good"]
    return {fg_id: dict(explode(fg_id)) for fg_id in fg_ids}


def pick_substitute(rng, original_code, candidate_codes, weights):
    """Weighted-random pick of a different item_code, excluding original_code."""
    others = [c for c in candidate_codes if c != original_code]
    other_weights = [weights[c] for c in others]
    return rng.choices(others, weights=other_weights, k=1)[0]


def run_engine(conn, seed=None, verbose=True):
    rng = random.Random(seed)
    cur = conn.cursor()

    bom_explosion = load_bom_explosion(conn)

    item_code = {i: c for i, c in cur.execute("SELECT item_id, item_code FROM items")}
    code_to_id = {c: i for i, c in item_code.items()}
    sale_price = {i: p for i, p in cur.execute("SELECT item_id, sale_price FROM items")}
    fg_codes = [c for c in ITEM_POPULARITY if c in code_to_id]

    # idempotency: undo any substitutions from a previous run and reset fulfillment
    # before reprocessing (does NOT reset on_hand -- see module docstring)
    cur.execute(
        """
        UPDATE order_lines
        SET item_id = original_item_id,
            unit_price = (SELECT sale_price FROM items WHERE items.item_id = order_lines.original_item_id),
            original_item_id = NULL
        WHERE original_item_id IS NOT NULL
        """
    )
    cur.execute("UPDATE order_lines SET fulfilled = 1")

    inv_rows = cur.execute(
        "SELECT item_id, on_hand_qty, reorder_point, reorder_qty, lead_time_days FROM inventory"
    ).fetchall()
    on_hand = {r[0]: r[1] for r in inv_rows}
    reorder_point = {r[0]: r[2] for r in inv_rows}
    reorder_qty = {r[0]: r[3] for r in inv_rows}
    lead_time_days = {r[0]: r[4] for r in inv_rows}
    standard_cost = {i: c for i, c in cur.execute("SELECT item_id, standard_cost FROM items")}

    events = cur.execute(
        """
        SELECT ol.order_line_id, o.order_id, o.order_date, ol.item_id, ol.quantity
        FROM orders o JOIN order_lines ol ON ol.order_id = o.order_id
        ORDER BY o.order_date, o.order_id, ol.order_line_id
        """
    ).fetchall()

    pending_receipts = []  # heap of (arrival_dt_str, item_id)
    open_order = set()

    new_txns = []                 # (item_id, txn_type, quantity, unit_cost, txn_date, reference)
    unfulfilled_line_ids = []     # order_line_ids to mark fulfilled = 0
    substituted_lines = []        # (order_line_id, new_item_id, new_unit_price, original_item_id)
    reorders_triggered = 0
    lines_fulfilled_direct = 0
    lines_substituted = 0
    lines_left = 0                # customer walked away (the 15% branch)
    lines_substitute_stockout = 0  # substitute also unavailable
    lost_revenue = 0.0

    def apply_due_receipts(as_of_dt_str):
        nonlocal reorders_triggered
        while pending_receipts and pending_receipts[0][0] <= as_of_dt_str:
            arrival_dt_str, item_id = heapq.heappop(pending_receipts)
            qty = reorder_qty[item_id]
            on_hand[item_id] += qty
            new_txns.append(
                (item_id, "receipt", qty, standard_cost.get(item_id, 0), arrival_dt_str, "Reorder")
            )
            open_order.discard(item_id)

    def maybe_trigger_reorder(rm_id, order_date):
        nonlocal reorders_triggered
        if on_hand[rm_id] <= reorder_point[rm_id] and rm_id not in open_order:
            order_dt = datetime.strptime(order_date, "%Y-%m-%d %H:%M:%S")
            arrival_dt = order_dt + timedelta(days=lead_time_days[rm_id])
            heapq.heappush(pending_receipts, (arrival_dt.strftime("%Y-%m-%d %H:%M:%S"), rm_id))
            open_order.add(rm_id)
            reorders_triggered += 1

    def consume(required, order_date, order_id):
        for rm_id, need in required.items():
            on_hand[rm_id] -= need
            new_txns.append(
                (rm_id, "consumption", -need, standard_cost.get(rm_id, 0), order_date, f"Order {order_id}")
            )
            maybe_trigger_reorder(rm_id, order_date)

    for order_line_id, order_id, order_date, fg_item_id, order_qty in events:
        apply_due_receipts(order_date)

        explosion = bom_explosion.get(fg_item_id)
        if not explosion:
            continue  # finished good with no RM formula (shouldn't happen, but don't crash)

        required = {rm_id: qty_per_unit * order_qty for rm_id, qty_per_unit in explosion.items()}
        can_fulfill = all(on_hand[rm_id] >= need for rm_id, need in required.items())

        if can_fulfill:
            consume(required, order_date, order_id)
            lines_fulfilled_direct += 1
            continue

        # original item is out of stock -- flag its short raw materials for reorder either way
        for rm_id in required:
            maybe_trigger_reorder(rm_id, order_date)

        if rng.random() >= SUBSTITUTION_PROBABILITY:
            # customer leaves without ordering
            unfulfilled_line_ids.append(order_line_id)
            lines_left += 1
            continue

        # customer tries something else
        original_code = item_code[fg_item_id]
        substitute_code = pick_substitute(rng, original_code, fg_codes, ITEM_POPULARITY)
        sub_item_id = code_to_id[substitute_code]
        sub_explosion = bom_explosion.get(sub_item_id, {})
        sub_required = {rm_id: qty_per_unit * order_qty for rm_id, qty_per_unit in sub_explosion.items()}
        sub_can_fulfill = all(on_hand[rm_id] >= need for rm_id, need in sub_required.items())

        if sub_can_fulfill:
            consume(sub_required, order_date, order_id)
            substituted_lines.append((order_line_id, sub_item_id, sale_price[sub_item_id], fg_item_id))
            lines_substituted += 1
        else:
            for rm_id in sub_required:
                maybe_trigger_reorder(rm_id, order_date)
            unfulfilled_line_ids.append(order_line_id)
            lines_substitute_stockout += 1

    if events:
        apply_due_receipts(events[-1][2])

    still_in_transit = len(pending_receipts)
    lines_stockout = lines_left + lines_substitute_stockout
    lines_fulfilled = lines_fulfilled_direct + lines_substituted

    if unfulfilled_line_ids:
        placeholders = ",".join("?" * len(unfulfilled_line_ids))
        lost_revenue = cur.execute(
            f"SELECT COALESCE(SUM(quantity * unit_price), 0) FROM order_lines WHERE order_line_id IN ({placeholders})",
            unfulfilled_line_ids,
        ).fetchone()[0]

    # persist
    cur.executemany(
        "INSERT INTO inventory_transactions (item_id, txn_type, quantity, unit_cost, txn_date, reference) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        new_txns,
    )
    cur.executemany(
        "UPDATE inventory SET on_hand_qty = ?, last_updated = datetime('now') WHERE item_id = ?",
        [(qty, item_id) for item_id, qty in on_hand.items()],
    )
    if unfulfilled_line_ids:
        cur.executemany(
            "UPDATE order_lines SET fulfilled = 0 WHERE order_line_id = ?",
            [(oid,) for oid in unfulfilled_line_ids],
        )
    if substituted_lines:
        cur.executemany(
            "UPDATE order_lines SET item_id = ?, unit_price = ?, original_item_id = ? WHERE order_line_id = ?",
            [(new_id, price, orig_id, oid) for oid, new_id, price, orig_id in substituted_lines],
        )

    # roll up order-level status from its lines
    cur.execute(
        """
        UPDATE orders
        SET status = CASE
            WHEN (SELECT COUNT(*) FROM order_lines ol WHERE ol.order_id = orders.order_id AND ol.fulfilled = 0) = 0
                THEN 'completed'
            WHEN (SELECT COUNT(*) FROM order_lines ol WHERE ol.order_id = orders.order_id AND ol.fulfilled = 1) = 0
                THEN 'stockout'
            ELSE 'partial'
        END
        """
    )

    conn.commit()

    negative_items = [item_id for item_id, qty in on_hand.items() if qty < -1e-9]

    if verbose:
        print(f"Processed {len(events)} order lines.")
        print(f"  Fulfilled directly:      {lines_fulfilled_direct}")
        print(f"  Fulfilled via substitute: {lines_substituted}")
        print(f"  Left without ordering:    {lines_left}")
        print(f"  Substitute also stocked out: {lines_substitute_stockout}")
        print(f"  Total stockout (no sale): {lines_stockout}")
        print(f"Logged {len(new_txns)} new inventory transactions "
              f"({sum(1 for t in new_txns if t[1] == 'consumption')} consumption, "
              f"{sum(1 for t in new_txns if t[1] == 'receipt')} receipt).")
        print(f"Reorders triggered: {reorders_triggered}  |  still in transit at end: {still_in_transit}")
        print(f"Estimated lost revenue from unfulfilled lines: ${lost_revenue:,.2f}")
        print(f"Negative on_hand items (should be empty): "
              f"{[item_code[i] for i in negative_items] if negative_items else 'none'}")
        print()
        print(f"{'item':<18}{'final on_hand':>15}{'reorder_point':>15}")
        for item_id, qty in sorted(on_hand.items(), key=lambda kv: item_code[kv[0]]):
            print(f"{item_code[item_id]:<18}{qty:>15.1f}{reorder_point[item_id]:>15.1f}")


def main():
    parser = argparse.ArgumentParser(description="Run the inventory consumption + reorder engine.")
    parser.add_argument("--db", default="data/coffee_shop.db", help="Path to the SQLite database")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for substitution behavior")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    run_engine(conn, seed=args.seed)
    conn.close()


if __name__ == "__main__":
    main()
