"""
core/db_products.py
Products database — handles products, aliases, groups.

Tables
------
products      — main product records
product_alias — sibling aliases (many per product, sync on change)
groups        — named product groups (Bulk, Canned, …)
"""

import sqlite3
import threading
from contextlib import contextmanager
from config import DB_PRODUCTS

_local = threading.local()


@contextmanager
def _conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PRODUCTS, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield _local.conn
    except Exception:
        _local.conn.rollback()
        raise


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    barcode         TEXT    NOT NULL UNIQUE,
    brand           TEXT    NOT NULL DEFAULT '',
    name            TEXT    NOT NULL,
    cost            REAL    NOT NULL DEFAULT 0.0,
    selling_price   REAL    NOT NULL DEFAULT 0.0,
    group_id        INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    discount_level1 INTEGER DEFAULT NULL,   -- qty threshold for level-1 price
    discount_level2 INTEGER DEFAULT NULL,   -- qty threshold for level-2 price (higher qty)
    gct_applicable  INTEGER NOT NULL DEFAULT 1,   -- 1 = yes, 0 = no
    is_case         INTEGER NOT NULL DEFAULT 0,   -- 1 = case item
    case_qty        INTEGER DEFAULT NULL,          -- units per case
    case_product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    stock           INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS product_alias (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    alias       TEXT    NOT NULL,
    UNIQUE (product_id, alias)
);

-- Indexes for fast barcode / name lookups
CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_products_name    ON products(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_alias_alias      ON product_alias(alias COLLATE NOCASE);
"""


def init_db():
    """Create tables if they don't exist."""
    with _conn() as con:
        con.executescript(SCHEMA)
        con.commit()


# ── Groups ────────────────────────────────────────────────────────────────────

def get_groups() -> list[dict]:
    with _conn() as con:
        return [dict(r) for r in con.execute("SELECT * FROM groups ORDER BY name")]


def add_group(name: str) -> int:
    with _conn() as con:
        cur = con.execute("INSERT OR IGNORE INTO groups (name) VALUES (?)", (name,))
        con.commit()
        return cur.lastrowid


def delete_group(group_id: int):
    with _conn() as con:
        con.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        con.commit()


# ── Products ──────────────────────────────────────────────────────────────────

def get_products(search: str = "", group_id: int = None,
                 limit: int = 100, offset: int = 0) -> list[dict]:
    """Return products with optional full-text search and group filter."""
    q = """
        SELECT p.*, g.name AS group_name
        FROM   products p
        LEFT   JOIN groups g ON g.id = p.group_id
        WHERE  1=1
    """
    params: list = []
    if search:
        q += """
          AND (p.barcode LIKE ?
            OR p.name    LIKE ?
            OR p.brand   LIKE ?
            OR EXISTS (
                SELECT 1 FROM product_alias a
                WHERE  a.product_id = p.id
                AND    a.alias LIKE ?
            ))
        """
        s = f"%{search}%"
        params += [s, s, s, s]
    if group_id is not None:
        q += " AND p.group_id = ?"
        params.append(group_id)
    q += " ORDER BY p.name COLLATE NOCASE LIMIT ? OFFSET ?"
    params += [limit, offset]
    with _conn() as con:
        return [dict(r) for r in con.execute(q, params)]


def get_product_by_id(product_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT p.*, g.name AS group_name FROM products p "
            "LEFT JOIN groups g ON g.id = p.group_id WHERE p.id = ?",
            (product_id,)
        ).fetchone()
        return dict(row) if row else None


def get_product_by_barcode(barcode: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT p.*, g.name AS group_name FROM products p "
            "LEFT JOIN groups g ON g.id = p.group_id WHERE p.barcode = ?",
            (barcode,)
        ).fetchone()
        return dict(row) if row else None


def add_product(barcode: str, brand: str, name: str, cost: float,
                selling_price: float, group_id: int = None,
                gct_applicable: bool = True, is_case: bool = False,
                case_qty: int = None, case_product_id: int = None,
                discount_level1: int = None, discount_level2: int = None,
                stock: int = 0) -> int:
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO products
               (barcode, brand, name, cost, selling_price, group_id,
                gct_applicable, is_case, case_qty, case_product_id,
                discount_level1, discount_level2, stock)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (barcode, brand, name, cost, selling_price, group_id,
             int(gct_applicable), int(is_case), case_qty, case_product_id,
             discount_level1, discount_level2, stock)
        )
        con.commit()
        return cur.lastrowid


def update_product(product_id: int, **fields) -> bool:
    """Update arbitrary product fields. Returns True if a row was changed."""
    if not fields:
        return False
    fields["updated_at"] = "datetime('now')"
    # Build SET clause — datetime gets special treatment (no quoting)
    set_parts = []
    params = []
    for k, v in fields.items():
        if k == "updated_at":
            set_parts.append("updated_at = datetime('now')")
        else:
            set_parts.append(f"{k} = ?")
            params.append(v)
    params.append(product_id)
    sql = f"UPDATE products SET {', '.join(set_parts)} WHERE id = ?"
    with _conn() as con:
        cur = con.execute(sql, params)
        con.commit()
        return cur.rowcount > 0


def delete_product(product_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM products WHERE id = ?", (product_id,))
        con.commit()
        return cur.rowcount > 0


def update_stock(product_id: int, delta: int):
    """Add delta (positive or negative) to stock atomically."""
    with _conn() as con:
        con.execute(
            "UPDATE products SET stock = MAX(0, stock + ?) WHERE id = ?",
            (delta, product_id)
        )
        con.commit()


# ── Aliases ───────────────────────────────────────────────────────────────────

def get_aliases(product_id: int) -> list[str]:
    with _conn() as con:
        rows = con.execute(
            "SELECT alias FROM product_alias WHERE product_id = ? ORDER BY alias",
            (product_id,)
        ).fetchall()
        return [r["alias"] for r in rows]


def set_aliases(product_id: int, aliases: list[str]):
    """
    Replace all aliases for a product.
    Because aliases are siblings, changing one updates all — just pass the
    full new list every time.
    """
    with _conn() as con:
        con.execute("DELETE FROM product_alias WHERE product_id = ?", (product_id,))
        con.executemany(
            "INSERT OR IGNORE INTO product_alias (product_id, alias) VALUES (?, ?)",
            [(product_id, a.strip()) for a in aliases if a.strip()]
        )
        con.commit()


def search_by_alias(alias: str) -> list[dict]:
    with _conn() as con:
        return [dict(r) for r in con.execute(
            """SELECT p.*, g.name AS group_name
               FROM   product_alias a
               JOIN   products p ON p.id = a.product_id
               LEFT   JOIN groups g ON g.id = p.group_id
               WHERE  a.alias LIKE ?""",
            (f"%{alias}%",)
        )]


def count_products(search: str = "", group_id: int = None) -> int:
    q = "SELECT COUNT(*) FROM products p WHERE 1=1"
    params: list = []
    if search:
        q += """ AND (p.barcode LIKE ? OR p.name LIKE ? OR p.brand LIKE ?
                  OR EXISTS (SELECT 1 FROM product_alias a
                             WHERE a.product_id=p.id AND a.alias LIKE ?))"""
        s = f"%{search}%"
        params += [s, s, s, s]
    if group_id is not None:
        q += " AND p.group_id = ?"
        params.append(group_id)
    with _conn() as con:
        return con.execute(q, params).fetchone()[0]
