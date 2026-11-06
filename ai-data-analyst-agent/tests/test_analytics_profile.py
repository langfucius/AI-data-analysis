from app.analytics.profile import build_profile


def test_profile_calculates_descriptive_statistics():
    result = build_profile(
        ["revenue", "customer_id"],
        [
            {"revenue": 100, "customer_id": 1},
            {"revenue": 200, "customer_id": 2},
            {"revenue": 300, "customer_id": 3},
        ],
    )

    assert result["row_count"] == 3
    assert result["column_count"] == 2
    assert "revenue" in result["numeric_summary"]["column"].tolist()
    assert "customer_id" not in result["numeric_summary"]["column"].tolist()


def test_profile_counts_missing_values():
    result = build_profile(
        ["revenue"],
        [
            {"revenue": 100},
            {"revenue": None},
            {"revenue": 300},
        ],
    )

    assert result["missing_cells"] == 1
