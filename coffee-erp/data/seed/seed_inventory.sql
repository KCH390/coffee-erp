-- ============================================================
-- Seed Data: Inventory (raw materials only -- intermediates and
-- finished goods are built to order, not stocked)
--
-- Reorder points/quantities derived from a full BOM explosion of
-- REAL average daily FG volume (measured from a 60-day run of
-- simulate_orders.py --seed 42), NOT a flat per-SKU guess. The
-- earlier version assumed 15 units/day/SKU uniformly; actual
-- volume (which includes occasional large wholesale orders)
-- runs 2-3x higher and unevenly across SKUs, which under-sized
-- the original reorder points enough to cause sustained
-- stockouts once run through the inventory engine (Phase 3).
--
-- reorder_point = daily_usage * (lead_time_days + safety_days)
-- reorder_qty   = daily_usage * (lead_time_days + safety_days + 5-day
--                 review buffer), rounded up to whole packs and the
--                 item's minimum order -- sized so a SINGLE order
--                 reliably survives the full lead time even with
--                 day-to-day demand variance (reorder_qty > reorder_point
--                 always holds now, unlike the earlier version)
-- on_hand_qty   = seeded at reorder_qty (freshly stocked)
--
-- NOTE: if you change ITEM_POPULARITY, avg_daily_orders, or the
-- wholesale mix in simulate_orders.py, these numbers go stale --
-- rerun the calibration (recompute daily usage from actual order
-- history, same as this file was generated) rather than hand-editing.
-- ============================================================

INSERT INTO inventory (item_id, on_hand_qty, reorder_point, reorder_qty, lead_time_days, pack_size, min_order_qty)
SELECT items.item_id, v.on_hand_qty, v.reorder_point, v.reorder_qty, v.lead_time_days, v.pack_size, v.min_order_qty
FROM items JOIN (
    SELECT 'CREAM-HH' AS item_code, 608 AS on_hand_qty, 262.61 AS reorder_point, 608 AS reorder_qty, 2 AS lead_time_days, 32 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'CREAM-WM' AS item_code, 7680 AS on_hand_qty, 3374.68 AS reorder_point, 7680 AS reorder_qty, 2 AS lead_time_days, 128 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'BASE-ESPRESSO' AS item_code, 5248 AS on_hand_qty, 3428.64 AS reorder_point, 5248 AS reorder_qty, 7 AS lead_time_days, 128 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'BASE-BREWED' AS item_code, 6016 AS on_hand_qty, 3939.19 AS reorder_point, 6016 AS reorder_qty, 7 AS lead_time_days, 128 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'BASE-COLDBREW' AS item_code, 3584 AS on_hand_qty, 2338.09 AS reorder_point, 3584 AS reorder_qty, 7 AS lead_time_days, 128 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'SYRUP-HAZELNUT' AS item_code, 254.0 AS on_hand_qty, 142.51 AS reorder_point, 254.0 AS reorder_qty, 5 AS lead_time_days, 25.4 AS pack_size, 4 AS min_order_qty
    UNION ALL SELECT 'SYRUP-MOCHA' AS item_code, 660.4 AS on_hand_qty, 395.4 AS reorder_point, 660.4 AS reorder_qty, 5 AS lead_time_days, 25.4 AS pack_size, 4 AS min_order_qty
    UNION ALL SELECT 'SYRUP-CARAMEL' AS item_code, 254.0 AS on_hand_qty, 155.55 AS reorder_point, 254.0 AS reorder_qty, 5 AS lead_time_days, 25.4 AS pack_size, 4 AS min_order_qty
    UNION ALL SELECT 'RM-ICE' AS item_code, 3520 AS on_hand_qty, 1001.0 AS reorder_point, 3520 AS reorder_qty, 1 AS lead_time_days, 320 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-SUGAR' AS item_code, 12000 AS on_hand_qty, 7011.68 AS reorder_point, 12000 AS reorder_qty, 5 AS lead_time_days, 2000 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-WHIPCREAM' AS item_code, 380 AS on_hand_qty, 162.57 AS reorder_point, 380 AS reorder_qty, 2 AS lead_time_days, 20 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-CINNAMON' AS item_code, 400 AS on_hand_qty, 178.14 AS reorder_point, 400 AS reorder_qty, 7 AS lead_time_days, 200 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-COCOA' AS item_code, 1500 AS on_hand_qty, 988.49 AS reorder_point, 1500 AS reorder_qty, 7 AS lead_time_days, 500 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-NUTMEG' AS item_code, 400 AS on_hand_qty, 178.14 AS reorder_point, 400 AS reorder_qty, 7 AS lead_time_days, 200 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-CARAMELDRIZZLE' AS item_code, 140 AS on_hand_qty, 77.78 AS reorder_point, 140 AS reorder_qty, 5 AS lead_time_days, 20 AS pack_size, 1 AS min_order_qty
) v ON items.item_code = v.item_code;

-- Opening balance transactions, one per raw material, for audit trail.
-- Dated well in the past (not the default datetime('now')) so it
-- chronologically precedes any simulated order history -- simulate_orders.py
-- generates dates going back up to --days days from "now" at the time IT
-- runs, which is always after this seed runs, so anchoring 400 days back
-- keeps this ahead of any reasonable --days value.
INSERT INTO inventory_transactions (item_id, txn_type, quantity, unit_cost, txn_date, reference)
SELECT i.item_id, 'receipt', i.on_hand_qty, it.standard_cost, datetime('now', '-400 days'), 'Opening Balance'
FROM inventory i JOIN items it ON it.item_id = i.item_id;