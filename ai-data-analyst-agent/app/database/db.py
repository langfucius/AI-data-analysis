"""Read-only database access helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.core.config import get_db_path, get_max_rows
from app.database.seed import initialize_database


def ensure_database() -> Path:
    path = get_db_path()
    if not path.exists():
        initialize_database(path)
    return path


def _readonly_connection(path: Path) -> sqlite3.Connection:
    # Path.as_uri() works on Windows and POSIX; mode=ro prevents database writes.
    uri = path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def get_table_names(db_path: Path | str | None = None) -> set[str]:
    path = Path(db_path) if db_path else ensure_database()
    with _readonly_connection(path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return {row["name"] for row in rows}


def get_schema(db_path: Path | str | None = None) -> str:
    path = Path(db_path) if db_path else ensure_database()
    lines: list[str] = []
    with _readonly_connection(path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for row in tables:
            table = row["name"]
            columns = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            column_text = ", ".join(
                f'{col["name"]} ({col["type"]})' for col in columns
            )
            lines.append(f"Table {table}: {column_text}")
    return "\n".join(lines)


def _authorizer(action: int, arg1: str | None, arg2: str | None,
                db_name: str | None, trigger_name: str | None) -> int:
    denied_names = [
        "SQLITE_INSERT", "SQLITE_UPDATE", "SQLITE_DELETE",
        "SQLITE_CREATE_INDEX", "SQLITE_CREATE_TABLE", "SQLITE_CREATE_TEMP_INDEX",
        "SQLITE_CREATE_TEMP_TABLE", "SQLITE_CREATE_TEMP_TRIGGER",
        "SQLITE_CREATE_TEMP_VIEW", "SQLITE_CREATE_TRIGGER", "SQLITE_CREATE_VIEW",
        "SQLITE_DROP_INDEX", "SQLITE_DROP_TABLE", "SQLITE_DROP_TEMP_INDEX",
        "SQLITE_DROP_TEMP_TABLE", "SQLITE_DROP_TEMP_TRIGGER", "SQLITE_DROP_TEMP_VIEW",
        "SQLITE_DROP_TRIGGER", "SQLITE_DROP_VIEW", "SQLITE_ALTER_TABLE",
        "SQLITE_ATTACH", "SQLITE_DETACH", "SQLITE_PRAGMA", "SQLITE_REINDEX",
        "SQLITE_ANALYZE", "SQLITE_TRANSACTION", "SQLITE_SAVEPOINT",
    ]
    denied = {getattr(sqlite3, name) for name in denied_names if hasattr(sqlite3, name)}
    if action in denied:
        return sqlite3.SQLITE_DENY
    if action == getattr(sqlite3, "SQLITE_FUNCTION", -1):
        function_name = (arg2 or arg1 or "").lower()
        if function_name in {"load_extension", "readfile", "writefile"}:
            return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def execute_readonly_query(
    sql: str,
    db_path: Path | str | None = None,
    max_rows: int | None = None,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    path = Path(db_path) if db_path else ensure_database()
    row_limit = max_rows or get_max_rows()
    conn = _readonly_connection(path)
    try:
        conn.set_authorizer(_authorizer)
        cursor = conn.execute(sql)
        columns = [item[0] for item in (cursor.description or [])]
        raw_rows = cursor.fetchmany(row_limit + 1)
        truncated = len(raw_rows) > row_limit
        raw_rows = raw_rows[:row_limit]
        rows = [dict(row) for row in raw_rows]
        return columns, rows, truncated
    finally:
        conn.close()
