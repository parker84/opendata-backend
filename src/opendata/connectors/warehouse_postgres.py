"""Postgres warehouse connector — the first real warehouse.

Auto-detects a connection the way the onboarding doc promises: a `DATABASE_URL`
env var, or the dbt profile referenced by the project's `dbt_project.yml`
(`~/.dbt/profiles.yml`, honoring `DBT_PROFILES_DIR`). Reuses dbt's existing
credentials so nothing new is typed. Read-only at the SQL layer; ships a
least-privilege GRANT to paste.

Requires the optional `psycopg` dependency (`pip install "opendata[postgres]"`).
Detection and the GRANT generator work without it; connect/index/execute need it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import yaml

from ..context.models import Column, Table
from .base import DetectResult, Env, HealthCheck, register

_ENV_VAR = re.compile(r"\{\{\s*env_var\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]([^'\"]*)['\"]\s*)?\)\s*\}\}")


def _interp(value, environ: dict):
    """Resolve dbt-style {{ env_var('X', 'default') }} in a profile value."""
    if not isinstance(value, str):
        return value
    return _ENV_VAR.sub(lambda m: environ.get(m.group(1), m.group(2) or ""), value)


def _profiles_path(environ: dict) -> Path:
    base = environ.get("DBT_PROFILES_DIR") or str(Path.home() / ".dbt")
    return Path(base) / "profiles.yml"


def _dbt_profile_name(root: Path) -> Optional[str]:
    proj = root / "dbt_project.yml"
    if not proj.exists():
        return None
    try:
        data = yaml.safe_load(proj.read_text()) or {}
    except Exception:  # noqa: BLE001
        return None
    return data.get("profile")


def _resolve_from_dbt(root: Path, environ: dict) -> Optional[dict]:
    name = _dbt_profile_name(root)
    p = _profiles_path(environ)
    if not name or not p.exists():
        return None
    try:
        profiles = yaml.safe_load(p.read_text()) or {}
    except Exception:  # noqa: BLE001
        return None
    prof = profiles.get(name)
    if not isinstance(prof, dict):
        return None
    target = prof.get("target")
    output = (prof.get("outputs") or {}).get(target)
    if not isinstance(output, dict):
        return None
    if str(output.get("type", "")).lower() not in ("postgres", "postgresql"):
        return None
    return {
        "type": "postgres",
        "source": "dbt",
        "profile": name,
        "target": target,
        "host": _interp(output.get("host", "localhost"), environ),
        "port": int(_interp(output.get("port", 5432), environ) or 5432),
        "user": _interp(output.get("user", ""), environ),
        "password": _interp(output.get("password", ""), environ),
        "dbname": _interp(output.get("dbname") or output.get("database", ""), environ),
        "schema": _interp(output.get("schema", "public"), environ),
    }


def _resolve_from_url(environ: dict) -> Optional[dict]:
    url = environ.get("DATABASE_URL", "")
    if not url:
        return None
    u = urlparse(url)
    if u.scheme not in ("postgres", "postgresql"):
        return None
    return {
        "type": "postgres",
        "source": "env:DATABASE_URL",
        "host": u.hostname or "localhost",
        "port": u.port or 5432,
        "user": unquote(u.username or ""),
        "password": unquote(u.password or ""),
        "dbname": (u.path or "/").lstrip("/") or "postgres",
        "schema": "public",
    }


def resolve(env_or_cfg) -> Optional[dict]:
    """Return full connection params from a DetectResult env, or pass a stored cfg
    (which already holds params) straight through."""
    if isinstance(env_or_cfg, Env):
        return _resolve_from_url(env_or_cfg.environ) or _resolve_from_dbt(
            env_or_cfg.root, env_or_cfg.environ
        )
    return env_or_cfg


class PostgresWarehouseConnector:
    key = "postgres"
    kind = "warehouse"

    def detect(self, env: Env) -> Optional[DetectResult]:
        params = resolve(env)
        if not params:
            return None
        # Store connection params but NOT the password (secret_ref instead).
        cfg = {k: v for k, v in params.items() if k != "password"}
        cfg["secret_ref"] = (
            "env:DATABASE_URL" if params.get("source", "").startswith("env")
            else "dbt:profiles.yml"
        )
        where = params.get("profile") or "DATABASE_URL"
        return DetectResult(
            key=self.key,
            kind=self.kind,
            summary=f"postgres  ({params['host']}/{params['dbname']} via {where})",
            config=cfg,
        )

    def grant_sql(self, cfg: dict) -> str:
        schema = cfg.get("schema", "public")
        db = cfg.get("dbname", "your_db")
        return (
            "-- opendata: least-privilege read-only role. Run as a superuser.\n"
            "CREATE ROLE opendata_ro NOLOGIN;\n"
            f"GRANT CONNECT ON DATABASE {db} TO opendata_ro;\n"
            f"GRANT USAGE ON SCHEMA {schema} TO opendata_ro;\n"
            f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO opendata_ro;\n"
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            "GRANT SELECT ON TABLES TO opendata_ro;\n"
            "-- then: GRANT opendata_ro TO <your_login_user>;"
        )

    def validate(self, cfg: dict) -> list[HealthCheck]:
        try:
            cols, _ = execute(cfg, "SELECT 1 AS ok")
            ok = cols == ["ok"]
            return [HealthCheck("postgres", ok, cfg.get("host", ""))]
        except Exception as e:  # noqa: BLE001
            return [HealthCheck("postgres", False, str(e), fix="check DATABASE_URL / dbt profile")]

    def index(self, cfg: dict, store) -> dict:
        schema = cfg.get("schema", "public")
        cols, rows = execute(
            cfg,
            "SELECT table_schema, table_name, column_name, data_type "
            "FROM information_schema.columns "
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
        store.note_connection(self.key, {"type": "postgres", "host": cfg.get("host")})
        return {"tables": len(tables)}


def _conn_params(cfg: dict) -> dict:
    p = resolve(cfg) or cfg
    # If only a secret_ref is stored, hydrate the password from the environment.
    if not p.get("password") and str(p.get("secret_ref", "")).startswith("env:DATABASE_URL"):
        fresh = _resolve_from_url(dict(os.environ))
        if fresh:
            p = fresh
    return p


def execute(cfg: dict, sql: str) -> tuple[list[str], list[tuple]]:
    """Run read-only SQL against Postgres; return (columns, rows)."""
    import psycopg  # lazy — only needed when actually querying Postgres

    p = _conn_params(cfg)
    conninfo = (
        f"host={p['host']} port={p.get('port', 5432)} dbname={p['dbname']} "
        f"user={p['user']} password={p.get('password', '')}"
    )
    with psycopg.connect(conninfo) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(sql)
            names = [d.name for d in cur.description] if cur.description else []
            return names, cur.fetchall()


register(PostgresWarehouseConnector())
