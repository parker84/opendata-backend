"""Golden verification — the dbt-test analog for golden SQL (docs/golden-sql.md §3).

Re-runs every golden and checks it still parses, executes, and returns the shape
declared in its `expects` block. Wire `opendata verify` into CI: a schema change
that breaks a golden fails the build. A broken golden is flagged with the likely
fix (re-verify), turning curation into a safety net rather than busywork.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import load_config
from ..connectors import execute as wh
from ..sql.validate import UnsafeSQL, validate_and_prepare
from .store import Golden, load_goldens


@dataclass
class VerifyResult:
    golden: Golden
    ok: bool
    detail: str = ""


def _check_expects(expects: dict, cols: list[str], rows: list[tuple]) -> str | None:
    want_cols = expects.get("columns")
    if want_cols is not None and list(want_cols) != list(cols):
        return f"columns {list(cols)} != expected {list(want_cols)}"
    min_rows = expects.get("min_rows")
    if min_rows is not None and len(rows) < int(min_rows):
        return f"{len(rows)} rows < expected min_rows {min_rows}"
    return None


def verify_all(root: Path) -> list[VerifyResult]:
    root = Path(root).resolve()
    cfg = load_config(root) or {}
    wh_cfg = {**(cfg.get("connections", {}) or {}).get("warehouse", {"type": "duckdb"}),
              "_root": str(root)}

    out: list[VerifyResult] = []
    for g in load_goldens(root):
        try:
            safe = validate_and_prepare(g.sql, dialect="duckdb")
        except UnsafeSQL as e:
            out.append(VerifyResult(g, False, f"unsafe SQL: {e}"))
            continue
        try:
            cols, rows = wh.execute(root, wh_cfg, safe)
        except Exception as e:  # noqa: BLE001 — schema drift usually lands here
            out.append(VerifyResult(g, False, f"won't run (schema drift?): {e}"))
            continue
        problem = _check_expects(g.expects, cols, rows)
        out.append(VerifyResult(g, problem is None, problem or f"{len(rows)} rows ok"))
    return out
