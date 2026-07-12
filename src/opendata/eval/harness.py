"""Eval harness — the golden set is the ground truth (architecture §7).

For each golden, the golden's own SQL result is treated as ground truth; we run
`engine.ask(golden.question)` and score the answer against it (execution success,
column-shape match, result-set match). Accuracy is tracked over releases; a
regression should fail CI. With the Claude provider and held-out (non-golden)
questions, this becomes a real text-to-SQL accuracy measure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import load_config
from ..connectors import execute as wh
from ..engine import ask
from ..golden.store import load_goldens
from ..sql.validate import validate_and_prepare


def _normalize(rows: list[tuple]) -> list[tuple]:
    return sorted(tuple(str(v) for v in row) for row in rows)


@dataclass
class CaseResult:
    id: str
    question: str
    ok: bool
    detail: str = ""


@dataclass
class EvalReport:
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return (sum(c.ok for c in self.cases) / len(self.cases)) if self.cases else 0.0


def run(root: Path) -> EvalReport:
    root = Path(root).resolve()
    cfg = load_config(root) or {}
    wh_cfg = {**(cfg.get("connections", {}) or {}).get("warehouse", {"type": "duckdb"}),
              "_root": str(root)}

    report = EvalReport()
    for g in load_goldens(root):
        try:
            truth_sql = validate_and_prepare(g.sql, dialect="duckdb")
            truth_cols, truth_rows = wh.execute(root, wh_cfg, truth_sql)
        except Exception as e:  # noqa: BLE001 — a golden that won't run is itself a failure
            report.cases.append(CaseResult(g.id, g.question, False, f"golden won't run: {e}"))
            continue

        ans = ask(root, g.question)
        if ans.error:
            report.cases.append(CaseResult(g.id, g.question, False, f"engine error: {ans.error}"))
        elif set(ans.columns) != set(truth_cols):
            report.cases.append(CaseResult(g.id, g.question, False, "column mismatch"))
        elif _normalize(ans.rows) != _normalize(truth_rows):
            report.cases.append(CaseResult(g.id, g.question, False, "result mismatch"))
        else:
            report.cases.append(CaseResult(g.id, g.question, True, ans.provenance))
    return report
