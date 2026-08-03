"""
Standard cost rollup for the coffee shop ERP.

Walks the BOM (formulas table) bottom-up: raw materials already have a
standard_cost (entered directly, e.g. from purchase price). Intermediates
and finished goods get their standard_cost computed as:

    standard_cost = material_cost + labor_cost

where material_cost sums (quantity * (1 + scrap_pct) * component_cost)
across the item's formula, and labor_cost sums route_operations time
(setup + run minutes) * the assigned workstation's hourly rate.

Items are processed in topological order (a component's cost is always
computed before anything that depends on it), so this works correctly
even if the BOM grows beyond the current two-tier RM -> SFG -> FG
structure -- e.g. if you later add a component that's itself built from
other intermediates.

Usage:
    python costing.py --db path/to/coffee_shop.db
"""

import argparse
import sqlite3
from collections import defaultdict, deque


def topological_item_order(conn):
    """
    Returns item_ids in an order such that every component appears
    before any parent that uses it. Raw materials (no formula, i.e.
    they never appear as a parent_item_id) come first automatically
    since they have no incoming dependency edges to resolve.
    """
    cur = conn.cursor()
    all_items = [row[0] for row in cur.execute("SELECT item_id FROM items")]

    # dependency edges: parent depends on component
    depends_on = defaultdict(set)   # parent_id -> set(component_id)
    dependents = defaultdict(set)   # component_id -> set(parent_id)

    for parent_id, component_id in cur.execute(
        "SELECT parent_item_id, component_item_id FROM formulas"
    ):
        depends_on[parent_id].add(component_id)
        dependents[component_id].add(parent_id)

    in_degree = {item_id: len(depends_on[item_id]) for item_id in all_items}
    queue = deque([item_id for item_id in all_items if in_degree[item_id] == 0])
    order = []

    while queue:
        item_id = queue.popleft()
        order.append(item_id)
        for dependent_id in dependents[item_id]:
            in_degree[dependent_id] -= 1
            if in_degree[dependent_id] == 0:
                queue.append(dependent_id)

    if len(order) != len(all_items):
        unresolved = set(all_items) - set(order)
        raise ValueError(
            f"Circular dependency detected in formulas table involving item_ids: {unresolved}"
        )

    return order


def compute_material_cost(conn, item_id, cost_by_item):
    cur = conn.cursor()
    total = 0.0
    for component_id, quantity, scrap_pct in cur.execute(
        "SELECT component_item_id, quantity, scrap_pct FROM formulas WHERE parent_item_id = ?",
        (item_id,),
    ):
        total += quantity * (1 + scrap_pct) * cost_by_item[component_id]
    return total


def compute_labor_cost(conn, item_id):
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT COALESCE(SUM((ro.setup_minutes + ro.run_minutes) / 60.0 * w.hourly_rate), 0)
        FROM routes rt
        JOIN route_operations ro ON ro.route_id = rt.route_id
        LEFT JOIN workstations w ON w.workstation_id = ro.workstation_id
        WHERE rt.item_id = ?
        """,
        (item_id,),
    ).fetchone()
    return row[0] if row else 0.0


def rollup_costs(conn, verbose=True):
    cur = conn.cursor()

    # seed with raw material costs already stored in items.standard_cost
    cost_by_item = {}
    item_type_by_id = {}
    for item_id, item_type, standard_cost in cur.execute(
        "SELECT item_id, item_type, standard_cost FROM items"
    ):
        item_type_by_id[item_id] = item_type
        if item_type == "raw_material":
            cost_by_item[item_id] = standard_cost

    order = topological_item_order(conn)
    updates = []

    for item_id in order:
        if item_type_by_id[item_id] == "raw_material":
            continue  # cost is an input, not computed

        material_cost = compute_material_cost(conn, item_id, cost_by_item)
        labor_cost = compute_labor_cost(conn, item_id)
        standard_cost = material_cost + labor_cost

        cost_by_item[item_id] = standard_cost
        updates.append((standard_cost, item_id))

    cur.executemany("UPDATE items SET standard_cost = ? WHERE item_id = ?", updates)
    conn.commit()

    if verbose:
        print(f"Updated standard_cost for {len(updates)} intermediate/finished-good items.")
        for row in cur.execute(
            """
            SELECT item_code, item_type, standard_cost, sale_price
            FROM items WHERE item_type != 'raw_material'
            ORDER BY item_type, item_code
            """
        ):
            code, item_type, cost, price = row
            margin = f"{price - cost:.2f} ({(price - cost) / price:.1%})" if price else "n/a"
            print(f"  {code:<20} [{item_type:<11}] cost=${cost:.3f}  price={price}  margin={margin}")


def main():
    parser = argparse.ArgumentParser(description="Roll up standard costs through the BOM.")
    parser.add_argument("--db", default="coffee_shop.db", help="Path to the SQLite database")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    rollup_costs(conn)
    conn.close()


if __name__ == "__main__":
    main()
