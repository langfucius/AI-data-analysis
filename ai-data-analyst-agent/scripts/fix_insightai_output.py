from pathlib import Path
from datetime import datetime
import shutil
import re
import subprocess
import sys

ROOT = Path.cwd()

targets = [
    "app/agent/graph.py",
    "app/analytics/chart_engine.py",
    "app/analytics/analysis_output.py",
    "tests/test_analysis_output.py",
]

backup = (
    ROOT / ".insightai_backups"
    / ("output_fix_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
)

# --------------------------------------------------
# 1. Read and validate existing source
# --------------------------------------------------

graph_path = ROOT / "app/agent/graph.py"
chart_path = ROOT / "app/analytics/chart_engine.py"

graph = graph_path.read_text(encoding="utf-8-sig")
chart = chart_path.read_text(encoding="utf-8-sig")

if "def analyze_results_node" not in graph:
    raise RuntimeError("Cannot locate analyze_results_node.")

if "def render_chart" not in chart:
    raise RuntimeError("Cannot locate render_chart.")

# --------------------------------------------------
# 2. Patch analysis output pipeline
# --------------------------------------------------

if "sanitize_analysis_text" not in graph:

    old = '''def analyze_results_node(state: AgentState) -> dict[str, Any]:
    analysis = summarize_results(
        question=state.get("question", ""),
        sql=state.get("sql", ""),
        columns=state.get("columns", []),
        rows=state.get("rows", []),
        mode=state.get("mode", "demo"),
    )

    return {"analysis": analysis, "error": ""}
'''

    new = '''def analyze_results_node(state: AgentState) -> dict[str, Any]:
    """Generate evidence-based prose without duplicating Plotly charts."""

    from app.analytics.analysis_output import sanitize_analysis_text

    analysis = summarize_results(
        question=state.get("question", ""),
        sql=state.get("sql", ""),
        columns=state.get("columns", []),
        rows=state.get("rows", []),
        mode=state.get("mode", "demo"),
    )

    analysis = sanitize_analysis_text(
        analysis,
        question=state.get("question", ""),
    )

    return {"analysis": analysis, "error": ""}
'''

    if old not in graph:
        raise RuntimeError(
            "The current graph.py differs from the expected version. "
            "No files have been changed."
        )

    graph = graph.replace(old, new, 1)

# --------------------------------------------------
# 3. Improve Plotly theme
# --------------------------------------------------

if 'template="plotly_dark"' not in chart:

    pattern = re.compile(
        r'''    fig\.update_layout\(
        template="plotly_white",
        height=420,
        margin=dict\(l=40, r=25, t=65, b=45\),
        hovermode="closest",
    \)

    return fig''',
        re.VERBOSE,
    )

    replacement = '''    # InsightAI unified dark visualization theme
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
            x=0.02,
            xanchor="left",
            font=dict(size=19, color="#F9FAFB"),
        ),
        height=430,
        margin=dict(l=55, r=65, t=75, b=65),
        hovermode="closest",
        hoverlabel=dict(
            bgcolor="#1F2937",
            font_color="#FFFFFF",
        ),
    )

    fig.update_xaxes(
        showgrid=False,
        zeroline=False,
        automargin=True,
    )

    fig.update_yaxes(
        showgrid=True,
        gridcolor="rgba(148,163,184,0.18)",
        zeroline=False,
        automargin=True,
        tickformat=",",
    )

    if spec.chart_type == "bar":
        fig.update_traces(
            marker_color="#78BDF2",
            marker_line_width=0,
            texttemplate="%{y:,.0f}",
            textposition="outside",
            cliponaxis=False,
        )

    elif spec.chart_type == "line":
        fig.update_traces(
            line=dict(color="#60A5FA", width=3),
            marker=dict(size=7, color="#93C5FD"),
        )

    elif spec.chart_type == "scatter":
        fig.update_traces(
            marker=dict(
                color="#60A5FA",
                size=9,
                opacity=0.8,
            )
        )

    elif spec.chart_type == "histogram":
        fig.update_traces(
            marker_color="#78BDF2",
            marker_line_width=0,
            opacity=0.85,
        )

    return fig'''

    updated, count = pattern.subn(replacement, chart, count=1)

    if count != 1:
        raise RuntimeError(
            "Cannot locate original Plotly style block. "
            "No files have been changed."
        )

    chart = updated

# --------------------------------------------------
# 4. Analysis output sanitizer
# --------------------------------------------------

output_code = r'''
"""Clean LLM analysis output before displaying it in Streamlit.

Plotly owns visualization.
The LLM owns textual interpretation.
"""

import re


_CHART_INTRO = re.compile(
    r"(无法直接|不能直接|没法直接|无法在这里)"
    r".{0,35}(画|绘制|生成).{0,20}(图|图表)"
    r"|(?:以下|下面).{0,30}(可视化|字符画|条形图)",
    re.IGNORECASE,
)

_CHART_HEADING = re.compile(
    r"(横向条形图|纵向条形图|条形图|柱状图|折线图|"
    r"散点图|直方图|箱线图|饼图|ASCII\s*chart|"
    r"text\s*chart|bar\s*chart)",
    re.IGNORECASE,
)

_CHART_ART = re.compile(
    r"[█▇▆▅▄▃▂▁▓▒░■□▰▮▯━─═]{5,}"
)

_INSIGHT_HEADING = re.compile(
    r"(关键发现|业务洞察|分析结论|结论|建议|"
    r"业务建议|总结|recommendations?|insights?|"
    r"conclusions?|key findings?)",
    re.IGNORECASE,
)


def _is_chart_row(line: str) -> bool:
    text = line.strip()

    if not text:
        return False

    if _CHART_ART.search(text):
        return True

    # Text tables belonging to a fake chart.
    if text.startswith("|") and text.endswith("|"):
        return True

    # Category + whitespace + numeric value.
    if re.search(
        r"\s{2,}[-+]?\d[\d,]*(?:\.\d+)?\s*(?:\([^)]*\))?$",
        text,
    ) and len(text) > 15:
        return True

    # Repeated ASCII bars.
    if re.search(r"[#=*~\-]{8,}", text):
        return True

    return False


def sanitize_analysis_text(
    content: str,
    question: str = "",
) -> str:
    """Remove duplicate text charts while preserving useful insights."""

    if not content:
        return "No additional textual analysis was returned."

    lines = str(content).replace("\r\n", "\n").split("\n")

    cleaned = []
    in_chart_block = False
    in_code_block = False

    for line in lines:
        text = line.strip()

        if not text:
            if not in_chart_block and cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue

        if _CHART_INTRO.search(text):
            in_chart_block = True
            continue

        if _CHART_HEADING.search(text):
            in_chart_block = True
            continue

        if _CHART_ART.search(text):
            continue

        if text.startswith("```"):
            if in_chart_block:
                in_code_block = not in_code_block
                continue

            in_code_block = not in_code_block
            cleaned.append(line)
            continue

        if in_code_block:
            cleaned.append(line)
            continue

        if in_chart_block:
            if _is_chart_row(text):
                continue

            if _INSIGHT_HEADING.search(text):
                in_chart_block = False

            elif (
                text.startswith("#")
                or re.match(r"^(?:\d+[.)]|[-*])\s+", text)
            ):
                in_chart_block = False

            elif len(text) > 100:
                # A substantive prose paragraph begins.
                in_chart_block = False

            else:
                # Skip short labels and fragments belonging to a chart.
                continue

        cleaned.append(line.rstrip())

    result = "\n".join(cleaned).strip()

    # Remove repeated empty lines.
    result = re.sub(r"\n{3,}", "\n\n", result)

    if not result:
        if any("\u4e00" <= c <= "\u9fff" for c in question):
            return (
                "图表已由 InsightAI 本地 Plotly 引擎生成。"
                "模型未提供额外的文字分析，请查看上方图表和查询结果。"
            )

        return (
            "Charts were rendered by the local Plotly engine. "
            "No additional textual interpretation was returned."
        )

    return result
'''

# --------------------------------------------------
# 5. Regression tests
# --------------------------------------------------

test_code = r'''
from app.analytics.analysis_output import sanitize_analysis_text


def test_removes_chart_apology():
    text = (
        "我这里没法直接画图形界面，但可以用文字画出来。\n"
        "以下是查询结果的可视化：\n"
        "收入横向条形图 —— 每格约 100\n"
        "Clothing █████████ 1000"
    )

    result = sanitize_analysis_text(text, "分析收入")

    assert "没法直接画图形界面" not in result
    assert "横向条形图" not in result
    assert "████" not in result


def test_preserves_business_insights():
    text = (
        "收入横向条形图 —— 每格约 100\n"
        "Clothing █████████ 1000\n"
        "\n"
        "## 关键发现\n"
        "Clothing has the highest revenue among the categories."
    )

    result = sanitize_analysis_text(text)

    assert "横向条形图" not in result
    assert "关键发现" in result
    assert "highest revenue" in result


def test_preserves_normal_analysis():
    text = (
        "Total revenue is 835243.96.\n"
        "Clothing contributes the largest share of revenue."
    )

    result = sanitize_analysis_text(text)

    assert "835243.96" in result
    assert "largest share" in result


def test_empty_output_has_fallback():
    result = sanitize_analysis_text(
        "收入横向条形图\n"
        "Clothing █████████ 1000",
        "请分析收入",
    )

    assert "Plotly" in result
    assert "字符画" not in result


def test_preserves_recommendations_after_chart():
    text = (
        "收入柱状图\n"
        "Books █████ 500\n"
        "\n"
        "## 建议\n"
        "Investigate why the Home category has lower revenue."
    )

    result = sanitize_analysis_text(text)

    assert "建议" in result
    assert "Investigate" in result
'''

# --------------------------------------------------
# 6. Backup and write
# --------------------------------------------------

backup.mkdir(parents=True, exist_ok=True)

for relative in targets:
    source = ROOT / relative

    if source.exists():
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

new_files = []

try:
    graph_path.write_text(graph, encoding="utf-8")
    chart_path.write_text(chart, encoding="utf-8")

    output_path = ROOT / "app/analytics/analysis_output.py"
    test_path = ROOT / "tests/test_analysis_output.py"

    if not output_path.exists():
        new_files.append(output_path)

    if not test_path.exists():
        new_files.append(test_path)

    output_path.write_text(output_code.lstrip(), encoding="utf-8")
    test_path.write_text(test_code.lstrip(), encoding="utf-8")

    print("Source changes written.")
    print("Running complete test suite...\n")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    print(result.stdout)

    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError("Tests failed. Rolling back changes.")

    print("\nALL TESTS PASSED.")
    print("Backup:", backup)

except Exception as exc:
    print("\nERROR:", exc)
    print("Restoring previous source files...")

    for relative in targets:
        source = ROOT / relative
        previous = backup / relative

        if previous.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(previous, source)

    for path in new_files:
        if path.exists():
            path.unlink()

    raise
