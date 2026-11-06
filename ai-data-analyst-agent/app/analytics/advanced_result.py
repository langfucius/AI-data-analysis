"""A defensive result snapshot shared by profiling, charts and reports."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

import pandas as pd
import sqlglot
from sqlglot import exp

from app.analytics.advanced_profile import build_advanced_profile


def json_safe(value: Any) -> Any:
    """Convert pandas/numpy values and non-finite numbers to strict JSON."""
    if isinstance(value, pd.DataFrame):
        return {"columns": list(value.columns), "index": list(value.index), "values": json_safe(value.to_numpy().tolist())}
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if hasattr(value, "item"):
        return json_safe(value.item())
    if isinstance(value, float):
        import math
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return value.isoformat()
    if pd.isna(value):
        return None
    return str(value)


@dataclass(frozen=True)
class AnalysisResult:
    """Own a copy; public data/profile access returns copies, never internal storage."""
    question: str
    sql: str
    source_tables: tuple[str, ...]
    truncated: bool
    limit_applied: bool
    execution_metadata: dict[str, Any]
    _frame: pd.DataFrame = field(repr=False)
    _profile: dict[str, Any] = field(repr=False)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_query(cls, columns: list[str], rows: list[dict[str, Any]], *, question: str = "", sql: str = "",
                   truncated: bool = False, execution_metadata: dict[str, Any] | None = None) -> AnalysisResult:
        if len(set(columns)) != len(columns):
            raise ValueError("Query columns must have unique names; use SQL aliases.")
        frame = pd.DataFrame(deepcopy(rows), columns=columns).copy(deep=True)
        tables: tuple[str, ...] = ()
        limited = False
        if sql:
            tree = sqlglot.parse_one(sql, read="sqlite")
            ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
            tables = tuple(sorted({t.name for t in tree.find_all(exp.Table) if t.name not in ctes}))
            limited = tree.args.get("limit") is not None
        return cls(question, sql, tables, truncated, limited, deepcopy(execution_metadata or {}),
                   frame, build_advanced_profile(frame))

    @property
    def dataframe(self) -> pd.DataFrame:
        return self._frame.copy(deep=True)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AnalysisResult:
        """Restore an internal serialized snapshot without another SQL query/profile pass."""
        profile = deepcopy(payload["profile"])
        for method, matrix in profile["correlations"].items():
            profile["correlations"][method] = pd.DataFrame(
                matrix["values"], index=matrix["index"], columns=matrix["columns"], dtype=float)
        result = cls(payload["question"], payload["sql"], tuple(payload["source_tables"]),
                     payload["truncated"], payload["limit_applied"], deepcopy(payload["execution_metadata"]),
                     pd.DataFrame(deepcopy(payload["rows"]), columns=payload["columns"]), profile, payload["timestamp"])
        if result.snapshot_id != payload["snapshot_id"]:
            raise ValueError("Snapshot fingerprint does not match its rows.")
        return result

    @property
    def profile(self) -> dict[str, Any]:
        return deepcopy(self._profile)

    @property
    def columns(self) -> list[str]:
        return list(self._frame.columns)

    @property
    def rows(self) -> list[dict[str, Any]]:
        return deepcopy(self._frame.to_dict("records"))

    @property
    def loaded_row_count(self) -> int:
        return len(self._frame)

    @property
    def snapshot_id(self) -> str:
        payload = json.dumps(json_safe({"columns": self.columns, "rows": self.rows}), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    @property
    def scope_notice(self) -> str:
        if self.truncated:
            return "Results are truncated. Statistics and charts describe only loaded rows."
        if self.limit_applied:
            return "Statistics and charts describe loaded query rows. SQL includes LIMIT; the full source may contain more rows."
        return "Statistics and charts describe the returned query rows, not necessarily the full source table."

    def to_dict(self) -> dict[str, Any]:
        from app.analytics.business_insights import insight_payload
        return json_safe({"source_tables": self.source_tables, "question": self.question, "sql": self.sql,
                          "columns": self.columns, "rows": self.rows, "loaded_row_count": self.loaded_row_count,
                          "column_metadata": self._profile["column_quality"], "profile": self._profile,
                          "truncated": self.truncated, "limit_applied": self.limit_applied,
                          "scope_notice": self.scope_notice, "execution_metadata": self.execution_metadata,
                          "timestamp": self.timestamp, "snapshot_id": self.snapshot_id,
                          "insights": insight_payload(self)})

    def summary(self) -> str:
        chinese = any("\u4e00" <= c <= "\u9fff" for c in self.question)
        p = self._profile
        if chinese:
            lines = [f"已加载 {self.loaded_row_count} 行，{len(self.columns)} 列。", f"缺失单元格：{p['missing_cells']}；重复记录：{p['duplicate_rows']}。"]
            lines.append("统计和图表仅描述已加载的查询结果；SQL 行数限制可能使结果不代表完整数据。")
        else:
            lines = [f"Loaded rows: {self.loaded_row_count}; columns: {len(self.columns)}.",
                     f"Missing cells: {p['missing_cells']}; duplicate rows: {p['duplicate_rows']}.", self.scope_notice]
        if not self.loaded_row_count:
            lines.append("没有符合条件的记录。" if chinese else "No matching records.")
        for item in p["numeric_summary"]:
            clean = json_safe(item)
            lines.append(f"{item['column']}: count={clean['count']}, mean={clean['mean']}, median={clean['median']}, min={clean['min']}, max={clean['max']}, sum={clean['sum']}.")
        from app.analytics.business_insights import EVIDENCE_SEPARATOR, narrative_report
        if self.loaded_row_count:
            return narrative_report(self) + EVIDENCE_SEPARATOR + "\n\n".join(lines)
        return "\n\n".join(lines)
