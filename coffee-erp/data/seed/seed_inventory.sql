-- ============================================================
-- Seed Data: Inventory (raw materials only)
--
-- CALIBRATED for a 97% target fulfillment rate
-- (Phase 6 working capital optimization). reorder_point uses a
-- statistical safety-stock formula:
--     reorder_point = mean_daily_demand * lead_time
--                     + z * std_daily_demand * sqrt(lead_time), z=0.562
-- mean/std daily demand measured from actual REQUESTED demand
-- history (not assumed). z was found by re-running the real
-- inventory_engine against actual order history at different z
-- values until simulated fulfillment matched the target -- see
-- src/optimize_inventory.py and data/optimization_trials.csv.
--
-- Result: avg inventory value $3,362.76 -> $3,362.76 (0.0% reduction) at 96.9% fulfillment.
-- ============================================================

INSERT INTO inventory (item_id, on_hand_qty, reorder_point, reorder_qty, lead_time_days, pack_size, min_order_qty)
SELECT items.item_id, v.on_hand_qty, v.reorder_point, v.reorder_qty, v.lead_time_days, v.pack_size, v.min_order_qty
FROM items JOIN (
    SELECT 'CREAM-HH' AS item_code, 480.0 AS on_hand_qty, 152.07 AS reorder_point, 480.0 AS reorder_qty, 2.0 AS lead_time_days, 32.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'CREAM-WM' AS item_code, 6016.0 AS on_hand_qty, 1906.38 AS reorder_point, 6016.0 AS reorder_qty, 2.0 AS lead_time_days, 128.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'BASE-ESPRESSO' AS item_code, 4224.0 AS on_hand_qty, 2624.19 AS reorder_point, 4224.0 AS reorder_qty, 7.0 AS lead_time_days, 128.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'BASE-BREWED' AS item_code, 4736.0 AS on_hand_qty, 2985.82 AS reorder_point, 4736.0 AS reorder_qty, 7.0 AS lead_time_days, 128.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'BASE-COLDBREW' AS item_code, 2432.0 AS on_hand_qty, 1479.39 AS reorder_point, 2432.0 AS reorder_qty, 7.0 AS lead_time_days, 128.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'SYRUP-HAZELNUT' AS item_code, 177.8 AS on_hand_qty, 98.17 AS reorder_point, 177.8 AS reorder_qty, 5.0 AS lead_time_days, 25.4 AS pack_size, 4.0 AS min_order_qty
    UNION ALL SELECT 'SYRUP-MOCHA' AS item_code, 482.6 AS on_hand_qty, 264.13 AS reorder_point, 482.6 AS reorder_qty, 5.0 AS lead_time_days, 25.4 AS pack_size, 4.0 AS min_order_qty
    UNION ALL SELECT 'SYRUP-CARAMEL' AS item_code, 254.0 AS on_hand_qty, 143.65 AS reorder_point, 254.0 AS reorder_qty, 5.0 AS lead_time_days, 25.4 AS pack_size, 4.0 AS min_order_qty
    UNION ALL SELECT 'RM-ICE' AS item_code, 3200.0 AS on_hand_qty, 626.78 AS reorder_point, 3200.0 AS reorder_qty, 1.0 AS lead_time_days, 320.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-SUGAR' AS item_code, 10000.0 AS on_hand_qty, 4737.27 AS reorder_point, 10000.0 AS reorder_qty, 5.0 AS lead_time_days, 2000.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-WHIPCREAM' AS item_code, 320.0 AS on_hand_qty, 109.13 AS reorder_point, 320.0 AS reorder_qty, 2.0 AS lead_time_days, 20.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-CINNAMON' AS item_code, 400.0 AS on_hand_qty, 134.89 AS reorder_point, 400.0 AS reorder_qty, 7.0 AS lead_time_days, 200.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-COCOA' AS item_code, 1500.0 AS on_hand_qty, 728.56 AS reorder_point, 1500.0 AS reorder_qty, 7.0 AS lead_time_days, 500.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-NUTMEG' AS item_code, 400.0 AS on_hand_qty, 134.89 AS reorder_point, 400.0 AS reorder_qty, 7.0 AS lead_time_days, 200.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-CARAMELDRIZZLE' AS item_code, 140.0 AS on_hand_qty, 71.82 AS reorder_point, 140.0 AS reorder_qty, 5.0 AS lead_time_days, 20.0 AS pack_size, 1.0 AS min_order_qty
) v ON items.item_code = v.item_code;

-- Opening balance transactions, one per raw material, for audit trail
INSERT INTO inventory_transactions (item_id, txn_type, quantity, unit_cost, txn_date, reference)
SELECT i.item_id, 'receipt', i.on_hand_qty, it.standard_cost, datetime('now', '-400 days'), 'Opening Balance'
FROM inventory i JOIN items it ON it.item_id = i.item_id;