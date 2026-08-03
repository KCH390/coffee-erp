"""
Builds a fresh coffee_shop.db from schema + seed files, then runs the
standard cost rollup so standard_cost is populated before you start
working with the data.

Usage:
    python src/db.py
"""

import sqlite3
from pathlib import Path

from costing import rollup_costs

DB_PATH = Path("data/coffee_shop.db")

SCHEMA_FILE = Path("sql/schema.sql")
SEED_FILES = [
    Path("data/seed/seed_data.sql"),
    Path("data/seed/seed_inventory.sql"),
]


def build_database(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        with conn:
            conn.executescript(SCHEMA_FILE.read_text())
            for seed_file in SEED_FILES:
                conn.executescript(seed_file.read_text())

        rollup_costs(conn, verbose=False)
        print(f"Fresh database created and seeded successfully at {db_path}")

    except sqlite3.Error as e:
        print(f"Database build failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    build_database()
