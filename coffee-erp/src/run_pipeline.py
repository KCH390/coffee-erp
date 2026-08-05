"""
Runs the full batch pipeline in the correct order, stopping immediately
if any step fails so you never end up with a half-rebuilt, inconsistent
database.

Steps (always run):
    1. db.py              -- fresh schema + seed data
    2. simulate_orders.py -- generate synthetic order history
    3. inventory_engine.py -- consume/reorder/substitute against that history

Optional (--optimize):
    4. optimize_inventory.py -- recalibrate safety stock to a target
       fulfillment rate (this step already leaves the database fully
       re-simulated and consistent -- no further steps needed after it)

Optional (--forecast):
    5. forecast_demand.py -- train the ML demand forecast (requested vs.
       fulfilled target comparison) against the final state and write
       results to data/results/. Read-only w.r.t. the database, so its
       position relative to --optimize doesn't affect correctness, but
       it's run last so the forecast reflects the final inventory policy.

NOT included here, since they're long-running/interactive rather than
one-shot steps:
    - dashboard.py  (run separately: streamlit run src/dashboard.py)
    - live_sim.py   (run separately: python src/live_sim.py)

Usage:
    python src/run_pipeline.py
    python src/run_pipeline.py --days 90 --avg-daily-orders 150
    python src/run_pipeline.py --optimize --target-fulfillment 0.97
    python src/run_pipeline.py --optimize --forecast
"""

import argparse
import subprocess
import sys


def run_step(description, cmd):
    print(f"\n{'=' * 70}\n{description}\n{'=' * 70}")
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n!!! Step failed: {description} (exit code {result.returncode}) !!!")
        print("Stopping -- fix the error above and re-run.")
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description="Run the full coffee shop ERP pipeline in order.")
    parser.add_argument("--days", type=int, default=60, help="Days of order history to simulate")
    parser.add_argument("--avg-daily-orders", type=float, default=120)
    parser.add_argument("--orders-seed", type=int, default=42, help="Seed for simulate_orders.py")
    parser.add_argument("--engine-seed", type=int, default=7, help="Seed for inventory_engine.py / optimize_inventory.py")
    parser.add_argument("--optimize", action="store_true", help="Also run optimize_inventory.py after the base pipeline")
    parser.add_argument("--target-fulfillment", type=float, default=0.97, help="Only used with --optimize")
    parser.add_argument("--forecast", action="store_true", help="Also run forecast_demand.py after the base pipeline")
    parser.add_argument("--forecast-seed", type=int, default=42, help="Seed for forecast_demand.py")
    args = parser.parse_args()

    python = sys.executable
    step = 0

    def next_step(label, cmd):
        nonlocal step
        step += 1
        run_step(f"Step {step}: {label}", cmd)

    next_step(
        "Rebuilding database (schema + seed data)",
        [python, "src/db.py"],
    )
    next_step(
        "Simulating order history",
        [python, "src/simulate_orders.py",
         "--days", str(args.days),
         "--avg-daily-orders", str(args.avg_daily_orders),
         "--seed", str(args.orders_seed)],
    )
    next_step(
        "Running inventory consumption + reorder engine",
        [python, "src/inventory_engine.py", "--seed", str(args.engine_seed)],
    )

    if args.optimize:
        next_step(
            "Optimizing inventory policy (working capital)",
            [python, "src/optimize_inventory.py",
             "--target-fulfillment", str(args.target_fulfillment),
             "--seed", str(args.engine_seed)],
        )

    if args.forecast:
        next_step(
            "Training ML demand forecast",
            [python, "src/forecast_demand.py", "--seed", str(args.forecast_seed)],
        )

    print(f"\n{'=' * 70}\nPipeline complete.\n{'=' * 70}")
    print("Next steps:")
    print("  streamlit run src/dashboard.py                 # view the dashboard")
    print("                                                  (Demand Forecast tab can also")
    print("                                                   recalculate on demand, anytime)")
    print("  python src/live_sim.py --tick-seconds 3         # start the live simulator")


if __name__ == "__main__":
    main()
