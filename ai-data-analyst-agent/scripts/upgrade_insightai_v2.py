from pathlib import Path
import ast
import shutil
import re
from datetime import datetime
import textwrap

ROOT = Path.cwd()

# --------------------------------------------------
# 1. Prepare UI patch before modifying any files
# --------------------------------------------------

ui_path = ROOT / "app/ui/streamlit_app.py"
ui_source = ui_path.read_text(encoding="utf-8-sig")
ui_tree = ast.parse(ui_source)

if "INSIGHTAI_V2_CHARTS_BEGIN" in ui_source:
    patched_ui = ui_source
else:
    streamlit_alias = "st"

    for node in ast.walk(ui_tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "streamlit":
                    streamlit_alias = alias.asname or "streamlit"

    candidates = []

    for node in ast.walk(ui_tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if not isinstance(value, ast.Call):
                continue

            func = value.func
            name = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute)
                else ""
            )

            if name == "run_analysis":
                target = node.targets[0] if isinstance(node, ast.Assign) else node.target
                if isinstance(target, ast.Name):
                    candidates.append((node, target.id))

    if not candidates:
        raise RuntimeError(
            "无法自动定位 UI 中的 run_analysis() 结果变量。"
            "为保护原 UI，本次没有修改任何项目文件。"
        )

    node, result_name = min(candidates, key=lambda x: x[0].lineno)

    snippet = f"""
# INSIGHTAI_V2_CHARTS_BEGIN
try:
    from app.analytics.chart_engine import create_charts
    from app.analytics.profile import build_profile

    _ia_result = {result_name}
    _ia_columns = _ia_result.get("columns", []) if isinstance(_ia_result, dict) else []
    _ia_rows = _ia_result.get("rows", []) if isinstance(_ia_result, dict) else []
    _ia_question = _ia_result.get("question", "") if isinstance(_ia_result, dict) else ""

    if _ia_columns and _ia_rows:
        _ia_figures = create_charts(
            _ia_columns, _ia_rows, question=str(_ia_question)
        )

        if _ia_figures:
            {streamlit_alias}.markdown("### 📊 Visual Analytics")
            for _ia_index, _ia_figure in enumerate(_ia_figures):
                {streamlit_alias}.plotly_chart(
                    _ia_figure,
                    use_container_width=True,
                    key=f"insightai_v2_chart_{{_ia_index}}"
                )
        else:
            {streamlit_alias}.info("当前查询结果不适合自动生成图表。")

        _ia_profile = build_profile(_ia_columns, _ia_rows)

        with {streamlit_alias}.expander("📈 Statistical Profile", expanded=False):
            _ia_c1, _ia_c2, _ia_c3 = {streamlit_alias}.columns(3)
            _ia_c1.metric("Rows", _ia_profile["row_count"])
            _ia_c2.metric("Columns", _ia_profile["column_count"])
            _ia_c3.metric("Missing Cells", _ia_profile["missing_cells"])

            if not _ia_profile["numeric_summary"].empty:
                {streamlit_alias}.markdown("**Numeric Statistics**")
                {streamlit_alias}.dataframe(
                    _ia_profile["numeric_summary"],
                    use_container_width=True,
                    hide_index=True
                )

            if _ia_profile["correlation"] is not None:
                {streamlit_alias}.markdown("**Correlation Matrix**")
                {streamlit_alias}.dataframe(
                    _ia_profile["correlation"],
                    use_container_width=True
                )

except Exception as _ia_error:
    {streamlit_alias}.warning(
        f"Visualization unavailable: {{type(_ia_error).__name__}}"
    )
# INSIGHTAI_V2_CHARTS_END
"""

    lines = ui_source.splitlines(keepends=True)
    indent = re.match(r"^[ \t]*", lines[node.lineno - 1]).group(0)
    block = "\n".join(
        indent + line if line else ""
        for line in textwrap.dedent(snippet).strip().splitlines()
    ) + "\n"

    lines.insert(node.end_lineno, block)
    patched_ui = "".join(lines)

# --------------------------------------------------
# 2. Backup existing files
# --------------------------------------------------

backup = ROOT / ".insightai_backups" / datetime.now().strftime("%Y%m%d_%H%M%S")
backup.mkdir(parents=True, exist_ok=True)

for relative in [
    "app/agent/graph.py",
    "app/agent/llm.py",
    "app/ui/streamlit_app.py",
    "README.md",
]:
    source = ROOT / relative
    if source.exists():
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

print("Backup:", backup)

# --------------------------------------------------
# 3. Create Analytics Engine
# --------------------------------------------------

files = {}

files["app/analytics/__init__.py"] = '''"""InsightAI analytics package."""
'''

files["app/analytics/chart_engine.py"] = r'''
"""Deterministic chart selection and Plotly rendering."""

from dataclasses import dataclass
from typing import Literal
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


ChartType = Literal["line", "bar", "scatter", "histogram", "box"]


@dataclass(frozen=True)
class ChartSpec:
    chart_type: ChartType
    x: str
    y: str | None
    title: str
    reason: str


def _frame(columns, rows):
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    if columns:
        df = df[[c for c in columns if c in df.columns]]

    return df


def _is_id(name):
    return bool(
        re.search(
            r"(^|[_\W])(id|key|code|phone|zip|postal)([_\W]|$)",
            str(name),
            re.IGNORECASE,
        )
    )


def _dates(df):
    result = []

    keywords = (
        "date", "time", "month", "year",
        "日期", "时间", "月份", "年份",
    )

    for col in df.columns:
        is_datetime = pd.api.types.is_datetime64_any_dtype(df[col])

        if not is_datetime and not any(
            k in str(col).lower() for k in keywords
        ):
            continue

        parsed = pd.to_datetime(df[col], errors="coerce")

        if parsed.notna().mean() >= 0.7:
            result.append(col)

    return result


def _numbers(df, date_columns):
    result = []

    for col in df.columns:
        if col in date_columns or _is_id(col):
            continue

        values = pd.to_numeric(df[col], errors="coerce")

        if values.notna().mean() < 0.8:
            continue

        if values.nunique(dropna=True) < 2:
            continue

        result.append(col)

    return result


def _categories(df, date_columns, numeric_columns):
    result = []

    for col in df.columns:
        if col in date_columns or col in numeric_columns:
            continue

        if _is_id(col):
            continue

        if not (
            pd.api.types.is_object_dtype(df[col])
            or pd.api.types.is_string_dtype(df[col])
            or pd.api.types.is_bool_dtype(df[col])
        ):
            continue

        count = df[col].nunique(dropna=True)

        if 2 <= count <= 40:
            result.append(col)

    return result


def infer_chart_spec(columns, rows, question=""):
    df = _frame(columns, rows)

    if len(df) < 2 or df.empty:
        return None

    dates = _dates(df)
    numbers = _numbers(df, dates)
    categories = _categories(df, dates, numbers)

    q = question.lower()

    wants_scatter = any(
        x in q for x in (
            "scatter", "correlation", "relationship",
            "相关性", "相关关系", "变量关系",
        )
    )

    wants_histogram = any(
        x in q for x in (
            "histogram", "distribution", "直方图", "分布",
        )
    )

    wants_box = any(
        x in q for x in (
            "box plot", "boxplot", "箱线图",
        )
    )

    if wants_scatter and len(numbers) >= 2:
        return ChartSpec(
            "scatter", numbers[0], numbers[1],
            f"{numbers[1]} vs {numbers[0]}",
            "Two numeric variables were identified.",
        )

    if wants_histogram and numbers:
        return ChartSpec(
            "histogram", numbers[0], None,
            f"Distribution of {numbers[0]}",
            "A numeric distribution was requested.",
        )

    if wants_box and numbers:
        return ChartSpec(
            "box",
            categories[0] if categories else numbers[0],
            numbers[0] if categories else None,
            f"Distribution of {numbers[0]}",
            "A box plot was requested.",
        )

    if dates and numbers:
        return ChartSpec(
            "line", dates[0], numbers[0],
            f"{numbers[0]} over time",
            "A date field and numeric measure were identified.",
        )

    if categories and numbers:
        return ChartSpec(
            "bar", categories[0], numbers[0],
            f"{numbers[0]} by {categories[0]}",
            "A category and numeric measure were identified.",
        )

    if numbers:
        return ChartSpec(
            "histogram", numbers[0], None,
            f"Distribution of {numbers[0]}",
            "A numeric variable was identified.",
        )

    if categories:
        return ChartSpec(
            "bar", categories[0], None,
            f"Count by {categories[0]}",
            "A categorical frequency distribution was identified.",
        )

    return None


def render_chart(spec, columns, rows):
    df = _frame(columns, rows)

    if spec.x not in df.columns:
        return None

    if spec.y is not None and spec.y not in df.columns:
        return None

    if spec.chart_type == "line":
        data = df[[spec.x, spec.y]].copy()
        data[spec.x] = pd.to_datetime(data[spec.x], errors="coerce")
        data[spec.y] = pd.to_numeric(data[spec.y], errors="coerce")
        data = data.dropna().sort_values(spec.x)

        if data.empty:
            return None

        fig = px.line(
            data, x=spec.x, y=spec.y,
            markers=True, title=spec.title,
        )

    elif spec.chart_type == "bar":
        if spec.y is None:
            data = (
                df[spec.x].astype("string")
                .value_counts()
                .rename_axis(spec.x)
                .reset_index(name="count")
            )

            if data.empty:
                return None

            fig = px.bar(data, x=spec.x, y="count", title=spec.title)
        else:
            data = df[[spec.x, spec.y]].copy()
            data[spec.x] = data[spec.x].astype("string")
            data[spec.y] = pd.to_numeric(data[spec.y], errors="coerce")
            data = data.dropna()

            if data.empty:
                return None

            fig = px.bar(data, x=spec.x, y=spec.y, title=spec.title)
            fig.update_layout(
                xaxis={"categoryorder": "total descending"}
            )

    elif spec.chart_type == "scatter":
        data = df[[spec.x, spec.y]].copy()

        for col in [spec.x, spec.y]:
            data[col] = pd.to_numeric(data[col], errors="coerce")

        data = data.dropna()

        if data.empty:
            return None

        fig = px.scatter(data, x=spec.x, y=spec.y, title=spec.title)

    elif spec.chart_type == "histogram":
        data = pd.to_numeric(df[spec.x], errors="coerce").dropna()

        if len(data) < 2:
            return None

        fig = px.histogram(
            x=data,
            nbins=min(30, max(5, int(len(data) ** 0.5))),
            title=spec.title,
            labels={"x": spec.x},
        )

    elif spec.chart_type == "box":
        if spec.y is None:
            data = pd.to_numeric(df[spec.x], errors="coerce").dropna()
            if data.empty:
                return None
            fig = px.box(y=data, title=spec.title)
        else:
            data = df[[spec.x, spec.y]].copy()
            data[spec.y] = pd.to_numeric(data[spec.y], errors="coerce")
            data = data.dropna()

            if data.empty:
                return None

            fig = px.box(
                data, x=spec.x, y=spec.y,
                title=spec.title, points="outliers",
            )

    else:
        return None

    fig.update_layout(
        template="plotly_white",
        height=420,
        margin=dict(l=40, r=25, t=65, b=45),
        hovermode="closest",
    )

    return fig


def create_charts(columns, rows, question=""):
    """Return one primary chart, and an optional distribution chart."""

    spec = infer_chart_spec(columns, rows, question)

    if spec is None:
        return []

    primary = render_chart(spec, columns, rows)

    if primary is None:
        return []

    figures = [primary]

    q = question.lower()
    wants_overview = any(
        x in q for x in ("overview", "dashboard", "概览", "分析报告")
    )

    if wants_overview and spec.chart_type in ("line", "bar"):
        df = _frame(columns, rows)
        dates = _dates(df)
        numbers = _numbers(df, dates)

        if numbers and len(df) >= 8:
            hist_spec = ChartSpec(
                "histogram",
                numbers[0],
                None,
                f"Distribution of {numbers[0]}",
                "Additional distribution view.",
            )

            hist = render_chart(hist_spec, columns, rows)

            if hist is not None:
                figures.append(hist)

    return figures


def create_chart(columns, rows, question=""):
    """Backward-compatible single-chart helper."""
    figures = create_charts(columns, rows, question)
    return figures[0] if figures else None
'''

files["app/analytics/profile.py"] = r'''
"""Descriptive statistics for query results."""

import re
import pandas as pd


def build_profile(columns, rows):
    df = pd.DataFrame(rows)

    if columns and not df.empty:
        df = df[[c for c in columns if c in df.columns]]

    numeric_records = []

    for col in df.columns:
        if re.search(
            r"(^|[_\W])(id|key|code|phone|zip|postal)([_\W]|$)",
            str(col),
            re.IGNORECASE,
        ):
            continue

        values = pd.to_numeric(df[col], errors="coerce").dropna()

        if len(values) < 2 or values.nunique() < 2:
            continue

        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1

        outliers = (
            (values < q1 - 1.5 * iqr)
            | (values > q3 + 1.5 * iqr)
        ).sum()

        numeric_records.append({
            "column": str(col),
            "mean": round(float(values.mean()), 3),
            "median": round(float(values.median()), 3),
            "std": round(float(values.std()), 3),
            "min": round(float(values.min()), 3),
            "max": round(float(values.max()), 3),
            "iqr_outliers": int(outliers),
        })

    numeric_df = pd.DataFrame(numeric_records)

    numeric_data = pd.DataFrame()

    for col in df.columns:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.notna().mean() >= 0.8 and values.nunique() >= 2:
            numeric_data[col] = values

    correlation = (
        numeric_data.corr().round(3)
        if len(numeric_data.columns) >= 2
        else None
    )

    return {
        "row_count": len(df),
        "column_count": len(df.columns),
        "missing_cells": int(df.isna().sum().sum()),
        "numeric_summary": numeric_df,
        "correlation": correlation,
    }
'''

# --------------------------------------------------
# 4. Add SQL self-repair using the existing API setup
# --------------------------------------------------

repair_function = r'''

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
'''

llm_path = ROOT / "app/agent/llm.py"
llm_source = llm_path.read_text(encoding="utf-8-sig")

if "INSIGHTAI_V2_SQL_REPAIR_BEGIN" not in llm_source:
    files["app/agent/llm.py"] = llm_source.rstrip() + "\n\n" + repair_function
else:
    files["app/agent/llm.py"] = llm_source

# --------------------------------------------------
# 5. Upgrade LangGraph with bounded SQL repair
# --------------------------------------------------

files["app/agent/graph.py"] = r'''
"""LangGraph workflow with bounded SQL self-repair."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.llm import (
    generate_sql,
    summarize_results,
    repair_sql,
)
from app.agent.sql_safety import validate_sql
from app.core.config import get_openai_api_key
from app.database.db import (
    ensure_database,
    execute_readonly_query,
    get_schema,
    get_table_names,
)

MAX_REPAIRS = 2


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
    repair_attempts: int


def inspect_schema_node(state: AgentState) -> dict[str, Any]:
    db_path = ensure_database()
    return {
        "schema": get_schema(db_path),
        "error": "",
        "repair_attempts": 0,
    }


def generate_sql_node(state: AgentState) -> dict[str, Any]:
    try:
        sql, explanation, mode = generate_sql(
            state["question"], state.get("schema", "")
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

        return {"sql": safe_sql, "error": ""}

    except Exception as exc:
        return {"error": str(exc)}


def execute_query_node(state: AgentState) -> dict[str, Any]:
    try:
        columns, rows, truncated = execute_readonly_query(
            state["sql"]
        )

        return {
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
            "error": "",
        }

    except Exception as exc:
        return {"error": f"Query execution failed: {exc}"}


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
            "error": "",
        }

    except Exception as exc:
        return {
            "repair_attempts": attempts + 1,
            "error": f"SQL repair failed: {exc}",
        }


def analyze_results_node(state: AgentState) -> dict[str, Any]:
    analysis = summarize_results(
        question=state.get("question", ""),
        sql=state.get("sql", ""),
        columns=state.get("columns", []),
        rows=state.get("rows", []),
        mode=state.get("mode", "demo"),
    )

    return {"analysis": analysis, "error": ""}


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
        state.get("mode") == "openai"
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


def run_analysis(question: str) -> dict[str, Any]:
    question = question.strip()

    if not question:
        return {
            "error": "Question cannot be empty.",
            "analysis": "请输入一个问题。",
        }

    result = agent_graph.invoke({"question": question})
    return dict(result)
'''

# --------------------------------------------------
# 6. Automated tests
# --------------------------------------------------

files["tests/test_chart_engine.py"] = r'''
from app.analytics.chart_engine import (
    infer_chart_spec,
    create_chart,
    create_charts,
)


def test_monthly_data_selects_line():
    columns = ["order_date", "revenue"]
    rows = [
        {"order_date": "2026-01-01", "revenue": 100},
        {"order_date": "2026-02-01", "revenue": 150},
        {"order_date": "2026-03-01", "revenue": 130},
    ]

    spec = infer_chart_spec(columns, rows)

    assert spec is not None
    assert spec.chart_type == "line"

    fig = create_chart(columns, rows)

    assert fig is not None
    assert fig.data[0].type == "scatter"


def test_category_data_selects_bar():
    columns = ["category", "revenue"]
    rows = [
        {"category": "Books", "revenue": 100},
        {"category": "Clothing", "revenue": 200},
        {"category": "Sports", "revenue": 150},
    ]

    fig = create_chart(columns, rows)

    assert fig is not None
    assert fig.data[0].type == "bar"


def test_scatter_requires_explicit_relationship_intent():
    columns = ["price", "quantity"]
    rows = [
        {"price": 10, "quantity": 5},
        {"price": 20, "quantity": 8},
        {"price": 30, "quantity": 12},
    ]

    spec = infer_chart_spec(
        columns, rows, "Show correlation between price and quantity"
    )

    assert spec is not None
    assert spec.chart_type == "scatter"


def test_histogram_intent():
    columns = ["revenue"]
    rows = [
        {"revenue": 100},
        {"revenue": 200},
        {"revenue": 300},
        {"revenue": 400},
    ]

    spec = infer_chart_spec(columns, rows, "Show revenue distribution")

    assert spec is not None
    assert spec.chart_type == "histogram"


def test_box_plot_intent():
    columns = ["category", "amount"]
    rows = [
        {"category": "A", "amount": 10},
        {"category": "A", "amount": 20},
        {"category": "B", "amount": 30},
        {"category": "B", "amount": 40},
    ]

    spec = infer_chart_spec(columns, rows, "Show a box plot")

    assert spec is not None
    assert spec.chart_type == "box"


def test_single_row_does_not_generate_chart():
    assert infer_chart_spec(
        ["revenue"], [{"revenue": 100}]
    ) is None


def test_id_is_not_selected_as_measure():
    columns = ["customer_id", "revenue"]
    rows = [
        {"customer_id": 1, "revenue": 100},
        {"customer_id": 2, "revenue": 200},
        {"customer_id": 3, "revenue": 300},
    ]

    spec = infer_chart_spec(columns, rows)

    assert spec is not None
    assert spec.y == "revenue"


def test_overview_can_generate_multiple_charts():
    columns = ["category", "revenue"]
    rows = [
        {"category": f"Category {i}", "revenue": 100 + i * 10}
        for i in range(12)
    ]

    figures = create_charts(columns, rows, "Show business overview")

    assert len(figures) == 2
'''

files["tests/test_analytics_profile.py"] = r'''
from app.analytics.profile import build_profile


def test_profile_calculates_descriptive_statistics():
    result = build_profile(
        ["revenue", "customer_id"],
        [
            {"revenue": 100, "customer_id": 1},
            {"revenue": 200, "customer_id": 2},
            {"revenue": 300, "customer_id": 3},
        ],
    )

    assert result["row_count"] == 3
    assert result["column_count"] == 2
    assert "revenue" in result["numeric_summary"]["column"].tolist()
    assert "customer_id" not in result["numeric_summary"]["column"].tolist()


def test_profile_counts_missing_values():
    result = build_profile(
        ["revenue"],
        [
            {"revenue": 100},
            {"revenue": None},
            {"revenue": 300},
        ],
    )

    assert result["missing_cells"] == 1
'''

# --------------------------------------------------
# 7. Write files
# --------------------------------------------------

for relative, content in files.items():
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip(), encoding="utf-8")

# Apply UI patch
if patched_ui != ui_source:
    ui_path.write_text(patched_ui, encoding="utf-8")

print("\nInsightAI upgrade files written.")
print("UI integration:", "installed" if patched_ui != ui_source else "already installed")
print("SQL repair:", "installed")
print("Analytics engine:", "installed")
print("Tests:", "installed")
