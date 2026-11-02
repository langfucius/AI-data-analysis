import pytest

from app.agent.sql_safety import SQLSafetyError, validate_sql


TABLES = {"orders", "customers", "products", "order_items"}


def test_select_query_is_allowed_and_limited():
    sql = validate_sql("SELECT order_id, total_amount FROM orders", TABLES)
    assert "SELECT" in sql.upper()
    assert "LIMIT" in sql.upper()


def test_existing_limit_is_preserved():
    sql = validate_sql("SELECT * FROM orders LIMIT 5", TABLES)
    assert "LIMIT 5" in sql.upper()


def test_unknown_table_is_rejected():
    with pytest.raises(SQLSafetyError, match="not allowed"):
        validate_sql("SELECT * FROM secret_table", TABLES)


def test_write_statement_is_rejected():
    with pytest.raises(SQLSafetyError, match="SELECT"):
        validate_sql("DELETE FROM orders", TABLES)


def test_multiple_statements_are_rejected():
    with pytest.raises(SQLSafetyError, match="one SQL statement"):
        validate_sql("SELECT * FROM orders; DROP TABLE orders", TABLES)


def test_dangerous_sqlite_function_is_rejected():
    with pytest.raises(SQLSafetyError, match="blocked"):
        validate_sql("SELECT load_extension('malicious')", TABLES)


def test_cte_is_allowed_when_base_table_is_allowed():
    sql = validate_sql(
        "WITH recent AS (SELECT order_id FROM orders) SELECT * FROM recent",
        TABLES
    )
    assert "WITH" in sql.upper()
