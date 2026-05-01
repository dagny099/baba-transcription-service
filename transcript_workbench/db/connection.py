"""SQLite connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Lightweight migrations for databases created before a column existed.
# `CREATE TABLE IF NOT EXISTS` won't add columns to an already-existing table,
# so each new column needs an explicit `ALTER TABLE ADD COLUMN`.
_MIGRATIONS: list[tuple[str, str, str]] = [
    # (table, column, definition)
    ("provider_runs", "cost_rate_usd", "REAL"),
    ("provider_runs", "cost_unit", "TEXT"),
]


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database(db_path: Path, schema_path: Path = SCHEMA_PATH) -> None:
    """Idempotently create the schema and apply pending column migrations."""
    conn = get_connection(db_path)
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        _apply_column_migrations(conn)
        conn.commit()
    finally:
        conn.close()


def _apply_column_migrations(conn: sqlite3.Connection) -> None:
    for table, column, definition in _MIGRATIONS:
        if not _column_exists(conn, table, column):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)
