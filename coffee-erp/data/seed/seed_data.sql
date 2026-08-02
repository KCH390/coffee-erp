-- ============================================================
-- Seed Data: Items, Formulas (RM -> SFG -> FG)
-- Quantities are placeholders (oz/ea) -- replace with real recipe amounts.
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

-- ============================================================
-- FORMULAS (BOM) -- Tier 1: RM -> SFG
-- ============================================================

-- Latte Base: Espresso + Whole Milk + Sugar
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='SFG-LATTE'), items.item_id, v.qty, 0.02
FROM items JOIN (
    SELECT 'BASE-ESPRESSO' AS item_code, 2.0 AS qty
    UNION ALL SELECT 'CREAM-WM', 6.0
    UNION ALL SELECT 'RM-SUGAR', 4.0
) v ON items.item_code = v.item_code;

-- Standard Base: Brewed Coffee + Half & Half + Sugar
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='SFG-STANDARD'), items.item_id, v.qty, 0.01
FROM items JOIN (
    SELECT 'BASE-BREWED' AS item_code, 12.0 AS qty
    UNION ALL SELECT 'CREAM-HH', 2.0
    UNION ALL SELECT 'RM-SUGAR', 4.0
) v ON items.item_code = v.item_code;

-- Americano Base: Espresso only
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='SFG-AMERICANO'), item_id, 2.0, 0.02
FROM items WHERE item_code = 'BASE-ESPRESSO';

-- Frappe Base: Espresso + Ice + Whole Milk + Sugar + Whipped Cream
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='SFG-FRAPPE'), items.item_id, v.qty, 0.03
FROM items JOIN (
    SELECT 'BASE-ESPRESSO' AS item_code, 2.0 AS qty
    UNION ALL SELECT 'RM-ICE', 8.0
    UNION ALL SELECT 'CREAM-WM', 4.0
    UNION ALL SELECT 'RM-SUGAR', 4.0
    UNION ALL SELECT 'RM-WHIPCREAM', 1.0
) v ON items.item_code = v.item_code;

-- Cold Brew Base: Cold Brew + Ice + Whole Milk + Sugar
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

-- Latte Standard: Latte Base + Sugar
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-LATTE-STD'), items.item_id, v.qty, 0.0
FROM items JOIN (
    SELECT 'SFG-LATTE' AS item_code, 1.0 AS qty
    UNION ALL SELECT 'RM-SUGAR', 2.0
) v ON items.item_code = v.item_code;

-- Spiced Latte: Latte Base + Nutmeg + Cinnamon + Hazelnut Syrup
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-LATTE-SPICED'), items.item_id, v.qty, 0.0
FROM items JOIN (
    SELECT 'SFG-LATTE' AS item_code, 1.0 AS qty
    UNION ALL SELECT 'RM-NUTMEG', 1.0
    UNION ALL SELECT 'RM-CINNAMON', 1.0
    UNION ALL SELECT 'SYRUP-HAZELNUT', 1.0
) v ON items.item_code = v.item_code;

-- Mocha Latte: Latte Base + Mocha Syrup + Cocoa Powder
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-LATTE-MOCHA'), items.item_id, v.qty, 0.0
FROM items JOIN (
    SELECT 'SFG-LATTE' AS item_code, 1.0 AS qty
    UNION ALL SELECT 'SYRUP-MOCHA', 1.0
    UNION ALL SELECT 'RM-COCOA', 2.0
) v ON items.item_code = v.item_code;

-- Brewed Coffee: Standard Base only
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-BREWED'), item_id, 1.0, 0.0
FROM items WHERE item_code = 'SFG-STANDARD';

-- Americano: Americano Base only
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-AMERICANO'), item_id, 1.0, 0.0
FROM items WHERE item_code = 'SFG-AMERICANO';

-- Caramel Frappe: Frappe Base + Caramel Syrup + Caramel Drizzle
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-FRAPPE-CARAMEL'), items.item_id, v.qty, 0.0
FROM items JOIN (
    SELECT 'SFG-FRAPPE' AS item_code, 1.0 AS qty
    UNION ALL SELECT 'SYRUP-CARAMEL', 1.0
    UNION ALL SELECT 'RM-CARAMELDRIZZLE', 0.5
) v ON items.item_code = v.item_code;

-- Mocha Frappe: Frappe Base + Cocoa Powder + Mocha Syrup
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-FRAPPE-MOCHA'), items.item_id, v.qty, 0.0
FROM items JOIN (
    SELECT 'SFG-FRAPPE' AS item_code, 1.0 AS qty
    UNION ALL SELECT 'RM-COCOA', 2.0
    UNION ALL SELECT 'SYRUP-MOCHA', 1.0
) v ON items.item_code = v.item_code;

-- Cold Brew (FG): Cold Brew Base only
INSERT INTO formulas (parent_item_id, component_item_id, quantity, scrap_pct)
SELECT (SELECT item_id FROM items WHERE item_code='FG-COLDBREW'), item_id, 1.0, 0.0
FROM items WHERE item_code = 'SFG-COLDBREW';
