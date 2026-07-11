"""DuckDB warehouse connector — the local/toy execution path.

Detects a DuckDB file (or a seed.sql to build one), introspects its schema, and
executes read-only SQL. Real warehouses (Snowflake/BigQuery/Postgres) implement
the same shape but detect creds from ~/.dbt/profiles.yml / env.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb

from ..context.models import Column, Table
from .base import DetectResult, Env, HealthCheck, register

DEFAULT_DB = "warehouse.duckdb"


def _db_path(root: Path, cfg: dict | None = None) -> Path:
    return root / (cfg or {}).get("duckdb_path", DEFAULT_DB)


def build_from_seed(root: Path, cfg: dict) -> Path:
    """Materialize the toy warehouse from seed.sql if it doesn't exist yet."""
    db = _db_path(root, cfg)
    seed = cfg.get("seed")
    if not db.exists() and seed and (root / seed).exists():
        con = duckdb.connect(str(db))
        try:
            con.execute((root / seed).read_text())
        finally:
            con.close()
    return db


class DuckDBWarehouseConnector:
    key = "duckdb"
    kind = "warehouse"

    def detect(self, env: Env) -> Optional[DetectResult]:
        seed = env.root / "seed.sql"
        db = env.root / DEFAULT_DB
        if db.exists():
            return DetectResult(
                key=self.key,
                kind=self.kind,
                summary=f"duckdb warehouse  ({DEFAULT_DB})",
                config={"type": "duckdb", "duckdb_path": DEFAULT_DB},
            )
        if seed.exists():
            return DetectResult(
                key=self.key,
                kind=self.kind,
                summary="duckdb warehouse  (will build from seed.sql)",
                config={"type": "duckdb", "duckdb_path": DEFAULT_DB, "seed": "seed.sql"},
            )
        return None

    def validate(self, cfg: dict) -> list[HealthCheck]:
        root = Path(cfg.get("_root", "."))
        db = _db_path(root, cfg)
        ok = db.exists()
        return [
            HealthCheck(
                name="duckdb warehouse",
                ok=ok,
                detail=str(db) if ok else "not built",
                fix=None if ok else "opendata init",
            )
        ]

    def grant_sql(self, cfg: dict) -> Optional[str]:
        return None  # local file — no grants needed

    def index(self, cfg: dict, store) -> dict:
        root = Path(cfg.get("_root", "."))
        db = build_from_seed(root, cfg)
        con = duckdb.connect(str(db), read_only=True)
        try:
            rows = con.execute(
                """
                SELECT table_schema, table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema NOT IN ('information_schema')
                ORDER BY table_schema, table_name, ordinal_position
                """
            ).fetchall()
        finally:
            con.close()
        tables: dict[tuple, Table] = {}
        for schema, table, col, dtype in rows:
            t = tables.get((schema, table))
            if t is None:
                t = Table(connection=self.key, schema=schema, name=table)
                tables[(schema, table)] = t
            t.columns.append(Column(name=col, type=dtype))
        for t in tables.values():
            store.add_table(t)
        store.note_connection(self.key, {"type": "duckdb", "path": str(db)})
        return {"tables": len(tables)}


def execute(root: Path, cfg: dict, sql: str) -> tuple[list[str], list[tuple]]:
    """Run read-only SQL against the toy warehouse; return (columns, rows)."""
    db = _db_path(root, cfg)
    con = duckdb.connect(str(db), read_only=True)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, cur.fetchall()
    finally:
        con.close()


register(DuckDBWarehouseConnector())
