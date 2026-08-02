import os
import sqlite3

db_path = "data/coffee_shop.db"

if os.path.exists(db_path):
    os.remove(db_path)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

for sql_file in ["sql/schema.sql", "data/seed/seed_data.sql"]:
    with open(sql_file, "r") as f:
        cursor.executescript(f.read())

conn.commit()
conn.close()

print("Fresh database created and seeded successfully.")