-- ============================================================
-- Seed Data: Inventory (raw materials only)
--
-- CALIBRATED for a 95% target fulfillment rate
-- (Phase 6 working capital optimization). reorder_point uses a
-- statistical safety-stock formula:
--     reorder_point = mean_daily_demand * lead_time
--                     + z * std_daily_demand * sqrt(lead_time), z=0.688
-- mean/std daily demand measured from actual simulated consumption
-- history (not assumed). z was found by re-running the real
-- inventory_engine against actual order history at different z
-- values until simulated fulfillment matched the target -- see
-- src/optimize_inventory.py and data/optimization_trials.csv.
--
-- Result: avg inventory value $2,941.10 -> $3,235.19 (-10.0% reduction) at 94.9% fulfillment.
-- ============================================================

INSERT INTO inventory (item_id, on_hand_qty, reorder_point, reorder_qty, lead_time_days, pack_size, min_order_qty)
SELECT items.item_id, v.on_hand_qty, v.reorder_point, v.reorder_qty, v.lead_time_days, v.pack_size, v.min_order_qty
FROM items JOIN (
    SELECT 'CREAM-HH' AS item_code, 544.0 AS on_hand_qty, 188.42 AS reorder_point, 544.0 AS reorder_qty, 2.0 AS lead_time_days, 32.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'CREAM-WM' AS item_code, 6272.0 AS on_hand_qty, 2075.44 AS reorder_point, 6272.0 AS reorder_qty, 2.0 AS lead_time_days, 128.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'BASE-ESPRESSO' AS item_code, 4608.0 AS on_hand_qty, 2846.28 AS reorder_point, 4608.0 AS reorder_qty, 7.0 AS lead_time_days, 128.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'BASE-BREWED' AS item_code, 5504.0 AS on_hand_qty, 3591.15 AS reorder_point, 5504.0 AS reorder_qty, 7.0 AS lead_time_days, 128.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'BASE-COLDBREW' AS item_code, 2944.0 AS on_hand_qty, 1901.55 AS reorder_point, 2944.0 AS reorder_qty, 7.0 AS lead_time_days, 128.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'SYRUP-HAZELNUT' AS item_code, 203.2 AS on_hand_qty, 104.81 AS reorder_point, 203.2 AS reorder_qty, 5.0 AS lead_time_days, 25.4 AS pack_size, 4.0 AS min_order_qty
    UNION ALL SELECT 'SYRUP-MOCHA' AS item_code, 457.2 AS on_hand_qty, 260.42 AS reorder_point, 457.2 AS reorder_qty, 5.0 AS lead_time_days, 25.4 AS pack_size, 4.0 AS min_order_qty
    UNION ALL SELECT 'SYRUP-CARAMEL' AS item_code, 228.6 AS on_hand_qty, 133.45 AS reorder_point, 228.6 AS reorder_qty, 5.0 AS lead_time_days, 25.4 AS pack_size, 4.0 AS min_order_qty
    UNION ALL SELECT 'RM-ICE' AS item_code, 3200.0 AS on_hand_qty, 642.43 AS reorder_point, 3200.0 AS reorder_qty, 1.0 AS lead_time_days, 320.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-SUGAR' AS item_code, 10000.0 AS on_hand_qty, 5192.54 AS reorder_point, 10000.0 AS reorder_qty, 5.0 AS lead_time_days, 2000.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-WHIPCREAM' AS item_code, 300.0 AS on_hand_qty, 102.3 AS reorder_point, 300.0 AS reorder_qty, 2.0 AS lead_time_days, 20.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-CINNAMON' AS item_code, 400.0 AS on_hand_qty, 143.33 AS reorder_point, 400.0 AS reorder_qty, 7.0 AS lead_time_days, 200.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-COCOA' AS item_code, 1500.0 AS on_hand_qty, 714.62 AS reorder_point, 1500.0 AS reorder_qty, 7.0 AS lead_time_days, 500.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-NUTMEG' AS item_code, 400.0 AS on_hand_qty, 143.33 AS reorder_point, 400.0 AS reorder_qty, 7.0 AS lead_time_days, 200.0 AS pack_size, 1.0 AS min_order_qty
    UNION ALL SELECT 'RM-CARAMELDRIZZLE' AS item_code, 120.0 AS on_hand_qty, 66.72 AS reorder_point, 120.0 AS reorder_qty, 5.0 AS lead_time_days, 20.0 AS pack_size, 1.0 AS min_order_qty
) v ON items.item_code = v.item_code;

-- Opening balance transactions, one per raw material, for audit trail
INSERT INTO inventory_transactions (item_id, txn_type, quantity, unit_cost, txn_date, reference)
SELECT i.item_id, 'receipt', i.on_hand_qty, it.standard_cost, datetime('now', '-400 days'), 'Opening Balance'
FROM inventory i JOIN items it ON it.item_id = i.item_id;