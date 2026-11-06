"""Agent integration and failure boundaries, with no external API calls."""
import json
import sqlite3
from types import SimpleNamespace

import pytest

from app.agent import graph, llm
from app.analytics.advanced_report import grounded_report
from app.analytics.advanced_result import AnalysisResult


@pytest.fixture
def agent_stubs(monkeypatch):
    monkeypatch.setattr(graph, "get_openai_api_key", lambda: "test-key")
    monkeypatch.setattr(graph, "generate_sql", lambda *_: ("SELECT total_amount FROM orders", "test", "openai"))
    monkeypatch.setattr(graph, "summarize_results", lambda **kwargs: kwargs["snapshot"].summary())
    return monkeypatch


def test_successful_snapshot_workflow(agent_stubs):
    agent_stubs.setattr(graph, "execute_readonly_query", lambda _: (["total_amount"], [{"total_amount": 12}, {"total_amount": 18}], False))
    state = graph.build_agent().invoke({"question": "Overview"})
    result = state["analysis_result"]
    assert result["loaded_row_count"] == 2
    assert result["profile"]["numeric_summary"][0]["sum"] == 30
    assert "mean=15.0" in state["analysis"]
    assert state["retry_count"] == 0
    assert state["chart_recommendations"]


def test_empty_results(agent_stubs):
    agent_stubs.setattr(graph, "execute_readonly_query", lambda _: (["total_amount"], [], False))
    state = graph.build_agent().invoke({"question": "Overview"})
    assert state["analysis_result"]["loaded_row_count"] == 0
    assert "No matching" in state["analysis"] and not state["error"]
    assert state["chart_recommendations"] == []


def test_truncated_scope_in_report(agent_stubs):
    agent_stubs.setattr(graph, "execute_readonly_query", lambda _: (["total_amount"], [{"total_amount": 10}], True))
    state = graph.build_agent().invoke({"question": "Overview"})
    assert state["analysis_result"]["truncated"]
    assert "truncated" in state["analysis"]


def test_generation_failure_returns_error(agent_stubs):
    def fail(*_):
        raise RuntimeError("LLM unavailable")
    agent_stubs.setattr(graph, "generate_sql", fail)
    state = graph.build_agent().invoke({"question": "Overview"})
    assert state["error"] == "LLM unavailable"
    assert state["retry_count"] == 0


def test_summary_failure_retains_deterministic_evidence(agent_stubs):
    def fail(**_):
        raise RuntimeError("summary unavailable")
    agent_stubs.setattr(graph, "summarize_results", fail)
    state = graph.build_agent().invoke({"question": "Overview"})
    assert not state["error"] and "Loaded rows:" in state["analysis"]


def test_retry_limit(agent_stubs):
    agent_stubs.setattr(graph, "generate_sql", lambda *_: ("SELECT * FROM orders WHERE id =", "broken", "openai"))
    calls = []
    def repair(**_):
        calls.append(1)
        return "SELECT * FROM orders WHERE id =", "still broken"
    agent_stubs.setattr(graph, "repair_sql", repair)
    state = graph.build_agent().invoke({"question": "Overview"})
    assert state["error"] and len(calls) == graph.MAX_REPAIRS
    assert state["retry_count"] == state["repair_attempts"] == graph.MAX_REPAIRS


def test_repaired_sql_must_be_validated_again(agent_stubs):
    agent_stubs.setattr(graph, "generate_sql", lambda *_: ("SELECT * FROM orders WHERE id =", "broken", "openai"))
    agent_stubs.setattr(graph, "repair_sql", lambda **_: ("DELETE FROM orders", "unsafe"))
    def never(*_):
        pytest.fail("Unsafe repaired SQL executed")
    agent_stubs.setattr(graph, "execute_readonly_query", never)
    state = graph.build_agent().invoke({"question": "Overview"})
    assert "Only read-only SELECT" in state["error"]
    assert state["retry_count"] == 1


def test_execution_syntax_error_can_be_repaired(agent_stubs):
    calls = []
    def execute(_):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("no such column: bad")
        return ["total"], [{"total": 3}], False
    agent_stubs.setattr(graph, "execute_readonly_query", execute)
    agent_stubs.setattr(graph, "repair_sql", lambda **_: ("SELECT COUNT(*) AS total FROM orders", "fixed"))
    state = graph.build_agent().invoke({"question": "Overview"})
    assert not state["error"] and state["retry_count"] == 1


def test_execution_permission_error_never_repaired(agent_stubs):
    def execute(_):
        raise sqlite3.DatabaseError("not authorized")
    def never(**_):
        pytest.fail("Permission failure repaired")
    agent_stubs.setattr(graph, "execute_readonly_query", execute)
    agent_stubs.setattr(graph, "repair_sql", never)
    state = graph.build_agent().invoke({"question": "Overview"})
    assert state["retry_count"] == 0 and state["error"]


def test_report_llm_selects_only_real_evidence():
    result = AnalysisResult.from_query(["value"], [{"value": 10}, {"value": 20}])
    def client(payload):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response)))
    text = grounded_report(result, lambda: client({"evidence_ids": ["metric_0"], "prose": "Revenue is 999999"}), "test", "openai")
    assert "AI-selected" in text and "999999" not in text and "mean=15.0" in text
    assert grounded_report(result, lambda: client({"evidence_ids": ["invented"]}), "test", "openai") == result.summary()


def test_real_demo_agent_and_api(monkeypatch):
    monkeypatch.setattr(llm, "get_openai_api_key", lambda: "")
    state = graph.run_analysis("Show monthly revenue trends.")
    assert state["mode"] == "demo" and not state["error"]
    assert state["analysis_result"]["loaded_row_count"] == len(state["rows"])
    from fastapi.testclient import TestClient
    from app.api.main import app
    response = TestClient(app).post("/analyze", json={"question": "What is the total revenue?"})
    assert response.status_code == 200, response.text
    assert response.json()["analysis_result"]["rows"] == response.json()["rows"]


def test_empty_question():
    assert graph.run_analysis("   ")["error"]
