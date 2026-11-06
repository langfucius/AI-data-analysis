"""Descriptive statistics for query results."""

import re
import pandas as pd


def build_profile(columns, rows):
    df = pd.DataFrame(rows)

    if columns and not df.empty:
        df = df[[c for c in columns if c in df.columns]]

    numeric_records = []

    for col in df.columns:
        if re.search(
            r"(^|[_\W])(id|key|code|phone|zip|postal)([_\W]|$)",
            str(col),
            re.IGNORECASE,
        ):
            continue

        values = pd.to_numeric(df[col], errors="coerce").dropna()

        if len(values) < 2 or values.nunique() < 2:
            continue

        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1

        outliers = (
            (values < q1 - 1.5 * iqr)
            | (values > q3 + 1.5 * iqr)
        ).sum()

        numeric_records.append({
            "column": str(col),
            "mean": round(float(values.mean()), 3),
            "median": round(float(values.median()), 3),
            "std": round(float(values.std()), 3),
            "min": round(float(values.min()), 3),
            "max": round(float(values.max()), 3),
            "iqr_outliers": int(outliers),
        })

    numeric_df = pd.DataFrame(numeric_records)

    numeric_data = pd.DataFrame()

    for col in df.columns:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.notna().mean() >= 0.8 and values.nunique() >= 2:
            numeric_data[col] = values

    correlation = (
        numeric_data.corr().round(3)
        if len(numeric_data.columns) >= 2
        else None
    )

    return {
        "row_count": len(df),
        "column_count": len(df.columns),
        "missing_cells": int(df.isna().sum().sum()),
        "numeric_summary": numeric_df,
        "correlation": correlation,
    }
