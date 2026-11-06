"""LangGraph workflow with bounded SQL self-repair."""

from __future__ import annotations

from typing import Any, TypedDict
from time import perf_counter
import sqlite3

from app.analytics.advanced_service import snapshot_from_agent
from app.analytics.advanced_visualization import recommend_charts
from dataclasses import asdict

from langgraph.graph import END, START, StateGraph

from app.agent.llm import (
    generate_sql,
    summarize_results,
    repair_sql,
)
from app.agent.sql_safety import validate_sql, SQLSafetyError, SQLSyntaxError
from app.core.config import get_openai_api_key
from app.database.db import (
    ensure_database,
    execute_readonly_query,
    get_schema,
    get_table_names,
)

MAX_REPAIRS = 2


class AgentState(TypedDict, total=False):
    original_question: str
    conversation_context: list[dict]
    answer_template: str
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
    repair_attempts: int
    retry_count: int
    safety_violation: bool
    repairable: bool
    execution_seconds: float
    analysis_result: dict[str, Any]
    chart_recommendations: list[dict[str, Any]]


def inspect_schema_node(state: AgentState) -> dict[str, Any]:
    db_path = ensure_database()
    return {
        "schema": get_schema(db_path),
        "error": "",
        "repair_attempts": 0,
        "retry_count": 0,
        "safety_violation": False,
    }


def generate_sql_node(state: AgentState) -> dict[str, Any]:
    try:
        query_question = state['question']
        if state.get('original_question'):
            query_question = ('用户原问题：' + state['original_question'] + '\n上下文补全后的问题：' + state['question']
                              + '\n必须回答原问题；补全只解析指代，不得替换任务。')
        sql, explanation, mode = generate_sql(
            query_question, state.get("schema", "")
        )

        return {
            "sql": sql,
            "sql_explanation": explanation,
            "mode": mode,
            "error": "",
        }

    except Exception as exc:
        return {"error": str(exc)}


def validate_sql_node(state: AgentState) -> dict[str, Any]:
    try:
        db_path = ensure_database()
        safe_sql = validate_sql(
            state.get("sql", ""),
            get_table_names(db_path),
        )

        return {"sql": safe_sql, "error": "", "safety_violation": False, "repairable": False}

    except SQLSafetyError as exc:
        return {"error": str(exc), "safety_violation": True, "repairable": False}
    except SQLSyntaxError as exc:
        return {"error": str(exc), "repairable": True}

    except Exception as exc:
        return {"error": str(exc)}


def execute_query_node(state: AgentState) -> dict[str, Any]:
    started = perf_counter()
    try:
        columns, rows, truncated = execute_readonly_query(
            state["sql"]
        )

        if len(set(columns)) != len(columns):
            return {"error": "Query columns must have unique names; use SQL aliases.", "repairable": False}

        return {
            "execution_seconds": perf_counter() - started,
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
            "error": "",
        }

    except Exception as exc:
        return {"error": f"Query execution failed: {exc}",
                "repairable": isinstance(exc, sqlite3.OperationalError) and any(t in str(exc).lower() for t in ("syntax", "no such column", "ambiguous", "incomplete input"))}


def repair_sql_node(state: AgentState) -> dict[str, Any]:
    attempts = state.get("repair_attempts", 0)

    if attempts >= MAX_REPAIRS:
        return {"error": state.get("error", "Repair limit reached.")}

    if state.get("mode") != "openai" or not get_openai_api_key():
        return {"error": state.get("error", "SQL repair requires an API key.")}

    try:
        sql, explanation = repair_sql(
            question=state.get("question", ""),
            schema=state.get("schema", ""),
            failed_sql=state.get("sql", ""),
            error=state.get("error", ""),
        )

        return {
            "sql": sql,
            "sql_explanation": explanation,
            "repair_attempts": attempts + 1,
            "retry_count": attempts + 1,
            "error": "",
        }

    except Exception as exc:
        return {
            "repair_attempts": attempts + 1,
            "retry_count": attempts + 1,
            "error": f"SQL repair failed: {exc}",
        }


def analyze_results_node(state: AgentState) -> dict[str, Any]:
    snapshot = snapshot_from_agent(dict(state))
    try:
        analysis = summarize_results(
            question=state.get("question", ""), sql=state.get("sql", ""),
            columns=snapshot.columns, rows=snapshot.rows, mode=state.get("mode", "demo"), snapshot=snapshot,
            answer_template=state.get('answer_template'),
            original_question=state.get('original_question'),
            conversation_context=state.get('conversation_context'),
        )
    except Exception:
        analysis = ('查询已完成，但本次文字解释生成失败。请重试；下方仍可查看查询数据与 SQL。'
                    if state.get('answer_template') is not None else snapshot.summary())
    return {"analysis": analysis, "error": "", "analysis_result": snapshot.to_dict(),
            "chart_recommendations": [asdict(s) for s in recommend_charts(snapshot)]}



def handle_error_node(state: AgentState) -> dict[str, Any]:
    question = state.get("question", "")

    if any("\u4e00" <= c <= "\u9fff" for c in question):
        message = (
            "### 本次分析未能完成\n\n"
            f"{state.get('error', '发生未知错误')}\n\n"
            f"SQL 自动修复尝试次数：{state.get('repair_attempts', 0)}"
        )
    else:
        message = (
            "### Analysis could not be completed\n\n"
            f"{state.get('error', 'Unknown error')}\n\n"
            f"SQL repair attempts: {state.get('repair_attempts', 0)}"
        )

    return {"analysis": message}


def _can_repair(state: AgentState) -> bool:
    return (
        state.get("repairable", False)
        and not state.get("safety_violation", False)
        and state.get("mode") == "openai"
        and bool(get_openai_api_key())
        and state.get("repair_attempts", 0) < MAX_REPAIRS
    )


def _route_after_generation(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "validate_sql"


def _route_after_sql_step(state: AgentState) -> str:
    if not state.get("error"):
        return "continue"

    return "repair_sql" if _can_repair(state) else "handle_error"


def _route_after_repair(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"

    return "validate_sql"


def build_agent():
    workflow = StateGraph(AgentState)

    workflow.add_node("inspect_schema", inspect_schema_node)
    workflow.add_node("generate_sql", generate_sql_node)
    workflow.add_node("validate_sql", validate_sql_node)
    workflow.add_node("execute_query", execute_query_node)
    workflow.add_node("repair_sql", repair_sql_node)
    workflow.add_node("analyze_results", analyze_results_node)
    workflow.add_node("handle_error", handle_error_node)

    workflow.add_edge(START, "inspect_schema")
    workflow.add_edge("inspect_schema", "generate_sql")

    workflow.add_conditional_edges(
        "generate_sql",
        _route_after_generation,
        {
            "validate_sql": "validate_sql",
            "handle_error": "handle_error",
        },
    )

    workflow.add_conditional_edges(
        "validate_sql",
        _route_after_sql_step,
        {
            "continue": "execute_query",
            "repair_sql": "repair_sql",
            "handle_error": "handle_error",
        },
    )

    workflow.add_conditional_edges(
        "execute_query",
        _route_after_sql_step,
        {
            "continue": "analyze_results",
            "repair_sql": "repair_sql",
            "handle_error": "handle_error",
        },
    )

    workflow.add_conditional_edges(
        "repair_sql",
        _route_after_repair,
        {
            "validate_sql": "validate_sql",
            "handle_error": "handle_error",
        },
    )

    workflow.add_edge("analyze_results", END)
    workflow.add_edge("handle_error", END)

    return workflow.compile()


agent_graph = build_agent()


def run_analysis(question: str, history: list[dict] | None = None, answer_template: str | None = None) -> dict[str, Any]:
    question = question.strip()

    if not question:
        return {
            "error": "Question cannot be empty.",
            "analysis": "请输入一个问题。",
        }

    from app.agent.dialogue import plan_turn
    from app.agent.answer_templates import TEMPLATES, instructions
    if answer_template is not None and answer_template not in TEMPLATES:
        return {'error':'未知回答模板','analysis':'请选择有效的回答模板。'}
    try:
        planning_question = question
        if answer_template is not None:
            planning_question += '\n用户选择的回答模板：' + instructions(answer_template) + '\n模板仅指导方法，不改变原问题的意图。数据检验应查询可逐项解释的证据，不要把不同检查的数值按section相加。'
        plan = plan_turn(planning_question, history, get_schema())
    except Exception as exc:
        return {"question": question, "error": str(exc), "analysis": "回答服务暂时不可用，请检查 API 连接。"}
    if plan['intent'] != 'query':
        return {"question": question, "analysis": plan['answer'], "mode": "conversation", "intent": plan['intent'], "error": ""}
    initial = {"question": plan['question']}
    initial['original_question'] = question
    from app.agent.dialogue import compact_history
    initial['conversation_context'] = compact_history(history)
    if answer_template is not None:
        initial['answer_template'] = answer_template
    result = agent_graph.invoke(initial)
    result['resolved_question'] = plan['question']
    result['question'] = question
    return dict(result)
