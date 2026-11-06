"""Explain observed business patterns with reproducible, deterministic facts.

No extra query or model call is made. Every comparison uses the same loaded
snapshot; shares never imply a denominator outside those rows.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from app.analytics.advanced_result import AnalysisResult


LABELS = {
    "revenue": ("收入", "Revenue"), "total_revenue": ("总收入", "Total revenue"),
    "total_amount": ("订单金额", "Order amount"), "total_spending": ("消费金额", "Spending"),
    "units_sold": ("销量", "Units sold"), "quantity": ("数量", "Quantity"),
    "delivered_orders": ("已交付订单数", "Delivered orders"), "order_count": ("订单数", "Orders"),
    "total_orders": ("订单总数", "Total orders"), "average_order_value": ("平均订单金额", "Average order value"),
    "category": ("产品类别", "Product category"), "product_name": ("产品", "Product"),
    "customer_name": ("客户", "Customer"), "status": ("订单状态", "Order status"),
    "month": ("月份", "Month"), "order_date": ("订单日期", "Order date"),
    "city": ("城市", "City"), "segment": ("客户分层", "Customer segment"),
}
VALUE_LABELS = {"delivered": "已交付", "cancelled": "已取消", "canceled": "已取消",
                "pending": "待处理", "shipped": "已发货", "returned": "已退货"}
EVIDENCE_SEPARATOR = "\n\n---\n\n"


def display_name(name: str, chinese: bool = True) -> str:
    return LABELS.get(name.lower(), (name, name.replace("_", " ").title()))[0 if chinese else 1]


def display_value(value: Any, chinese: bool = True) -> str:
    return VALUE_LABELS.get(str(value), str(value)) if chinese else str(value)


def number(value: float) -> str:
    if not np.isfinite(value):
        return "—"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def aggregation_for(name: str) -> str:
    """Never sum rates, prices or already averaged measures in recommendations."""
    return "mean" if re.search(r"(^|_)(avg|average|mean|median|rate|ratio|pct|percent|percentage|price|margin)(_|$)", name.lower()) else "sum"


def measure_columns(result: AnalysisResult) -> list[str]:
    types = result.profile["types"]
    names = [c for c in types["numeric"] if c not in types["identifier"]]
    priority = {"revenue": 0, "total_revenue": 0, "total_spending": 1, "total_amount": 2,
                "average_order_value": 3, "units_sold": 4, "quantity": 5}
    return sorted(names, key=lambda c: priority.get(c.lower(), 10))


def category_columns(result: AnalysisResult) -> list[str]:
    types = result.profile["types"]
    frame = result.dataframe
    columns = [c for c in types["categorical"] if c not in types["identifier"] and 2 <= frame[c].nunique() <= 100]
    # Prefer the named entity over its parent category in a product/customer ranking.
    priority = {"product_name": 0, "customer_name": 0, "category": 1, "status": 2, "segment": 3, "city": 4}
    return sorted(columns, key=lambda c: priority.get(c.lower(), 10))


@dataclass(frozen=True)
class BusinessInsight:
    id: str
    kind: str
    title: str
    text: str
    evidence: dict[str, Any]
    next_step: str


def build_business_insights(result: AnalysisResult) -> list[BusinessInsight]:
    """Measured endpoints, group gaps, concentration, relationships and quality."""
    zh = any("\u4e00" <= c <= "\u9fff" for c in result.question)
    frame = result.dataframe.replace([np.inf, -np.inf], np.nan)
    if frame.empty:
        return []
    types, measures = result.profile["types"], measure_columns(result)
    insights: list[BusinessInsight] = []
    choose = lambda cn, en: cn if zh else en

    if len(frame) == 1 and measures:
        facts = {c: float(frame[c].iloc[0]) for c in measures if pd.notna(frame[c].iloc[0])}
        if facts:
            text = "；".join(f"{display_name(c, zh)}{'为' if zh else ': '}{number(v)}" for c, v in facts.items())
            insights.append(BusinessInsight("result", "result", choose("本次查询的业务结果", "Business result"), text + choose("。", "."), facts,
                choose("按月份或产品类别拆分，判断这个结果主要来自哪里。", "Break down the result by month or product category to locate its main contributors.")))
            revenue = next((facts[c] for c in ("total_revenue", "revenue") if c in facts), None)
            orders = facts.get("delivered_orders")
            if revenue is not None and orders is not None and orders > 0:
                average = revenue / orders
                insights.append(BusinessInsight("order_value", "derived", choose("收入与订单规模", "Revenue relative to order volume"),
                    choose(f"本次收入除以已交付订单数，得到每单收入约 {number(average)}。这有助于把收入表现拆成订单规模和单笔金额两个方向。",
                           f"Revenue divided by delivered orders is approximately {number(average)} per order. Review both order volume and order value when comparing revenue."),
                    {"revenue": revenue, "orders": orders, "revenue_per_order": average},
                    choose("继续比较各月订单数与每单收入，区分量与价的变化。", "Compare monthly order counts and revenue per order to distinguish volume from value.")))

    if len(frame) > 1 and measures:
        measure = measures[0]
        label = display_name(measure, zh)
        agg = aggregation_for(measure)
        if types["date"]:
            date = types["date"][0]
            data = frame[[date, measure]].dropna().copy()
            data[date] = pd.to_datetime(data[date], errors="coerce", format="mixed")
            data = data.dropna().groupby(date)[measure].agg(agg).sort_index()
            if len(data) >= 2:
                first, last = float(data.iloc[0]), float(data.iloc[-1])
                delta = last - first
                percent = delta / first * 100 if first > 0 else None
                monthly = frame[date].dropna().astype(str).str.fullmatch(r"\d{4}-\d{2}").all()
                fmt = "%Y-%m" if monthly else "%Y-%m-%d"
                start, end = data.index[0].strftime(fmt), data.index[-1].strftime(fmt)
                direction = choose("上升", "increased") if delta > 0 else choose("下降", "decreased") if delta < 0 else choose("持平", "was unchanged")
                percentage = choose(f"，变化幅度 {abs(percent):.1f}%", f" ({abs(percent):.1f}%)") if percent is not None else choose("；起点不为正，不计算增长率", "; growth rate is omitted because the starting value is not positive")
                text = choose(f"从 {start} 到 {end}，{label}由 {number(first)} 变为 {number(last)}，{direction}{percentage}。这是已返回时间点的首尾比较，不代表期间持续同向变化。",
                              f"Between {start} and {end}, {label} moved from {number(first)} to {number(last)} and {direction}{percentage}. This compares observed endpoints, not an uninterrupted trend.")
                peak = data.idxmax().strftime(fmt)
                text += choose(f" 最高值出现在 {peak}，为 {number(float(data.max()))}。", f" The highest observed value was {number(float(data.max()))} in {peak}.")
                insights.append(BusinessInsight("trend", "trend", choose("走势与高点", "Direction and peak"), text,
                    {"measure": measure, "aggregation": agg, "start": start, "end": end, "first": first, "last": last,
                     "change": delta, "change_percent": percent, "peak_period": peak, "peak": float(data.max()), "observations": len(data)},
                    choose("结合订单数、客单金额和产品结构进一步拆分；当前结果不能单独确定变化原因。", "Break down orders, order value and product mix; this result alone cannot establish the cause.")))
                previous = float(data.iloc[-2])
                adjacent = monthly and (data.index[-1].to_period("M").ordinal - data.index[-2].to_period("M").ordinal == 1)
                if adjacent and previous > 0:
                    mom = (last / previous - 1) * 100
                    insights.append(BusinessInsight("latest_period", "period_change", choose("最近一期变化", "Latest period change"),
                        choose(f"{end} 较上一个已返回的相邻月份{('上升' if mom >= 0 else '下降')} {abs(mom):.1f}%（{number(previous)} → {number(last)}）。请先确认两个月份是否均已完整结束，再评价表现。",
                               f"{end} {'increased' if mom >= 0 else 'decreased'} by {abs(mom):.1f}% versus the adjacent returned month ({number(previous)} → {number(last)}). Confirm both periods are complete before judging performance."),
                        {"previous": previous, "latest": last, "change_percent": mom},
                        choose("核对最近月份完整性，再拆分订单量与每单收入。", "Check period completeness, then separate order volume and value.")))

        categories = category_columns(result)
        if categories and not types["date"]:
            category = categories[0]
            grouped = frame.dropna(subset=[category, measure]).groupby(category, observed=True)[measure].agg(agg).sort_values(ascending=False, kind="stable")
            if len(grouped) >= 2:
                top, bottom = float(grouped.iloc[0]), float(grouped.iloc[-1])
                top_name, bottom_name = display_value(grouped.index[0], zh), display_value(grouped.index[-1], zh)
                text = choose(f"在本次返回的{display_name(category, zh)}中，{top_name}的{label}最高，为 {number(top)}；{bottom_name}最低，为 {number(bottom)}，两者相差 {number(top-bottom)}。",
                              f"Among the returned {display_name(category, False)} groups, {top_name} has the highest {label} ({number(top)}), compared with {number(bottom)} for {bottom_name}; the gap is {number(top-bottom)}.")
                total = float(grouped.sum())
                share = top / total * 100 if agg == "sum" and grouped.ge(0).all() and total > 0 else None
                if share is not None:
                    text += choose(f" {top_name}占本次返回分组{label}合计的 {share:.1f}%，该占比不代表未返回数据。",
                                   f" {top_name} accounts for {share:.1f}% of the returned groups' total, not a share of unseen data.")
                insights.append(BusinessInsight("comparison", "comparison", choose("领先项与差距", "Leaders and gaps"), text,
                    {"category": category, "measure": measure, "aggregation": agg, "top_group": str(grouped.index[0]),
                     "top": top, "bottom_group": str(grouped.index[-1]), "bottom": bottom, "gap": top-bottom,
                     "share_percent": share, "returned_group_count": len(grouped)},
                    choose("进一步比较领先项与其他项的订单量、单价及时间分布，验证差异来自规模还是结构。", "Compare order volume, prices and time coverage across groups to investigate scale versus mix.")))

        if len(measures) >= 2 and any(word in result.question.lower() for word in ("相关", "关系", "correlation", "relationship", "scatter")):
            a, b = measures[:2]
            pair = frame[[a, b]].dropna()
            coefficient = result.profile["correlations"]["pearson"].loc[a, b]
            if len(pair) >= 3 and pd.notna(coefficient):
                r = float(coefficient)
                strength = choose("较强", "strong") if abs(r) >= .7 else choose("中等", "moderate") if abs(r) >= .4 else choose("较弱", "weak")
                sign = choose("正", "positive") if r >= 0 else choose("负", "negative")
                insights.append(BusinessInsight("relationship", "correlation", choose("变量关系", "Relationship"),
                    choose(f"在 {len(pair)} 条成对有效记录中，{display_name(a, zh)}与{display_name(b, zh)}的 Pearson 相关系数为 {r:.3f}，呈{strength}{sign}相关。相关性不能证明因果，且可能受分组或极端值影响。",
                           f"Across {len(pair)} complete pairs, Pearson r between {display_name(a, zh)} and {display_name(b, zh)} is {r:.3f}, a {strength} {sign} association. This does not establish causation and can reflect grouping or outliers."),
                    {"x": a, "y": b, "pearson": r, "pair_count": len(pair)},
                    choose("结合散点图与 Spearman 系数检查极端值和非线性关系。", "Inspect the scatter plot and Spearman correlation for outliers and nonlinearity.")))

        if not insights and frame[measure].notna().sum() >= 2:
            values = frame[measure].dropna()
            median, mean = float(values.median()), float(values.mean())
            text = choose(f"{label}的中位数为 {number(median)}，均值为 {number(mean)}，范围为 {number(float(values.min()))}～{number(float(values.max()))}。",
                          f"{label} has a median of {number(median)}, mean of {number(mean)}, and range of {number(float(values.min()))}–{number(float(values.max()))}.")
            if mean > median and median > 0:
                text += choose(" 均值高于中位数，提示高值可能拉高整体均值，建议同时查看分布。", " The mean exceeds the median; high values may pull up the average. Inspect the distribution as well.")
            insights.append(BusinessInsight("distribution", "distribution", choose("数值分布", "Distribution"), text,
                {"measure": measure, "mean": mean, "median": median},
                choose("检查箱线图中的极端值，区分正常高值与数据问题。", "Inspect extreme values in a box plot and distinguish valid high values from data issues.")))

    if not measures and len(frame) > 1:
        repeated = [c for c in category_columns(result) if frame[c].nunique() < len(frame)]
        if repeated:
            category = repeated[0]
            counts = frame[category].dropna().value_counts()
            top, valid = int(counts.iloc[0]), int(counts.sum())
            share = top / valid * 100
            name = display_value(counts.index[0], zh)
            insights.append(BusinessInsight("composition", "composition", choose("记录分布", "Record composition"),
                choose(f"在已加载且{display_name(category, zh)}非空的 {valid} 条记录中，{name}有 {top} 条，占 {share:.1f}%。这是记录数量分布，不代表收入或消费贡献。",
                       f"Of {valid} loaded records with a non-missing {display_name(category, False)}, {top} belong to {name} ({share:.1f}%). This is a distribution of records, not revenue or spending contribution."),
                {"category": category, "top_group": str(counts.index[0]), "count": top, "valid_count": valid, "share_percent": share},
                choose("加入业务指标后比较各分组的实际贡献，避免只用记录数量判断价值。", "Add a business measure to compare group contributions rather than equating record counts with value.")))

    p = result.profile
    relevant_outliers = [o for o in p["outliers"] if o["column"] in measures and o["count"] > 0]
    if p["missing_cells"] or p["duplicate_rows"] or relevant_outliers:
        outlier_count = sum(o["count"] for o in relevant_outliers)
        text = choose(f"已加载数据包含 {p['missing_cells']} 个缺失单元格和 {p['duplicate_rows']} 条整行重复；业务数值列共标记 {outlier_count} 个 IQR 异常单元格（可能来自同一行）。这些标记是核查线索，不能直接当作业务异常。",
                      f"Loaded data contains {p['missing_cells']} missing cells and {p['duplicate_rows']} repeated full rows; business numeric columns have {outlier_count} IQR-flagged cells (possibly in the same row). These are investigation flags, not confirmed business anomalies.")
        insights.append(BusinessInsight("quality", "quality", choose("解读前需要注意", "Interpretation checks"), text,
            {"missing_cells": p["missing_cells"], "duplicate_rows": p["duplicate_rows"], "outlier_cells": outlier_count},
            choose("核对数据来源与查询粒度，确认缺失和重复是否影响业务口径。", "Check data provenance and query grain before interpreting missing or repeated values.")))
    return insights


def insight_payload(result: AnalysisResult) -> list[dict[str, Any]]:
    return [asdict(item) for item in build_business_insights(result)]


def narrative_report(result: AnalysisResult) -> str:
    zh = any("\u4e00" <= c <= "\u9fff" for c in result.question)
    insights = build_business_insights(result)
    if not insights:
        return "没有足够的可比较数值，暂不生成趋势或差异结论。" if zh else "There are not enough comparable values to infer a trend or a group difference."
    lines = [f"**{item.title}**\n\n{item.text}" for item in insights]
    steps = list(dict.fromkeys(item.next_step for item in insights if item.kind != "quality"))[:2]
    if steps:
        lines.append(("**建议继续分析**" if zh else "**Suggested follow-up**") + "\n\n" + "\n\n".join(steps))
    return "\n\n".join(lines)
