"""OpenAI integration with bilingual local Demo Mode."""
from __future__ import annotations

import json
import os
from typing import Any

from app.agent.demo_mode import demo_sql
from app.core.config import get_openai_api_key, get_openai_model


def _get_client():
    from openai import OpenAI

    kwargs = {
        "api_key": get_openai_api_key(),
        "timeout": 45.0,
        "max_retries": 2,
    }

    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if base_url:
        kwargs["base_url"] = base_url

    return OpenAI(**kwargs)


def _is_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def generate_sql(question: str, schema: str) -> tuple[str, str, str]:
    """Return SQL, explanation and execution mode."""

    api_key = get_openai_api_key()

    if not api_key:
        if schema.startswith('Table uploaded_data:'):
            if any(word in question.lower() for word in ('多少', '行数', 'count', 'how many')):
                return 'SELECT COUNT(*) AS row_count FROM uploaded_data', '统计上传数据的总行数。', 'demo'
            if any(word in question.lower() for word in ('预览', 'preview', '查看数据')):
                return 'SELECT * FROM uploaded_data LIMIT 100', '无 API 模式展示前 100 行；自由分析请配置 API。', 'demo'
            raise ValueError('上传数据的 Demo 模式仅支持预览和行数查询；自由分析请配置模型 API。')
        sql, explanation = demo_sql(question)
        return sql, explanation, "demo"

    try:
        client = _get_client()

        response = client.chat.completions.create(
            model=get_openai_model(),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful SQLite analytics engineer. "
                        "Return JSON with exactly two keys: sql and explanation. "
                        "Generate exactly one read-only SELECT query. "
                        "Use only tables and columns in the supplied schema. "
                        "Never generate INSERT, UPDATE, DELETE, DROP, ALTER, "
                        "PRAGMA, ATTACH, or multiple statements. "
                        "Do not invent columns. Use SQLite syntax. "
                        "The application applies an automatic row limit."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Database schema:\n{schema}\n\n"
                        f"Question:\n{question}"
                    ),
                },
            ],
        )

        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)

        sql = str(payload.get("sql", "")).strip()
        explanation = str(
            payload.get("explanation", "Generated SQL query.")
        ).strip()

        if not sql:
            raise ValueError("The model returned an empty SQL query.")

        return sql, explanation, "openai"

    except Exception as exc:
        raise RuntimeError(
            "OpenAI SQL generation failed. Check your API key, model name, "
            f"API Base URL, network connection, and quota. Details: {exc}"
        ) from exc


def summarize_results(
    question: str,
    sql: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    mode: str,
    snapshot: Any = None,
    answer_template: str | None = None,
    original_question: str | None = None,
    conversation_context: list | None = None,
) -> str:

    from app.analytics.advanced_result import AnalysisResult
    from app.analytics.advanced_report import grounded_report
    result = snapshot if snapshot is not None else AnalysisResult.from_query(columns, rows, question=question, sql=sql)
    if answer_template is not None:
        from app.agent.answer_templates import explain_result
        return explain_result(result, answer_template, _get_client if get_openai_api_key() else None, get_openai_model(),
                              original_question=original_question, conversation_context=conversation_context)
    return grounded_report(result, _get_client if get_openai_api_key() else None,
                           get_openai_model(), mode)


def _local_summary(
    rows: list[dict[str, Any]],
    question: str = "",
) -> str:

    count = len(rows)
    first = rows[0]

    preview = ", ".join(
        f"{key}: {value}"
        for key, value in list(first.items())[:4]
    )

    if _is_chinese(question):
        return (
            f"查询成功，共返回 **{count}** 条记录。\n\n"
            f"首条结果摘要：{preview}。\n\n"
            "当前处于 Demo Mode，结果来自本地示例数据库。"
            "配置 OpenAI API Key 后，可以支持更广泛的自然语言 SQL "
            "生成和更深入的数据解释。"
        )

    return (
        f"Query completed successfully and returned **{count}** row(s).\n\n"
        f"First-row preview: {preview}.\n\n"
        "You are currently using Demo Mode with the local sample database. "
        "Configure an OpenAI API key for broader natural-language SQL "
        "generation and deeper data analysis."
    )


# INSIGHTAI_V2_SQL_REPAIR_BEGIN
def repair_sql(
    question: str,
    schema: str,
    failed_sql: str,
    error: str,
) -> tuple[str, str]:
    """Ask the configured LLM to repair a failed read-only SQL query."""

    client = _get_client()

    response = client.chat.completions.create(
        model=get_openai_model(),
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a SQLite SQL repair engineer. "
                    "Return JSON with exactly two keys: sql and explanation. "
                    "Repair the SQL based on the supplied error. "
                    "Generate exactly one read-only SELECT query. "
                    "Use only the supplied schema. "
                    "Never generate writes, DDL, PRAGMA, ATTACH, "
                    "multiple statements, or invented columns."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n"
                    f"Schema: {schema}\n"
                    f"Failed SQL: {failed_sql}\n"
                    f"Error: {error}"
                ),
            },
        ],
    )

    payload = json.loads(
        response.choices[0].message.content or "{}"
    )

    sql = str(payload.get("sql", "")).strip()
    explanation = str(
        payload.get("explanation", "Repaired SQL query.")
    ).strip()

    if not sql:
        raise ValueError("The model returned empty repaired SQL.")

    return sql, explanation
# INSIGHTAI_V2_SQL_REPAIR_END
