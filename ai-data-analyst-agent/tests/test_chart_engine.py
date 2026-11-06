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
