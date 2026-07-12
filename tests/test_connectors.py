from pathlib import Path

from opendata.connectors import REGISTRY
from opendata.connectors.base import Env, register
from opendata.connectors.warehouse_postgres import (
    PostgresWarehouseConnector,
    _interp,
    _resolve_from_url,
)

REPO = Path(__file__).resolve().parents[1]


def test_registry_has_builtins_and_dedupes():
    keys = [c.key for c in REGISTRY]
    assert {"dbt_core", "duckdb", "postgres"} <= set(keys)
    # register is idempotent by key
    before = len(REGISTRY)
    register(PostgresWarehouseConnector())
    assert len(REGISTRY) == before


def test_dbt_core_detects_and_indexes_toy():
    from opendata.connectors.dbt_core import DbtCoreConnector
    from opendata.context.store import ContextStore

    root = REPO / "examples" / "toy"
    c = DbtCoreConnector()
    r = c.detect(Env(root=root, environ={}))
    assert r is not None and r.ok
    store = ContextStore(root)
    stats = c.index({**r.config, "_root": str(root)}, store)
    assert stats["tables"] == 2
    assert stats["metrics"] == 1
    assert {t.name for t in store.tables} == {"events", "dim_teams"}


def test_postgres_detect_from_database_url():
    c = PostgresWarehouseConnector()
    env = Env(root=REPO, environ={
        "DATABASE_URL": "postgresql://ro:p%40ss@db.example.com:6543/analytics"
    })
    r = c.detect(env)
    assert r is not None
    assert r.config["host"] == "db.example.com"
    assert r.config["port"] == 6543
    assert r.config["dbname"] == "analytics"
    assert "password" not in r.config  # secret never stored
    assert r.config["secret_ref"] == "env:DATABASE_URL"


def test_postgres_url_password_urldecoded():
    p = _resolve_from_url({"DATABASE_URL": "postgres://u:p%40ss@h:5432/db"})
    assert p["password"] == "p@ss"


def test_postgres_grant_sql_is_read_only():
    c = PostgresWarehouseConnector()
    grant = c.grant_sql({"dbname": "analytics", "schema": "marts"})
    assert "GRANT SELECT" in grant
    assert "marts" in grant
    for forbidden in ("INSERT", "UPDATE", "DELETE", "ALL PRIVILEGES"):
        assert forbidden not in grant


def test_env_var_interpolation():
    assert _interp("{{ env_var('PGHOST') }}", {"PGHOST": "h1"}) == "h1"
    assert _interp("{{ env_var('MISSING', 'fallback') }}", {}) == "fallback"
    assert _interp("literal", {}) == "literal"
