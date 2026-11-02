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
) -> str:

    if not rows:
        if _is_chinese(question):
            return (
                "查询已成功执行，但没有返回符合条件的数据。"
                "可以尝试调整问题或时间范围。"
            )
        return (
            "The query ran successfully but returned no matching rows. "
            "Try adjusting your filters or time range."
        )

    api_key = get_openai_api_key()

    if api_key and mode == "openai":
        try:
            client = _get_client()

            response = client.chat.completions.create(
                model=get_openai_model(),
                temperature=0.2,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a professional business data analyst. "
                            "Explain query results concisely and accurately. "
                            "Use only the supplied data. Do not invent facts "
                            "or claim unsupported causation. "
                            "Answer in the same language as the user's question."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question: {question}\n"
                            f"SQL: {sql}\n"
                            f"Columns: {columns}\n"
                            f"Rows (up to 20): "
                            f"{json.dumps(rows[:20], ensure_ascii=False, default=str)}"
                        ),
                    },
                ],
            )

            return (
                response.choices[0].message.content
                or _local_summary(rows, question)
            )

        except Exception as exc:
            fallback = _local_summary(rows, question)

            if _is_chinese(question):
                return fallback + (
                    f"\n\n注意：AI 深度解释暂时不可用 "
                    f"({type(exc).__name__})，以上为本地数据摘要。"
                )

            return fallback + (
                f"\n\nNote: AI explanation was unavailable "
                f"({type(exc).__name__}). Showing a local data summary."
            )

    return _local_summary(rows, question)


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
