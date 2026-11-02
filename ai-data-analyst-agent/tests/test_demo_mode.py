from app.agent.demo_mode import demo_sql
from app.database.seed import initialize_database
from app.database.db import execute_readonly_query


def test_demo_revenue_query_executes(tmp_path):
    sql, explanation = demo_sql("What is the total revenue?")
    path = initialize_database(tmp_path / "test.db")
    columns, rows, _ = execute_readonly_query(sql, db_path=path)
    assert "total_revenue" in columns
    assert len(rows) == 1
    assert rows[0]["total_revenue"] > 0
    assert explanation


def test_demo_top_products_returns_five_rows(tmp_path):
    sql, _ = demo_sql("Show the top 5 best-selling products.")
    path = initialize_database(tmp_path / "test.db")
    _, rows, _ = execute_readonly_query(sql, db_path=path)
    assert 1 <= len(rows) <= 5
