"""Deterministic, non-mutating statistical profiling without optional SciPy."""
from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd


def column_types(frame: pd.DataFrame) -> dict[str, list[str]]:
    """Infer dates conservatively; identifiers are numeric but not measures."""
    kinds: dict[str, list[str]] = {k: [] for k in ("numeric", "categorical", "date", "identifier")}
    for name in frame.columns:
        s = frame[name]
        identifier = bool(re.search(r"(^|_)(id|key|code|zip|phone)($|_)", str(name), re.I))
        if identifier:
            kinds["identifier"].append(name)
        is_date = pd.api.types.is_datetime64_any_dtype(s)
        if not is_date and not pd.api.types.is_numeric_dtype(s) and s.notna().any():
            values = s.dropna().astype(str)
            if values.str.match(r"^\d{4}[-/]\d{1,2}([-/]\d{1,2})?([ T].*)?$").all():
                is_date = pd.to_datetime(values, errors="coerce", format="mixed").notna().all()
        if is_date:
            kinds["date"].append(name)
        elif pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            kinds["numeric"].append(name)
        else:
            kinds["categorical"].append(name)
    return kinds


def _kendall(x: np.ndarray, y: np.ndarray) -> float:
    """Kendall tau-b, O(n log n) with ties and pairwise missing deletion."""
    n = len(x)
    if n < 2:
        return float("nan")
    def ties(a: np.ndarray) -> int:
        _, counts = np.unique(a, return_counts=True)
        return int(sum(int(c) * (int(c) - 1) // 2 for c in counts))
    pairs = n * (n - 1) // 2
    denominator = math.sqrt((pairs - ties(x)) * (pairs - ties(y)))
    if not denominator:
        return float("nan")
    ranks = np.searchsorted(np.unique(y), y) + 1
    order = np.lexsort((y, x))
    tree = [0] * (int(ranks.max()) + 1)
    def prefix(i: int) -> int:
        value = 0
        while i:
            value += tree[i]
            i -= i & -i
        return value
    score = seen = start = 0
    while start < n:
        end = start + 1
        while end < n and x[order[end]] == x[order[start]]:
            end += 1
        for index in order[start:end]:
            rank = int(ranks[index])
            score += prefix(rank - 1) - (seen - prefix(rank))
        for index in order[start:end]:
            rank = int(ranks[index])
            while rank < len(tree):
                tree[rank] += 1
                rank += rank & -rank
            seen += 1
        start = end
    return score / denominator


def correlation(frame: pd.DataFrame, method: str = "pearson") -> pd.DataFrame:
    if method not in {"pearson", "spearman", "kendall"}:
        raise ValueError("Choose pearson, spearman or kendall.")
    numeric = frame[column_types(frame)["numeric"]].replace([np.inf, -np.inf], np.nan)
    result = pd.DataFrame(np.nan, index=numeric.columns, columns=numeric.columns)
    for i, a in enumerate(numeric.columns):
        for b in numeric.columns[i:]:
            pair = numeric[[a, b]].dropna() if a != b else numeric[[a]].dropna()
            x = pair.iloc[:, 0].to_numpy(dtype=float)
            y = pair.iloc[:, -1].to_numpy(dtype=float)
            value = float("nan")
            if len(x) >= 2 and np.ptp(x) > 0 and np.ptp(y) > 0:
                if method == "kendall":
                    value = _kendall(x, y)
                else:
                    if method == "spearman":
                        x, y = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
                    value = float(np.corrcoef(x, y)[0, 1])
            result.loc[a, b] = result.loc[b, a] = value
    return result


def build_advanced_profile(frame: pd.DataFrame) -> dict[str, Any]:
    """All statistics describe loaded rows; no input conversion or mutation."""
    kinds = column_types(frame)
    summaries, quality, outliers, distributions = [], [], [], {}
    for name in frame.columns:
        s = frame[name]
        missing = int(s.isna().sum())
        info = {"column": name, "dtype": str(s.dtype), "missing": missing,
                "missing_percent": 100 * missing / len(frame) if len(frame) else 0.0,
                "unique": int(s.nunique(dropna=True)), "constant": s.nunique(dropna=True) <= 1,
                "identifier": name in kinds["identifier"], "non_finite": 0}
        if name in kinds["numeric"]:
            finite = s.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
            info["non_finite"] = int((s.notna() & ~np.isfinite(s.astype(float))).sum())
            q1, q3 = finite.quantile(.25), finite.quantile(.75)
            low, high = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
            mask = (finite < low) | (finite > high)
            outliers.append({"column": name, "lower": low, "upper": high, "count": int(mask.sum())})
            summary = {"column": name, **finite.describe().to_dict(), "median": finite.median(),
                       "sum": finite.sum(min_count=1), "skew": finite.skew(), "zeros": int((finite == 0).sum())}
            summaries.append(summary)
            counts, edges = np.histogram(finite, bins=min(20, max(1, int(len(finite) ** .5)))) if len(finite) else ([], [])
            distributions[name] = {"counts": list(map(int, counts)), "edges": list(map(float, edges))}
        else:
            distributions[name] = [{"value": str(k), "count": int(v)} for k, v in s.value_counts(dropna=True).head(20).items()]
        quality.append(info)
    return {"row_count": len(frame), "column_count": len(frame.columns), "types": kinds,
            "missing_cells": int(frame.isna().sum().sum()), "duplicate_rows": int(frame.duplicated().sum()),
            "numeric_summary": summaries, "column_quality": quality, "outliers": outliers,
            "distributions": distributions,
            "correlations": {m: correlation(frame, m) for m in ("pearson", "spearman", "kendall")}}
