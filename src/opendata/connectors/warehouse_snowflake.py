"""Snowflake warehouse connector.

Auto-detects from the dbt profile named in `dbt_project.yml` (type `snowflake`),
or from `SNOWFLAKE_*` env vars. Reuses dbt's credentials; read-only at the SQL
layer; ships a least-privilege role GRANT to paste. Config stores a secret
reference, never the password.

Requires the optional `snowflake-connector-python` dependency
(`pip install "opendata[snowflake]"`). Detection and the GRANT generator work
without it; connect/index/execute need it.
"""

from __future__ import annotations

import os
from typing import Optional

from ..context.models import Column, Table
from .base import DetectResult, Env, HealthCheck, register
from .dbt_profiles import load_output

# dbt Snowflake output key → our normalized connection key.
_FIELDS = ("account", "user", "password", "role", "database", "warehouse", "schema")


def _resolve_from_dbt(root, environ: dict) -> Optional[dict]:
    found = load_output(root, environ, ("snowflake",))
    if not found:
        return None
    o = found["output"]
    return {
        "type": "snowflake",
        "source": "dbt",
        "profile": found["profile"],
        "target": found["target"],
        "account": o.get("account", ""),
        "user": o.get("user", ""),
        "password": o.get("password", ""),
        "role": o.get("role", ""),
        "database": o.get("database", ""),
        "warehouse": o.get("warehouse", ""),
        "schema": o.get("schema", "PUBLIC"),
    }


def _resolve_from_env(environ: dict) -> Optional[dict]:
    if not (environ.get("SNOWFLAKE_ACCOUNT") and environ.get("SNOWFLAKE_USER")):
        return None
    return {
        "type": "snowflake",
        "source": "env",
        "account": environ.get("SNOWFLAKE_ACCOUNT", ""),
        "user": environ.get("SNOWFLAKE_USER", ""),
        "password": environ.get("SNOWFLAKE_PASSWORD", ""),
        "role": environ.get("SNOWFLAKE_ROLE", ""),
        "database": environ.get("SNOWFLAKE_DATABASE", ""),
        "warehouse": environ.get("SNOWFLAKE_WAREHOUSE", ""),
        "schema": environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
    }


def resolve(env_or_cfg):
    """Full connection params from a DetectResult env, or pass a stored cfg through."""
    if isinstance(env_or_cfg, Env):
        return _resolve_from_env(env_or_cfg.environ) or _resolve_from_dbt(
            env_or_cfg.root, env_or_cfg.environ
        )
    return env_or_cfg


class SnowflakeWarehouseConnector:
    key = "snowflake"
    kind = "warehouse"

    def detect(self, env: Env) -> Optional[DetectResult]:
        params = resolve(env)
        if not params:
            return None
        cfg = {k: v for k, v in params.items() if k != "password"}
        cfg["secret_ref"] = (
            "env:SNOWFLAKE_PASSWORD" if params.get("source") == "env" else "dbt:profiles.yml"
        )
        where = params.get("profile") or "SNOWFLAKE_* env"
        return DetectResult(
            key=self.key,
            kind=self.kind,
            summary=f"snowflake  ({params['account']}/{params['database']} via {where})",
            config=cfg,
        )

    def grant_sql(self, cfg: dict) -> str:
        db = cfg.get("database", "YOUR_DB")
        wh = cfg.get("warehouse", "YOUR_WH")
        return (
            "-- opendata: least-privilege read-only role. Run as ACCOUNTADMIN.\n"
            "CREATE ROLE IF NOT EXISTS OPENDATA_RO;\n"
            f"GRANT USAGE ON WAREHOUSE {wh} TO ROLE OPENDATA_RO;\n"
            f"GRANT USAGE ON DATABASE {db} TO ROLE OPENDATA_RO;\n"
            f"GRANT USAGE ON ALL SCHEMAS IN DATABASE {db} TO ROLE OPENDATA_RO;\n"
            f"GRANT SELECT ON ALL TABLES IN DATABASE {db} TO ROLE OPENDATA_RO;\n"
            f"GRANT SELECT ON FUTURE TABLES IN DATABASE {db} TO ROLE OPENDATA_RO;\n"
            "-- then: GRANT ROLE OPENDATA_RO TO USER <your_user>;"
        )

    def validate(self, cfg: dict) -> list[HealthCheck]:
        try:
            cols, _ = execute(cfg, "SELECT 1 AS OK")
            return [HealthCheck("snowflake", bool(cols), cfg.get("account", ""))]
        except Exception as e:  # noqa: BLE001
            return [HealthCheck("snowflake", False, str(e), fix="check SNOWFLAKE_* / dbt profile")]

    def index(self, cfg: dict, store) -> dict:
        db = cfg.get("database", "")
        schema = cfg.get("schema", "PUBLIC")
        cols, rows = execute(
            cfg,
            "SELECT table_schema, table_name, column_name, data_type "
            f"FROM {db}.information_schema.columns "
            f"WHERE table_schema = '{schema}' "
            "ORDER BY table_schema, table_name, ordinal_position",
        )
        tables: dict[tuple, Table] = {}
        for sch, tbl, col, dtype in rows:
            t = tables.get((sch, tbl))
            if t is None:
                t = Table(connection=self.key, schema=sch, name=tbl)
                tables[(sch, tbl)] = t
            t.columns.append(Column(name=col, type=dtype))
        for t in tables.values():
            store.add_table(t)
        store.note_connection(self.key, {"type": "snowflake", "account": cfg.get("account")})
        return {"tables": len(tables)}


def _conn_params(cfg: dict) -> dict:
    p = resolve(cfg) or cfg
    if not p.get("password") and str(p.get("secret_ref", "")) == "env:SNOWFLAKE_PASSWORD":
        p = {**p, "password": os.environ.get("SNOWFLAKE_PASSWORD", "")}
    return p


def execute(cfg: dict, sql: str) -> tuple[list[str], list[tuple]]:
    """Run read-only SQL against Snowflake; return (columns, rows)."""
    import snowflake.connector  # lazy — only needed when actually querying Snowflake

    p = _conn_params(cfg)
    conn = snowflake.connector.connect(
        account=p["account"],
        user=p["user"],
        password=p.get("password", ""),
        role=p.get("role") or None,
        warehouse=p.get("warehouse") or None,
        database=p.get("database") or None,
        schema=p.get("schema") or None,
    )
    try:
        cur = conn.cursor()
        cur.execute(sql)
        names = [d[0] for d in cur.description] if cur.description else []
        return names, cur.fetchall()
    finally:
        conn.close()


register(SnowflakeWarehouseConnector())
