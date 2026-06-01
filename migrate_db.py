"""
migrate_db.py
Run once after upgrading to add new columns and tables.
Safe to run multiple times — uses IF NOT EXISTS / try-except.

Usage:
    python migrate_db.py
"""
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DB_PRODUCTS, DB_USERS, DB_CHECKOUT, DB_CONFIG

print("Running database migrations...\n")


# ── Products DB ───────────────────────────────────────────────────────────────
con = sqlite3.connect(DB_PRODUCTS)

# discount_levels table
con.execute("""
    CREATE TABLE IF NOT EXISTS discount_levels (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        name             TEXT    NOT NULL DEFAULT '',
        discount_percent REAL    NOT NULL DEFAULT 0.0,
        min_quantity     INTEGER NOT NULL DEFAULT 1
    )
""")
print("✓  discount_levels table")

# cost column on price_groups
try:
    con.execute("ALTER TABLE price_groups ADD COLUMN cost REAL NOT NULL DEFAULT 0.0")
    print("✓  price_groups.cost column")
except Exception:
    print("~  price_groups.cost already exists")

# profit_margin column on groups
try:
    con.execute("ALTER TABLE groups ADD COLUMN profit_margin REAL DEFAULT 0.0")
    print("✓  groups.profit_margin column")
except Exception:
    print("~  groups.profit_margin already exists")

# Seed default discount levels
if con.execute("SELECT COUNT(*) FROM discount_levels").fetchone()[0] == 0:
    con.execute("INSERT INTO discount_levels (name, discount_percent, min_quantity) VALUES ('Level 1 - Bulk', 5.0, 6)")
    con.execute("INSERT INTO discount_levels (name, discount_percent, min_quantity) VALUES ('Level 2 - Wholesale', 10.0, 12)")
    print("✓  Seeded 2 default discount levels")
else:
    print("~  Discount levels already seeded")

con.commit(); con.close()

# ── Config DB ─────────────────────────────────────────────────────────────────
con = sqlite3.connect(DB_CONFIG)

# Ensure theme key exists
con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('theme', 'amber')")
con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('thermal_printer_name', '')")
con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('normal_printer_name', '')")
con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('label_printer_name', '')")
con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('receipt_copies', '1')")
con.commit(); con.close()
print("✓  Config DB settings seeded")

print("\n✓  All migrations complete.")
print("Run: python main.py")
