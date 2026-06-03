"""
core/db_checkout.py
Checkout database — receipts, line items, refund/void records.

Tables
------
receipts      — one row per completed transaction
receipt_items — line items per receipt
refunds       — void / partial-refund records linked to a receipt
"""

import sqlite3
import threading
from contextlib import contextmanager
from config import DB_CHECKOUT

_local = threading.local()


@contextmanager
def _conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_CHECKOUT, check_same_thread=False)
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
CREATE TABLE IF NOT EXISTS receipts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_number  TEXT    NOT NULL UNIQUE,   -- e.g. "#0041"
    user_id         INTEGER NOT NULL,          -- cashier
    session_id      INTEGER NOT NULL,
    subtotal        REAL    NOT NULL DEFAULT 0.0,
    gct_amount      REAL    NOT NULL DEFAULT 0.0,
    discount_amount REAL    NOT NULL DEFAULT 0.0,
    total           REAL    NOT NULL DEFAULT 0.0,
    payment_method  TEXT    NOT NULL DEFAULT 'cash'
                            CHECK(payment_method IN ('cash','card','split')),
    cash_tendered   REAL    DEFAULT NULL,
    card_amount     REAL    DEFAULT NULL,
    change_given    REAL    DEFAULT NULL,
    status          TEXT    NOT NULL DEFAULT 'completed'
                            CHECK(status IN ('completed','voided','refunded')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS receipt_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id      INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    product_id      INTEGER NOT NULL,
    barcode         TEXT    NOT NULL,
    product_name    TEXT    NOT NULL,
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      REAL    NOT NULL,
    discount_amount REAL    NOT NULL DEFAULT 0.0,
    gct_amount      REAL    NOT NULL DEFAULT 0.0,
    line_total      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS refunds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id      INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL,          -- supervisor/manager who actioned it
    refund_type     TEXT    NOT NULL CHECK(refund_type IN ('void','partial','full')),
    reason          TEXT    NOT NULL DEFAULT '',
    amount          REAL    NOT NULL DEFAULT 0.0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_receipts_number   ON receipts(receipt_number);
CREATE INDEX IF NOT EXISTS idx_receipts_user     ON receipts(user_id);
CREATE INDEX IF NOT EXISTS idx_receipts_session  ON receipts(session_id);
CREATE INDEX IF NOT EXISTS idx_receipts_date     ON receipts(created_at);
CREATE INDEX IF NOT EXISTS idx_items_receipt     ON receipt_items(receipt_id);
CREATE INDEX IF NOT EXISTS idx_refunds_receipt   ON refunds(receipt_id);
"""


def init_db():
    with _conn() as con:
        con.executescript(SCHEMA)
        con.commit()


# ── Receipt number generator ──────────────────────────────────────────────────

def _next_receipt_number(con) -> str:
    row = con.execute(
        "SELECT receipt_number FROM receipts ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        try:
            num = int(row["receipt_number"].lstrip("#")) + 1
        except ValueError:
            num = 1
    else:
        num = 1
    return f"#{num:04d}"


# ── Receipts ──────────────────────────────────────────────────────────────────

def save_receipt(
    user_id: int,
    session_id: int,
    items: list[dict],           # list of line-item dicts
    subtotal: float,
    gct_amount: float,
    discount_amount: float,
    total: float,
    payment_method: str = "cash",
    cash_tendered: float = None,
    card_amount: float = None,
    change_given: float = None,
) -> dict:
    """
    Persist a completed transaction. Returns the saved receipt dict including
    the auto-generated receipt_number.

    items dicts must contain:
        product_id, barcode, product_name, quantity,
        unit_price, discount_amount, gct_amount, line_total
    """
    with _conn() as con:
        receipt_number = _next_receipt_number(con)
        cur = con.execute(
            """INSERT INTO receipts
               (receipt_number, user_id, session_id, subtotal, gct_amount,
                discount_amount, total, payment_method,
                cash_tendered, card_amount, change_given)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (receipt_number, user_id, session_id, subtotal, gct_amount,
             discount_amount, total, payment_method,
             cash_tendered, card_amount, change_given)
        )
        receipt_id = cur.lastrowid
        con.executemany(
            """INSERT INTO receipt_items
               (receipt_id, product_id, barcode, product_name,
                quantity, unit_price, discount_amount, gct_amount, line_total)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [(receipt_id,
              it["product_id"], it["barcode"], it["product_name"],
              it["quantity"], it["unit_price"], it["discount_amount"],
              it["gct_amount"], it["line_total"])
             for it in items]
        )
        con.commit()
        return get_receipt_by_id(receipt_id)


def get_receipt_by_id(receipt_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM receipts WHERE id = ?", (receipt_id,)
        ).fetchone()
        if not row:
            return None
        receipt = dict(row)
        receipt["items"] = [
            dict(r) for r in con.execute(
                "SELECT * FROM receipt_items WHERE receipt_id = ?", (receipt_id,)
            )
        ]
        return receipt


def get_receipt_by_number(receipt_number: str) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM receipts WHERE receipt_number = ?", (receipt_number,)
        ).fetchone()
        if not row:
            return None
        return get_receipt_by_id(row["id"])


def count_receipts(
    user_id: int = None, session_id: int = None,
    status: str = None, search: str = "",
    date_from: str = "", date_to: str = "",
) -> int:
    q = "SELECT COUNT(*) FROM receipts WHERE 1=1"
    params: list = []
    if user_id    is not None: q += " AND user_id = ?";       params.append(user_id)
    if session_id is not None: q += " AND session_id = ?";    params.append(session_id)
    if status:                 q += " AND status = ?";        params.append(status)
    if search:
        q += " AND receipt_number LIKE ?";                    params.append(f"%{search}%")
    if date_from: q += " AND date(created_at) >= ?";         params.append(date_from)
    if date_to:   q += " AND date(created_at) <= ?";         params.append(date_to)
    with _conn() as con:
        return con.execute(q, params).fetchone()[0]


def get_receipts(
    user_id: int = None,
    session_id: int = None,
    status: str = None,
    search: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    q = "SELECT * FROM receipts WHERE 1=1"
    params: list = []
    if user_id    is not None: q += " AND user_id = ?";           params.append(user_id)
    if session_id is not None: q += " AND session_id = ?";        params.append(session_id)
    if status:                 q += " AND status = ?";            params.append(status)
    if search:
        q += " AND receipt_number LIKE ?"
        params.append(f"%{search}%")
    if date_from: q += " AND date(created_at) >= ?";             params.append(date_from)
    if date_to:   q += " AND date(created_at) <= ?";             params.append(date_to)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    with _conn() as con:
        return [dict(r) for r in con.execute(q, params)]


def void_receipt(receipt_id: int, user_id: int, reason: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "UPDATE receipts SET status='voided' WHERE id=? AND status='completed'",
            (receipt_id,)
        )
        if cur.rowcount == 0:
            return False
        con.execute(
            "INSERT INTO refunds (receipt_id, user_id, refund_type, reason, amount) "
            "SELECT id, ?, 'void', ?, total FROM receipts WHERE id=?",
            (user_id, reason, receipt_id)
        )
        con.commit()
        return True


def refund_receipt(receipt_id: int, user_id: int, reason: str,
                   amount: float, refund_type: str = "full") -> bool:
    with _conn() as con:
        cur = con.execute(
            "UPDATE receipts SET status='refunded' WHERE id=? AND status='completed'",
            (receipt_id,)
        )
        if cur.rowcount == 0:
            return False
        con.execute(
            "INSERT INTO refunds (receipt_id, user_id, refund_type, reason, amount) "
            "VALUES (?,?,?,?,?)",
            (receipt_id, user_id, refund_type, reason, amount)
        )
        con.commit()
        return True


# ── Reporting helpers ─────────────────────────────────────────────────────────

def session_totals(session_id: int) -> dict:
    """Return aggregated sales totals for a session."""
    with _conn() as con:
        row = con.execute(
            """SELECT
                COUNT(*)                                        AS transaction_count,
                COALESCE(SUM(CASE WHEN status='completed'
                              THEN total ELSE 0 END), 0)       AS total_sales,
                COALESCE(SUM(CASE WHEN status='completed'
                              THEN gct_amount ELSE 0 END), 0)  AS total_gct,
                COALESCE(SUM(CASE WHEN status='completed'
                              THEN discount_amount ELSE 0 END),0) AS total_discount,
                COUNT(CASE WHEN status='voided'   THEN 1 END)  AS voided_count,
                COUNT(CASE WHEN status='refunded' THEN 1 END)  AS refunded_count
               FROM receipts WHERE session_id = ?""",
            (session_id,)
        ).fetchone()
        return dict(row)


def session_group_totals(session_id: int) -> list[dict]:
    """Return sales broken down by product group for a session.

    Joins receipt_items.product_id to the products DB to get group names.
    Returns list of {group_name, total_sales, item_count} sorted by total desc.
    """
    from config import DB_PRODUCTS
    with _conn() as con:
        con.execute(f"ATTACH DATABASE ? AS pdb", (DB_PRODUCTS,))
        try:
            rows = con.execute(
                """SELECT
                       COALESCE(g.name, 'Ungrouped')  AS group_name,
                       SUM(ri.line_total)              AS total_sales,
                       SUM(ri.quantity)                AS item_count
                   FROM receipt_items ri
                   JOIN receipts r ON r.id = ri.receipt_id
                   LEFT JOIN pdb.products p ON p.id = ri.product_id
                   LEFT JOIN pdb.groups g ON g.id = p.group_id
                   WHERE r.session_id = ?
                     AND r.status = 'completed'
                   GROUP BY g.id, g.name
                   ORDER BY total_sales DESC""",
                (session_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.execute("DETACH DATABASE pdb")


def session_voided_receipts(session_id: int) -> list[dict]:
    """Return all voided receipts for a session with their void reason."""
    with _conn() as con:
        rows = con.execute(
            """SELECT r.receipt_number, r.total, r.created_at,
                      rf.reason, rf.created_at AS voided_at
               FROM receipts r
               LEFT JOIN refunds rf ON rf.receipt_id = r.id
               WHERE r.session_id = ? AND r.status = 'voided'
               ORDER BY r.created_at""",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_refunds_for_receipt(receipt_id: int) -> list[dict]:
    """Return all refund/void records for a receipt, newest first."""
    with _conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM refunds WHERE receipt_id = ? ORDER BY id DESC",
            (receipt_id,)
        )]


def get_session_receipts(session_id: int) -> list[dict]:
    """Return all receipts for a session."""
    with _conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM receipts WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,)
        )]
