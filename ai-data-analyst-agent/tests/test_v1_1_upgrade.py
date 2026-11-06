from pathlib import Path

import app.agent.graph as graph
from app.agent.sql_safety import validate_sql


def test_missing_limit_is_added(monkeypatch):
    monkeypatch.setattr(
        "app.agent.sql_safety.get_max_rows", lambda: 100
    )
    sql = validate_sql("SELECT * FROM orders", {"orders"})
    assert "LIMIT 100" in sql.upper()


def test_large_limit_is_clamped(monkeypatch):
    monkeypatch.setattr(
        "app.agent.sql_safety.get_max_rows", lambda: 100
    )
    sql = validate_sql(
        "SELECT * FROM orders LIMIT 999999", {"orders"}
    )
    assert "LIMIT 100" in sql.upper()


def test_small_limit_is_preserved(monkeypatch):
    monkeypatch.setattr(
        "app.agent.sql_safety.get_max_rows", lambda: 100
    )
    sql = validate_sql(
        "SELECT * FROM orders LIMIT 10", {"orders"}
    )
    assert "LIMIT 10" in sql.upper()


def test_negative_limit_is_clamped(monkeypatch):
    monkeypatch.setattr(
        "app.agent.sql_safety.get_max_rows", lambda: 100
    )
    sql = validate_sql(
        "SELECT * FROM orders LIMIT -1", {"orders"}
    )
    assert "LIMIT 100" in sql.upper()


def test_agent_repairs_sql_syntax_error(monkeypatch):
    monkeypatch.setattr(graph, 'get_openai_api_key', lambda: 'mock-key')
    monkeypatch.setattr(
        graph, "ensure_database", lambda: Path("fake.db")
    )
    monkeypatch.setattr(
        graph, "get_schema",
        lambda _path: "Table orders: id INTEGER"
    )
    monkeypatch.setattr(
        graph, "get_table_names", lambda _path: {"orders"}
    )
    monkeypatch.setattr(
        graph,
        "generate_sql",
        lambda _q, _s: (
            "SELECT * FROM orders WHERE id =",
            "broken",
            "openai",
        ),
    )

    repair_calls = []

    def fake_repair(**kwargs):
        repair_calls.append(kwargs)
        return (
            "SELECT COUNT(*) AS total FROM orders",
            "fixed",
        )

    monkeypatch.setattr(graph, "repair_sql", fake_repair)
    monkeypatch.setattr(
        graph,
        "execute_readonly_query",
        lambda _sql: (["total"], [{"total": 3}], False),
    )
    monkeypatch.setattr(
        graph, "summarize_results",
        lambda **_kwargs: "Analysis OK",
    )

    result = graph.build_agent().invoke(
        {"question": "How many orders?"}
    )

    assert result["analysis"] == "Analysis OK"
    assert result["retry_count"] == 1
    assert len(repair_calls) == 1


def test_agent_does_not_repair_safety_violation(monkeypatch):
    monkeypatch.setattr(
        graph, "ensure_database", lambda: Path("fake.db")
    )
    monkeypatch.setattr(
        graph, "get_schema",
        lambda _path: "Table orders: id INTEGER"
    )
    monkeypatch.setattr(
        graph, "get_table_names", lambda _path: {"orders"}
    )
    monkeypatch.setattr(
        graph,
        "generate_sql",
        lambda _q, _s: (
            "DELETE FROM orders",
            "unsafe",
            "openai",
        ),
    )

    def forbidden_repair(**_kwargs):
        raise AssertionError(
            "Safety violations must not enter the repair workflow."
        )

    monkeypatch.setattr(graph, "repair_sql", forbidden_repair)

    result = graph.build_agent().invoke(
        {"question": "Delete orders"}
    )

    assert "Only read-only SELECT queries are allowed" in result["analysis"]

