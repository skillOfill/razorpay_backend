"""
License key storage: SQLite (local) or Postgres (e.g. Neon on Render).
Set DATABASE_URL (postgresql://...) to use Postgres; otherwise uses SQLite.
On Render free tier, use Neon so the DB is not wiped on deploy.
"""
import os
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_PATH = os.environ.get("LICENSE_DB_PATH", os.path.join(os.path.dirname(__file__), "license_keys.db"))

# Prefer Postgres if URL looks like Postgres (Neon, Render Postgres, etc.)
USE_POSTGRES = DATABASE_URL and (
    DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")
)

if USE_POSTGRES:
    # Heroku/Render sometimes give postgres://; psycopg2 wants postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = "postgresql://" + DATABASE_URL.split("://", 1)[1]


def _row_to_dict(row):
    if row is None:
        return None
    if hasattr(row, "_mapping"):
        return dict(row)
    return dict(zip([c[0] for c in row.cursor_description], row)) if hasattr(row, "cursor_description") else row


@contextmanager
def get_db():
    if USE_POSTGRES:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS license_keys (
                        license_key TEXT PRIMARY KEY,
                        email TEXT NOT NULL,
                        order_id TEXT,
                        payment_id TEXT UNIQUE,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                    """
                )
            conn.commit()
            yield conn
        finally:
            conn.close()
    else:
        import sqlite3
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
    order_id = order_id or ""
    payment_id = payment_id or ""
    with get_db() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(
                """
                INSERT INTO license_keys (license_key, email, order_id, payment_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (license_key) DO UPDATE SET
                    email = EXCLUDED.email,
                    order_id = EXCLUDED.order_id,
                    payment_id = EXCLUDED.payment_id
                """,
                (license_key, email, order_id, payment_id),
            )
        else:
            cur.execute(
                "INSERT OR REPLACE INTO license_keys (license_key, email, order_id, payment_id) VALUES (?, ?, ?, ?)",
                (license_key, email, order_id, payment_id),
            )
        conn.commit()


def is_valid_key(license_key: str) -> bool:
    if not (license_key and license_key.strip()):
        return False
    key = license_key.strip()
    with get_db() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute("SELECT 1 FROM license_keys WHERE license_key = %s", (key,))
        else:
            cur.execute("SELECT 1 FROM license_keys WHERE license_key = ?", (key,))
        row = cur.fetchone()
    return row is not None


def get_key_by_order(order_id: str) -> str | None:
    with get_db() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute("SELECT license_key FROM license_keys WHERE order_id = %s", (order_id,))
        else:
            cur.execute("SELECT license_key FROM license_keys WHERE order_id = ?", (order_id,))
        row = cur.fetchone()
    if row is None:
        return None
    return row["license_key"] if hasattr(row, "keys") else row[0]


def email_has_license(email: str) -> bool:
    """True if this email has any issued license (for auto-unlock after Google Login + Payment)."""
    if not (email and email.strip()):
        return False
    email = email.strip().lower()
    with get_db() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute("SELECT 1 FROM license_keys WHERE LOWER(email) = %s", (email,))
        else:
            cur.execute("SELECT 1 FROM license_keys WHERE LOWER(email) = ?", (email,))
        row = cur.fetchone()
    return row is not None
