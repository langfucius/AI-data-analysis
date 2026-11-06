"""Shared, in-page data exploration and a single chart view per answer."""
from __future__ import annotations

import json
import pandas as pd
import streamlit as st

from app.analytics.advanced_result import AnalysisResult
from app.analytics.advanced_service import analyze_sql, snapshot_from_agent
from app.analytics.advanced_visualization import (
    AGGREGATIONS, CHART_TYPES, AdvancedChartSpec, chart_title, create_advanced_chart, recommend_charts,
)
from app.analytics.business_insights import EVIDENCE_SEPARATOR, display_name, measure_columns


def text(en: str, zh: str) -> str:
    return zh if st.session_state.get("language", "简体中文") == "简体中文" else en


def render_analysis_text(report: str) -> None:
    body, separator, evidence = report.partition(EVIDENCE_SEPARATOR)
    st.markdown(body)
    if separator:
        with st.expander(text("Statistical basis", "查看统计依据")):
            st.markdown(evidence)


def render_visual_explorer(result: AnalysisResult, key: str, *, theme: str = "dark") -> None:
    """One live figure; recommended configurations have sensible default axes."""
    specs = recommend_charts(result)
    language = "zh" if st.session_state.get("language", "简体中文") == "简体中文" else "en"
    if not specs:
        if result.loaded_row_count <= 1:
            st.caption(text("A single result is shown as a value, rather than an unnecessary chart.", "单条结果直接显示数值，不生成没有比较意义的图表。"))
        else:
            st.caption(text("No comparable numeric or categorical fields were found.", "尚未找到适合比较的数值或分类字段。"))
        return
    # Include the fingerprint in widget keys so a new SQL result cannot inherit
    # incompatible axes from a previous result.
    widget = f"{key}_{result.snapshot_id[:12]}"
    chosen = st.selectbox(text("View", "图表视角"), range(len(specs)),
                          format_func=lambda i: chart_title(specs[i], language), key=f"{widget}_view")
    spec = specs[chosen]
    custom = st.checkbox(text("Customize chart", "自定义图表与分组"), key=f"{widget}_custom")
    if custom:
        kinds = result.profile["types"]
        chart = st.selectbox(text("Chart type", "图表类型"), CHART_TYPES, index=CHART_TYPES.index(spec.chart_type), key=f"{widget}_type")
        if chart == "heatmap":
            method = st.selectbox(text("Correlation method", "相关性方法"), ["pearson", "spearman", "kendall"], key=f"{widget}_method")
            spec = AdvancedChartSpec(chart, correlation_method=method)
        else:
            numeric = measure_columns(result) + [c for c in kinds["identifier"] if c in kinds["numeric"]]
            x_options = kinds["numeric"] if chart in ("scatter", "histogram") else result.columns
            if not x_options:
                st.info(text("No numeric fields are available for this chart.", "当前结果没有可用于此图的数值字段。"))
                return
            x_default = spec.x if spec.x in x_options else x_options[0]
            x = st.selectbox("X", x_options, index=x_options.index(x_default),
                             format_func=lambda c: display_name(c, language == "zh"), key=f"{widget}_{chart}_x")
            y_options = [None] + numeric
            y_default = spec.y if spec.y in numeric else (numeric[0] if numeric and chart not in ("histogram", "box") else None)
            y = st.selectbox("Y", y_options, index=y_options.index(y_default),
                             format_func=lambda c: display_name(c, language == "zh") if c else text("Not selected / row count", "不选 / 记录数"), key=f"{widget}_{chart}_y") if chart != "histogram" else None
            aggregation = "none"
            if chart in ("bar", "line", "pie"):
                default = spec.aggregation if spec.aggregation != "none" else ("sum" if y else "count")
                aggregation = st.selectbox(text("Aggregation", "聚合方式"), AGGREGATIONS, index=AGGREGATIONS.index(default), key=f"{widget}_{chart}_aggregation")
            color = st.selectbox(text("Group / color", "分组 / 颜色"), [None] + result.columns, key=f"{widget}_{chart}_color") if chart != "pie" else None
            spec = AdvancedChartSpec(chart, x, y, aggregation, color)
    try:
        figure = create_advanced_chart(result, spec, language=language, theme=theme, presentation=True)
        st.plotly_chart(figure, use_container_width=True, key=f"{widget}_figure",
                        config={"displaylogo": False, "toImageButtonOptions": {"format": "png", "scale": 2}})
        notice = text("Charts use only the loaded query rows; each metric has its own axis and unit.", "图表仅使用本次查询已加载的数据；不同量纲的指标分开呈现。")
        if spec.aggregation == "mean":
            notice += text(" Values are unweighted group means.", " 当前为组内非加权均值。")
        st.caption(notice)
    except ValueError as exc:
        st.warning(text("This configuration is incompatible: ", "当前图表配置不适用：") + str(exc))


def render_conversation_result(state: dict, key: str) -> None:
    if state.get("mode") == "conversation":
        return
    if state.get("error"):
        return
    result = snapshot_from_agent(state)
    if state.get("mode") == "demo":
        st.caption(text("Demo Mode · Results from local sample data", "Demo 模式 · 使用本地示例数据进行分析"))
    if result.execution_metadata.get('answer_relevance') == 'irrelevant':
        st.warning(text('The query did not answer your question. Unrelated charts are hidden; query evidence remains available below.', '本次查询没有回答原问题，已隐藏无关图表；下方保留查询证据供核对。'))
    elif result.loaded_row_count:
        render_visual_explorer(result, key)
    else:
        st.info(text("No matching records. Try adjusting the filters.", "没有匹配记录，可以调整筛选条件后继续分析。"))
    with st.expander(text("Data, SQL and exports", "查看数据、SQL 与导出")):
        st.caption(result.scope_notice if st.session_state.get("language") == "English" else
                   "以下统计与图表只描述已加载的查询结果，不一定代表全表。" + (" 当前结果已截断。" if result.truncated else ""))
        st.dataframe(result.dataframe, hide_index=True, use_container_width=True)
        st.code(result.sql, language="sql")
        quality = result.profile
        st.dataframe(pd.DataFrame(quality["column_quality"]), hide_index=True)
        st.dataframe(pd.DataFrame(quality["numeric_summary"]), hide_index=True)
        st.download_button(text("Download rows (CSV)", "下载数据 CSV"), result.dataframe.to_csv(index=False).encode("utf-8-sig"),
                           "analysis.csv", "text/csv", key=f"{key}_csv")
        st.download_button(text("Download analysis", "下载分析报告"), state.get("analysis", result.summary()).encode("utf-8"),
                           "analysis.md", "text/markdown", key=f"{key}_report")
        st.download_button(text("Download evidence (JSON)", "下载完整统计证据 JSON"), json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False),
                           "analysis.json", "application/json", key=f"{key}_evidence")


def render_data_workspace() -> None:
    """Expose SQL as an optional tool in the same workspace as business chat."""
    from app.database.db import ensure_database, get_table_names
    from app.ui.advanced_components import render_snapshot
    st.subheader(text("Explore data", "数据探索"))
    st.caption(text("Select a real source table. Use the same data for charts, quality checks and exports.",
                    "选择真实数据表，查看分析解读、图表、数据质量和导出；需要时再展开 SQL。"))
    tables = sorted(get_table_names(ensure_database()))
    table = st.selectbox(text("Source table", "数据表"), tables, key="workspace_source")
    if st.session_state.get("workspace_last_source") != table:
        st.session_state.workspace_last_source = table
        st.session_state.workspace_sql = f'SELECT * FROM "{table}"'
        st.session_state.pop("workspace_snapshot", None)
        st.session_state.pop("workspace_error", None)
    with st.expander(text("SQL query (optional)", "SQL 查询（可选）")):
        with st.form("workspace_query"):
            sql = st.text_area(text("Read-only SQL", "只读 SQL"), key="workspace_sql")
            submitted = st.form_submit_button(text("Run query", "执行查询"))
    if submitted or "workspace_snapshot" not in st.session_state:
        try:
            st.session_state.workspace_snapshot = analyze_sql(sql, text("Business overview", "数据概览"))
            st.session_state.pop("workspace_error", None)
        except Exception as exc:
            st.session_state.workspace_error = str(exc)
    if st.session_state.get("workspace_error"):
        st.error(st.session_state.workspace_error)
        st.caption(text("The previous successful result remains below.", "下方保留上一次成功查询的结果。"))
    if "workspace_snapshot" in st.session_state:
        result = st.session_state.workspace_snapshot
        render_analysis_text(result.summary())
        render_snapshot(result, "workspace", theme="dark")
