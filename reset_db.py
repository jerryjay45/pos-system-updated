"""
reset_db.py — Delete and recreate all POS databases with the latest schema.
Run from the project root:  python reset_db.py

WARNING: This will delete all existing data.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DATA_DIR, RECEIPT_DIR, LABEL_DIR, \
                   DB_PRODUCTS, DB_USERS, DB_CHECKOUT, DB_CONFIG

# ── 1. Delete existing databases ──────────────────────────────────────────────
print("Removing existing databases...")
for db in [DB_PRODUCTS, DB_USERS, DB_CHECKOUT, DB_CONFIG]:
    if os.path.exists(db):
        os.remove(db)
        print(f"  Deleted {os.path.basename(db)}")
    else:
        print(f"  {os.path.basename(db)} not found — skipping")

# ── 2. Create required directories ────────────────────────────────────────────
for d in [DATA_DIR, RECEIPT_DIR, LABEL_DIR]:
    os.makedirs(d, exist_ok=True)

# ── 3. Initialise all databases with new schema ───────────────────────────────
print("\nCreating databases...")
from core import init_all_databases
init_all_databases()
print("  All databases created.")

# ── 4. Seed sample data ───────────────────────────────────────────────────────
print("\nSeeding default data...")

# Default manager account
from core.db_users import get_users
users = get_users()
if any(u["username"] == "MANAGER" for u in users):
    print("  Default manager account already exists.")
else:
    print("  Default manager: username=MANAGER  password=ADMIN")

# Default product groups
from core.db_products import get_groups, add_group, update_group_margin
existing_groups = {g["name"] for g in get_groups()}
default_groups = [
    ("BEVERAGES",   0.30),
    ("CANNED GOODS",0.25),
    ("DAIRY",       0.20),
    ("DRY GOODS",   0.25),
    ("FROZEN",      0.20),
    ("HOUSEHOLD",   0.35),
    ("PERSONAL CARE",0.35),
    ("SNACKS",      0.30),
]
for name, margin in default_groups:
    if name not in existing_groups:
        gid = add_group(name)
        update_group_margin(gid, margin)
        print(f"  Group: {name}  ({int(margin*100)}% margin)")

# Default config / business info
from core.db_config import get_business, update_business
biz = get_business()
if not biz.get("name"):
    update_business(
        name="MY STORE",
        address="123 MAIN STREET",
        phone="",
        email="",
        website="",
    )
    print("  Business info seeded (update via Manager → Business Info).")

print("\nSeeding test products...")
from core.db_products import add_product, get_groups, get_products, add_price_group, get_price_groups

# Get group IDs by name
groups = {g["name"]: g["id"] for g in get_groups()}

# Seed price groups
print("\nSeeding price groups...")
existing_pgs = {pg["name"] for pg in get_price_groups()}
price_group_ids = {}
default_price_groups = [
    ("STANDARD SOFT DRINK 330ML", "alias"),
    ("COCA COLA VARIANTS 330ML",  "variant"),
    ("STANDARD MILK 1L",          "alias"),
]
for name, type_ in default_price_groups:
    if name not in existing_pgs:
        pid = add_price_group(name, type_)
        price_group_ids[name] = pid
        print(f"  Price group: {name} ({type_})")
    else:
        pid = next(pg["id"] for pg in get_price_groups() if pg["name"] == name)
        price_group_ids[name] = pid

# Only seed if no products exist
if get_products(limit=1):
    print("  Products already exist — skipping.")
else:
    test_products = [
        # (barcode,        name,                        cost,  gct,   group,           stock, alias_pg,                        variant_pg)
        ("6001234500001", "COCA COLA ORIGINAL 330ML",   1.50,  True,  "BEVERAGES",      48,   "STANDARD SOFT DRINK 330ML",     "COCA COLA VARIANTS 330ML"),
        ("6001234500002", "COCA COLA VANILLA 330ML",    1.50,  True,  "BEVERAGES",      24,   "STANDARD SOFT DRINK 330ML",     "COCA COLA VARIANTS 330ML"),
        ("6001234500003", "COCA COLA ZERO 330ML",       1.50,  True,  "BEVERAGES",      30,   "STANDARD SOFT DRINK 330ML",     "COCA COLA VARIANTS 330ML"),
        ("6001234500004", "PEPSI 330ML",                1.50,  True,  "BEVERAGES",      36,   "STANDARD SOFT DRINK 330ML",     None),
        ("6001234500005", "SPRITE 330ML",               1.50,  True,  "BEVERAGES",      30,   "STANDARD SOFT DRINK 330ML",     None),
        ("6001234500006", "7UP 330ML",                  1.50,  True,  "BEVERAGES",      28,   "STANDARD SOFT DRINK 330ML",     None),
        ("6001234500007", "MTN DEW 330ML",              1.50,  True,  "BEVERAGES",      22,   "STANDARD SOFT DRINK 330ML",     None),
        ("6001234500008", "COCA COLA 2L",               3.00,  True,  "BEVERAGES",      24,   None,                            None),
        ("6001234500009", "WHOLE MILK 1L",              2.20,  False, "DAIRY",          20,   "STANDARD MILK 1L",              None),
        ("6001234500010", "SKIMMED MILK 1L",            2.20,  False, "DAIRY",          15,   "STANDARD MILK 1L",              None),
        ("6001234500011", "CHEDDAR CHEESE 500G",        5.50,  False, "DAIRY",          10,   None,                            None),
        ("6001234500012", "MACKEREL IN BRINE 185G",     1.80,  True,  "CANNED GOODS",   40,   None,                            None),
        ("6001234500013", "CORNED BEEF 340G",           3.50,  True,  "CANNED GOODS",   30,   None,                            None),
        ("6001234500014", "KIDNEY BEANS 400G",          1.20,  True,  "CANNED GOODS",   50,   None,                            None),
        ("6001234500015", "TOMATO PASTE 170G",          1.10,  True,  "CANNED GOODS",   45,   None,                            None),
        ("6001234500016", "WHITE RICE 2KG",             4.50,  False, "DRY GOODS",      25,   None,                            None),
        ("6001234500017", "ALL PURPOSE FLOUR 1KG",      2.80,  False, "DRY GOODS",      20,   None,                            None),
        ("6001234500018", "WHITE SUGAR 1KG",            2.50,  False, "DRY GOODS",      30,   None,                            None),
        ("6001234500019", "LAYS CLASSIC 150G",          2.00,  True,  "SNACKS",         40,   None,                            None),
        ("6001234500020", "PRINGLES ORIGINAL 165G",     3.50,  True,  "SNACKS",         25,   None,                            None),
        ("6001234500021", "OREO COOKIES 137G",          2.50,  True,  "SNACKS",         35,   None,                            None),
        ("6001234500022", "COLGATE TOOTHPASTE 100ML",   3.00,  True,  "PERSONAL CARE",  20,   None,                            None),
        ("6001234500023", "DOVE SOAP 135G",             2.20,  True,  "PERSONAL CARE",  30,   None,                            None),
        ("6001234500024", "HEAD & SHOULDERS 400ML",     6.50,  True,  "PERSONAL CARE",  15,   None,                            None),
        ("6001234500025", "AJAX DISH LIQUID 500ML",     3.20,  True,  "HOUSEHOLD",      20,   None,                            None),
        ("6001234500026", "SPONGE SCOURER 3PK",         2.50,  True,  "HOUSEHOLD",      25,   None,                            None),
        ("6001234500027", "GARBAGE BAGS 20PK",          4.00,  True,  "HOUSEHOLD",      18,   None,                            None),
    ]

    all_groups = get_groups()
    for barcode, name, cost, gct, group_name, stock, alias_pg_name, variant_pg_name in test_products:
        gid    = groups.get(group_name)
        margin = next((g["profit_margin"] for g in all_groups if g["id"] == gid), 0.25)
        price  = round(cost * (1 + margin), 2)
        add_product(
            barcode=barcode, name=name,
            cost=cost, selling_price=price,
            group_id=gid, gct_applicable=gct, stock=stock,
            alias_group_id=price_group_ids.get(alias_pg_name),
            variant_group_id=price_group_ids.get(variant_pg_name),
        )
        print(f"  {name}  cost=${cost:.2f}  price=${price:.2f}")

print("\nDone! You can now run:  python main.py")
