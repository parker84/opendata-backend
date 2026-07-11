"""SQL guardrails via sqlglot — the always-on safety layer (architecture §6).

Read-only enforced at parse time; a LIMIT is injected if the query has none.
This is what makes it safe to point opendata at a production warehouse.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

# Statement types we refuse to run. opendata is read-only, period.
_FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,  # catches things sqlglot parses as raw commands (TRUNCATE, GRANT…)
)


class UnsafeSQL(ValueError):
    """Raised when a statement is not a read-only SELECT."""


def validate_and_prepare(sql: str, dialect: str = "duckdb", limit: int = 100) -> str:
    """Parse, enforce read-only, inject a LIMIT, and return normalized SQL."""
    try:
        tree = sqlglot.parse_one(sql, read=dialect)
    except Exception as e:  # noqa: BLE001 — surface a clean message to the engine
        raise UnsafeSQL(f"could not parse SQL: {e}") from e

    if tree is None:
        raise UnsafeSQL("empty statement")

    for node in tree.walk():
        if isinstance(node, _FORBIDDEN):
            raise UnsafeSQL(f"refused: only read-only SELECT is allowed (found {type(node).__name__})")

    # The top-level statement must be a query (SELECT / WITH … SELECT / UNION).
    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)) and not (
        isinstance(tree, exp.With) or tree.find(exp.Select)
    ):
        raise UnsafeSQL("refused: statement is not a query")

    if isinstance(tree, exp.Select) and not tree.args.get("limit"):
        tree = tree.limit(limit)

    return tree.sql(dialect=dialect)
