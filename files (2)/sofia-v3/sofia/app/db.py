"""
Sofia — database layer.

mysql-connector-python, pooled, with a context manager per request.

Two things this module refuses to do, both learned the hard way:
  1. It never swallows a connection error at startup. `init_db()` raises.
     A database that is silently unreachable produces a site that looks
     fine and fails on every write.
  2. It never builds SQL by string concatenation. Every value is a
     parameter. There are no exceptions to this, including for values
     that "obviously" came from our own code.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterable, Sequence

import mysql.connector
from mysql.connector import pooling, Error as MySQLError

from config import Config

log = logging.getLogger("sofia.db")

_pool: pooling.MySQLConnectionPool | None = None


def init_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is not None:
        return _pool

    _pool = pooling.MySQLConnectionPool(
        pool_name="sofia_pool",
        pool_size=Config.DB_POOL_SIZE,
        pool_reset_session=True,
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        database=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
        autocommit=False,
        connection_timeout=10,
        time_zone="+00:00",
    )
    return _pool


@contextmanager
def connection():
    """Borrow a pooled connection. Rolls back on exception, always closes."""
    pool = init_pool()
    conn = pool.get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except MySQLError:
            pass
        raise
    finally:
        try:
            conn.close()  # returns it to the pool
        except MySQLError:
            pass


@contextmanager
def cursor(dictionary: bool = True, buffered: bool = True):
    with connection() as conn:
        cur = conn.cursor(dictionary=dictionary, buffered=buffered)
        try:
            yield cur
        finally:
            cur.close()


# --------------------------------------------------------------------------- #
#  Query helpers
# --------------------------------------------------------------------------- #
def query_all(sql: str, params: Sequence[Any] = ()) -> list[dict]:
    with cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchall() or []


def query_one(sql: str, params: Sequence[Any] = ()) -> dict | None:
    with cursor() as cur:
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
        return row or None


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """Returns lastrowid for INSERT, rowcount otherwise."""
    with cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.lastrowid or cur.rowcount


def execute_many(sql: str, seq: Iterable[Sequence[Any]]) -> int:
    with cursor() as cur:
        cur.executemany(sql, [tuple(p) for p in seq])
        return cur.rowcount


# --------------------------------------------------------------------------- #
#  Startup check
# --------------------------------------------------------------------------- #
REQUIRED_TABLES = (
    "users", "admins", "sessions", "password_resets", "credit_ledger",
    "jobs", "payments", "rulesets", "rate_limits", "audit_log",
    "contact_messages",
)


def init_db() -> None:
    """
    Verify the database is reachable and the schema is present.

    Raises on failure. Callers must NOT wrap this in a bare except —
    if the schema is missing you want to know at boot, not at the first
    signup attempt three days later.
    """
    try:
        with cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
            cur.execute(
                "SELECT table_name AS tbl_name FROM information_schema.tables "
                "WHERE table_schema = %s",
                (Config.DB_NAME,),
            )
            present = {
                (r["tbl_name"] if isinstance(r, dict) else r[0]).lower()
                for r in (cur.fetchall() or [])
            }
    except MySQLError as exc:
        raise RuntimeError(
            f"Cannot reach MySQL at {Config.DB_HOST}:{Config.DB_PORT} "
            f"as '{Config.DB_USER}' on database '{Config.DB_NAME}'. "
            f"Driver said: {exc}"
        ) from exc

    missing = [t for t in REQUIRED_TABLES if t not in present]
    if missing:
        raise RuntimeError(
            "Database is reachable but the schema is incomplete. "
            f"Missing tables: {', '.join(missing)}. "
            "Import schema.sql through phpMyAdmin before starting the app."
        )

    log.info("Database OK — %d tables present.", len(present))
