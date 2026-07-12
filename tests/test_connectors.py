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
    assert {"dbt_core", "duckdb", "postgres", "snowflake"} <= set(keys)
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


# ── Snowflake ────────────────────────────────────────────────────────────────

SNOWFLAKE_PROFILE = """
analytics:
  target: prod
  outputs:
    prod:
      type: snowflake
      account: xy12345.us-east-1
      user: svc
      password: "{{ env_var('SNOWFLAKE_PASSWORD') }}"
      role: TRANSFORMER
      database: ANALYTICS
      warehouse: COMPUTE_WH
      schema: PUBLIC
"""


def test_snowflake_detect_from_env():
    from opendata.connectors.warehouse_snowflake import SnowflakeWarehouseConnector

    c = SnowflakeWarehouseConnector()
    env = Env(root=Path("/does-not-exist"), environ={
        "SNOWFLAKE_ACCOUNT": "ab12345", "SNOWFLAKE_USER": "me",
        "SNOWFLAKE_DATABASE": "DB", "SNOWFLAKE_WAREHOUSE": "WH",
    })
    r = c.detect(env)
    assert r is not None
    assert r.config["account"] == "ab12345"
    assert r.config["database"] == "DB"
    assert "password" not in r.config
    assert r.config["secret_ref"] == "env:SNOWFLAKE_PASSWORD"


def test_snowflake_detect_from_dbt_profile(tmp_path):
    from opendata.connectors.warehouse_snowflake import (
        SnowflakeWarehouseConnector,
        resolve,
    )

    (tmp_path / "dbt_project.yml").write_text("name: analytics\nprofile: analytics\n")
    prof = tmp_path / "dbtprof"
    prof.mkdir()
    (prof / "profiles.yml").write_text(SNOWFLAKE_PROFILE)
    env = Env(root=tmp_path, environ={
        "DBT_PROFILES_DIR": str(prof), "SNOWFLAKE_PASSWORD": "sekret",
    })

    r = SnowflakeWarehouseConnector().detect(env)
    assert r is not None
    assert r.config["account"] == "xy12345.us-east-1"
    assert r.config["database"] == "ANALYTICS"
    assert r.config["warehouse"] == "COMPUTE_WH"
    assert "password" not in r.config
    assert r.config["secret_ref"] == "dbt:profiles.yml"
    # env_var interpolation resolves the real password (not stored in cfg)
    assert resolve(env)["password"] == "sekret"


def test_snowflake_grant_sql_is_read_only():
    from opendata.connectors.warehouse_snowflake import SnowflakeWarehouseConnector

    g = SnowflakeWarehouseConnector().grant_sql({"database": "ANALYTICS", "warehouse": "WH"})
    assert "CREATE ROLE IF NOT EXISTS OPENDATA_RO" in g
    assert "GRANT SELECT ON ALL TABLES IN DATABASE ANALYTICS" in g
    for forbidden in ("INSERT", "UPDATE", "DELETE"):
        assert forbidden not in g


def test_dbt_profiles_load_output(tmp_path):
    from opendata.connectors.dbt_profiles import load_output

    (tmp_path / "dbt_project.yml").write_text("profile: proj\n")
    pd = tmp_path / "p"
    pd.mkdir()
    (pd / "profiles.yml").write_text(
        "proj:\n  target: dev\n  outputs:\n    dev:\n"
        "      type: postgres\n      host: h\n"
    )
    env = {"DBT_PROFILES_DIR": str(pd)}
    out = load_output(tmp_path, env, ("postgres",))
    assert out["output"]["host"] == "h"
    assert out["target"] == "dev"
    assert load_output(tmp_path, env, ("snowflake",)) is None
