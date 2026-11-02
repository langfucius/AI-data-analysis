"""LangGraph workflow for the AI Data Analyst Agent."""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.llm import generate_sql, summarize_results
from app.agent.sql_safety import validate_sql
from app.database.db import (
    ensure_database, execute_readonly_query, get_schema, get_table_names
)


class AgentState(TypedDict, total=False):
    question: str
    schema: str
    sql: str
    sql_explanation: str
    mode: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool
    analysis: str
    error: str


def inspect_schema_node(state: AgentState) -> dict[str, Any]:
    db_path = ensure_database()
    return {"schema": get_schema(db_path), "error": ""}


def generate_sql_node(state: AgentState) -> dict[str, Any]:
    try:
        sql, explanation, mode = generate_sql(
            state["question"], state.get("schema", "")
        )
        return {
            "sql": sql,
            "sql_explanation": explanation,
            "mode": mode,
            "error": ""
        }
    except Exception as exc:
        return {"error": str(exc)}


def validate_sql_node(state: AgentState) -> dict[str, Any]:
    try:
        db_path = ensure_database()
        safe_sql = validate_sql(state.get("sql", ""), get_table_names(db_path))
        return {"sql": safe_sql, "error": ""}
    except Exception as exc:
        return {"error": str(exc)}


def execute_query_node(state: AgentState) -> dict[str, Any]:
    try:
        columns, rows, truncated = execute_readonly_query(state["sql"])
        return {
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
            "error": ""
        }
    except Exception as exc:
        return {"error": f"Query execution failed: {exc}"}


def analyze_results_node(state: AgentState) -> dict[str, Any]:
    analysis = summarize_results(
        question=state.get("question", ""),
        sql=state.get("sql", ""),
        columns=state.get("columns", []),
        rows=state.get("rows", []),
        mode=state.get("mode", "demo"),
    )
    return {"analysis": analysis}


def handle_error_node(state: AgentState) -> dict[str, Any]:
    return {
        "analysis": (
            "### 无法完成本次分析\n\n"
            f"{state.get('error', '发生未知错误')}\n\n"
            "请检查问题、数据库 Schema 或 SQL 安全限制后重试。"
        )
    }


def _route_after_step(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "continue"


def build_agent():
    workflow = StateGraph(AgentState)
    workflow.add_node("inspect_schema", inspect_schema_node)
    workflow.add_node("generate_sql", generate_sql_node)
    workflow.add_node("validate_sql", validate_sql_node)
    workflow.add_node("execute_query", execute_query_node)
    workflow.add_node("analyze_results", analyze_results_node)
    workflow.add_node("handle_error", handle_error_node)

    workflow.add_edge(START, "inspect_schema")
    workflow.add_edge("inspect_schema", "generate_sql")
    workflow.add_conditional_edges(
        "generate_sql", _route_after_step,
        {"continue": "validate_sql", "handle_error": "handle_error"}
    )
    workflow.add_conditional_edges(
        "validate_sql", _route_after_step,
        {"continue": "execute_query", "handle_error": "handle_error"}
    )
    workflow.add_conditional_edges(
        "execute_query", _route_after_step,
        {"continue": "analyze_results", "handle_error": "handle_error"}
    )
    workflow.add_edge("analyze_results", END)
    workflow.add_edge("handle_error", END)
    return workflow.compile()


agent_graph = build_agent()


def run_analysis(question: str) -> dict[str, Any]:
    question = question.strip()
    if not question:
        return {"error": "Question cannot be empty.", "analysis": "请输入一个问题。"}
    result = agent_graph.invoke({"question": question})
    return dict(result)
