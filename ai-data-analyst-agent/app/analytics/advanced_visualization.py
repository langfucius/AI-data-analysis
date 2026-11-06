"""Validated Plotly chart construction from one AnalysisResult snapshot."""
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from app.analytics.advanced_result import AnalysisResult
from app.analytics.business_insights import aggregation_for, category_columns, display_name, measure_columns

CHART_TYPES = ("bar", "line", "scatter", "histogram", "box", "heatmap", "pie")
AGGREGATIONS = ("none", "sum", "mean", "median", "count", "min", "max")


@dataclass(frozen=True)
class AdvancedChartSpec:
    chart_type: str
    x: str | None = None
    y: str | None = None
    aggregation: str = "none"
    color: str | None = None
    correlation_method: str = "pearson"


def recommend_charts(result: AnalysisResult) -> list[AdvancedChartSpec]:
    if result.loaded_row_count < 2:
        return []
    t = result.profile["types"]
    measures = measure_columns(result)
    categories = category_columns(result)
    if not measures:
        repeated = [c for c in categories if result.dataframe[c].nunique() < result.loaded_row_count]
        categories = repeated or categories
    specs: list[AdvancedChartSpec] = []
    if t["date"] and measures:
        specs.extend(AdvancedChartSpec("line", t["date"][0], measure, aggregation_for(measure)) for measure in measures)
    if categories:
        specs.extend(AdvancedChartSpec("bar", categories[0], measure, aggregation_for(measure)) for measure in measures)
        if not measures:
            specs.append(AdvancedChartSpec("bar", categories[0], None, "count"))
        wants_composition = any(word in result.question.lower() for word in ("占比", "构成", "结构", "composition", "share", "percentage"))
        if wants_composition and result.dataframe[categories[0]].nunique() <= 8:
            if not measures:
                specs.insert(0, AdvancedChartSpec("pie", categories[0], None, "count"))
            elif aggregation_for(measures[0]) == "sum":
                values = result.dataframe[measures[0]].replace([np.inf, -np.inf], np.nan).dropna()
                if len(values) and values.ge(0).all() and values.sum() > 0:
                    specs.insert(0, AdvancedChartSpec("pie", categories[0], measures[0], "sum"))
    if measures:
        specs.extend([AdvancedChartSpec("histogram", measures[0]), AdvancedChartSpec("box", measures[0])])
    if len(measures) >= 2:
        if any(s in result.question.lower() for s in ("relationship", "scatter", "correlation", "相关", "关系")):
            specs.insert(0, AdvancedChartSpec("scatter", measures[0], measures[1]))
        specs.append(AdvancedChartSpec("heatmap"))
    return specs


def create_advanced_chart(result: AnalysisResult, spec: AdvancedChartSpec, *, language: str = "en",
                          theme: str = "light", presentation: bool = False) -> go.Figure:
    if spec.chart_type not in CHART_TYPES or spec.aggregation not in AGGREGATIONS:
        raise ValueError("Unsupported chart type or aggregation.")
    frame = result.dataframe
    if frame.empty:
        raise ValueError("No loaded rows to visualize.")
    kinds = result.profile["types"]
    for col in (spec.x, spec.y, spec.color):
        if col is not None and col not in frame:
            raise ValueError(f"Unknown column: {col}")
    if spec.chart_type == "heatmap":
        if spec.correlation_method not in result.profile["correlations"]:
            raise ValueError("Unsupported correlation method.")
        matrix = result.profile["correlations"][spec.correlation_method]
        matrix = matrix.drop(index=kinds["identifier"], columns=kinds["identifier"], errors="ignore")
        if len(matrix) < 2 or not matrix.notna().any().any():
            raise ValueError("Correlation heatmap requires two varying numeric measures.")
        labels = [display_name(c, language == "zh") for c in matrix.columns]
        fig = go.Figure(go.Heatmap(z=matrix.to_numpy(), x=labels, y=labels,
                                   zmin=-1, zmax=1, colorscale="RdBu", reversescale=True,
                                   texttemplate="%{z:.2f}", hovertemplate="%{y} / %{x}<br>r = %{z:.3f}<extra></extra>"))
        title = f"{spec.correlation_method.title()} correlation — loaded rows"
    else:
        if spec.x is None:
            raise ValueError("Select an X column.")
        if spec.chart_type in ("scatter", "histogram", "box") and spec.aggregation != "none":
            raise ValueError("This chart requires raw rows (aggregation=none).")
        for col in kinds["numeric"]:
            frame[col] = frame[col].replace([np.inf, -np.inf], np.nan)
        if spec.chart_type == "line":
            if spec.x not in kinds["date"] and spec.x not in kinds["numeric"]:
                raise ValueError("Line charts require a date or numeric X column.")
            if spec.x in kinds["date"]:
                frame[spec.x] = pd.to_datetime(frame[spec.x], errors="coerce", format="mixed")
        if spec.chart_type == "scatter" and (spec.x not in kinds["numeric"] or spec.y not in kinds["numeric"]):
            raise ValueError("Scatter plots require two numeric columns.")
        if spec.chart_type in ("histogram", "box"):
            measure = spec.x if spec.chart_type == "histogram" else (spec.y or spec.x)
            if measure not in kinds["numeric"]:
                raise ValueError("Select a numeric measure for distribution charts.")
        if spec.chart_type in ("bar", "line", "pie"):
            if spec.y is None and spec.aggregation != "count":
                raise ValueError("Select Y, or choose count aggregation.")
            if spec.y is not None and spec.y not in kinds["numeric"]:
                raise ValueError("Y must be numeric.")
        required = list(dict.fromkeys(c for c in (spec.x, spec.y, spec.color) if c))
        if spec.aggregation == "count":
            required = list(dict.fromkeys(c for c in (spec.x, spec.color) if c))
        data = frame.dropna(subset=required).copy()
        if data.empty:
            raise ValueError("No complete finite rows for the selected columns.")
        y = spec.y
        if spec.aggregation != "none":
            groups = list(dict.fromkeys(c for c in (spec.x, spec.color) if c))
            output = "__value__"
            while output in data.columns:
                output += "_"
            if spec.aggregation == "count":
                # Count rows, independent of nullable Y.
                data = frame.dropna(subset=groups).groupby(groups, dropna=False, observed=True).size().reset_index(name=output)
            else:
                data = data.groupby(groups, dropna=False, observed=True)[y].agg(spec.aggregation).reset_index(name=output)
            y = output
        if spec.chart_type == "line":
            keys = list(dict.fromkeys(c for c in (spec.x, spec.color) if c))
            if data.duplicated(keys).any():
                raise ValueError("Repeated X values require aggregation or grouping for a line chart.")
            data = data.sort_values(spec.x)
        title = f"{spec.chart_type.title()}: {spec.aggregation + ' ' if spec.aggregation != 'none' else ''}{spec.y or spec.x}"
        if spec.chart_type in ("bar", "line", "scatter", "box"):
            kwargs = {"x": spec.x, "y": y, "color": spec.color, "title": title}
            if spec.chart_type == "box" and spec.y is None:
                kwargs.update(x=None, y=spec.x)
            if presentation and spec.chart_type == "bar" and spec.x in kinds["categorical"]:
                kwargs.update(x=y, y=spec.x, orientation="h", text=y)
            if presentation and spec.chart_type == "line":
                kwargs.update(markers=True)
            if spec.chart_type == "box":
                kwargs.update(points="outliers")
            fig = getattr(px, spec.chart_type)(data, **kwargs)
        elif spec.chart_type == "histogram":
            fig = px.histogram(data, x=spec.x, color=spec.color, title=title)
        else:
            if spec.color:
                raise ValueError("Pie charts use X as grouping; color grouping is unsupported.")
            if data[y].lt(0).any() or data[y].sum() <= 0:
                raise ValueError("Pie values must be non-negative with a positive total.")
            if data[spec.x].nunique() > 12:
                raise ValueError("Use a bar chart for more than twelve pie categories.")
            fig = px.pie(data, names=spec.x, values=y, title=title)
        if y == "__value__":
            fig.update_yaxes(title=f"{spec.aggregation}({spec.y or 'rows'})")
    if presentation:
        title = chart_title(spec, language)
        palette = ["#818cf8", "#2dd4bf", "#fbbf24", "#fb7185", "#38bdf8", "#c084fc"]
        fig.update_layout(colorway=palette, legend_title_text=display_name(spec.color, language == "zh") if spec.color else None)
        horizontal = spec.chart_type == "bar" and spec.x in kinds["categorical"]
        x_label = display_name(spec.x, language == "zh") if spec.x else ""
        y_label = display_name(spec.y, language == "zh") if spec.y else ("记录数" if language == "zh" else "Rows")
        if spec.aggregation == "mean":
            y_label += "（组内均值）" if language == "zh" else " (group mean)"
        if spec.chart_type not in ("heatmap", "pie"):
            fig.update_xaxes(title=y_label if horizontal else x_label, showgrid=horizontal, zeroline=False)
            fig.update_yaxes(title=x_label if horizontal else y_label, showgrid=not horizontal, zeroline=False)
        if spec.chart_type == "bar":
            fig.update_traces(texttemplate="%{x:,.2f}" if horizontal else "%{y:,.2f}", textposition="outside", cliponaxis=False,
                              marker_line_width=0, hovertemplate=("%{y}<br>%{x:,.2f}<extra>%{fullData.name}</extra>" if horizontal else "%{x}<br>%{y:,.2f}<extra>%{fullData.name}</extra>"))
            if horizontal:
                fig.update_yaxes(categoryorder="total ascending")
        if spec.chart_type == "line":
            fig.update_traces(line_width=3, marker_size=7, hovertemplate="%{y:,.2f}<extra>%{fullData.name}</extra>")
            fig.update_layout(hovermode="x unified")
            if len(data) >= 12 and spec.x in kinds["date"]:
                fig.update_xaxes(rangeslider_visible=True)
            if not spec.color and len(data) >= 2:
                peak_row = data.loc[data[y].idxmax()]
                fig.add_annotation(x=peak_row[spec.x], y=peak_row[y], text=("最高 " if language == "zh" else "Peak ") + f"{peak_row[y]:,.2f}",
                                   showarrow=True, arrowhead=2, ay=-38, bgcolor="#312e81", font_color="white")
        if spec.chart_type == "scatter":
            fig.update_traces(marker_size=9, marker_opacity=.7)
        if spec.chart_type == "pie":
            fig.update_traces(hole=.48, textinfo="label+percent", hovertemplate="%{label}<br>%{value:,.2f}<br>%{percent}<extra></extra>")
        if spec.chart_type == "histogram":
            fig.update_yaxes(title="频数" if language == "zh" else "Frequency")
        if spec.chart_type == "box" and spec.y is None:
            fig.update_yaxes(title=display_name(spec.x, language == "zh"))
            fig.update_xaxes(title="")
    height = min(900, max(430, 28 * data[spec.x].nunique() + 110)) if presentation and spec.chart_type == "bar" and spec.x in kinds["categorical"] else 450
    fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white", title=title, height=height,
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=35, r=90, t=80, b=55),
                      meta={"snapshot_id": result.snapshot_id, "loaded_rows": result.loaded_row_count,
                            "scope": result.scope_notice})
    return fig


def chart_title(spec: AdvancedChartSpec, language: str = "en") -> str:
    zh = language == "zh"
    x = display_name(spec.x, zh) if spec.x else ""
    y = display_name(spec.y, zh) if spec.y else ("记录数" if zh else "Row count")
    if spec.chart_type == "line":
        return f"{y}随{x}的变化" if zh else f"{y} over {x}"
    if spec.chart_type == "bar":
        return f"{x}的{y}对比" if zh else f"{y} by {x}"
    if spec.chart_type == "scatter":
        return f"{x}与{y}的关系" if zh else f"{y} versus {x}"
    if spec.chart_type == "histogram":
        return f"{x}的分布" if zh else f"Distribution of {x}"
    if spec.chart_type == "box":
        return f"{display_name(spec.y or spec.x, zh)}的分布与极端值" if zh else f"Spread and outliers: {display_name(spec.y or spec.x, False)}"
    if spec.chart_type == "pie":
        return f"{x}的{y}构成" if zh else f"Composition of {y} by {x}"
    return f"{spec.correlation_method.title()} 相关性" if zh else f"{spec.correlation_method.title()} correlation"
