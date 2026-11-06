"""Separate Streamlit page; the V1 entry point and settings remain available."""
from __future__ import annotations

import streamlit as st

from app.agent.graph import run_analysis
from app.analytics.advanced_service import analyze_sql
from app.database.db import ensure_database, get_table_names
from app.ui.advanced_components import label, render_agent_result, render_snapshot

st.set_page_config(page_title="InsightAI | Data analysis", page_icon="📈", layout="wide")
languages = ["简体中文", "English"]
current = st.session_state.get("language", languages[0])
language = st.sidebar.selectbox("Language / 语言", languages, index=languages.index(current), key="advanced_language")
st.session_state.language = language
st.title(label("Data analysis", "数据分析"))
st.markdown(label("[Return to the unified workspace](/)", "[返回统一分析工作台](/)"))
st.caption(label("Explore real SQLite query results with deterministic statistics and interactive charts.",
                 "基于真实 SQLite 查询结果，探索统计证据与交互图表。"))
tables = sorted(get_table_names(ensure_database()))
dataset_tab, ai_tab = st.tabs([label("Dataset Explorer", "数据探索"), label("AI Analysis", "AI 分析")])
with dataset_tab:
    table = st.selectbox(label("Source table", "来源表"), tables)
    if st.session_state.get("advanced_source_table") != table:
        st.session_state.advanced_source_table = table
        st.session_state.advanced_sql = f'SELECT * FROM "{table}"'
    with st.form("advanced_query"):
        sql = st.text_area(label("Read-only SQL", "只读 SQL"), key="advanced_sql")
        submitted = st.form_submit_button(label("Run query", "执行查询"))
    if submitted or "advanced_snapshot" not in st.session_state:
        try:
            snapshot = analyze_sql(sql, "数据概览" if language == "简体中文" else "Business overview")
            st.session_state.advanced_snapshot = snapshot
            st.session_state.pop("advanced_query_error", None)
        except Exception as exc:
            st.session_state.advanced_query_error = str(exc)
    if st.session_state.get("advanced_query_error"):
        st.error(st.session_state.advanced_query_error)
        st.caption(label("The previous successful snapshot remains below.", "下方保留上一次成功查询的快照。"))
    if "advanced_snapshot" in st.session_state:
        st.code(st.session_state.advanced_snapshot.sql, language="sql")
        render_snapshot(st.session_state.advanced_snapshot)
with ai_tab:
    with st.form("advanced_ai"):
        question = st.text_input(label("Business question", "业务问题"), value=label("Show monthly revenue trends.", "展示每月收入趋势。"))
        ask = st.form_submit_button(label("Analyze", "分析"))
    if ask:
        with st.spinner(label("Analyzing…", "分析中…")):
            st.session_state.advanced_agent_result = run_analysis(question)
    if "advanced_agent_result" in st.session_state:
        render_agent_result(st.session_state.advanced_agent_result)
