"""Reusable bilingual views for the Advanced Analytics page."""
from __future__ import annotations

import json
from dataclasses import asdict
import pandas as pd
import streamlit as st

from app.analytics.advanced_result import AnalysisResult
from app.analytics.advanced_report import recommended_next_analysis
from app.analytics.advanced_visualization import (
    AGGREGATIONS, CHART_TYPES, AdvancedChartSpec, create_advanced_chart, recommend_charts,
)


def label(en: str, zh: str) -> str:
    return zh if st.session_state.get("language", "简体中文") == "简体中文" else en


def render_snapshot(result: AnalysisResult, key: str = "dataset", *, theme: str = "light") -> None:
    p = result.profile
    st.caption(label("All views use the same loaded snapshot: ", "所有视图使用同一份查询快照：") + result.snapshot_id[:12])
    st.info(result.scope_notice if st.session_state.get("language") == "English" else
            "统计和图表仅描述已加载的查询结果。SQL 行数限制或筛选可能使结果不代表完整数据。" + (" 当前结果已截断。" if result.truncated else ""))
    tabs = st.tabs([label("Overview", "概览"), label("Data Quality", "数据质量"),
                    label("Visual Explorer", "图表探索"), label("Correlation", "相关性"), label("Export", "导出")])
    with tabs[0]:
        st.write(label("Source tables", "来源表"), ", ".join(result.source_tables))
        cols = st.columns(4)
        for col, title, value in zip(cols, [label("Loaded rows", "加载行数"), label("Columns", "列数"),
                                          label("Missing cells", "缺失单元格"), label("Duplicate rows", "重复记录")],
                                     [result.loaded_row_count, len(result.columns), p["missing_cells"], p["duplicate_rows"]]):
            col.metric(title, value)
        st.dataframe(result.dataframe, hide_index=True)
        st.subheader(label("Numeric summary", "数值统计"))
        st.dataframe(pd.DataFrame(p["numeric_summary"]), hide_index=True)
        st.write(label("Detected column roles", "识别的列类型"), p["types"])
    with tabs[1]:
        st.caption(label("Duplicates count repeated full rows after the first occurrence. Outliers use 1.5 × IQR; they are flags, not errors.",
                         "重复记录指首条之后的整行重复；异常值采用 1.5 × IQR 规则，仅供调查，不代表错误。"))
        st.dataframe(pd.DataFrame(p["column_quality"]), hide_index=True)
        st.dataframe(pd.DataFrame(p["outliers"]), hide_index=True)
        with st.expander(label("Distributions", "分布")):
            st.json(p["distributions"])
    with tabs[2]:
        from app.ui.analysis_workspace import render_visual_explorer
        render_visual_explorer(result, key, theme=theme)
    with tabs[3]:
        method = st.selectbox(label("Method", "方法"), ["pearson", "spearman", "kendall"], key=f"{key}_method")
        st.dataframe(p["correlations"][method])
        st.caption(label("Pairwise complete finite observations; constants and insufficient pairs are undefined. Identifiers are excluded from the heatmap.",
                         "按变量对排除缺失与无穷值；常量或有效记录不足时相关系数未定义。热力图排除标识符。"))
        try:
            st.plotly_chart(create_advanced_chart(result, AdvancedChartSpec("heatmap", correlation_method=method),
                                                       language="zh" if st.session_state.get("language") != "English" else "en",
                                                       theme=theme, presentation=True),
                            key=f"{key}_correlation", use_container_width=True)
        except ValueError as exc:
            st.info(str(exc))
    with tabs[4]:
        st.download_button(label("Download loaded rows (CSV)", "下载已加载数据（CSV）"), result.dataframe.to_csv(index=False).encode("utf-8-sig"),
                           "insightai_rows.csv", "text/csv", key=f"{key}_csv")
        st.download_button(label("Download summary", "下载分析摘要"), result.summary().encode("utf-8"),
                           "insightai_summary.md", "text/markdown", key=f"{key}_summary")
        st.download_button(label("Download full evidence (JSON)", "下载完整证据（JSON）"),
                           json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False, indent=2),
                           "insightai_evidence.json", "application/json", key=f"{key}_json")
        st.caption(label("CSV may contain spreadsheet formulas from source text; import text columns as text in spreadsheet software.",
                         "CSV 保留原始文本；在电子表格中请将文本列按文本导入，避免源文本被识别为公式。"))


def render_agent_result(state: dict) -> None:
    from app.analytics.advanced_service import snapshot_from_agent
    if state.get("error"):
        st.error(state["error"])
        return
    result = snapshot_from_agent(state)
    st.code(result.sql, language="sql")
    st.markdown(state.get("analysis") or result.summary())
    st.caption(label("Retry count", "修复次数") + f": {state.get('retry_count', 0)}; mode: {state.get('mode', '')}")
    st.subheader(label("Recommended next analysis", "建议后续分析"))
    for idea in recommended_next_analysis(result):
        st.write("• " + idea)
    render_snapshot(result, "agent")
