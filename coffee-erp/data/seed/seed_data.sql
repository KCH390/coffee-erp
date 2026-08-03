-- ============================================================
-- Seed Data: Items, Formulas (RM -> SFG -> FG), Routes, Route Operations
-- Quantities are placeholders (oz/ea) -- replace with real recipe amounts.
-- Route timing: source "hours" values converted to minutes (hours * 60),
-- placed in run_minutes; setup_minutes left at 0 for now.
-- ============================================================

-- ---------- RAW MATERIALS ----------
INSERT INTO items (item_code, item_name, item_type, uom, standard_cost, sale_price) VALUES
('CREAM-HH',        'Half & Half',        'raw_material', 'oz', 0.15, NULL),
('CREAM-WM',         'Whole Milk',         'raw_material', 'oz', 0.06, NULL),
('BASE-ESPRESSO',    'Espresso (base)',    'raw_material', 'oz', 0.40, NULL),
('BASE-BREWED',      'Brewed Coffee (base)','raw_material','oz', 0.10, NULL),
('BASE-COLDBREW',    'Cold Brew (base)',   'raw_material', 'oz', 0.20, NULL),
('SYRUP-HAZELNUT',   'Hazelnut Syrup',     'raw_material', 'oz', 0.25, NULL),
('SYRUP-MOCHA',      'Mocha Syrup',        'raw_material', 'oz', 0.25, NULL),
('SYRUP-CARAMEL',    'Caramel Syrup',      'raw_material', 'oz', 0.25, NULL),
('RM-ICE',           'Ice',                'raw_material', 'oz', 0.01, NULL),
('RM-SUGAR',         'Sugar',              'raw_material', 'g',  0.01, NULL),
('RM-WHIPCREAM',     'Whipped Cream',      'raw_material', 'oz', 0.20, NULL),
('RM-CINNAMON',      'Cinnamon',           'raw_material', 'g',  0.02, NULL),
('RM-COCOA',         'Cocoa Powder',       'raw_material', 'g',  0.03, NULL),
('RM-NUTMEG',        'Nutmeg',             'raw_material', 'g',  0.03, NULL),
('RM-CARAMELDRIZZLE','Caramel Drizzle',    'raw_material', 'oz', 0.20, NULL);

-- ---------- SEMI-FINISHED GOODS (SFG) ----------
INSERT INTO items (item_code, item_name, item_type, uom, standard_cost, sale_price) VALUES
('SFG-LATTE',      'Latte Base',      'intermediate', 'ea', 0, NULL),
('SFG-STANDARD',   'Standard Base',   'intermediate', 'ea', 0, NULL),
('SFG-AMERICANO',  'Americano Base',  'intermediate', 'ea', 0, NULL),
('SFG-FRAPPE',     'Frappe Base',     'intermediate', 'ea', 0, NULL),
('SFG-COLDBREW',   'Cold Brew Base',  'intermediate', 'ea', 0, NULL);

-- ---------- FINISHED GOODS (FG) ----------
INSERT INTO items (item_code, item_name, item_type, uom, standard_cost, sale_price) VALUES
('FG-LATTE-STD',     'Latte Standard',   'finished_good', 'ea', 0, 4.50),
('FG-LATTE-SPICED',  'Spiced Latte',     'finished_good', 'ea', 0, 5.25),
('FG-LATTE-MOCHA',   'Mocha Latte',      'finished_good', 'ea', 0, 5.25),
('FG-BREWED',        'Brewed Coffee',    'finished_good', 'ea', 0, 3.00),
('FG-AMERICANO',     'Americano',        'finished_good', 'ea', 0, 3.75),
('FG-FRAPPE-CARAMEL','Caramel Frappe',   'finished_good', 'ea', 0, 5.75),
('FG-FRAPPE-MOCHA',  'Mocha Frappe',     'finished_good', 'ea', 0, 5.75),
('FG-COLDBREW',      'Cold Brew',        'finished_good', 'ea', 0, 4.25);


-- ---------- WORKSTATIONS ----------
INSERT INTO workstations (workstation_name, hourly_rate, description) VALUES
('Barista', 15.00, 'General barista labor -- brewing, steaming, assembly, add-ons');

-- ============================================================
-- FORMULAS (BOM) -- Tier 1: RM -> SFG
-- ============================================================

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='SFG-LATTE'), items.item_id, v.qty, 0.02
FROM items JOIN (
    SELECT 'BASE-ESPRESSO' AS item_code, 2.0 AS qty
    UNION ALL SELECT 'CREAM-WM', 6.0
    UNION ALL SELECT 'RM-SUGAR', 4.0
) v ON items.item_code = v.item_code;

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='SFG-STANDARD'), items.item_id, v.qty, 0.01
FROM items JOIN (
    SELECT 'BASE-BREWED' AS item_code, 12.0 AS qty
    UNION ALL SELECT 'CREAM-HH', 2.0
    UNION ALL SELECT 'RM-SUGAR', 4.0
) v ON items.item_code = v.item_code;

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='SFG-AMERICANO'), item_id, 2.0, 0.02
FROM items WHERE item_code = 'BASE-ESPRESSO';

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='SFG-FRAPPE'), items.item_id, v.qty, 0.03
FROM items JOIN (
    SELECT 'BASE-ESPRESSO' AS item_code, 2.0 AS qty
    UNION ALL SELECT 'RM-ICE', 8.0
    UNION ALL SELECT 'CREAM-WM', 4.0
    UNION ALL SELECT 'RM-SUGAR', 4.0
    UNION ALL SELECT 'RM-WHIPCREAM', 1.0
) v ON items.item_code = v.item_code;

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='SFG-COLDBREW'), items.item_id, v.qty, 0.02
FROM items JOIN (
    SELECT 'BASE-COLDBREW' AS item_code, 8.0 AS qty
    UNION ALL SELECT 'RM-ICE', 6.0
    UNION ALL SELECT 'CREAM-WM', 2.0
    UNION ALL SELECT 'RM-SUGAR', 2.0
) v ON items.item_code = v.item_code;

-- ============================================================
-- FORMULAS (BOM) -- Tier 2: SFG (+ RM add-ons) -> FG
-- ============================================================

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-LATTE-STD'), items.item_id, v.qty, 0.0
FROM items JOIN (
    SELECT 'SFG-LATTE' AS item_code, 1.0 AS qty
    UNION ALL SELECT 'RM-SUGAR', 2.0
) v ON items.item_code = v.item_code;

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-LATTE-SPICED'), items.item_id, v.qty, 0.0
FROM items JOIN (
    SELECT 'SFG-LATTE' AS item_code, 1.0 AS qty
    UNION ALL SELECT 'RM-NUTMEG', 1.0
    UNION ALL SELECT 'RM-CINNAMON', 1.0
    UNION ALL SELECT 'SYRUP-HAZELNUT', 1.0
) v ON items.item_code = v.item_code;

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-LATTE-MOCHA'), items.item_id, v.qty, 0.0
FROM items JOIN (
    SELECT 'SFG-LATTE' AS item_code, 1.0 AS qty
    UNION ALL SELECT 'SYRUP-MOCHA', 1.0
    UNION ALL SELECT 'RM-COCOA', 2.0
) v ON items.item_code = v.item_code;

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-BREWED'), item_id, 1.0, 0.0
FROM items WHERE item_code = 'SFG-STANDARD';

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-AMERICANO'), item_id, 1.0, 0.0
FROM items WHERE item_code = 'SFG-AMERICANO';

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-FRAPPE-CARAMEL'), items.item_id, v.qty, 0.0
FROM items JOIN (
    SELECT 'SFG-FRAPPE' AS item_code, 1.0 AS qty
    UNION ALL SELECT 'SYRUP-CARAMEL', 1.0
    UNION ALL SELECT 'RM-CARAMELDRIZZLE', 0.5
) v ON items.item_code = v.item_code;

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-FRAPPE-MOCHA'), items.item_id, v.qty, 0.0
FROM items JOIN (
    SELECT 'SFG-FRAPPE' AS item_code, 1.0 AS qty
    UNION ALL SELECT 'RM-COCOA', 2.0
    UNION ALL SELECT 'SYRUP-MOCHA', 1.0
) v ON items.item_code = v.item_code;

INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-COLDBREW'), item_id, 1.0, 0.0
FROM items WHERE item_code = 'SFG-COLDBREW';

-- ============================================================
-- ROUTES -- one route header per item that has production steps
-- (all intermediates + all finished goods, so future manual route
-- edits have a place to attach even if a given item has 0 ops today)
-- ============================================================

INSERT INTO routes (item_id, route_name, description)
SELECT item_id, item_code || ' Route', NULL
FROM items
WHERE item_type IN ('intermediate', 'finished_good');

-- ============================================================
-- ROUTE OPERATIONS -- SFG production steps (explicit, as provided)
-- Source "hours" converted to minutes: run_minutes = hours * 60
-- ============================================================

INSERT INTO route_operations (route_id, operation_seq, operation_name, workstation_id, setup_minutes, run_minutes)
SELECT rt.route_id, v.operation_seq, v.operation_name,
       (SELECT workstation_id FROM workstations WHERE workstation_name='Barista'),
       0, ROUND(v.hours * 60, 2)
FROM routes rt
JOIN items it ON it.item_id = rt.item_id
JOIN (
    SELECT 'SFG-LATTE' AS item_code, 1 AS operation_seq, 'Brew Espresso' AS operation_name, 0.033333 AS hours
    UNION ALL SELECT 'SFG-LATTE', 2, 'Steam Milk', 0.033333

    UNION ALL SELECT 'SFG-STANDARD', 1, 'Brew Coffee', 0.008333333
    UNION ALL SELECT 'SFG-STANDARD', 2, 'Add Milk', 0.008333333
    UNION ALL SELECT 'SFG-STANDARD', 3, 'Add Sugar', 0.008333333

    UNION ALL SELECT 'SFG-AMERICANO', 1, 'Brew Espresso', 0.033333
    UNION ALL SELECT 'SFG-AMERICANO', 2, 'Add Water', 0.033333

    UNION ALL SELECT 'SFG-FRAPPE', 1, 'Brew Espresso', 0.0333333
    UNION ALL SELECT 'SFG-FRAPPE', 2, 'Add Sugar', 0.008333333
    UNION ALL SELECT 'SFG-FRAPPE', 3, 'Add Milk', 0.008333333
    UNION ALL SELECT 'SFG-FRAPPE', 4, 'Add Ice', 0.008333333
    UNION ALL SELECT 'SFG-FRAPPE', 5, 'Grind', 0.0333333

    UNION ALL SELECT 'SFG-COLDBREW', 1, 'Brew Coffee', 0.008333333
    UNION ALL SELECT 'SFG-COLDBREW', 2, 'Add Milk', 0.008333333
    UNION ALL SELECT 'SFG-COLDBREW', 3, 'Add Sugar', 0.008333333
    UNION ALL SELECT 'SFG-COLDBREW', 4, 'Add Ice', 0.008333333
) v ON it.item_code = v.item_code;

-- ============================================================
-- ROUTE OPERATIONS -- FG-level "add raw material" steps, generated
-- automatically: for every raw material directly in a finished good's
-- formula, add an operation at 0.01 hr (0.6 min). Sequence continues
-- after any existing operations on that item's route.
-- ============================================================

INSERT INTO route_operations (route_id, operation_seq, operation_name, workstation_id, setup_minutes, run_minutes)
SELECT
    rt.route_id,
    ROW_NUMBER() OVER (PARTITION BY rt.route_id ORDER BY ci.item_code)
        + COALESCE((SELECT MAX(ro.operation_seq) FROM route_operations ro WHERE ro.route_id = rt.route_id), 0),
    'Add ' || ci.item_name,
    (SELECT workstation_id FROM workstations WHERE workstation_name='Barista'),
    0,
    ROUND(0.01 * 60, 2)
FROM formulas f
JOIN items p  ON p.item_id = f.parent_item_id
JOIN items ci ON ci.item_id = f.component_item_id
JOIN routes rt ON rt.item_id = p.item_id
WHERE p.item_type = 'finished_good' AND ci.item_type = 'raw_material';
