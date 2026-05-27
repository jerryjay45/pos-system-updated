"""
seed_data.py
Run once to populate the database with test products, groups, and quick keys.

Usage:
    python seed_data.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.makedirs("data", exist_ok=True)

from core import init_all_databases
init_all_databases()

from core.db_products import add_product, add_group, get_products, get_groups
from core.db_config   import set_quick_key
from core.db_users    import add_user, get_users

print("Seeding database...\n")

# ── Groups ────────────────────────────────────────────────────────────────────
existing_groups = {g["name"] for g in get_groups()}
groups = {}
for name in ["Beverages", "Snacks", "Dairy", "Bulk", "Household", "Bakery"]:
    if name not in existing_groups:
        gid = add_group(name)
    else:
        from core.db_products import get_groups
        gid = next(g["id"] for g in get_groups() if g["name"] == name)
    groups[name] = gid
    print(f"  Group: {name}")

# ── Products ──────────────────────────────────────────────────────────────────
existing_barcodes = {p["barcode"] for p in get_products(limit=1000)}

products = [
    # Beverages
    dict(barcode="5000112637", brand="Coca Cola",  name="Coca Cola 330ml",     cost=0.90,  selling_price=1.70,  group_id=groups["Beverages"], gct_applicable=True,  is_case=False),
    dict(barcode="5000112638", brand="Coca Cola",  name="Coca Cola 330ml x24", cost=20.00, selling_price=38.00, group_id=groups["Beverages"], gct_applicable=True,  is_case=True,  case_qty=24),
    dict(barcode="5000112567", brand="Sprite",     name="Sprite Soda 330ml",   cost=0.90,  selling_price=1.70,  group_id=groups["Beverages"], gct_applicable=True,  is_case=False),
    dict(barcode="5000112599", brand="Pepsi",      name="Pepsi 330ml",         cost=0.88,  selling_price=1.70,  group_id=groups["Beverages"], gct_applicable=True,  is_case=False),
    dict(barcode="5000445566", brand="Juice Box",  name="Apple Juice 250ml",   cost=0.70,  selling_price=1.25,  group_id=groups["Beverages"], gct_applicable=True,  is_case=False),
    dict(barcode="5000998877", brand="H2O",        name="Water 500ml",         cost=0.40,  selling_price=0.85,  group_id=groups["Beverages"], gct_applicable=True,  is_case=False),

    # Snacks
    dict(barcode="0011223344", brand="Lays",       name="Lays Classic",        cost=1.50,  selling_price=2.50,  group_id=groups["Snacks"],    gct_applicable=True,  is_case=False),
    dict(barcode="0011223355", brand="Lays",       name="Lays BBQ",            cost=1.50,  selling_price=2.50,  group_id=groups["Snacks"],    gct_applicable=True,  is_case=False),
    dict(barcode="0011223366", brand="Pringles",   name="Pringles Original",   cost=2.00,  selling_price=3.50,  group_id=groups["Snacks"],    gct_applicable=True,  is_case=False),
    dict(barcode="0099887766", brand="Planter's",  name="Peanuts 150g",        cost=1.20,  selling_price=2.00,  group_id=groups["Snacks"],    gct_applicable=True,  is_case=False),

    # Dairy
    dict(barcode="0044332211", brand="Dairy Farm", name="Milk 1L",             cost=1.80,  selling_price=2.95,  group_id=groups["Dairy"],     gct_applicable=False, is_case=False),
    dict(barcode="0044332222", brand="Dairy Farm", name="Butter 250g",         cost=2.50,  selling_price=4.50,  group_id=groups["Dairy"],     gct_applicable=False, is_case=False),
    dict(barcode="0044332233", brand="Dairy Farm", name="Cheddar Cheese 200g", cost=3.00,  selling_price=5.50,  group_id=groups["Dairy"],     gct_applicable=False, is_case=False),
    dict(barcode="0044332244", brand="Dairy Farm", name="Yogurt 150g",         cost=1.00,  selling_price=1.75,  group_id=groups["Dairy"],     gct_applicable=False, is_case=False),

    # Bulk / Grocery
    dict(barcode="0012345678", brand="Grace",      name="Flour 1kg",           cost=1.80,  selling_price=2.75,  group_id=groups["Bulk"],      gct_applicable=False, is_case=False),
    dict(barcode="0012345679", brand="Grace",      name="Flour 1kg x25",       cost=42.00, selling_price=65.00, group_id=groups["Bulk"],      gct_applicable=False, is_case=True,  case_qty=25),
    dict(barcode="0098765432", brand="Carib",      name="Rice 1kg",            cost=2.20,  selling_price=3.00,  group_id=groups["Bulk"],      gct_applicable=False, is_case=False),
    dict(barcode="0098765433", brand="Carib",      name="Rice 5kg",            cost=10.00, selling_price=14.00, group_id=groups["Bulk"],      gct_applicable=False, is_case=False),
    dict(barcode="0087654321", brand="Grace",      name="Cornmeal 1kg",        cost=1.60,  selling_price=2.50,  group_id=groups["Bulk"],      gct_applicable=False, is_case=False),
    dict(barcode="0076543210", brand="Carib",      name="Sugar 1kg",           cost=1.40,  selling_price=2.20,  group_id=groups["Bulk"],      gct_applicable=False, is_case=False),
    dict(barcode="0065432109", brand="Carib",      name="Brown Sugar 1kg",     cost=1.50,  selling_price=2.40,  group_id=groups["Bulk"],      gct_applicable=False, is_case=False),

    # Household
    dict(barcode="0054321098", brand="Scotties",   name="Toilet Paper 4pk",    cost=2.50,  selling_price=4.25,  group_id=groups["Household"], gct_applicable=True,  is_case=False),
    dict(barcode="0043210987", brand="Scotties",   name="Paper Towel 2pk",     cost=2.00,  selling_price=3.50,  group_id=groups["Household"], gct_applicable=True,  is_case=False),
    dict(barcode="0032109876", brand="Palmolive",  name="Dish Soap 500ml",     cost=1.80,  selling_price=3.25,  group_id=groups["Household"], gct_applicable=True,  is_case=False),

    # Bakery
    dict(barcode="0021098765", brand="Local",      name="Bread Loaf",          cost=1.50,  selling_price=2.50,  group_id=groups["Bakery"],    gct_applicable=False, is_case=False),
    dict(barcode="0010987654", brand="Local",      name="Dinner Rolls 6pk",    cost=1.20,  selling_price=2.00,  group_id=groups["Bakery"],    gct_applicable=False, is_case=False),
]

added = 0
skipped = 0
product_ids = {}
for p in products:
    if p["barcode"] in existing_barcodes:
        skipped += 1
    else:
        pid = add_product(**p)
        product_ids[p["name"]] = pid
        existing_barcodes.add(p["barcode"])
        added += 1
        print(f"  + {p['name']} (${p['selling_price']:.2f})")

print(f"\n  Added: {added}  |  Skipped (already exist): {skipped}")

# ── Quick Keys ────────────────────────────────────────────────────────────────
print("\nAssigning Quick Keys...")

# Re-fetch IDs for products that may have existed before
from core.db_products import get_products as gp
all_products = {p["name"]: p for p in gp(limit=1000)}

qk_assignments = [
    (1, "Coca Cola 330ml"),
    (2, "Lays Classic"),
    (3, "Flour 1kg"),
    (4, "Rice 1kg"),
    (5, "Milk 1L"),
    (6, "Bread Loaf"),
    (7, "Water 500ml"),
    (8, "Sprite Soda 330ml"),
]

for slot, name in qk_assignments:
    if name in all_products:
        p = all_products[name]
        set_quick_key(slot, p["id"], p["name"], p["selling_price"])
        print(f"  F{slot} → {name} (${p['selling_price']:.2f})")

# ── Extra users ───────────────────────────────────────────────────────────────
print("\nChecking users...")
existing_users = {u["username"] for u in get_users()}

extra_users = [
    ("Sarah Cashier",   "sarah",  "sarah123",  "cashier"),
    ("Jerry Cashier",   "jerry",  "jerry123",  "cashier"),
    ("Mark Supervisor", "mark",   "mark123",   "supervisor"),
]

for full_name, username, password, role in extra_users:
    if username not in existing_users:
        add_user(full_name, username, password, role)
        print(f"  + {full_name} ({role}) — {username} / {password}")
    else:
        print(f"  ~ {username} already exists")

print("\n✓ Seed complete!\n")
print("Test accounts:")
print("  manager    / admin      → Manager dashboard")
print("  mark       / mark123    → Supervisor dashboard")
print("  sarah      / sarah123   → Cashier dashboard")
print("  jerry      / jerry123   → Cashier dashboard")
print("\nQuick keys F1–F8 are assigned.")
print("Run: python main.py")
