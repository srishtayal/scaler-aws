import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).resolve().parent.parent / "route53.db"))


def connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    conn = connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
          account_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS hosted_zones (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '',
          private_zone INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS records (
          id TEXT PRIMARY KEY, zone_id TEXT NOT NULL, name TEXT NOT NULL, type TEXT NOT NULL,
          value TEXT NOT NULL, ttl INTEGER NOT NULL DEFAULT 300, routing_policy TEXT NOT NULL DEFAULT 'Simple',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(zone_id) REFERENCES hosted_zones(id) ON DELETE CASCADE
        );
        """)
        conn.execute("INSERT OR IGNORE INTO users(id, email, name, account_id) VALUES (1, 'admin@example.com', 'Route 53 Administrator', '1234-5678-9012')")
