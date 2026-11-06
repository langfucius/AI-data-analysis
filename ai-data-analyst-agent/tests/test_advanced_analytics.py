"""Contract tests for statistics, immutable snapshots and real chart values."""
import json

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from app.analytics.advanced_profile import build_advanced_profile, column_types, correlation
from app.analytics.advanced_result import AnalysisResult
from app.analytics.advanced_service import analyze_sql
from app.analytics.advanced_visualization import AdvancedChartSpec as Spec, create_advanced_chart, recommend_charts


@pytest.fixture
def result():
    frame = pd.DataFrame({"date": ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01"],
                          "category": ["A", "A", "B", "B"], "revenue": [10., 20., 30., 40.],
                          "units": [1, 2, 3, 4], "customer_id": [1, 2, 3, 4]})
    return AnalysisResult.from_query(list(frame.columns), frame.to_dict("records"), question="business overview")


def test_statistics_missing_duplicates_outliers():
    frame = pd.DataFrame({"value": [1., 1., 2., 2., 3., 100., None], "group": ["A"] * 7})
    original = frame.copy(deep=True)
    p = build_advanced_profile(frame)
    assert p["missing_cells"] == 1
    assert p["duplicate_rows"] == 2
    assert p["outliers"][0]["count"] == 1
    s = p["numeric_summary"][0]
    assert s["sum"] == 109 and s["median"] == 2
    assert s["mean"] == pytest.approx(109 / 6)
    assert p["column_quality"][0]["missing_percent"] == pytest.approx(100 / 7)
    assert sum(p["distributions"]["value"]["counts"]) == 6
    assert_frame_equal(frame, original)


@pytest.mark.parametrize("method", ["pearson", "spearman", "kendall"])
def test_correlation_pairwise_and_constants(method):
    frame = pd.DataFrame({"a": [1, 2, 3, None], "b": [3, 2, 1, 9], "constant": [1] * 4})
    matrix = correlation(frame, method)
    assert matrix.loc["a", "b"] == pytest.approx(-1)
    assert np.isnan(matrix.loc["constant", "constant"])


def test_kendall_ties_known_value():
    frame = pd.DataFrame({"a": [1, 1, 2, 3], "b": [1, 2, 2, 3]})
    assert correlation(frame, "kendall").loc["a", "b"] == pytest.approx(.8)


def test_spearman_uses_ranks():
    frame = pd.DataFrame({"a": [1, 2, 3, 4], "b": [1, 4, 9, 16]})
    assert correlation(frame, "spearman").loc["a", "b"] == pytest.approx(1)
    assert correlation(frame, "pearson").loc["a", "b"] < 1


def test_date_and_identifier_inference():
    frame = pd.DataFrame({"period": ["2025-01", "2025-02"], "code": [1, 2],
                          "label": ["123", "456"], "bad_date": ["2025-01-01", "invalid"]})
    t = column_types(frame)
    assert t["date"] == ["period"]
    assert "code" in t["identifier"] and "bad_date" in t["categorical"]
    assert "label" not in t["numeric"]


def test_snapshot_defensive_copies_and_exports(result):
    before = result.snapshot_id
    frame = result.dataframe
    frame.loc[0, "revenue"] = 999
    profile = result.profile
    profile["numeric_summary"][0]["mean"] = 999
    rows = result.rows
    rows[0]["revenue"] = 999
    assert result.snapshot_id == before
    assert result.dataframe.loc[0, "revenue"] == 10
    assert result.profile["numeric_summary"][0]["mean"] == 25
    assert "mean=25.0" in result.summary()
    assert json.loads(json.dumps(result.to_dict(), allow_nan=False))["loaded_row_count"] == 4


def test_input_rows_are_copied():
    rows = [{"a": 1}]
    r = AnalysisResult.from_query(["a"], rows)
    rows[0]["a"] = 2
    assert r.rows == [{"a": 1}]


@pytest.mark.parametrize("spec,trace", [
    (Spec("bar", "category", "revenue", "sum"), "bar"),
    (Spec("line", "date", "revenue", "sum"), "scatter"),
    (Spec("scatter", "units", "revenue"), "scatter"),
    (Spec("histogram", "revenue"), "histogram"),
    (Spec("box", "category", "revenue"), "box"),
    (Spec("heatmap"), "heatmap"),
    (Spec("pie", "category", "revenue", "sum"), "pie"),
])
def test_all_chart_types_and_snapshot(result, spec, trace):
    before = result.dataframe
    fig = create_advanced_chart(result, spec)
    assert fig.data[0].type == trace
    assert fig.layout.meta["snapshot_id"] == result.snapshot_id
    assert len(fig.to_json()) > 100
    assert_frame_equal(before, result.dataframe)


@pytest.mark.parametrize("aggregation,expected", [("sum", [30, 70]), ("mean", [15, 35]),
                                                   ("median", [15, 35]), ("count", [2, 2]),
                                                   ("min", [10, 30]), ("max", [20, 40])])
def test_aggregations(result, aggregation, expected):
    fig = create_advanced_chart(result, Spec("bar", "category", "revenue", aggregation))
    assert list(fig.data[0].y) == expected


@pytest.mark.parametrize("spec", [Spec("invalid"), Spec("bar", "absent", "revenue"),
    Spec("scatter", "category", "revenue"), Spec("histogram", "category"),
    Spec("bar", "category", "date"), Spec("line", "category", "revenue"),
    Spec("bar", "category", "revenue", "invalid"), Spec("pie", "category", "revenue", color="units"),
    Spec("histogram", "revenue", aggregation="sum"), Spec("heatmap", correlation_method="invalid")])
def test_invalid_chart_configurations(result, spec):
    with pytest.raises(ValueError):
        create_advanced_chart(result, spec)


def test_recommendations_are_deterministic(result):
    specs = recommend_charts(result)
    assert specs == recommend_charts(result)
    assert specs[0].chart_type == "line"
    assert all(s.y != "customer_id" for s in specs)
    assert not any(s.chart_type == "scatter" for s in specs)
    relationship = AnalysisResult.from_query(result.columns, result.rows, question="relationship")
    assert recommend_charts(relationship)[0].chart_type == "scatter"


def test_null_and_nonfinite_handling():
    r = AnalysisResult.from_query(["x", "y"], [{"x": "A", "y": None}, {"x": "A", "y": 2.}, {"x": "B", "y": float("inf")}])
    assert r.profile["column_quality"][1]["non_finite"] == 1
    fig = create_advanced_chart(r, Spec("bar", "x", "y", "sum"))
    assert list(fig.data[0].y) == [2]
    count = create_advanced_chart(r, Spec("bar", "x", "y", "count"))
    assert list(count.data[0].y) == [2, 1]
    json.dumps(r.to_dict(), allow_nan=False)


def test_empty_result_and_truncation():
    empty = AnalysisResult.from_query(["value"], [], truncated=True)
    assert empty.loaded_row_count == 0 and empty.profile["missing_cells"] == 0
    assert "truncated" in empty.summary()
    assert recommend_charts(empty) == []
    with pytest.raises(ValueError, match="No loaded"):
        create_advanced_chart(empty, Spec("histogram", "value"))


def test_real_sql_snapshot_and_source():
    r = analyze_sql("SELECT order_id, total_amount FROM orders ORDER BY order_id LIMIT 3")
    assert r.loaded_row_count == 3 and r.source_tables == ("orders",)
    assert r.limit_applied and "LIMIT" in r.scope_notice
    assert r.profile["numeric_summary"][1]["sum"] == pytest.approx(sum(row["total_amount"] for row in r.rows))


@pytest.mark.parametrize("sql", ["DELETE FROM orders", "DROP TABLE orders", "PRAGMA table_info(orders)",
                                "SELECT * FROM orders; DELETE FROM orders", "SELECT load_extension('x')",
                                "SELECT * FROM main.orders", "SELECT * FROM sqlite_master",
                                "WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x",
                                "WITH x AS (DELETE FROM orders WHERE) SELECT * FROM x"])
def test_service_sql_safety(sql):
    from app.agent.sql_safety import SQLSafetyError
    with pytest.raises(SQLSafetyError):
        analyze_sql(sql)


def test_pie_negative_rejected():
    r = AnalysisResult.from_query(["group", "value"], [{"group": "A", "value": -1}, {"group": "B", "value": 3}])
    with pytest.raises(ValueError, match="non-negative"):
        create_advanced_chart(r, Spec("pie", "group", "value", "sum"))


def test_line_duplicate_requires_aggregation():
    r = AnalysisResult.from_query(["day", "value"], [{"day": "2025-01-01", "value": 1}, {"day": "2025-01-01", "value": 2}])
    with pytest.raises(ValueError, match="aggregation"):
        create_advanced_chart(r, Spec("line", "day", "value"))


def test_duplicate_aliases_rejected():
    with pytest.raises(ValueError, match="unique"):
        AnalysisResult.from_query(["x", "x"], [])


def test_count_with_entirely_missing_y():
    r = AnalysisResult.from_query(["group", "value"], [{"group": "A", "value": float("nan")}, {"group": "B", "value": float("nan")}])
    fig = create_advanced_chart(r, Spec("bar", "group", "value", "count"))
    assert list(fig.data[0].y) == [1, 1]


def test_histogram_requires_numeric_x_even_with_y(result):
    with pytest.raises(ValueError, match="numeric"):
        create_advanced_chart(result, Spec("histogram", "category", "revenue"))


def test_snapshot_roundtrip(result):
    restored = AnalysisResult.from_dict(result.to_dict())
    assert restored.to_dict() == result.to_dict()
    assert restored.timestamp == result.timestamp
    assert_frame_equal(restored.profile["correlations"]["kendall"], result.profile["correlations"]["kendall"])
    altered = result.to_dict()
    altered["rows"][0]["revenue"] = 999
    with pytest.raises(ValueError, match="fingerprint"):
        AnalysisResult.from_dict(altered)
