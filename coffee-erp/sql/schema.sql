-- ============================================================
-- Coffee Shop ERP Simulation — Full Schema
-- ============================================================

DROP TABLE IF EXISTS financial_transactions;
DROP TABLE IF EXISTS order_lines;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS inventory_transactions;
DROP TABLE IF EXISTS inventory;
DROP TABLE IF EXISTS route_operations;
DROP TABLE IF EXISTS routes;
DROP TABLE IF EXISTS formulas;
DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS workstations;

-- ---------- ITEMS (the hub) ----------
CREATE TABLE items (
    item_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_code       TEXT NOT NULL UNIQUE,
    item_name       TEXT NOT NULL,
    item_type       TEXT NOT NULL CHECK (item_type IN ('raw_material','intermediate','finished_good')),
    uom             TEXT NOT NULL,
    standard_cost   REAL DEFAULT 0,
    sale_price      REAL,
    active          INTEGER DEFAULT 1
);

-- ---------- FORMULAS / BOM (what an item is made of) ----------
CREATE TABLE formulas (
    formula_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_item_id  INTEGER NOT NULL,
    component_item_id INTEGER NOT NULL,
    quantity        REAL NOT NULL,
    scrap_pct       REAL DEFAULT 0,

    FOREIGN KEY(parent_item_id) REFERENCES items(item_id),
    FOREIGN KEY(component_item_id) REFERENCES items(item_id)
);

-- ---------- WORKSTATIONS (resources that perform route operations) ----------
CREATE TABLE workstations (
    workstation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    workstation_name TEXT NOT NULL UNIQUE,
    hourly_rate      REAL NOT NULL DEFAULT 0,
    description      TEXT
);

-- ---------- ROUTES (route header per item) ----------
CREATE TABLE routes (
    route_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL,
    route_name      TEXT NOT NULL,
    description     TEXT,

    FOREIGN KEY(item_id) REFERENCES items(item_id)
);

-- ---------- ROUTE OPERATIONS (steps within a route) ----------
CREATE TABLE route_operations (
    operation_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id        INTEGER NOT NULL,
    operation_seq   INTEGER NOT NULL,
    operation_name  TEXT NOT NULL,
    workstation_id  INTEGER,
    setup_minutes   REAL DEFAULT 0,
    run_minutes     REAL DEFAULT 0,

    FOREIGN KEY(route_id) REFERENCES routes(route_id),
    FOREIGN KEY(workstation_id) REFERENCES workstations(workstation_id)
);

-- ---------- INVENTORY ----------
CREATE TABLE inventory (
    inventory_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL UNIQUE,
    on_hand_qty     REAL NOT NULL DEFAULT 0,
    reorder_point   REAL DEFAULT 0,
    reorder_qty     REAL DEFAULT 0,
    lead_time_days  REAL DEFAULT 0,
    pack_size       REAL NOT NULL DEFAULT 1,   -- qty per purchase unit, in items.uom (e.g. 128 for a 128oz jug)
    min_order_qty   REAL NOT NULL DEFAULT 1,   -- supplier's minimum order, in PACKS (not base uom)
    last_updated    TEXT DEFAULT (datetime('now')),

    FOREIGN KEY(item_id) REFERENCES items(item_id)
);

CREATE TABLE inventory_transactions (
    txn_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         INTEGER NOT NULL,
    txn_type        TEXT NOT NULL CHECK (txn_type IN ('receipt','consumption','adjustment')),
    quantity        REAL NOT NULL,
    unit_cost       REAL,
    txn_date        TEXT NOT NULL DEFAULT (datetime('now')),
    reference       TEXT,

    FOREIGN KEY(item_id) REFERENCES items(item_id)
);

-- ---------- CUSTOMERS & ORDERS ----------
CREATE TABLE customers (
    customer_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name   TEXT NOT NULL,
    segment         TEXT
);

CREATE TABLE orders (
    order_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id     INTEGER,
    order_date      TEXT NOT NULL DEFAULT (datetime('now')),
    status          TEXT DEFAULT 'completed',

    FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_lines (
    order_line_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         INTEGER NOT NULL,
    item_id          INTEGER NOT NULL,
    quantity         REAL NOT NULL,
    unit_price       REAL NOT NULL,
    fulfilled        INTEGER NOT NULL DEFAULT 1,  -- set to 0 by inventory_engine.py on a stockout
    original_item_id INTEGER,                     -- set by inventory_engine.py when the customer
                                                    -- substituted away from this item due to a stockout

    FOREIGN KEY(order_id) REFERENCES orders(order_id),
    FOREIGN KEY(item_id) REFERENCES items(item_id),
    FOREIGN KEY(original_item_id) REFERENCES items(item_id)
);

-- ---------- FINANCIALS (simple rollup, not double-entry) ----------
CREATE TABLE financial_transactions (
    fin_txn_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    txn_date        TEXT NOT NULL DEFAULT (datetime('now')),
    txn_type        TEXT NOT NULL CHECK (txn_type IN ('revenue','cogs','opex','inventory_purchase')),
    item_id         INTEGER,
    amount          REAL NOT NULL,
    reference       TEXT,

    FOREIGN KEY(item_id) REFERENCES items(item_id)
);

-- ============================================================
-- VIEWS
-- ============================================================

-- Material cost rollup per item (one level; run bottom-up RM -> SFG -> FG
-- in your costing script so parent standard_cost is populated before
-- it's used as a component cost further up the chain)
DROP VIEW IF EXISTS v_item_material_cost;
CREATE VIEW v_item_material_cost AS
SELECT f.parent_item_id AS item_id,
       SUM(f.quantity * (1 + f.scrap_pct) * ci.standard_cost) AS material_cost
FROM formulas f
JOIN items ci ON ci.item_id = f.component_item_id
GROUP BY f.parent_item_id;

-- Labor cost rollup per item: minutes * workstation hourly rate
DROP VIEW IF EXISTS v_item_labor_cost;
CREATE VIEW v_item_labor_cost AS
SELECT rt.item_id,
       SUM((ro.setup_minutes + ro.run_minutes) / 60.0 * w.hourly_rate) AS labor_cost,
       SUM(ro.setup_minutes + ro.run_minutes) AS total_minutes
FROM routes rt
JOIN route_operations ro ON ro.route_id = rt.route_id
LEFT JOIN workstations w ON w.workstation_id = ro.workstation_id
GROUP BY rt.item_id;

-- Margin by finished good, using current sale price vs standard cost
DROP VIEW IF EXISTS v_item_margin;
CREATE VIEW v_item_margin AS
SELECT item_id, item_name, sale_price, standard_cost,
       (sale_price - standard_cost) AS gross_margin,
       CASE WHEN sale_price > 0 THEN (sale_price - standard_cost) / sale_price ELSE NULL END AS margin_pct
FROM items
WHERE item_type = 'finished_good';

-- Inventory value on hand
DROP VIEW IF EXISTS v_inventory_value;
CREATE VIEW v_inventory_value AS
SELECT i.item_id, it.item_name, i.on_hand_qty, it.standard_cost,
       i.on_hand_qty * it.standard_cost AS inventory_value
FROM inventory i
JOIN items it ON it.item_id = i.item_id;
