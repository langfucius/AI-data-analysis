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

    identifiers = [c for c in df.columns if _is_id(c)]
    if identifiers and numbers:
        return ChartSpec("bar", identifiers[0], numbers[0],
                         f"{numbers[0]} by {identifiers[0]}",
                         "Identifier used as a category, never as a measure.")

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
