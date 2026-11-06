"""SQL validation for the sample SQLite database."""
from __future__ import annotations

import re
import sqlglot
from sqlglot import exp

from app.core.config import get_max_rows


class SQLSafetyError(ValueError):
    """Raised when SQL fails safety validation."""


class SQLSyntaxError(ValueError):
    """SQL parsing failed; eligible for bounded repair."""


FORBIDDEN_FUNCTIONS = {"load_extension", "readfile", "writefile"}


def _enforce_limit(tree: exp.Expression) -> exp.Expression:
    max_rows = get_max_rows()
    limit_node = tree.args.get("limit")

    if limit_node is None:
        return tree.limit(max_rows, copy=True)

    limit_expression = limit_node.expression
    requested_rows = max_rows

    if isinstance(limit_expression, exp.Literal) and not limit_expression.is_string:
        try:
            requested_rows = int(limit_expression.this)
        except (TypeError, ValueError):
            requested_rows = max_rows

    # SQLite interprets a negative LIMIT as unlimited.
    if requested_rows < 0:
        requested_rows = max_rows

    return tree.limit(min(requested_rows, max_rows), copy=True)


def validate_sql(sql: str, allowed_tables: set[str]) -> str:
    if not sql or not sql.strip():
        raise SQLSafetyError("The generated SQL query is empty.")

    # Classify policy violations before parsing: malformed nested writes must
    # never be sent to the repair model. Tokenization ignores quoted text.
    try:
        tokens = sqlglot.tokenize(sql, read="sqlite")
    except sqlglot.errors.TokenError as exc:
        raise SQLSafetyError("SQL contains invalid tokens; query rejected.") from exc
    blocked_tokens = {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "PRAGMA", "ATTACH", "DETACH", "TRUNCATE", "MERGE", "INTO"}
    if any(token.token_type.name == "SEMICOLON" for token in tokens[:-1]):
        raise SQLSafetyError("Only one SQL statement is allowed.")
    if any(token.token_type.name in blocked_tokens for token in tokens):
        raise SQLSafetyError("Only read-only SELECT queries are allowed.")

    if re.search(
        r"\b(load_extension|readfile|writefile)\s*\(",
        sql,
        flags=re.IGNORECASE,
    ):
        raise SQLSafetyError("The query contains a blocked SQLite function.")

    try:
        statements = [
            item for item in sqlglot.parse(sql, read="sqlite") if item
        ]
    except sqlglot.errors.ParseError as exc:
        # Malformed writes are still safety violations, not repair candidates.
        leading = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.DOTALL).lstrip()
        if not re.match(r"(?i)^(SELECT|WITH)\b", leading):
            raise SQLSafetyError("Only read-only SELECT queries are allowed.") from exc
        raise SQLSyntaxError(
            f"SQL could not be parsed: {exc}"
        ) from exc

    if len(statements) != 1:
        raise SQLSafetyError("Only one SQL statement is allowed.")

    tree = statements[0]

    if not isinstance(tree, (exp.Select, exp.Union)):
        raise SQLSafetyError(
            "Only read-only SELECT queries are allowed."
        )

    forbidden_nodes = (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
                       exp.Alter, exp.Command, exp.Into)
    if any(isinstance(node, forbidden_nodes) for node in tree.walk()):
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
            raise SQLSafetyError(
                "Cross-database references are not allowed."
            )

    tree = _enforce_limit(tree)

    return tree.sql(dialect="sqlite")
