"""
ML Demand Forecasting.

Predicts daily demand per finished good using a RandomForestRegressor
on day-of-week, weekend, and item-identity features.

IMPORTANT MODELING CHOICE: the target is REQUESTED quantity, recovered
via COALESCE(original_item_id, item_id) on order_lines, not FULFILLED
quantity. If you forecast off fulfilled sales, any item that stocked
out gets a systematically understated demand signal (you can't sell
what you don't have) -- which then feeds back into inventory sizing
even LESS safety stock next time, compounding the problem. This is a
classic demand-censoring bias in inventory forecasting. This script
quantifies the bias directly: it trains a second model on fulfilled-
only quantity and compares both against the true requested-quantity
test set, so the difference is a measured number, not just an
assertion. (The same fix was applied to optimize_inventory.py's
compute_demand_stats(), which had the identical bug.)

The core logic lives in run_forecast(conn, seed) so it can be called
from here (CLI) or from the dashboard (recalculate-on-demand, read-only,
never mutates the database).

Usage:
    python src/forecast_demand.py --db data/coffee_shop.db
"""

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


def load_daily_panel(conn):
    """
    Full (item, date) panel of finished-good demand, both the TRUE
    requested quantity and the (censored) fulfilled-only quantity,
    zero-filled for days with no orders of that item.
    """
    df = pd.read_sql_query(
        """
        SELECT o.order_date, ol.item_id, ol.original_item_id, ol.quantity, ol.fulfilled
        FROM order_lines ol JOIN orders o ON o.order_id = ol.order_id
        JOIN items it ON it.item_id = ol.item_id
        """,
        conn,
    )
    fg_items = pd.read_sql_query(
        "SELECT item_id, item_code FROM items WHERE item_type='finished_good'", conn
    )

    df["effective_item_id"] = df["original_item_id"].fillna(df["item_id"]).astype(int)
    df["date"] = pd.to_datetime(df["order_date"]).dt.normalize()
    df["fulfilled_qty"] = df["quantity"] * df["fulfilled"]

    requested = df.groupby(["effective_item_id", "date"])["quantity"].sum().rename("requested_qty")
    fulfilled = df.groupby(["effective_item_id", "date"])["fulfilled_qty"].sum().rename("fulfilled_qty")
    panel = pd.concat([requested, fulfilled], axis=1).reset_index()
    panel = panel.rename(columns={"effective_item_id": "item_id"})

    full_dates = pd.date_range(panel["date"].min(), panel["date"].max(), freq="D")
    full_panel = pd.MultiIndex.from_product(
        [fg_items["item_id"], full_dates], names=["item_id", "date"]
    ).to_frame(index=False)
    panel = full_panel.merge(panel, on=["item_id", "date"], how="left").fillna(0)
    panel = panel.merge(fg_items, on="item_id")
    return panel


def add_features(panel):
    panel = panel.copy()
    panel["day_of_week"] = panel["date"].dt.dayofweek
    panel["is_weekend"] = (panel["day_of_week"] >= 5).astype(int)
    # NOTE: no trend/ordinal-date feature. Tested with one -- it was the
    # 2nd most "important" feature and made both models WORSE against the
    # historical baseline, because this data's demand process is
    # stationary by construction (fixed popularity weights, no real
    # trend), so a trend feature just lets the model fit sampling noise
    # over a 60-day window as if it were a real pattern.
    panel = pd.get_dummies(panel, columns=["item_code"], prefix="item")
    return panel


def time_based_split(panel, test_frac=0.2):
    cutoff = panel["date"].quantile(1 - test_frac, interpolation="nearest")
    train = panel[panel["date"] < cutoff]
    test = panel[panel["date"] >= cutoff]
    return train, test


def feature_columns(panel):
    return [c for c in panel.columns
            if (c.startswith("item_") and c != "item_id") or c in ("day_of_week", "is_weekend")]


def run_forecast(conn, seed=42, test_frac=0.2, verbose=True):
    """
    Trains both models, evaluates them, and returns a dict with
    everything needed to report or plot the results:
        metrics, predictions (DataFrame), bias_by_item (DataFrame),
        importances (Series), train_range, test_range
    Read-only w.r.t. the database -- never writes anything, safe to
    call from the dashboard on a button click.
    """
    panel = load_daily_panel(conn)
    panel = add_features(panel)

    train, test = time_based_split(panel, test_frac=test_frac)
    feat_cols = feature_columns(panel)

    if verbose:
        print(f"Train: {len(train)} rows ({train['date'].min().date()} to {train['date'].max().date()})")
        print(f"Test:  {len(test)} rows ({test['date'].min().date()} to {test['date'].max().date()})")
        print()

    model_requested = RandomForestRegressor(n_estimators=200, random_state=seed, min_samples_leaf=3)
    model_requested.fit(train[feat_cols], train["requested_qty"])
    pred_requested = model_requested.predict(test[feat_cols])

    model_fulfilled = RandomForestRegressor(n_estimators=200, random_state=seed, min_samples_leaf=3)
    model_fulfilled.fit(train[feat_cols], train["fulfilled_qty"])
    pred_from_fulfilled_model = model_fulfilled.predict(test[feat_cols])

    y_true = test["requested_qty"].values
    mae_correct = mean_absolute_error(y_true, pred_requested)
    rmse_correct = np.sqrt(mean_squared_error(y_true, pred_requested))
    mae_naive = mean_absolute_error(y_true, pred_from_fulfilled_model)
    rmse_naive = np.sqrt(mean_squared_error(y_true, pred_from_fulfilled_model))

    dummy_cols = [c for c in train.columns if c.startswith("item_") and c != "item_id"]
    baseline_lookup = train.groupby(dummy_cols + ["day_of_week"])["requested_qty"].mean()
    test_keys = test.set_index(dummy_cols + ["day_of_week"]).index
    pred_baseline = test_keys.map(baseline_lookup).to_numpy()
    pred_baseline = np.nan_to_num(pred_baseline, nan=train["requested_qty"].mean())
    mae_baseline = mean_absolute_error(y_true, pred_baseline)

    if verbose:
        print("=" * 70)
        print("Forecast accuracy (all evaluated against TRUE requested demand):")
        print(f"  Historical mean baseline (item x day-of-week):  MAE={mae_baseline:.3f}")
        print(f"  Model trained on FULFILLED qty (censored/naive): MAE={mae_naive:.3f}  RMSE={rmse_naive:.3f}")
        print(f"  Model trained on REQUESTED qty (correct):        MAE={mae_correct:.3f}  RMSE={rmse_correct:.3f}")
        print("=" * 70)

    test_eval = test[["item_id", "date", "requested_qty", "fulfilled_qty"]].copy()
    test_eval["pred_correct"] = pred_requested
    test_eval["pred_naive"] = pred_from_fulfilled_model
    test_eval["bias_naive"] = test_eval["pred_naive"] - test_eval["requested_qty"]
    test_eval["bias_correct"] = test_eval["pred_correct"] - test_eval["requested_qty"]

    item_dummy_cols = [c for c in panel.columns if c.startswith("item_") and c != "item_id"]
    item_code_map = panel[item_dummy_cols].idxmax(axis=1)
    panel_item_lookup = panel[["item_id"]].copy()
    panel_item_lookup["item_code"] = item_code_map.str.replace("item_", "", regex=False)
    code_by_id = panel_item_lookup.drop_duplicates("item_id").set_index("item_id")["item_code"]

    stockout_rate = pd.read_sql_query(
        """
        SELECT COALESCE(original_item_id, item_id) AS item_id, 1 - AVG(fulfilled) AS stockout_rate
        FROM order_lines GROUP BY COALESCE(original_item_id, item_id)
        """,
        conn,
    ).set_index("item_id")["stockout_rate"]

    if verbose:
        print("\nMean forecast bias by item (positive = over-predicts, negative = under-predicts), "
              "sorted by historical stockout rate:")
        print(f"{'item':<20}{'stockout_rate':>14}{'naive_bias':>14}{'correct_bias':>14}")

    bias_rows = []
    for item_id in sorted(code_by_id.index, key=lambda i: -stockout_rate.get(i, 0)):
        sub = test_eval[test_eval.item_id == item_id]
        if not len(sub):
            continue
        code = code_by_id[item_id]
        so_rate = stockout_rate.get(item_id, 0)
        naive_bias = sub["bias_naive"].mean()
        correct_bias = sub["bias_correct"].mean()
        if verbose:
            print(f"{code:<20}{so_rate:>13.1%}{naive_bias:>14.3f}{correct_bias:>14.3f}")
        bias_rows.append({
            "item_code": code, "stockout_rate": so_rate,
            "naive_bias": naive_bias, "correct_bias": correct_bias,
        })

    importances = pd.Series(model_requested.feature_importances_, index=feat_cols).sort_values(ascending=False)
    if verbose:
        print("\nTop feature importances (requested-demand model):")
        print(importances.head(10).to_string())

    predictions = test[["item_id", "date", "requested_qty", "fulfilled_qty"]].copy()
    predictions["item_code"] = predictions["item_id"].map(code_by_id)
    predictions["predicted_requested"] = pred_requested
    predictions["predicted_from_fulfilled_model"] = pred_from_fulfilled_model

    metrics = {
        "mae_baseline": mae_baseline,
        "mae_naive_fulfilled_model": mae_naive,
        "rmse_naive_fulfilled_model": rmse_naive,
        "mae_correct_requested_model": mae_correct,
        "rmse_correct_requested_model": rmse_correct,
    }

    return {
        "metrics": metrics,
        "predictions": predictions,
        "bias_by_item": pd.DataFrame(bias_rows),
        "importances": importances,
        "train_range": (train["date"].min(), train["date"].max()),
        "test_range": (test["date"].min(), test["date"].max()),
    }


def main():
    parser = argparse.ArgumentParser(description="Train a demand forecasting model per finished good.")
    parser.add_argument("--db", default="data/coffee_shop.db")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    result = run_forecast(conn, seed=args.seed, verbose=True)
    conn.close()

    results_dir = Path("data/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    result["predictions"].to_csv(results_dir / "demand_forecast_predictions.csv", index=False)
    result["bias_by_item"].to_csv(results_dir / "demand_forecast_bias_by_item.csv", index=False)
    with open(results_dir / "demand_forecast_metrics.json", "w") as f:
        json.dump(result["metrics"], f, indent=2)

    print(f"\nWrote predictions, bias summary, and metrics to {results_dir}/")


if __name__ == "__main__":
    main()
