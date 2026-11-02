"""Bilingual AI Data Analyst Agent Dashboard."""

import os

import pandas as pd
import plotly.express as px
import streamlit as st

from dotenv import set_key, unset_key

from app.agent.graph import run_analysis
from app.core.config import (
    PROJECT_ROOT,
    get_openai_api_key,
    get_openai_model,
    is_llm_enabled,
)
from app.database.db import ensure_database, execute_readonly_query


# ==================================================
# 1. PAGE CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="InsightAI | Data Analyst",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

ensure_database()

ENV_PATH = PROJECT_ROOT / ".env"


# ==================================================
# 2. MULTI-LANGUAGE TRANSLATIONS
# ==================================================

LANGUAGES = ["简体中文", "English"]

TEXT = {
    "简体中文": {
        "language": "语言 / Language",
        "status": "Agent 状态",
        "demo": "Demo 演示模式",
        "openai": "OpenAI 模式",
        "demo_desc": "本地示例查询 · 无需 API Key",
        "openai_desc": "OpenAI API 已配置",
        "api": "⚙️ API 配置",
        "api_desc": "配置你的 AI 模型和 API 连接。",
        "api_key": "API Key",
        "api_key_hint": "留空表示保留已经保存的 Key",
        "model": "模型名称",
        "base_url": "API Base URL（可选）",
        "base_url_hint": "OpenAI 官方 API 可留空",
        "save": "保存 API 配置",
        "test": "测试 API 连接",
        "clear": "清除 API Key",
        "saved": "配置已保存！",
        "cleared": "API Key 已清除，已切换至 Demo Mode。",
        "test_ok": "API 连接成功！",
        "test_error": "连接失败",
        "missing_key": "请先配置并保存 API Key。",
        "security": "API Key 仅保存在本地 .env 文件中。请勿上传到 GitHub。",
        "database": "数据来源",
        "database_name": "零售销售示例数据库",
        "tables": "Customers · Products · Orders · Order Items",
        "capabilities": "Agent 能力",
        "capability_list": "自然语言转 SQL\nSQL 安全验证\n只读数据库查询\n数据分析与可视化",
        "clear_chat": "清空对话",
        "hero_tag": "AI 驱动的数据分析工作台",
        "hero_title": "让数据成为",
        "hero_highlight": "商业洞察。",
        "hero_desc": "用自然语言提问，让 AI Agent 自动生成 SQL、分析数据并解释结果。",
        "revenue": "已交付订单收入",
        "orders": "已交付订单数",
        "customers": "客户总数",
        "explore": "✦ 快速数据分析",
        "chat": "AI 数据分析助手",
        "placeholder": "输入关于销售数据的问题……",
        "thinking": "Agent 正在分析数据……",
        "sql": "查看生成的 SQL",
        "results": "查询结果",
        "download": "下载 CSV",
        "chart": "数据可视化",
        "no_results": "查询成功，但没有返回记录。",
        "truncated": "结果已达到最大返回行数限制。",
        "error": "分析过程中出现错误",
        "footer": "InsightAI · AI Data Analyst Agent",
        "questions": [
            "总收入是多少？",
            "展示最畅销的 5 个产品。",
            "展示每月收入趋势。",
            "比较不同产品类别的销售额。",
            "哪些客户消费最高？",
            "订单状态分布是什么？",
        ],
    },

    "English": {
        "language": "Language / 语言",
        "status": "Agent Status",
        "demo": "Demo Mode",
        "openai": "OpenAI Mode",
        "demo_desc": "Local sample queries · No API key required",
        "openai_desc": "OpenAI API configured",
        "api": "⚙️ API Settings",
        "api_desc": "Configure your AI model and API connection.",
        "api_key": "API Key",
        "api_key_hint": "Leave blank to keep the saved key",
        "model": "Model Name",
        "base_url": "API Base URL (Optional)",
        "base_url_hint": "Leave blank for the official OpenAI API",
        "save": "Save API Settings",
        "test": "Test API Connection",
        "clear": "Clear API Key",
        "saved": "API settings saved!",
        "cleared": "API key cleared. Switched to Demo Mode.",
        "test_ok": "API connection successful!",
        "test_error": "Connection failed",
        "missing_key": "Please configure and save your API key first.",
        "security": "API keys are stored locally in .env. Never upload this file to GitHub.",
        "database": "Data Source",
        "database_name": "Sample Retail Sales Database",
        "tables": "Customers · Products · Orders · Order Items",
        "capabilities": "Agent Capabilities",
        "capability_list": "Natural Language to SQL\nSQL Safety Validation\nRead-only Database Queries\nData Analysis & Visualization",
        "clear_chat": "Clear Conversation",
        "hero_tag": "AI-POWERED ANALYTICS WORKSPACE",
        "hero_title": "Turn Data Into",
        "hero_highlight": "Insights.",
        "hero_desc": "Ask questions in natural language. Let the AI agent generate SQL, analyze data, and explain results.",
        "revenue": "Delivered Revenue",
        "orders": "Delivered Orders",
        "customers": "Total Customers",
        "explore": "✦ Quick Analysis",
        "chat": "AI Data Analyst Assistant",
        "placeholder": "Ask a question about your sales data...",
        "thinking": "Agent is analyzing your data...",
        "sql": "View Generated SQL",
        "results": "Query Results",
        "download": "Download CSV",
        "chart": "Data Visualization",
        "no_results": "The query succeeded but returned no records.",
        "truncated": "Results reached the maximum row limit.",
        "error": "An error occurred during analysis",
        "footer": "InsightAI · AI Data Analyst Agent",
        "questions": [
            "What is the total revenue?",
            "Show the top 5 best-selling products.",
            "Show monthly revenue trends.",
            "Compare sales by category.",
            "Who are the top customers?",
            "What is the order status distribution?",
        ],
    },
}


# ==================================================
# 3. SESSION STATE
# ==================================================

if "language" not in st.session_state:
    st.session_state.language = "简体中文"

if "messages" not in st.session_state:
    st.session_state.messages = []

if "flash_message" not in st.session_state:
    st.session_state.flash_message = ""


# ==================================================
# 4. API CONFIGURATION FUNCTIONS
# ==================================================

def save_api_settings(api_key, model, base_url):

    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    if api_key.strip():
        set_key(str(ENV_PATH), "OPENAI_API_KEY", api_key.strip())
        os.environ["OPENAI_API_KEY"] = api_key.strip()

    model = model.strip() or "gpt-4o-mini"

    set_key(str(ENV_PATH), "OPENAI_MODEL", model)
    os.environ["OPENAI_MODEL"] = model

    if base_url.strip():
        set_key(str(ENV_PATH), "OPENAI_BASE_URL", base_url.strip())
        os.environ["OPENAI_BASE_URL"] = base_url.strip()
    else:
        if ENV_PATH.exists():
            unset_key(str(ENV_PATH), "OPENAI_BASE_URL")
        os.environ.pop("OPENAI_BASE_URL", None)


def clear_api_settings():

    if ENV_PATH.exists():
        unset_key(str(ENV_PATH), "OPENAI_API_KEY")

    os.environ.pop("OPENAI_API_KEY", None)


def test_api_connection():

    api_key = get_openai_api_key()

    if not api_key:
        raise ValueError("API Key is missing.")

    from openai import OpenAI

    base_url = os.getenv("OPENAI_BASE_URL", "").strip()

    kwargs = {
        "api_key": api_key,
        "timeout": 25.0,
    }

    if base_url:
        kwargs["base_url"] = base_url

    client = OpenAI(**kwargs)

    client.chat.completions.create(
        model=get_openai_model(),
        messages=[
            {"role": "user", "content": "Reply with OK."}
        ],
        max_tokens=5,
    )


# ==================================================
# 5. LANGUAGE SELECTOR
# ==================================================

with st.sidebar:

    st.markdown(
        """
        <div style="font-size:27px;font-weight:800;">
            ✦ InsightAI
        </div>
        <div style="font-size:10px;letter-spacing:2px;color:#818cf8;">
            DATA ANALYST AGENT
        </div>
        """,
        unsafe_allow_html=True,
    )

    language = st.selectbox(
        "🌐 Language / 语言",
        LANGUAGES,
        index=LANGUAGES.index(st.session_state.language),
    )

    st.session_state.language = language

T = TEXT[language]


# ==================================================
# 6. SIDEBAR API SETTINGS
# ==================================================

with st.sidebar:

    st.divider()

    st.markdown(f"### {T['status']}")

    if is_llm_enabled():
        st.success(f"● {T['openai']}")
        st.caption(T["openai_desc"])
    else:
        st.info(f"● {T['demo']}")
        st.caption(T["demo_desc"])

    if st.session_state.flash_message:
        st.success(st.session_state.flash_message)
        st.session_state.flash_message = ""

    with st.expander(T["api"], expanded=False):

        st.caption(T["api_desc"])

        with st.form("api_configuration_form"):

            api_key_input = st.text_input(
                T["api_key"],
                type="password",
                placeholder="sk-...",
                help=T["api_key_hint"],
            )

            model_input = st.text_input(
                T["model"],
                value=get_openai_model(),
            )

            base_url_input = st.text_input(
                T["base_url"],
                value=os.getenv("OPENAI_BASE_URL", ""),
                placeholder="https://api.openai.com/v1",
                help=T["base_url_hint"],
            )

            save_clicked = st.form_submit_button(
                T["save"],
                use_container_width=True,
            )

        if save_clicked:

            try:
                save_api_settings(
                    api_key_input,
                    model_input,
                    base_url_input,
                )

                st.session_state.flash_message = T["saved"]
                st.rerun()

            except Exception as exc:
                st.error(f"{T['error']}: {exc}")

        if st.button(T["test"], use_container_width=True):

            try:
                test_api_connection()
                st.success(T["test_ok"])

            except Exception as exc:
                st.error(f"{T['test_error']}: {exc}")

        if st.button(T["clear"], use_container_width=True):

            clear_api_settings()
            st.session_state.flash_message = T["cleared"]
            st.rerun()

        st.caption(T["security"])

    st.divider()

    st.markdown(f"### {T['database']}")
    st.markdown(f"**{T['database_name']}**")
    st.caption("SQLite · sample_sales.db")
    st.caption(T["tables"])

    st.divider()

    st.markdown(f"### {T['capabilities']}")
    st.markdown(T["capability_list"])

    if st.button(T["clear_chat"], use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption(T["footer"])


# ==================================================
# 7. CUSTOM CSS
# ==================================================

st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(ellipse at 75% 0%, #1b2850 0%, transparent 38%),
        #0b1020;
    color: #f1f5f9;
}

[data-testid="stHeader"] {
    background: transparent;
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #111a2e, #0d1425);
    border-right: 1px solid rgba(148,163,184,0.12);
}

.block-container {
    max-width: 1450px;
    padding-top: 2rem;
    padding-bottom: 5rem;
}

h1, h2, h3 {
    color: #f8fafc !important;
}

p, label {
    color: #cbd5e1;
}

.hero {
    padding: 32px;
    border: 1px solid rgba(129,140,248,0.25);
    border-radius: 22px;
    background: linear-gradient(
        120deg,
        rgba(79,70,229,0.20),
        rgba(30,41,59,0.45)
    );
    margin-bottom: 25px;
}

.hero-tag {
    color: #a5b4fc;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 2px;
    margin-bottom: 12px;
}

.hero h1 {
    font-size: 38px;
    font-weight: 800;
    margin: 0;
}

.hero h1 span {
    color: #a5b4fc;
}

.hero p {
    color: #aab7cc;
    font-size: 15px;
    margin-top: 12px;
}

[data-testid="stMetric"] {
    background: linear-gradient(145deg, #17233b, #111a2e);
    border: 1px solid rgba(148,163,184,0.13);
    border-radius: 17px;
    padding: 20px;
}

[data-testid="stMetricLabel"] {
    color: #94a3b8 !important;
}

[data-testid="stMetricValue"] {
    color: #f8fafc !important;
    font-weight: 800;
}

.stButton > button {
    background: #17233b;
    color: #e2e8f0;
    border: 1px solid rgba(129,140,248,0.25);
    border-radius: 12px;
    min-height: 45px;
    font-weight: 600;
    transition: all 0.2s ease;
}

.stButton > button:hover {
    border-color: #818cf8;
    background: #26345a;
    color: white;
}

[data-testid="stChatInput"] {
    background: #17233b;
    border: 1px solid rgba(129,140,248,0.35);
    border-radius: 16px;
}

[data-testid="stChatMessage"] {
    background: rgba(21,31,53,0.65);
    border: 1px solid rgba(148,163,184,0.10);
    border-radius: 16px;
    padding: 15px;
    margin-bottom: 12px;
}

[data-testid="stExpander"] {
    background: rgba(21,31,53,0.55);
    border: 1px solid rgba(148,163,184,0.13);
    border-radius: 12px;
}

hr {
    border-color: rgba(148,163,184,0.15);
}

footer {
    visibility: hidden;
}

</style>
""", unsafe_allow_html=True)


# ==================================================
# 8. DASHBOARD STATISTICS
# ==================================================

def get_dashboard_stats():

    _, revenue_rows, _ = execute_readonly_query("""
        SELECT
            ROUND(COALESCE(SUM(total_amount), 0), 2) AS revenue,
            COUNT(*) AS orders
        FROM orders
        WHERE status = 'delivered'
    """, max_rows=1)

    _, customer_rows, _ = execute_readonly_query(
        "SELECT COUNT(*) AS customers FROM customers",
        max_rows=1,
    )

    revenue = revenue_rows[0]["revenue"] if revenue_rows else 0
    orders = revenue_rows[0]["orders"] if revenue_rows else 0
    customers = customer_rows[0]["customers"] if customer_rows else 0

    return revenue, orders, customers


# ==================================================
# 9. HERO SECTION
# ==================================================

st.markdown(
    f"""
    <div class="hero">
        <div class="hero-tag">✦ {T['hero_tag']}</div>
        <h1>{T['hero_title']} <span>{T['hero_highlight']}</span></h1>
        <p>{T['hero_desc']}</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ==================================================
# 10. KPI CARDS
# ==================================================

try:

    revenue, orders, customers = get_dashboard_stats()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(T["revenue"], f"{float(revenue):,.2f}")

    with col2:
        st.metric(T["orders"], f"{int(orders):,}")

    with col3:
        st.metric(T["customers"], f"{int(customers):,}")

except Exception as exc:
    st.warning(f"{T['error']}: {exc}")


# ==================================================
# 11. QUICK QUESTIONS
# ==================================================

st.markdown(f"### {T['explore']}")

def queue_question(question):
    st.session_state.pending_question = question


questions = T["questions"]

for start in range(0, len(questions), 3):

    cols = st.columns(3)

    for col, question in zip(cols, questions[start:start + 3]):

        with col:

            index = questions.index(question)

            st.button(
                question,
                key=f"quick_{language}_{index}",
                use_container_width=True,
                on_click=queue_question,
                args=(question,),
            )


# ==================================================
# 12. RESULT RENDERING
# ==================================================

def render_result(result, key_suffix="0"):

    if result.get("error"):
        st.error(result["error"])
        return

    if result.get("mode") == "demo":
        st.caption(f"● {T['demo']}")
    else:
        st.caption(f"● {T['openai']}")

    sql = result.get("sql")

    if sql:

        with st.expander(T["sql"]):

            st.code(sql, language="sql")

            if result.get("sql_explanation"):
                st.caption(result["sql_explanation"])

    rows = result.get("rows") or []
    columns = result.get("columns") or []

    if not rows:
        st.info(T["no_results"])
        return

    frame = pd.DataFrame(rows, columns=columns or None)

    st.markdown(f"#### {T['results']}")

    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        T["download"],
        data=frame.to_csv(index=False).encode("utf-8-sig"),
        file_name="analysis_results.csv",
        mime="text/csv",
        key=f"download_{key_suffix}",
    )

    numeric_columns = frame.select_dtypes(
        include="number"
    ).columns.tolist()

    label_column = next(
        (
            column for column in frame.columns
            if column not in numeric_columns
        ),
        None,
    )

    if len(frame) > 1 and numeric_columns and label_column:

        value_column = numeric_columns[0]

        if "month" in label_column.lower():

            figure = px.line(
                frame,
                x=label_column,
                y=value_column,
                markers=True,
                title=T["chart"],
            )

        else:

            figure = px.bar(
                frame.head(20),
                x=label_column,
                y=value_column,
                title=T["chart"],
            )

        figure.update_layout(
            template="plotly_dark",
            height=370,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=10, r=10, t=55, b=10),
            font=dict(color="#cbd5e1"),
        )

        st.plotly_chart(
            figure,
            use_container_width=True,
            config={"displayModeBar": False},
        )

    if result.get("truncated"):
        st.warning(T["truncated"])


# ==================================================
# 13. CHAT HISTORY
# ==================================================

for index, message in enumerate(st.session_state.messages):

    with st.chat_message(message["role"]):

        st.markdown(message["content"])

        if message.get("result"):
            render_result(
                message["result"],
                key_suffix=f"history_{index}",
            )


# ==================================================
# 14. CHAT INPUT AND AGENT EXECUTION
# ==================================================

prompt = st.chat_input(T["placeholder"])

queued_prompt = st.session_state.pop(
    "pending_question",
    None,
)

if queued_prompt:
    prompt = queued_prompt


if prompt:

    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
    })

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):

        with st.spinner(T["thinking"]):

            try:
                result = run_analysis(prompt)

            except Exception as exc:
                result = {
                    "error": str(exc),
                    "analysis": None,
                }

        answer = (
            result.get("analysis")
            or result.get("error")
            or "No response generated."
        )

        if result.get("error"):
            st.error(answer)
        else:
            st.markdown(answer)

        render_result(
            result,
            key_suffix=f"new_{len(st.session_state.messages)}",
        )

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "result": result,
    })
