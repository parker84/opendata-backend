"""Warehouse execution dispatch.

The engine and eval harness call `execute(root, cfg, sql)` without knowing which
warehouse backs the connection. Dispatch on the connection `type` so new
warehouses (Snowflake, BigQuery, …) plug in by adding a branch + a connector.
All backends enforce read-only at the SQL layer (see sql/validate.py) before we
ever get here.
"""

from __future__ import annotations

from pathlib import Path


def execute(root: Path, cfg: dict, sql: str) -> tuple[list[str], list[tuple]]:
    kind = (cfg or {}).get("type", "duckdb")
    if kind == "duckdb":
        from . import warehouse_duckdb

        return warehouse_duckdb.execute(root, cfg, sql)
    if kind in ("postgres", "postgresql"):
        from . import warehouse_postgres

        return warehouse_postgres.execute(cfg, sql)
    raise ValueError(f"unknown warehouse type: {kind!r}")
