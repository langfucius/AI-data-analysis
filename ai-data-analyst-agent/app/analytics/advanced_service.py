"""Validated query entry point and snapshot adapter for the existing Agent."""
from __future__ import annotations

from time import perf_counter
from typing import Any

from app.agent.sql_safety import validate_sql
from app.analytics.advanced_result import AnalysisResult
from app.database.db import ensure_database, execute_readonly_query, get_table_names


def analyze_sql(sql: str, question: str = "") -> AnalysisResult:
    started = perf_counter()
    path = ensure_database()
    safe_sql = validate_sql(sql, get_table_names(path))
    columns, rows, truncated = execute_readonly_query(safe_sql, path)
    return AnalysisResult.from_query(columns, rows, question=question, sql=safe_sql, truncated=truncated,
                                     execution_metadata={"duration_seconds": perf_counter() - started, "mode": "sql", "read_only": True})


def snapshot_from_agent(state: dict[str, Any]) -> AnalysisResult:
    if state.get("analysis_result"):
        return AnalysisResult.from_dict(state["analysis_result"])
    return AnalysisResult.from_query(state.get("columns", []), state.get("rows", []),
                                     question=state.get("question", ""), sql=state.get("sql", ""),
                                     truncated=state.get("truncated", False),
                                     execution_metadata={"mode": state.get("mode", "demo"), "read_only": True,
                                                         "retry_count": state.get("retry_count", 0),
                                                         "duration_seconds": state.get("execution_seconds", 0)})
