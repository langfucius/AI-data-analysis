"""Business explanations and presentation must agree with the loaded rows."""
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app.analytics.advanced_result import AnalysisResult
from app.analytics.advanced_visualization import AdvancedChartSpec, create_advanced_chart, recommend_charts
from app.analytics.business_insights import build_business_insights
from app.agent import llm


ROOT = Path(__file__).resolve().parents[1]


def result(rows, question="分析收入变化"):
    return AnalysisResult.from_query(list(rows[0]), rows, question=question)


def test_trend_endpoints_latest_month_and_peak():
    snapshot = result([{"month": "2025-03", "revenue": 180}, {"month": "2025-01", "revenue": 100},
                       {"month": "2025-02", "revenue": 200}])
    insights = {i.id: i for i in build_business_insights(snapshot)}
    trend = insights["trend"]
    assert trend.evidence["change_percent"] == 80
    assert trend.evidence["peak_period"] == "2025-02"
    assert "不代表期间持续同向变化" in trend.text
    assert insights["latest_period"].evidence["change_percent"] == pytest.approx(-10)
    assert "完整" in insights["latest_period"].text
    assert "走势与高点" in snapshot.summary()


def test_missing_month_does_not_claim_month_over_month():
    snapshot = result([{"month": "2025-01", "revenue": 100}, {"month": "2025-03", "revenue": 200}])
    assert "latest_period" not in {i.id for i in build_business_insights(snapshot)}


@pytest.mark.parametrize("starting", [0, -100])
def test_nonpositive_base_does_not_invent_growth_rate(starting):
    snapshot = result([{"month": "2025-01", "revenue": starting}, {"month": "2025-02", "revenue": 200}])
    trend = next(i for i in build_business_insights(snapshot) if i.id == "trend")
    assert trend.evidence["change_percent"] is None
    assert "不计算增长率" in trend.text


def test_rank_shares_use_only_returned_groups_and_business_measure():
    snapshot = result([{"product_name": "A", "units_sold": 99, "revenue": 100},
                       {"product_name": "B", "units_sold": 1, "revenue": 300}], "分析畅销产品的收入差异")
    insight = next(i for i in build_business_insights(snapshot) if i.kind == "comparison")
    assert insight.evidence["measure"] == "revenue"
    assert insight.evidence["top_group"] == "B"
    assert insight.evidence["gap"] == 200
    assert insight.evidence["share_percent"] == 75
    assert "不代表未返回数据" in insight.text
    assert recommend_charts(snapshot)[0].y == "revenue"


def test_rates_not_summed_and_no_share_of_averages():
    snapshot = result([{"category": "A", "conversion_rate": .1}, {"category": "A", "conversion_rate": .3},
                       {"category": "B", "conversion_rate": .5}], "分析类别转化率")
    spec = recommend_charts(snapshot)[0]
    assert spec.aggregation == "mean"
    insight = next(i for i in build_business_insights(snapshot) if i.kind == "comparison")
    assert insight.evidence["bottom"] == pytest.approx(.2)
    assert insight.evidence["share_percent"] is None


def test_scalar_business_meaning_and_derived_order_value():
    snapshot = result([{"total_revenue": 1000, "delivered_orders": 4}], "总收入是多少")
    insights = build_business_insights(snapshot)
    assert insights[0].evidence["total_revenue"] == 1000
    assert insights[1].evidence["revenue_per_order"] == 250
    assert "每单收入约 250" in snapshot.summary()
    assert recommend_charts(snapshot) == []


def test_correlation_text_has_pair_count_and_no_causal_claim():
    snapshot = result([{"revenue": 10, "orders": 1}, {"revenue": 20, "orders": 2},
                       {"revenue": 30, "orders": 3}, {"revenue": None, "orders": 4}], "分析收入与订单的相关关系")
    insight = next(i for i in build_business_insights(snapshot) if i.kind == "correlation")
    assert insight.evidence["pair_count"] == 3
    assert insight.evidence["pearson"] == pytest.approx(1)
    assert "不能证明因果" in insight.text


def test_negative_comparison_does_not_make_pie_share():
    snapshot = result([{"category": "A", "profit": -10}, {"category": "B", "profit": 20}])
    insight = next(i for i in build_business_insights(snapshot) if i.kind == "comparison")
    assert insight.evidence["share_percent"] is None


def test_presentation_is_horizontal_sorted_and_preserves_values():
    snapshot = result([{"category": "A", "revenue": 10}, {"category": "B", "revenue": 30}])
    original = snapshot.dataframe
    fig = create_advanced_chart(snapshot, AdvancedChartSpec("bar", "category", "revenue", "sum"),
                                language="zh", theme="dark", presentation=True)
    assert fig.data[0].orientation == "h"
    assert list(fig.data[0].x) == [10, 30]
    assert fig.layout.yaxis.categoryorder == "total ascending"
    assert "收入" in fig.layout.title.text
    assert fig.layout.meta["snapshot_id"] == snapshot.snapshot_id
    pd.testing.assert_frame_equal(original, snapshot.dataframe)


def test_trend_chart_marks_actual_peak():
    snapshot = result([{"month": "2025-01", "revenue": 100}, {"month": "2025-02", "revenue": 200}])
    fig = create_advanced_chart(snapshot, recommend_charts(snapshot)[0], language="zh", presentation=True)
    assert fig.layout.annotations[0].y == 200
    assert "最高" in fig.layout.annotations[0].text


def test_unified_workspace_has_explorer_and_safe_sql(monkeypatch):
    monkeypatch.setattr(llm, "get_openai_api_key", lambda: "")
    app = AppTest.from_file(str(ROOT / "app/ui/streamlit_app.py"), default_timeout=90).run()
    assert not app.exception
    app.radio(key="workspace_mode").set_value("explore").run()
    assert not app.exception
    assert app.session_state.workspace_snapshot.loaded_row_count > 0
    assert len(app.get("plotly_chart")) >= 1
    fingerprint = app.session_state.workspace_snapshot.snapshot_id
    app.text_area(key="workspace_sql").set_value("DELETE FROM orders")
    app.button(key="FormSubmitter:workspace_query-执行查询").click().run()
    assert not app.exception and len(app.error) == 1
    assert app.session_state.workspace_snapshot.snapshot_id == fingerprint


def test_chart_selection_survives_chat_rerun(monkeypatch):
    monkeypatch.setattr(llm, "get_openai_api_key", lambda: "")
    app = AppTest.from_file(str(ROOT / "app/ui/streamlit_app.py"), default_timeout=90).run()
    app.session_state.pending_question = "展示每月收入趋势。"
    app.run()
    assert not app.exception
    chart_view = next(s for s in app.selectbox if s.label == "图表视角")
    assert len(chart_view.options) >= 2
    chart_view.set_value(1).run()
    assert not app.exception
    assert next(s for s in app.selectbox if s.label == "图表视角").value == 1
    assert len(app.get("plotly_chart")) == 1


def test_categorical_record_counts_are_not_called_revenue():
    snapshot = result([{"segment": "A"}, {"segment": "A"}, {"segment": "B"}], "分析客户分层")
    insight = next(i for i in build_business_insights(snapshot) if i.kind == "composition")
    assert insight.evidence["share_percent"] == pytest.approx(200 / 3)
    assert "不代表收入" in insight.text


@pytest.mark.parametrize("kind,x,y,aggregation", [
    ("bar", "category", "revenue", "sum"), ("line", "month", "revenue", "sum"),
    ("scatter", "units", "revenue", "none"), ("histogram", "revenue", None, "none"),
    ("box", "category", "revenue", "none"), ("heatmap", None, None, "none"),
    ("pie", "category", "revenue", "sum"),
])
def test_all_presentation_modes_serialize(kind, x, y, aggregation):
    snapshot = result([{"category": "A", "month": "2025-01", "revenue": 10, "units": 1},
                       {"category": "B", "month": "2025-02", "revenue": 20, "units": 2}])
    fig = create_advanced_chart(snapshot, AdvancedChartSpec(kind, x, y, aggregation),
                                language="zh", theme="dark", presentation=True)
    assert fig.layout.meta["snapshot_id"] == snapshot.snapshot_id
    assert len(fig.to_json()) > 100
