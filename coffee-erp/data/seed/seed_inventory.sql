-- ============================================================
-- Seed Data: Inventory (raw materials only -- intermediates and
-- finished goods are built to order, not stocked)
--
-- Reorder points/quantities derived from a full BOM explosion
-- (RM required per unit of each FG) assuming 15 units/day sold
-- per FG SKU (120 drinks/day total) -- a placeholder until the
-- order simulator (Phase 2) provides real historical volume.
--
-- reorder_point   = daily_usage * (lead_time_days + safety_days)
-- reorder_qty     = ~7 days of usage, rounded up to whole packs,
--                   respecting each item's minimum order (in packs)
-- on_hand_qty     = seeded at reorder_qty (freshly stocked)
-- ============================================================

INSERT INTO inventory (item_id, on_hand_qty, reorder_point, reorder_qty, lead_time_days, pack_size, min_order_qty)
SELECT items.item_id, v.on_hand_qty, v.reorder_point, v.reorder_qty, v.lead_time_days, v.pack_size, v.min_order_qty
FROM items JOIN (
    SELECT 'CREAM-HH' AS item_code, 224 AS on_hand_qty, 121.2 AS reorder_point, 224 AS reorder_qty, 2 AS lead_time_days, 32 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'CREAM-WM' AS item_code, 3072 AS on_hand_qty, 1718.4 AS reorder_point, 3072 AS reorder_qty, 2 AS lead_time_days, 128 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'BASE-ESPRESSO' AS item_code, 1408 AS on_hand_qty, 1842.0 AS reorder_point, 1408 AS reorder_qty, 7 AS lead_time_days, 128 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'BASE-BREWED' AS item_code, 1280 AS on_hand_qty, 1818.0 AS reorder_point, 1280 AS reorder_qty, 7 AS lead_time_days, 128 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'BASE-COLDBREW' AS item_code, 896 AS on_hand_qty, 1224.0 AS reorder_point, 896 AS reorder_qty, 7 AS lead_time_days, 128 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'SYRUP-HAZELNUT' AS item_code, 127.0 AS on_hand_qty, 120.0 AS reorder_point, 127.0 AS reorder_qty, 5 AS lead_time_days, 25.4 AS pack_size, 4 AS min_order_qty
    UNION ALL SELECT 'SYRUP-MOCHA' AS item_code, 228.6 AS on_hand_qty, 240.0 AS reorder_point, 228.6 AS reorder_qty, 5 AS lead_time_days, 25.4 AS pack_size, 4 AS min_order_qty
    UNION ALL SELECT 'SYRUP-CARAMEL' AS item_code, 127.0 AS on_hand_qty, 120.0 AS reorder_point, 127.0 AS reorder_qty, 5 AS lead_time_days, 25.4 AS pack_size, 4 AS min_order_qty
    UNION ALL SELECT 'RM-ICE' AS item_code, 2560 AS on_hand_qty, 678.0 AS reorder_point, 2560 AS reorder_qty, 1 AS lead_time_days, 320 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-SUGAR' AS item_code, 4000 AS on_hand_qty, 3427.2 AS reorder_point, 4000 AS reorder_qty, 5 AS lead_time_days, 2000 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-WHIPCREAM' AS item_code, 220 AS on_hand_qty, 123.6 AS reorder_point, 220 AS reorder_qty, 2 AS lead_time_days, 20 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-CINNAMON' AS item_code, 200 AS on_hand_qty, 150.0 AS reorder_point, 200 AS reorder_qty, 7 AS lead_time_days, 200 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-COCOA' AS item_code, 500 AS on_hand_qty, 600.0 AS reorder_point, 500 AS reorder_qty, 7 AS lead_time_days, 500 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-NUTMEG' AS item_code, 200 AS on_hand_qty, 150.0 AS reorder_point, 200 AS reorder_qty, 7 AS lead_time_days, 200 AS pack_size, 1 AS min_order_qty
    UNION ALL SELECT 'RM-CARAMELDRIZZLE' AS item_code, 60 AS on_hand_qty, 60.0 AS reorder_point, 60 AS reorder_qty, 5 AS lead_time_days, 20 AS pack_size, 1 AS min_order_qty
) v ON items.item_code = v.item_code;

-- Opening balance transactions, one per raw material, for audit trail
INSERT INTO inventory_transactions (item_id, txn_type, quantity, unit_cost, reference)
SELECT i.item_id, 'receipt', i.on_hand_qty, it.standard_cost, 'Opening Balance'
FROM inventory i JOIN items it ON it.item_id = i.item_id;