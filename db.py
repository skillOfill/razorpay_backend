"""SQLite store for license keys (payment_id -> key, email, etc.)."""
import os
import sqlite3
from contextlib import contextmanager
DB_PATH = os.environ.get("LICENSE_DB_PATH", os.path.join(os.path.dirname(__file__), "license_keys.db"))


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS license_keys (
                license_key TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                order_id TEXT,
                payment_id TEXT UNIQUE,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        yield conn
    finally:
        conn.close()


def add_key(license_key: str, email: str, order_id: str = None, payment_id: str = None) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO license_keys (license_key, email, order_id, payment_id) VALUES (?, ?, ?, ?)",
            (license_key, email, order_id or "", payment_id or ""),
        )
        conn.commit()


def is_valid_key(license_key: str) -> bool:
    if not (license_key and license_key.strip()):
        return False
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM license_keys WHERE license_key = ?",
            (license_key.strip(),),
        ).fetchone()
    return row is not None


def get_key_by_order(order_id: str) -> str | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT license_key FROM license_keys WHERE order_id = ?",
            (order_id,),
        ).fetchone()
    return row[0] if row else None
