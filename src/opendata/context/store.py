"""Context store — the unified catalog everything retrieves from.

v0 is a local JSON document with lexical retrieval. The architecture calls for
SQLite/DuckDB + a vector index (sqlite-vec/LanceDB); this slice keeps it
dependency-light and honest — retrieval is token-overlap, not embeddings, and is
clearly the first thing to upgrade.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import Metric, Table

STORE_FILE = "context.json"

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


@dataclass
class Retrieved:
    tables: list[Table] = field(default_factory=list)
    metrics: list[Metric] = field(default_factory=list)


class ContextStore:
    def __init__(self, root: Path):
        self.root = root
        self.tables: list[Table] = []
        self.metrics: list[Metric] = []
        self.connections: dict[str, dict] = {}

    # ── mutation (used by connectors' index()) ──────────────────────────────
    def add_table(self, t: Table) -> None:
        self.tables = [x for x in self.tables if x.fqn != t.fqn]
        self.tables.append(t)

    def add_metric(self, m: Metric) -> None:
        self.metrics = [x for x in self.metrics if x.name != m.name]
        self.metrics.append(m)

    def note_connection(self, key: str, info: dict) -> None:
        self.connections[key] = info

    # ── persistence ─────────────────────────────────────────────────────────
    @property
    def path(self) -> Path:
        return self.root / ".opendata" / STORE_FILE

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "connections": self.connections,
                    "tables": [t.to_dict() for t in self.tables],
                    "metrics": [m.to_dict() for m in self.metrics],
                },
                indent=2,
            )
        )
        return self.path

    @classmethod
    def load(cls, root: Path) -> "ContextStore":
        s = cls(root)
        if s.path.exists():
            data = json.loads(s.path.read_text())
            s.connections = data.get("connections", {})
            s.tables = [Table.from_dict(d) for d in data.get("tables", [])]
            s.metrics = [Metric.from_dict(d) for d in data.get("metrics", [])]
        return s

    # ── retrieval (lexical v0) ───────────────────────────────────────────────
    def _table_text(self, t: Table) -> str:
        cols = " ".join(f"{c.name} {c.description}" for c in t.columns)
        return f"{t.name} {t.schema} {t.description} {cols}"

    def retrieve(self, question: str, k: int = 5) -> Retrieved:
        q = _tokens(question)

        def score(text: str) -> int:
            return len(q & _tokens(text))

        tables = sorted(
            self.tables, key=lambda t: score(self._table_text(t)), reverse=True
        )
        metrics = sorted(
            self.metrics,
            key=lambda m: score(f"{m.name} {m.label} {m.definition}"),
            reverse=True,
        )
        top_tables = [t for t in tables if score(self._table_text(t)) > 0][:k] or tables[:1]
        top_metrics = [m for m in metrics if score(f"{m.name} {m.label} {m.definition}") > 0][:k]
        return Retrieved(tables=top_tables, metrics=top_metrics)

    def find_metric(self, question: str) -> Metric | None:
        q = _tokens(question)
        best, best_score = None, 0
        for m in self.metrics:
            if not m.sql:
                continue
            s = len(q & _tokens(f"{m.name} {m.label} {m.definition}"))
            if s > best_score:
                best, best_score = m, s
        # require a real overlap so we don't force a metric onto every question
        return best if best_score >= 2 else None
