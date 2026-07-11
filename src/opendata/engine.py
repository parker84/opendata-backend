"""Answer engine — question → grounded SQL/metric → result (architecture §6).

Precedence: golden hit → metric-first → generate. Every path validates SQL
(read-only guard + LIMIT) before executing, and returns provenance so the answer
can always show its work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import load_config
from .connectors import warehouse_duckdb
from .context.store import ContextStore
from .golden.store import best_match
from .llm.provider import get_provider
from .sql.validate import UnsafeSQL, validate_and_prepare


@dataclass
class Answer:
    question: str
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    provenance: str = ""  # e.g. "golden:weekly_active_teams" / "metric:active_team" / "generated"
    error: str | None = None


def _resolve_sql(root: Path, store: ContextStore, question: str) -> tuple[str, str]:
    """Return (sql, provenance) using golden → metric → generate precedence."""
    g = best_match(root, question)
    if g and g.sql:
        return g.sql, f"golden:{g.id}"

    m = store.find_metric(question)
    if m and m.sql:
        return m.sql, f"metric:{m.name}"

    retrieved = store.retrieve(question)
    sql = get_provider().generate_sql(question, retrieved)
    return sql, "generated"


def ask(root: Path, question: str) -> Answer:
    root = Path(root).resolve()
    cfg = load_config(root) or {}
    store = ContextStore.load(root)

    try:
        raw_sql, provenance = _resolve_sql(root, store, question)
    except Exception as e:  # noqa: BLE001
        return Answer(question=question, sql="", provenance="none", error=str(e))

    try:
        safe_sql = validate_and_prepare(raw_sql, dialect="duckdb")
    except UnsafeSQL as e:
        return Answer(question=question, sql=raw_sql, provenance=provenance, error=str(e))

    wh = (cfg.get("connections", {}) or {}).get("warehouse", {"type": "duckdb"})
    wh = {**wh, "_root": str(root)}
    try:
        cols, rows = warehouse_duckdb.execute(root, wh, safe_sql)
    except Exception as e:  # noqa: BLE001 — a real engine would self-repair here
        return Answer(question=question, sql=safe_sql, provenance=provenance, error=str(e))

    return Answer(
        question=question,
        sql=safe_sql,
        columns=cols,
        rows=rows,
        provenance=provenance,
    )
