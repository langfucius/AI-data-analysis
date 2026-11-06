"""Regression coverage for query output and resource limits."""
import sqlite3

import pytest

from app.database.db import execute_readonly_query, get_schema


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "contract.db"
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE "odd""name" (value INTEGER)')
    return path


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_row_limits(database, limit):
    with pytest.raises(ValueError, match="positive integer"):
        execute_readonly_query("SELECT 1", database, max_rows=limit)


@pytest.mark.parametrize("budget", [0, -1, float("inf"), float("nan")])
def test_invalid_timeouts(database, budget):
    with pytest.raises(ValueError, match="finite and positive"):
        execute_readonly_query("SELECT 1", database, timeout_seconds=budget)


def test_duplicate_columns_cannot_silently_discard_values(database):
    with pytest.raises(ValueError, match="unique SQL aliases"):
        execute_readonly_query("SELECT 1 AS value, 2 AS value", database)
    columns, rows, truncated = execute_readonly_query(
        "SELECT 1 AS first_value, 2 AS second_value", database
    )
    assert columns == ["first_value", "second_value"]
    assert rows == [{"first_value": 1, "second_value": 2}]
    assert not truncated


def test_schema_quotes_identifiers(database):
    assert 'Table odd"name: value (INTEGER)' in get_schema(database)


def test_limit_preserves_truncation_signal(database):
    _, rows, truncated = execute_readonly_query(
        "SELECT 1 AS value UNION ALL SELECT 2", database, max_rows=1
    )
    assert rows == [{"value": 1}]
    assert truncated
