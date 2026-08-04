"""
Phase 5 -- Interactive dashboard for the coffee shop ERP.

Run with:
    streamlit run src/dashboard.py

Expects data/coffee_shop.db to already exist and be populated via:
    python src/db.py
    python src/simulate_orders.py --days 60 --avg-daily-orders 120 --seed 42
    python src/inventory_engine.py --seed 7
"""

import sqlite3
import time
from pathlib import Path

import pandas as pd
import streamlit as st

DEFAULT_DB_PATH = "data/coffee_shop.db"


# ---------------------------------------------------------------------
# Data loading -- kept separate from UI code so it's easy to test/reuse.
# Each function opens its own short-lived connection (Streamlit's cache
# needs hashable args, so we cache on the db_path string, not a
# connection object).
# ---------------------------------------------------------------------

@st.cache_data
def load_items(db_path):
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query("SELECT * FROM items", conn)


@st.cache_data
def load_margin(db_path):
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM v_item_margin ORDER BY margin_pct DESC", conn
        )


@st.cache_data
def load_cost_breakdown(db_path):
    """Material vs. labor cost per item, for both SFG and FG tiers."""
    with sqlite3.connect(db_path) as conn:
        items = pd.read_sql_query("SELECT * FROM items", conn)
        formulas = pd.read_sql_query("SELECT * FROM formulas", conn)
        routes = pd.read_sql_query("SELECT * FROM routes", conn)
        route_ops = pd.read_sql_query("SELECT * FROM route_operations", conn)
        workstations = pd.read_sql_query("SELECT * FROM workstations", conn)

    labor = route_ops.merge(routes, on="route_id").merge(workstations, on="workstation_id", how="left")
    labor["op_cost"] = (labor["setup_minutes"] + labor["run_minutes"]) / 60 * labor["hourly_rate"].fillna(0)
    labor_by_item = labor.groupby("item_id")["op_cost"].sum().rename("labor_cost")

    comp_cost = items.set_index("item_id")["standard_cost"]
    formulas = formulas.copy()
    formulas["component_cost"] = formulas["component_item_id"].map(comp_cost)
    formulas["line_cost"] = formulas["quantity"] * (1 + formulas["scrap_pct"]) * formulas["component_cost"]
    material_by_item = formulas.groupby("parent_item_id")["line_cost"].sum().rename("material_cost")

    breakdown = (
        items.set_index("item_id")[["item_code", "item_name", "item_type"]]
        .join(material_by_item)
        .join(labor_by_item)
        .fillna(0)
    )
    breakdown = breakdown[breakdown.item_type.isin(["intermediate", "finished_good"])]
    return breakdown.reset_index()


@st.cache_data
def load_inventory(db_path):
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT it.item_code, it.item_name, i.on_hand_qty, i.reorder_point,
                   i.reorder_qty, i.pack_size, i.min_order_qty, i.lead_time_days
            FROM inventory i JOIN items it ON it.item_id = i.item_id
            ORDER BY it.item_code
            """,
            conn,
        )


@st.cache_data
def load_inventory_value(db_path):
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT * FROM v_inventory_value ORDER BY inventory_value DESC", conn
        )


@st.cache_data
def load_orders_daily(db_path):
    with sqlite3.connect(db_path) as conn:
        orders = pd.read_sql_query(
            """
            SELECT o.order_id, o.order_date, o.status, ol.quantity, ol.unit_price, ol.fulfilled
            FROM orders o JOIN order_lines ol ON ol.order_id = o.order_id
            """,
            conn,
        )
    orders["date"] = pd.to_datetime(orders["order_date"]).dt.date
    orders["revenue"] = orders["quantity"] * orders["unit_price"] * orders["fulfilled"]
    daily = orders.groupby("date").agg(
        orders=("order_id", "nunique"),
        lines=("order_id", "size"),
        revenue=("revenue", "sum"),
        fulfilled_lines=("fulfilled", "sum"),
    )
    daily["fulfillment_rate"] = daily["fulfilled_lines"] / daily["lines"]
    return daily


@st.cache_data
def load_fulfillment_summary(db_path):
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                CASE
                    WHEN original_item_id IS NOT NULL THEN 'substituted'
                    WHEN fulfilled = 1 THEN 'fulfilled_direct'
                    ELSE 'stockout_no_sale'
                END AS outcome,
                COUNT(*) AS n
            FROM order_lines
            GROUP BY outcome
            """,
            conn,
        )


@st.cache_data
def load_substitutions(db_path):
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT orig.item_code AS wanted, new.item_code AS got, COUNT(*) AS n
            FROM order_lines ol
            JOIN items orig ON orig.item_id = ol.original_item_id
            JOIN items new ON new.item_id = ol.item_id
            WHERE ol.original_item_id IS NOT NULL
            GROUP BY wanted, got
            ORDER BY n DESC
            """,
            conn,
        )


@st.cache_data
def load_working_capital_series(db_path):
    """
    Reconstructs total raw-material inventory value over time from the
    inventory_transactions log: running on-hand balance per item, per
    day, valued at that item's current standard_cost.

    (An approximation -- standard_cost is the item's cost as of NOW, not
    a historical cost at the time, so this shows "what today's on-hand
    quantities over time would have been worth," not a true historical
    valuation. Fine for a working-capital trend view; would need a cost
    history table to do it properly.)
    """
    with sqlite3.connect(db_path) as conn:
        txns = pd.read_sql_query(
            "SELECT item_id, txn_date, quantity FROM inventory_transactions", conn
        )
        cost_by_item = pd.read_sql_query(
            "SELECT item_id, standard_cost FROM items", conn
        ).set_index("item_id")["standard_cost"]

    txns["date"] = pd.to_datetime(txns["txn_date"]).dt.normalize()
    daily_delta = txns.groupby(["item_id", "date"])["quantity"].sum().unstack("item_id").fillna(0)

    full_range = pd.date_range(daily_delta.index.min(), daily_delta.index.max(), freq="D")
    daily_delta = daily_delta.reindex(full_range).fillna(0)

    running_balance = daily_delta.cumsum()
    values = running_balance.multiply(cost_by_item, axis=1)
    total_value = values.sum(axis=1).rename("inventory_value")
    return total_value


# ---------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Coffee Shop ERP Dashboard", layout="wide")

    st.sidebar.header("Database")
    db_path = st.sidebar.text_input("Path to coffee_shop.db", value=DEFAULT_DB_PATH)

    if not Path(db_path).exists():
        st.error(
            f"No database found at `{db_path}`. Run `python src/db.py`, "
            "`python src/simulate_orders.py`, and `python src/inventory_engine.py` first."
        )
        return

    if st.sidebar.button("Clear cache / reload data"):
        st.cache_data.clear()

    st.sidebar.divider()
    auto_refresh = st.sidebar.checkbox(
        "Auto-refresh (for use with live_sim.py)", value=False
    )
    refresh_seconds = st.sidebar.number_input(
        "Refresh every (seconds)", min_value=1, max_value=60, value=5, disabled=not auto_refresh
    )

    st.title("☕ Coffee Shop ERP Dashboard")

    # ---- KPI row ----
    orders_daily = load_orders_daily(db_path)
    inv_value_df = load_inventory_value(db_path)
    fulfillment = load_fulfillment_summary(db_path)

    total_revenue = orders_daily["revenue"].sum()
    total_inventory_value = inv_value_df["inventory_value"].sum()

    fulfilled_n = fulfillment.loc[fulfillment.outcome != "stockout_no_sale", "n"].sum()
    total_lines = fulfillment["n"].sum()
    fulfillment_rate = fulfilled_n / total_lines if total_lines else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Revenue", f"${total_revenue:,.0f}")
    col2.metric("Current Inventory Value", f"${total_inventory_value:,.0f}")
    col3.metric("Order Fulfillment Rate", f"{fulfillment_rate:.1%}")
    col4.metric("Days of Order History", f"{len(orders_daily)}")

    st.divider()

    tab_inventory, tab_costing, tab_orders, tab_working_capital = st.tabs(
        ["📦 Inventory", "💰 Costing & Margin", "🧾 Orders & Fulfillment", "📈 Working Capital"]
    )

    # ---- Inventory tab ----
    with tab_inventory:
        st.subheader("On-Hand Inventory vs. Reorder Point")
        inv = load_inventory(db_path)
        inv["status"] = inv.apply(
            lambda r: "🔴 At/below reorder point" if r.on_hand_qty <= r.reorder_point else "🟢 OK",
            axis=1,
        )

        chart_df = inv.set_index("item_code")[["on_hand_qty", "reorder_point"]]
        st.bar_chart(chart_df)

        st.dataframe(
            inv[["item_code", "item_name", "on_hand_qty", "reorder_point", "reorder_qty",
                 "pack_size", "min_order_qty", "lead_time_days", "status"]],
            use_container_width=True,
            hide_index=True,
        )

        low_stock = inv[inv.on_hand_qty <= inv.reorder_point]
        if len(low_stock):
            st.warning(f"{len(low_stock)} item(s) at or below reorder point: "
                       f"{', '.join(low_stock.item_code)}")
        else:
            st.success("All raw materials are above their reorder point.")

    # ---- Costing & Margin tab ----
    with tab_costing:
        st.subheader("Gross Margin by Finished Good")
        margin = load_margin(db_path)
        st.bar_chart(margin.set_index("item_name")["margin_pct"])
        st.dataframe(margin, use_container_width=True, hide_index=True)

        st.subheader("Cost Breakdown: Material vs. Labor")
        tier = st.radio("Tier", ["finished_good", "intermediate"], horizontal=True,
                         format_func=lambda t: "Finished Goods" if t == "finished_good" else "SFG / Intermediates")
        breakdown = load_cost_breakdown(db_path)
        tier_breakdown = breakdown[breakdown.item_type == tier].set_index("item_code")
        st.bar_chart(tier_breakdown[["material_cost", "labor_cost"]])
        st.dataframe(tier_breakdown.reset_index(), use_container_width=True, hide_index=True)

    # ---- Orders & Fulfillment tab ----
    with tab_orders:
        st.subheader("Daily Order Volume & Revenue")
        c1, c2 = st.columns(2)
        c1.line_chart(orders_daily["orders"])
        c2.line_chart(orders_daily["revenue"])

        st.subheader("Last 30 Days: Rolling Averages")
        st.caption(
            "Smooths out day-to-day noise (weekday/weekend swings, random variation) "
            "to show the underlying trend."
        )
        last_30 = orders_daily.tail(30).copy()
        rolling = orders_daily[["revenue", "orders", "fulfillment_rate"]].rolling(30, min_periods=1).mean()
        rolling = rolling.tail(30)
        rolling.columns = ["30d_avg_revenue", "30d_avg_orders", "30d_avg_fulfillment_rate"]

        c3, c4 = st.columns(2)
        c3.line_chart(pd.DataFrame({
            "daily": last_30["revenue"],
            "30-day avg": rolling["30d_avg_revenue"],
        }))
        c3.caption("Revenue: daily vs. 30-day rolling average")
        c4.line_chart(pd.DataFrame({
            "daily": last_30["orders"],
            "30-day avg": rolling["30d_avg_orders"],
        }))
        c4.caption("Orders: daily vs. 30-day rolling average")

        st.line_chart(pd.DataFrame({
            "daily": last_30["fulfillment_rate"],
            "30-day avg": rolling["30d_avg_fulfillment_rate"],
        }))
        st.caption("Fulfillment rate: daily vs. 30-day rolling average")

        m1, m2, m3 = st.columns(3)
        m1.metric("30-Day Avg Daily Revenue", f"${rolling['30d_avg_revenue'].iloc[-1]:,.0f}")
        m2.metric("30-Day Avg Daily Orders", f"{rolling['30d_avg_orders'].iloc[-1]:,.0f}")
        m3.metric("30-Day Avg Fulfillment Rate", f"{rolling['30d_avg_fulfillment_rate'].iloc[-1]:.1%}")

        st.subheader("Fulfillment Outcomes")
        st.bar_chart(fulfillment.set_index("outcome")["n"])

        st.subheader("Substitutions: What Customers Wanted vs. What They Got")
        subs = load_substitutions(db_path)
        if len(subs):
            st.dataframe(subs, use_container_width=True, hide_index=True)
        else:
            st.info("No substitutions occurred in this simulation run.")

    # ---- Working Capital tab ----
    with tab_working_capital:
        st.subheader("Raw Material Inventory Value Over Time")
        st.caption(
            "Reconstructed from the inventory transaction log, valued at each item's "
            "CURRENT standard cost (an approximation, not true historical costing)."
        )
        wc_series = load_working_capital_series(db_path)
        wc_last_30 = wc_series.tail(30)
        wc_rolling_30 = wc_series.rolling(30, min_periods=1).mean().tail(30)
        st.line_chart(pd.DataFrame({
            "daily": wc_last_30,
            "30-day avg": wc_rolling_30,
        }))

        st.metric("Latest Inventory Value", f"${wc_series.iloc[-1]:,.0f}")
        st.metric("30-Day Avg Inventory Value", f"${wc_rolling_30.iloc[-1]:,.0f}")
        st.metric("Peak Inventory Value", f"${wc_series.max():,.0f}")
        st.metric("All-Time Average Inventory Value", f"${wc_series.mean():,.0f}")

    if auto_refresh:
        time.sleep(refresh_seconds)
        st.cache_data.clear()
        st.rerun()


if __name__ == "__main__":
    main()
