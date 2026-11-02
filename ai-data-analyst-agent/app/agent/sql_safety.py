"""SQL validation for the sample SQLite database.

This is a defense-in-depth layer, not a replacement for database permissions.
Queries are parsed, restricted to SELECT statements, limited to known tables,
and executed against a read-only SQLite connection with an authorizer.
"""
from __future__ import annotations

import re
import sqlglot
from sqlglot import exp

from app.core.config import get_max_rows


class SQLSafetyError(ValueError):
    """Raised when a generated SQL query fails safety validation."""


FORBIDDEN_FUNCTIONS = {"load_extension", "readfile", "writefile"}


def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    if not sql or not sql.strip():
        raise SQLSafetyError("The generated SQL query is empty.")

    if re.search(
        r"\b(load_extension|readfile|writefile)\s*\(", sql, flags=re.IGNORECASE
    ):
        raise SQLSafetyError("The query contains a blocked SQLite function.")

    try:
        statements = [item for item in sqlglot.parse(sql, read="sqlite") if item]
    except Exception as exc:
        raise SQLSafetyError(f"SQL could not be parsed: {exc}") from exc

    if len(statements) != 1:
        raise SQLSafetyError("Only one SQL statement is allowed.")

    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise SQLSafetyError("Only read-only SELECT queries are allowed.")

    cte_names = {
        cte.alias_or_name.lower()
        for cte in tree.find_all(exp.CTE)
        if cte.alias_or_name
    }
    allowed = {name.lower() for name in allowed_tables}
    for table in tree.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name not in allowed and table_name not in cte_names:
            raise SQLSafetyError(
                f"Access to table '{table.name}' is not allowed. "
                f"Available tables: {', '.join(sorted(allowed_tables))}."
            )
        if table.db or table.catalog:
            raise SQLSafetyError("Cross-database references are not allowed.")

    # Cap result size. The database connection is read-only as a second safeguard.
    if tree.args.get("limit") is None:
        tree = tree.limit(get_max_rows(), copy=True)

    return tree.sql(dialect="sqlite")
