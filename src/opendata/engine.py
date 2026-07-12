"""Answer engine — question → grounded SQL/metric → result (architecture §6).

Precedence: golden hit → metric-first → generate. Every path validates SQL
(read-only guard + LIMIT) before executing, returns provenance, and — for the
generated path — self-repairs once against the DB error before giving up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import load_config
from .connectors import execute as wh
from .context.store import ContextStore
from .golden.store import best_match, load_goldens
from .llm.provider import get_provider
from .sql.validate import UnsafeSQL, validate_and_prepare

MAX_REPAIRS = 1


def _jsonable(v):
    return v if isinstance(v, (str, int, float, bool, type(None))) else str(v)


@dataclass
class Answer:
    question: str
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    provenance: str = ""  # "golden:…" / "metric:…" / "generated"
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "sql": self.sql,
            "columns": self.columns,
            "rows": [[_jsonable(c) for c in row] for row in self.rows],
            "provenance": self.provenance,
            "error": self.error,
        }


def _resolve_sql(root: Path, store: ContextStore, question: str, provider):
    """Return (sql, provenance) using golden → metric → generate precedence."""
    g = best_match(root, question)
    if g and g.sql:
        return g.sql, f"golden:{g.id}"

    m = store.find_metric(question)
    if m and m.sql:
        return m.sql, f"metric:{m.name}"

    retrieved = store.retrieve(question)
    sql = provider.generate_sql(question, retrieved, examples=load_goldens(root))
    return sql, "generated"


def ask(root: Path, question: str) -> Answer:
    root = Path(root).resolve()
    cfg = load_config(root) or {}
    store = ContextStore.load(root)
    provider = get_provider()

    try:
        raw_sql, provenance = _resolve_sql(root, store, question, provider)
    except Exception as e:  # noqa: BLE001
        return Answer(question=question, sql="", provenance="none", error=str(e))

    wh_cfg = (cfg.get("connections", {}) or {}).get("warehouse", {"type": "duckdb"})
    wh_cfg = {**wh_cfg, "_root": str(root)}

    sql = raw_sql
    last_err = None
    # Generated SQL gets a bounded self-repair loop; golden/metric SQL is trusted.
    repairs = MAX_REPAIRS if provenance == "generated" else 0
    for attempt in range(repairs + 1):
        try:
            safe_sql = validate_and_prepare(sql, dialect="duckdb")
        except UnsafeSQL as e:
            last_err = str(e)
            break
        try:
            cols, rows = wh.execute(root, wh_cfg, safe_sql)
            return Answer(question=question, sql=safe_sql, columns=cols, rows=rows,
                          provenance=provenance)
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            if attempt < repairs and hasattr(provider, "repair_sql"):
                try:
                    sql = provider.repair_sql(question, sql, last_err, store.retrieve(question))
                    continue
                except Exception:  # noqa: BLE001 — repair itself failed; give up
                    break
            break

    return Answer(question=question, sql=sql, provenance=provenance, error=last_err)
