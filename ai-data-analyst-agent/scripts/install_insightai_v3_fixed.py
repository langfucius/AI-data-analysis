from pathlib import Path
from datetime import datetime
import shutil
import subprocess
import sys

ROOT = Path.cwd()

FILES = {}

FILES["app/analytics/profiling.py"] = r'''
"""Advanced data profiling and quality analysis."""

import pandas as pd

DATE_HINTS = (
    "date", "time", "timestamp",
    "created_at", "updated_at",
    "datetime", "month",
)


def prepare_dataframe(df):
    result = df.copy()

    for col in result.columns:
        if pd.api.types.is_datetime64_any_dtype(result[col]):
            continue

        if not any(h in str(col).lower() for h in DATE_HINTS):
            continue

        parsed = pd.to_datetime(result[col], errors="coerce")

        if len(result) and parsed.notna().mean() >= 0.8:
            result[col] = parsed

    return result


def profile_dataframe(df):
    numeric = list(
        df.select_dtypes(include="number").columns
    )

    dates = [
        c for c in df.columns
        if pd.api.types.is_datetime64_any_dtype(df[c])
    ]

    missing = df.isna().sum()

    missing_df = pd.DataFrame({
        "column": df.columns,
        "missing": missing.values,
        "missing_pct": [
            round(float(missing[c]) / max(len(df), 1) * 100, 2)
            for c in df.columns
        ],
    })

    summary = (
        df[numeric].describe().T.reset_index()
        if numeric else pd.DataFrame()
    )

    if not summary.empty:
        summary = summary.rename(columns={"index": "column"})

    outliers = []

    for col in numeric:
        values = df[col].dropna()

        if len(values) < 4:
            continue

        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1

        count = int(
            ((values < q1 - 1.5 * iqr) |
             (values > q3 + 1.5 * iqr)).sum()
        )

        outliers.append({
            "column": col,
            "outlier_count": count,
            "outlier_pct": round(count / len(values) * 100, 2),
        })

    categorical = [
        c for c in df.columns
        if c not in numeric and c not in dates
    ]

    return {
        "row_count": len(df),
        "column_count": len(df.columns),
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_cells": int(missing.sum()),
        "missing_by_column": missing_df,
        "numeric_columns": numeric,
        "categorical_columns": categorical,
        "datetime_columns": dates,
        "numeric_summary": summary,
        "outliers": pd.DataFrame(outliers),
    }


def correlation_analysis(df, method="pearson"):
    if method not in ("pearson", "spearman", "kendall"):
        raise ValueError("Unsupported correlation method.")

    numeric = df.select_dtypes(include="number")

    if numeric.shape[1] < 2:
        return pd.DataFrame()

    return numeric.corr(method=method)
'''

FILES["app/analytics/result.py"] = r'''
"""Unified data snapshot shared by all analytics modules."""

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from app.analytics.profiling import (
    prepare_dataframe,
    profile_dataframe,
)


@dataclass
class AnalysisResult:
    source_table: str
    dataframe: pd.DataFrame
    profile: dict
    truncated: bool = False
    generated_at: str = ""

    @property
    def row_count(self):
        return len(self.dataframe)

    @property
    def columns(self):
        return list(self.dataframe.columns)


def build_analysis_result(
    source_table,
    dataframe,
    truncated=False,
):
    prepared = prepare_dataframe(dataframe)

    return AnalysisResult(
        source_table=source_table,
        dataframe=prepared,
        profile=profile_dataframe(prepared),
        truncated=truncated,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
'''

# IMPORTANT:
# V3 chart engine is separate. Never overwrite chart_engine.py.

FILES["app/analytics/advanced_chart_engine.py"] = r'''
"""Advanced visualization engine. V2 chart_engine remains untouched."""

import pandas as pd
import plotly.express as px

from pandas.api.types import (
    is_datetime64_any_dtype,
    is_numeric_dtype,
)


def recommend_chart(df, x=None, y=None):
    numeric = list(df.select_dtypes(include="number").columns)

    dates = [
        c for c in df.columns
        if is_datetime64_any_dtype(df[c])
    ]

    categories = [
        c for c in df.columns
        if c not in numeric and c not in dates
        and 2 <= df[c].nunique(dropna=True) <= 40
    ]

    if x in df.columns and y in df.columns:
        if is_datetime64_any_dtype(df[x]):
            return "line"

        if is_numeric_dtype(df[x]) and is_numeric_dtype(df[y]):
            return "scatter"

        if is_numeric_dtype(df[y]):
            return "bar"

    if dates and numeric:
        return "line"

    if categories and numeric:
        return "bar"

    if len(numeric) >= 2:
        return "heatmap"

    if numeric:
        return "histogram"

    return "table"


def _theme(fig, title):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#111827",
        plot_bgcolor="#0F172A",
        font=dict(
            family="Segoe UI, Arial, sans-serif",
            size=13,
            color="#E5E7EB",
        ),
        title=dict(
            text=title,
            x=0.02,
            xanchor="left",
        ),
        height=440,
        margin=dict(l=55, r=45, t=70, b=65),
        hovermode="closest",
    )

    fig.update_xaxes(
        showgrid=False,
        automargin=True,
    )

    fig.update_yaxes(
        showgrid=True,
        gridcolor="rgba(148,163,184,0.18)",
        automargin=True,
    )

    return fig


def build_chart(
    dataframe,
    chart_type,
    x=None,
    y=None,
    color=None,
    aggregation="sum",
    max_categories=20,
):
    df = dataframe.copy()
    kind = chart_type.lower()

    supported = {
        "bar", "line", "scatter",
        "histogram", "box", "heatmap", "pie",
    }

    if kind not in supported:
        raise ValueError(f"Unsupported chart type: {kind}")

    if aggregation not in ("sum", "mean", "count"):
        raise ValueError("Unsupported aggregation.")

    if kind == "heatmap":
        numeric = df.select_dtypes(include="number")

        if numeric.shape[1] < 2:
            raise ValueError("Heatmap requires two numeric columns.")

        fig = px.imshow(
            numeric.corr(),
            text_auto=".2f",
            zmin=-1,
            zmax=1,
            color_continuous_scale="RdBu_r",
            aspect="auto",
        )

        return _theme(fig, "Correlation Heatmap")

    if kind == "histogram":
        col = y or x

        if col not in df.columns or not is_numeric_dtype(df[col]):
            raise ValueError("Histogram requires a numeric column.")

        fig = px.histogram(df, x=col, nbins=30)

        return _theme(fig, f"Distribution of {col}")

    if kind == "scatter":
        if x not in df.columns or y not in df.columns:
            raise ValueError("Scatter requires X and Y.")

        if not (
            is_numeric_dtype(df[x])
            and is_numeric_dtype(df[y])
        ):
            raise ValueError("Scatter requires numeric X and Y.")

        fig = px.scatter(
            df,
            x=x,
            y=y,
            color=color if color in df.columns else None,
            opacity=0.8,
        )

        return _theme(fig, f"{y} vs {x}")

    if kind == "box":
        if y not in df.columns or not is_numeric_dtype(df[y]):
            raise ValueError("Box plot requires numeric Y.")

        fig = px.box(
            df,
            x=x if x in df.columns else None,
            y=y,
            color=color if color in df.columns else None,
        )

        return _theme(fig, f"Distribution of {y}")

    if kind in ("bar", "line", "pie"):
        if x not in df.columns or y not in df.columns:
            raise ValueError(f"{kind} requires valid X and Y.")

        if not is_numeric_dtype(df[y]):
            raise ValueError("Y must be numeric.")

        groups = [x]

        if color in df.columns and color not in (x, y) and kind != "pie":
            groups.append(color)

        grouped = (
            df.groupby(groups, dropna=False, observed=True)[y]
            .agg(aggregation)
            .reset_index()
        )

        if kind == "bar":
            if grouped[x].nunique() > max_categories:
                keep = (
                    grouped.groupby(x, dropna=False)[y]
                    .sum()
                    .nlargest(max_categories)
                    .index
                )
                grouped = grouped[grouped[x].isin(keep)]

            grouped = grouped.sort_values(y, ascending=False)

            fig = px.bar(
                grouped,
                x=x,
                y=y,
                color=color if color in grouped.columns and color != x else None,
                barmode="group",
            )

            fig.update_traces(
                marker_color="#78BDF2",
                marker_line_width=0,
            )

            return _theme(fig, f"{y} by {x}")

        if kind == "line":
            grouped = grouped.sort_values(x)

            fig = px.line(
                grouped,
                x=x,
                y=y,
                color=color if color in grouped.columns and color != x else None,
                markers=True,
            )

            fig.update_traces(
                line=dict(color="#60A5FA", width=3),
                marker=dict(size=7),
            )

            return _theme(fig, f"{y} over {x}")

        totals = (
            grouped.groupby(x, dropna=False)[y]
            .sum()
            .sort_values(ascending=False)
        )

        top = totals.head(8)

        pie_data = top.rename_axis(x).reset_index(name=y)

        if len(totals) > 8:
            other = pd.DataFrame([{
                x: "Other",
                y: float(totals.iloc[8:].sum()),
            }])
            pie_data = pd.concat([pie_data, other], ignore_index=True)

        fig = px.pie(
            pie_data,
            names=x,
            values=y,
            hole=0.4,
        )

        return _theme(fig, f"{y} Composition")

    raise ValueError("Unable to construct chart.")
'''

# --------------------------------------------------
# ADVANCED ANALYTICS PAGE
# --------------------------------------------------

FILES["app/ui/pages/2_Advanced_Analytics.py"] = r'''
"""InsightAI Advanced Analytics workbench."""

import pandas as pd
import streamlit as st
import plotly.express as px

from app.database.db import (
    ensure_database,
    get_table_names,
    execute_readonly_query,
)

from app.analytics.result import build_analysis_result

from app.analytics.profiling import correlation_analysis

from app.analytics.advanced_chart_engine import (
    recommend_chart,
    build_chart,
)


st.title("📊 Advanced Analytics")

st.caption(
    "Statistical profiling · Data quality · Interactive visualization"
)

try:
    db_path = ensure_database()
    tables = sorted(get_table_names(db_path))
except Exception as exc:
    st.error(f"Database error: {exc}")
    st.stop()

if not tables:
    st.warning("No database tables found.")
    st.stop()

with st.sidebar:
    st.header("Data Source")

    selected_table = st.selectbox(
        "Database table",
        tables,
    )

    row_limit = st.slider(
        "Maximum rows",
        100,
        10000,
        5000,
        100,
    )

safe_table = selected_table.replace('"', '""')
sql = f'SELECT * FROM "{safe_table}"'

try:
    columns, rows, truncated = execute_readonly_query(
        sql,
        db_path=db_path,
        max_rows=row_limit,
    )

    dataframe = pd.DataFrame(rows, columns=columns)

except Exception as exc:
    st.error(f"Query failed: {exc}")
    st.stop()

if dataframe.empty:
    st.warning("No data available.")
    st.stop()

# Single immutable-in-practice snapshot for the whole page.
result = build_analysis_result(
    selected_table,
    dataframe,
    truncated,
)

df = result.dataframe
profile = result.profile

st.caption(
    f"Source: {result.source_table} · "
    f"Rows: {result.row_count:,} · "
    f"Generated: {result.generated_at}"
)

if result.truncated:
    st.warning(
        "The result is truncated. All displayed statistics "
        "describe loaded rows, not the complete database table."
    )

k1, k2, k3, k4 = st.columns(4)

k1.metric("Rows", f"{profile['row_count']:,}")
k2.metric("Columns", f"{profile['column_count']:,}")
k3.metric("Missing Cells", f"{profile['missing_cells']:,}")
k4.metric("Duplicate Rows", f"{profile['duplicate_rows']:,}")

overview, visual, quality, correlation = st.tabs([
    "Overview",
    "Visual Explorer",
    "Data Quality",
    "Correlation",
])

with overview:
    st.subheader("Data Preview")
    st.dataframe(df.head(30), use_container_width=True)

    st.subheader("Descriptive Statistics")

    if not profile["numeric_summary"].empty:
        st.dataframe(
            profile["numeric_summary"],
            use_container_width=True,
        )
    else:
        st.info("No numeric columns found.")

    info = pd.DataFrame({
        "column": df.columns,
        "dtype": [str(x) for x in df.dtypes],
        "unique": [int(df[c].nunique()) for c in df.columns],
        "missing": [int(df[c].isna().sum()) for c in df.columns],
    })

    st.subheader("Column Information")
    st.dataframe(info, use_container_width=True)

with visual:
    st.subheader("Interactive Chart Builder")

    numeric = profile["numeric_columns"]

    if not numeric:
        st.info("No numeric columns available.")
    else:
        a, b = st.columns(2)

        with a:
            chart_choice = st.selectbox(
                "Chart Type",
                [
                    "Auto", "Line", "Bar", "Scatter",
                    "Histogram", "Box", "Heatmap", "Pie",
                ],
            )

            x_choice = st.selectbox(
                "X Axis",
                ["(auto)"] + list(df.columns),
            )

        with b:
            y_choice = st.selectbox(
                "Y Axis",
                ["(auto)"] + numeric,
            )

            aggregation = st.selectbox(
                "Aggregation",
                ["sum", "mean", "count"],
            )

        color_choice = st.selectbox(
            "Group / Color",
            ["(none)"] + list(df.columns),
        )

        x = None if x_choice == "(auto)" else x_choice
        y = None if y_choice == "(auto)" else y_choice

        kind = chart_choice.lower()

        if kind == "auto":
            kind = recommend_chart(df, x, y)

        dates = profile["datetime_columns"]
        categories = profile["categorical_columns"]

        if kind in ("line", "bar", "pie"):
            if x is None:
                if kind == "line" and dates:
                    x = dates[0]
                elif categories:
                    x = categories[0]
                else:
                    x = numeric[0]

            if y is None:
                y = numeric[0]

        elif kind == "scatter":
            if y is None:
                y = numeric[0]

            if x is None:
                candidates = [c for c in numeric if c != y]
                if candidates:
                    x = candidates[0]

        elif kind in ("histogram", "box"):
            if y is None:
                y = numeric[0]

            if kind == "histogram":
                x = y

        color = None if color_choice == "(none)" else color_choice

        if kind == "table":
            st.info("No suitable chart identified.")
        else:
            try:
                fig = build_chart(
                    df,
                    kind,
                    x=x,
                    y=y,
                    color=color,
                    aggregation=aggregation,
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    config={
                        "displaylogo": False,
                        "scrollZoom": True,
                    },
                )

                st.caption(
                    "This chart uses the same data snapshot as the "
                    "statistical profile above."
                )

            except (ValueError, KeyError) as exc:
                st.warning(str(exc))

with quality:
    st.subheader("Data Quality")

    missing = profile["missing_by_column"]

    if profile["missing_cells"]:
        st.dataframe(
            missing.sort_values("missing", ascending=False),
            use_container_width=True,
        )
    else:
        st.success("No missing values detected.")

    st.subheader("IQR Outlier Detection")

    outliers = profile["outliers"]

    if not outliers.empty:
        st.dataframe(outliers, use_container_width=True)
    else:
        st.info("Insufficient numeric data for outlier detection.")

    st.caption(
        "IQR flags statistical outliers, not necessarily erroneous data."
    )

with correlation:
    st.subheader("Correlation Analysis")

    method = st.selectbox(
        "Method",
        ["pearson", "spearman", "kendall"],
    )

    corr = correlation_analysis(df, method)

    if corr.empty:
        st.info("At least two numeric columns are required.")
    else:
        fig = px.imshow(
            corr,
            text_auto=".2f",
            zmin=-1,
            zmax=1,
            color_continuous_scale="RdBu_r",
            aspect="auto",
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#111827",
            plot_bgcolor="#0F172A",
            font_color="#E5E7EB",
            title=f"{method.title()} Correlation",
        )

        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            corr.style.format("{:.3f}"),
            use_container_width=True,
        )

with st.expander("SQL and Data Evidence"):
    st.write("Database:", str(db_path))
    st.write("Table:", selected_table)
    st.write("Loaded rows:", result.row_count)
    st.write("Truncated:", result.truncated)
    st.code(sql, language="sql")
'''

# --------------------------------------------------
# V3 TESTS: IMPORT NEW MODULE, NOT OLD V2 MODULE
# --------------------------------------------------

FILES["tests/test_v3_analytics.py"] = r'''
import pandas as pd
import pytest

from app.analytics.profiling import (
    prepare_dataframe,
    profile_dataframe,
    correlation_analysis,
)

from app.analytics.result import build_analysis_result

from app.analytics.advanced_chart_engine import (
    recommend_chart,
    build_chart,
)


def sample_data():
    return pd.DataFrame({
        "order_date": [
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
        ],
        "category": ["A", "A", "B", "B", "C"],
        "revenue": [10., 20., 30., 40., 1000.],
        "units": [1, 2, 3, 4, 5],
    })


def test_datetime_inference():
    df = prepare_dataframe(sample_data())
    assert pd.api.types.is_datetime64_any_dtype(df["order_date"])


def test_profile_counts():
    profile = profile_dataframe(sample_data())
    assert profile["row_count"] == 5
    assert profile["column_count"] == 4


def test_missing_and_duplicates():
    df = pd.DataFrame({
        "value": [1., 2., 2., None],
        "category": ["A", "B", "B", "C"],
    })

    profile = profile_dataframe(df)

    assert profile["missing_cells"] == 1
    assert profile["duplicate_rows"] == 1


def test_iqr_outliers():
    profile = profile_dataframe(sample_data())
    row = profile["outliers"].query("column == 'revenue'")

    assert len(row) == 1
    assert int(row.iloc[0]["outlier_count"]) >= 1


def test_correlation():
    corr = correlation_analysis(sample_data(), "spearman")

    assert "revenue" in corr.columns
    assert "units" in corr.columns


def test_invalid_correlation():
    with pytest.raises(ValueError):
        correlation_analysis(sample_data(), "invalid")


def test_unified_result():
    result = build_analysis_result("orders", sample_data())

    assert result.source_table == "orders"
    assert result.row_count == 5
    assert "revenue" in result.columns


def test_recommend_line():
    df = prepare_dataframe(sample_data())

    assert recommend_chart(df, "order_date", "revenue") == "line"


def test_recommend_bar():
    assert recommend_chart(
        sample_data(), "category", "revenue"
    ) == "bar"


def test_recommend_scatter():
    assert recommend_chart(
        sample_data(), "revenue", "units"
    ) == "scatter"


def test_bar_chart():
    fig = build_chart(
        sample_data(), "bar",
        x="category", y="revenue",
    )

    assert fig.data[0].type == "bar"


def test_line_chart():
    df = prepare_dataframe(sample_data())

    fig = build_chart(
        df, "line",
        x="order_date", y="revenue",
    )

    assert fig.data[0].type == "scatter"
    assert fig.data[0].mode == "lines+markers"


def test_histogram():
    fig = build_chart(
        sample_data(), "histogram",
        x="revenue",
    )

    assert fig.data[0].type == "histogram"


def test_box():
    fig = build_chart(
        sample_data(), "box",
        y="revenue",
    )

    assert fig.data[0].type == "box"


def test_heatmap():
    fig = build_chart(sample_data(), "heatmap")
    assert fig.data[0].type == "heatmap"


def test_scatter():
    fig = build_chart(
        sample_data(), "scatter",
        x="revenue", y="units",
    )

    assert fig.data[0].type == "scatter"


def test_pie():
    fig = build_chart(
        sample_data(), "pie",
        x="category", y="revenue",
    )

    assert fig.data[0].type == "pie"


def test_invalid_column():
    with pytest.raises(ValueError):
        build_chart(
            sample_data(), "bar",
            x="missing", y="revenue",
        )


def test_original_dataframe_not_mutated():
    df = sample_data()
    original = df.copy(deep=True)

    build_chart(
        df, "bar",
        x="category", y="revenue",
    )

    pd.testing.assert_frame_equal(df, original)
'''

FILES["docs/INSIGHTAI_V3_ANALYTICS.md"] = r'''
# InsightAI V3 Analytics

## Backward compatibility

The original `app.analytics.chart_engine` is intentionally preserved.

Existing V2 functions:
- infer_chart_spec
- create_chart
- create_charts

The V3 engine lives in:
- app.analytics.advanced_chart_engine

## New capabilities

- Data profiling
- Missing-value analysis
- Duplicate detection
- IQR outlier detection
- Pearson / Spearman / Kendall correlation
- Interactive bar, line, scatter, histogram, box, heatmap and pie charts
- Read-only database analytics page
- Shared AnalysisResult snapshot

## Run

```powershell
.\.venv\Scripts\python.exe -m streamlit run app\ui\streamlit_app.py
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

## Limitations

The current analytics page operates on a bounded read-only query result.
Correlation does not prove causation.
IQR flags do not prove data errors.
Forecasting and autonomous multi-step LLM planning are not included.
'''

# --------------------------------------------------
# 1. BACKUP
# --------------------------------------------------

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = ROOT / ".backups" / f"insightai_v3_fixed_{STAMP}"

EXISTING = {}

for relative in FILES:
    source = ROOT / relative
    EXISTING[relative] = source.exists()

    if source.exists():
        dest = BACKUP / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

print("Backup:", BACKUP)

# --------------------------------------------------
# 2. WRITE + TEST + ROLLBACK
# --------------------------------------------------

try:
    for relative, content in FILES.items():
        path = ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.lstrip(), encoding="utf-8")

    print("\nV3 modules installed without replacing V2 chart_engine.py.")

    # Verify backward compatibility again.
    from app.analytics.chart_engine import (
        infer_chart_spec,
        create_chart,
        create_charts,
    )

    print("V2 chart API: preserved.")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-v"],
        cwd=ROOT,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError("Test suite failed.")

    print("\nALL TESTS PASSED.")
    print("Backup:", BACKUP)

except Exception as exc:
    print("\nERROR:", exc)
    print("Rolling back V3 files...")

    for relative in FILES:
        target = ROOT / relative
        previous = BACKUP / relative

        if EXISTING[relative]:
            if previous.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(previous, target)
        elif target.exists():
            target.unlink()

    raise
