from app.database.seed import initialize_database
from app.database.db import get_schema, get_table_names, execute_readonly_query


def test_seed_database_has_expected_tables(tmp_path):
    path = initialize_database(tmp_path / "test.db")
    tables = get_table_names(path)
    assert {"customers", "products", "orders", "order_items"} <= tables


def test_schema_contains_orders(tmp_path):
    path = initialize_database(tmp_path / "test.db")
    schema = get_schema(path)
    assert "Table orders" in schema
    assert "total_amount" in schema


def test_readonly_query_returns_rows(tmp_path):
    path = initialize_database(tmp_path / "test.db")
    columns, rows, truncated = execute_readonly_query(
        "SELECT order_id, status FROM orders LIMIT 3",
        db_path=path,
        max_rows=10,
    )
    assert columns == ["order_id", "status"]
    assert len(rows) == 3
    assert truncated is False
