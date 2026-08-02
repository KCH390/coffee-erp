DROP TABLE IF EXISTS route_operations;
DROP TABLE IF EXISTS routes;
DROP TABLE IF EXISTS formulas;
DROP TABLE IF EXISTS items;

CREATE TABLE items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_code TEXT NOT NULL UNIQUE,
    item_name TEXT NOT NULL,
    item_type TEXT NOT NULL,
    uom TEXT NOT NULL,
    standard_cost REAL DEFAULT 0,
    sale_price REAL
);

CREATE TABLE formulas (
    formula_id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_item_id INTEGER NOT NULL,
    component_item_id INTEGER NOT NULL,
    quantity REAL NOT NULL,
    scrap_pct REAL DEFAULT 0,

    FOREIGN KEY(parent_item_id) REFERENCES items(item_id),
    FOREIGN KEY(component_item_id) REFERENCES items(item_id)
);

CREATE TABLE routes (
    route_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    route_name TEXT NOT NULL,
    description TEXT,

    FOREIGN KEY(item_id) REFERENCES items(item_id)
);

CREATE TABLE route_operations (
    operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER NOT NULL,
    operation_seq INTEGER NOT NULL,
    operation_name TEXT NOT NULL,
    workstation TEXT,
    setup_minutes REAL DEFAULT 0,
    run_minutes REAL DEFAULT 0,

    FOREIGN KEY(route_id) REFERENCES routes(route_id)
);