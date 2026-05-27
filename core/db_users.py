"""
core/db_users.py
Users database — roles, authentication, sessions.

Tables
------
users         — staff accounts (cashier / supervisor / manager)
sessions      — cashier login sessions (open / closed)
"""

import sqlite3
import threading
import hashlib
import secrets
from contextlib import contextmanager
from datetime import datetime
from config import DB_USERS

_local = threading.local()


@contextmanager
def _conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_USERS, check_same_thread=False)
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
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name   TEXT    NOT NULL,
    username    TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT  NOT NULL,
    role        TEXT    NOT NULL CHECK(role IN ('cashier','supervisor','manager')),
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    opened_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    closed_at   TEXT    DEFAULT NULL,
    total_sales REAL    NOT NULL DEFAULT 0.0,
    status      TEXT    NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open','closed'))
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_sessions_user  ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{h}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split(":", 1)
        candidate = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        # Use secrets.compare_digest to prevent timing attacks
        return secrets.compare_digest(candidate, h)
    except (ValueError, AttributeError):
        return False


# ── Init ──────────────────────────────────────────────────────────────────────

def init_db():
    """Create tables and seed a default manager account if none exists."""
    with _conn() as con:
        con.executescript(SCHEMA)
        # Seed default manager only on first run
        if con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            con.execute(
                "INSERT INTO users (full_name, username, password_hash, role) "
                "VALUES (?, ?, ?, ?)",
                ("Admin Manager", "manager",
                 _hash_password("admin"), "manager")
            )
        con.commit()


# ── Authentication ────────────────────────────────────────────────────────────

def authenticate(username: str, password: str) -> dict | None:
    """
    Returns the user dict (without password_hash) on success, else None.
    Only active users may log in.
    """
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,)
        ).fetchone()
        if row and _verify_password(password, row["password_hash"]):
            user = dict(row)
            del user["password_hash"]
            return user
    return None


# ── Users CRUD ────────────────────────────────────────────────────────────────

def get_users(search: str = "", role: str = "") -> list[dict]:
    q = "SELECT id, full_name, username, role, is_active, created_at FROM users WHERE 1=1"
    params: list = []
    if search:
        q += " AND (full_name LIKE ? OR username LIKE ?)"
        s = f"%{search}%"
        params += [s, s]
    if role:
        q += " AND role = ?"
        params.append(role)
    q += " ORDER BY role, full_name COLLATE NOCASE"
    with _conn() as con:
        return [dict(r) for r in con.execute(q, params)]


def get_user_by_id(user_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT id, full_name, username, role, is_active, created_at "
            "FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def add_user(full_name: str, username: str, password: str,
             role: str, is_active: bool = True) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO users (full_name, username, password_hash, role, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            (full_name, username, _hash_password(password), role, int(is_active))
        )
        con.commit()
        return cur.lastrowid


def update_user(user_id: int, full_name: str = None, username: str = None,
                password: str = None, role: str = None,
                is_active: bool = None) -> bool:
    parts, params = [], []
    if full_name  is not None: parts.append("full_name = ?");      params.append(full_name)
    if username   is not None: parts.append("username = ?");       params.append(username)
    if password   is not None: parts.append("password_hash = ?");  params.append(_hash_password(password))
    if role       is not None: parts.append("role = ?");           params.append(role)
    if is_active  is not None: parts.append("is_active = ?");      params.append(int(is_active))
    if not parts:
        return False
    parts.append("updated_at = datetime('now')")
    params.append(user_id)
    with _conn() as con:
        cur = con.execute(
            f"UPDATE users SET {', '.join(parts)} WHERE id = ?", params
        )
        con.commit()
        return cur.rowcount > 0


def delete_user(user_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM users WHERE id = ?", (user_id,))
        con.commit()
        return cur.rowcount > 0


# ── Sessions ──────────────────────────────────────────────────────────────────

def open_session(user_id: int) -> int:
    """Open a new cashier session. Returns session id."""
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO sessions (user_id) VALUES (?)", (user_id,)
        )
        con.commit()
        return cur.lastrowid


def close_session(session_id: int, total_sales: float) -> bool:
    with _conn() as con:
        cur = con.execute(
            "UPDATE sessions SET status='closed', closed_at=datetime('now'), "
            "total_sales=? WHERE id=? AND status='open'",
            (total_sales, session_id)
        )
        con.commit()
        return cur.rowcount > 0


def get_sessions(user_id: int = None, status: str = None) -> list[dict]:
    q = """
        SELECT s.*, u.full_name, u.username
        FROM   sessions s
        JOIN   users u ON u.id = s.user_id
        WHERE  1=1
    """
    params: list = []
    if user_id is not None:
        q += " AND s.user_id = ?"
        params.append(user_id)
    if status:
        q += " AND s.status = ?"
        params.append(status)
    q += " ORDER BY s.opened_at DESC"
    with _conn() as con:
        return [dict(r) for r in con.execute(q, params)]


def get_open_session(user_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM sessions WHERE user_id=? AND status='open' "
            "ORDER BY opened_at DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        return dict(row) if row else None


def add_session_sales(session_id: int, amount: float):
    """Increment running total for an open session."""
    with _conn() as con:
        con.execute(
            "UPDATE sessions SET total_sales = total_sales + ? WHERE id = ?",
            (amount, session_id)
        )
        con.commit()
