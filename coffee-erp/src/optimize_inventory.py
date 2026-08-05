"""
Phase 6 -- Working Capital Optimizer.

Your current reorder points are sized on a flat "cover N days" heuristic,
which is why fulfillment sits near 100% -- that's a lot of safety stock
for very little service-level benefit. This script replaces that with a
proper statistical safety-stock formula:

    reorder_point = mean_daily_demand * lead_time
                     + z * std_daily_demand * sqrt(lead_time)

where z is the standard-normal quantile for your target service level
(e.g. z ~= 1.88 for 97%). mean/std daily demand are measured from your
ACTUAL simulated consumption history, not assumed.

Closed-form z alone won't hit the target exactly, though -- this system
has substitution effects, several finished goods sharing the same raw
materials, and lumpy wholesale orders, none of which the textbook
formula accounts for. So this script CALIBRATES z empirically: it
repeatedly re-runs the real inventory_engine.run_engine() against your
actual order history at different z values (reusing the same, already-
tested consumption/substitution/reorder logic -- not a reimplementation)
and searches for the z that actually produces ~97% fulfillment when
simulated, not just in theory.

Requires an existing full pipeline run (db.py + simulate_orders.py +
inventory_engine.py) so there's real order + consumption history to
calibrate against. Mutates the database's inventory/inventory_transactions
state as part of searching -- that's expected, the final state is left
at the optimized (target-service-level) parameters. Also writes:
  - data/seed/seed_inventory.sql   (regenerated with optimized values)
  - data/optimization_trials.csv   (every (z, fulfillment, inventory $)
                                     trial, for charting the tradeoff curve)

Usage:
    python src/optimize_inventory.py --target-fulfillment 0.97
"""

import argparse
import csv
import math
import sqlite3
from pathlib import Path

import pandas as pd

from inventory_engine import run_engine

REVIEW_PERIOD_DAYS = 5  # same order-cycle buffer used in the original seed_inventory.sql


def norm_ppf(p):
    """
    Inverse standard normal CDF (quantile function), via Peter Acklam's
    rational approximation. No scipy dependency needed for something
    this project only needs at ~1e-4 precision (empirical calibration
    refines it anyway).
    """
    if not (0 < p < 1):
        raise ValueError("p must be in (0, 1)")

    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]

    p_low = 0.02425
    p_high = 1 - p_low

    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p <= p_high:
        q = p - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    else:
        q = math.sqrt(-2 * math.log(1-p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def compute_demand_stats(conn, since=None):
    """
    Mean and std of DAILY demand per raw material, from actual consumption
    history. If `since` is given (a "YYYY-MM-DD HH:MM:SS" string), only
    transactions on or after that date are used -- for a rolling-window
    recalibration rather than all-time history.
    """
    query = "SELECT item_id, txn_date, quantity FROM inventory_transactions WHERE txn_type='consumption'"
    params = ()
    if since is not None:
        query += " AND txn_date >= ?"
        params = (since,)
    txns = pd.read_sql_query(query, conn, params=params)
    txns["date"] = pd.to_datetime(txns["txn_date"]).dt.normalize()
    daily = txns.groupby(["item_id", "date"])["quantity"].sum().abs().unstack("item_id").fillna(0)
    full_range = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_range).fillna(0)
    return daily.mean(), daily.std()


def working_capital_avg(conn):
    """Average raw-material inventory value over the transaction history, at current standard_cost."""
    txns = pd.read_sql_query("SELECT item_id, txn_date, quantity FROM inventory_transactions", conn)
    cost_by_item = pd.read_sql_query("SELECT item_id, standard_cost FROM items", conn).set_index("item_id")["standard_cost"]
    txns["date"] = pd.to_datetime(txns["txn_date"]).dt.normalize()
    daily_delta = txns.groupby(["item_id", "date"])["quantity"].sum().unstack("item_id").fillna(0)
    full_range = pd.date_range(daily_delta.index.min(), daily_delta.index.max(), freq="D")
    daily_delta = daily_delta.reindex(full_range).fillna(0)
    running_balance = daily_delta.cumsum()
    values = running_balance.multiply(cost_by_item, axis=1)
    return values.sum(axis=1).mean()


def fulfillment_rate(conn):
    row = conn.execute("SELECT AVG(fulfilled) FROM order_lines").fetchone()
    return row[0] if row and row[0] is not None else 0.0


def compute_policy(z, mean_daily, std_daily, lead_time_days, pack_size, min_order_qty):
    """Given z and demand stats, compute reorder_point/reorder_qty/on_hand for one item."""
    safety_stock = z * std_daily * math.sqrt(lead_time_days)
    reorder_point = mean_daily * lead_time_days + safety_stock
    target_qty = mean_daily * (lead_time_days + REVIEW_PERIOD_DAYS)
    packs_needed = max(math.ceil(target_qty / pack_size), min_order_qty)
    reorder_qty = packs_needed * pack_size
    return max(reorder_point, 0), reorder_qty


def evaluate(conn, z, item_ids, mean_daily, std_daily, lead_time_days, pack_size, min_order_qty, seed):
    """Apply policy(z) to all raw materials, re-run the real engine, measure the result."""
    policies = {}
    for item_id in item_ids:
        rp, rq = compute_policy(
            z, mean_daily[item_id], std_daily[item_id],
            lead_time_days[item_id], pack_size[item_id], min_order_qty[item_id],
        )
        policies[item_id] = (rp, rq)

    cur = conn.cursor()
    cur.executemany(
        "UPDATE inventory SET reorder_point=?, reorder_qty=?, on_hand_qty=? WHERE item_id=?",
        [(rp, rq, rq, item_id) for item_id, (rp, rq) in policies.items()],
    )
    cur.execute("DELETE FROM inventory_transactions")
    cur.executemany(
        "INSERT INTO inventory_transactions (item_id, txn_type, quantity, unit_cost, txn_date, reference) "
        "SELECT item_id, 'receipt', on_hand_qty, "
        "(SELECT standard_cost FROM items WHERE items.item_id = inventory.item_id), "
        "datetime('now', '-400 days'), 'Opening Balance (trial)' "
        "FROM inventory WHERE item_id = ?",
        [(item_id,) for item_id in item_ids],
    )
    conn.commit()

    run_engine(conn, seed=seed, verbose=False)

    return fulfillment_rate(conn), working_capital_avg(conn), policies


def main():
    parser = argparse.ArgumentParser(description="Calibrate safety stock to hit a target fulfillment rate.")
    parser.add_argument("--db", default="data/coffee_shop.db")
    parser.add_argument("--target-fulfillment", type=float, default=0.97)
    parser.add_argument("--tolerance", type=float, default=0.003)
    parser.add_argument("--seed", type=int, default=7, help="Fixed seed for fair comparison across trials")
    parser.add_argument("--max-iterations", type=int, default=8, help="Bisection refinement steps after the coarse grid")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")

    print("Computing demand statistics from actual consumption history...")
    mean_daily, std_daily = compute_demand_stats(conn)

    inv_rows = conn.execute(
        "SELECT item_id, lead_time_days, pack_size, min_order_qty FROM inventory"
    ).fetchall()
    item_ids = [r[0] for r in inv_rows]
    lead_time_days = {r[0]: r[1] for r in inv_rows}
    pack_size = {r[0]: r[2] for r in inv_rows}
    min_order_qty = {r[0]: r[3] for r in inv_rows}
    item_code = {i: c for i, c in conn.execute("SELECT item_id, item_code FROM items")}

    baseline_fulfillment = fulfillment_rate(conn)
    baseline_wc = working_capital_avg(conn)
    print(f"Baseline (current policy):  fulfillment={baseline_fulfillment:.1%}  "
          f"avg inventory value=${baseline_wc:,.2f}")
    print()

    trials = []

    def try_z(z):
        fr, wc, policies = evaluate(conn, z, item_ids, mean_daily, std_daily,
                                     lead_time_days, pack_size, min_order_qty, args.seed)
        trials.append((z, fr, wc))
        print(f"  z={z:5.2f}  fulfillment={fr:.1%}  avg inventory value=${wc:,.2f}")
        return fr, wc, policies

    print("Coarse grid search:")
    grid = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    grid_results = [(z, *try_z(z)[:2]) for z in grid]

    # find the bracket [z_lo, z_hi] where fulfillment crosses the target
    z_lo, z_hi = grid[0], grid[-1]
    for i in range(len(grid_results) - 1):
        z1, fr1, _ = grid_results[i]
        z2, fr2, _ = grid_results[i + 1]
        if fr1 <= args.target_fulfillment <= fr2:
            z_lo, z_hi = z1, z2
            break
    else:
        if grid_results[-1][1] < args.target_fulfillment:
            z_lo, z_hi = grid_results[-1][0], grid_results[-1][0] + 1.0
            print(f"  Target above grid range -- extending search to z={z_hi}")
            try_z(z_hi)

    print(f"\nRefining within [{z_lo}, {z_hi}]:")
    best = min(trials, key=lambda t: abs(t[1] - args.target_fulfillment))
    for _ in range(args.max_iterations):
        z_mid = (z_lo + z_hi) / 2
        fr, wc, policies = try_z(z_mid)
        if abs(fr - args.target_fulfillment) < abs(best[1] - args.target_fulfillment):
            best = (z_mid, fr, wc)
        if abs(fr - args.target_fulfillment) <= args.tolerance:
            break
        if fr < args.target_fulfillment:
            z_lo = z_mid
        else:
            z_hi = z_mid

    best_z = best[0]
    print(f"\nBest z found: {best_z:.3f}  (fulfillment={best[1]:.1%}, target={args.target_fulfillment:.1%})")

    # leave the DB in the best-found state
    final_fr, final_wc, final_policies = evaluate(
        conn, best_z, item_ids, mean_daily, std_daily, lead_time_days, pack_size, min_order_qty, args.seed
    )

    print()
    print("=" * 70)
    print(f"{'BEFORE (current policy)':<35}{'AFTER (optimized, z=' + f'{best_z:.2f})':<35}")
    print(f"{'Fulfillment: ' + f'{baseline_fulfillment:.1%}':<35}{'Fulfillment: ' + f'{final_fr:.1%}':<35}")
    print(f"{'Avg inventory: $' + f'{baseline_wc:,.2f}':<35}{'Avg inventory: $' + f'{final_wc:,.2f}':<35}")
    savings = baseline_wc - final_wc
    pct = savings / baseline_wc if baseline_wc else 0
    print(f"\nWorking capital freed: ${savings:,.2f} ({pct:.1%} reduction)")
    print("=" * 70)

    # persist trials for the notebook
    trials_path = Path("data/results/optimization_trials.csv")
    trials_path.parent.mkdir(parents=True, exist_ok=True)
    with open(trials_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["z", "fulfillment_rate", "avg_inventory_value"])
        writer.writerows(trials)
    print(f"\nWrote {len(trials)} trials to {trials_path}")

    # regenerate seed_inventory.sql with the optimized policy
    lines = [
        "-- ============================================================",
        "-- Seed Data: Inventory (raw materials only)",
        "--",
        f"-- CALIBRATED for a {args.target_fulfillment:.0%} target fulfillment rate",
        f"-- (Phase 6 working capital optimization). reorder_point uses a",
        "-- statistical safety-stock formula:",
        "--     reorder_point = mean_daily_demand * lead_time",
        f"--                     + z * std_daily_demand * sqrt(lead_time), z={best_z:.3f}",
        "-- mean/std daily demand measured from actual simulated consumption",
        "-- history (not assumed). z was found by re-running the real",
        "-- inventory_engine against actual order history at different z",
        "-- values until simulated fulfillment matched the target -- see",
        "-- src/optimize_inventory.py and data/optimization_trials.csv.",
        "--",
        f"-- Result: avg inventory value ${baseline_wc:,.2f} -> ${final_wc:,.2f} "
        f"({pct:.1%} reduction) at {final_fr:.1%} fulfillment.",
        "-- ============================================================",
        "",
        "INSERT INTO inventory (item_id, on_hand_qty, reorder_point, reorder_qty, lead_time_days, pack_size, min_order_qty)",
        "SELECT items.item_id, v.on_hand_qty, v.reorder_point, v.reorder_qty, v.lead_time_days, v.pack_size, v.min_order_qty",
        "FROM items JOIN (",
    ]
    value_lines = []
    for idx, item_id in enumerate(item_ids):
        rp, rq = final_policies[item_id]
        prefix = "    SELECT" if idx == 0 else "    UNION ALL SELECT"
        value_lines.append(
            f"{prefix} '{item_code[item_id]}' AS item_code, {round(rq,2)} AS on_hand_qty, "
            f"{round(rp,2)} AS reorder_point, {round(rq,2)} AS reorder_qty, "
            f"{lead_time_days[item_id]} AS lead_time_days, {pack_size[item_id]} AS pack_size, "
            f"{min_order_qty[item_id]} AS min_order_qty"
        )
    lines.extend(value_lines)
    lines.append(") v ON items.item_code = v.item_code;")
    lines.append("")
    lines.append("-- Opening balance transactions, one per raw material, for audit trail")
    lines.append("INSERT INTO inventory_transactions (item_id, txn_type, quantity, unit_cost, txn_date, reference)")
    lines.append("SELECT i.item_id, 'receipt', i.on_hand_qty, it.standard_cost, datetime('now', '-400 days'), 'Opening Balance'")
    lines.append("FROM inventory i JOIN items it ON it.item_id = i.item_id;")

    seed_path = Path("data/seed/seed_inventory.sql")
    seed_path.write_text("\n".join(lines))
    print(f"Wrote optimized policy to {seed_path}")

    conn.close()


if __name__ == "__main__":
    main()
