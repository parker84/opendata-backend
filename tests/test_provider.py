from opendata.context.models import Column, Table
from opendata.context.store import Retrieved
from opendata.llm.provider import StubProvider, get_provider


def test_get_provider_offline_defaults_to_stub():
    assert get_provider().name == "stub"


def test_get_provider_explicit_stub():
    assert get_provider("stub").name == "stub"


def test_stub_generates_select_from_top_table():
    ctx = Retrieved(tables=[Table("duckdb", "main", "dim_teams", "", [Column("team_id", "int")])])
    sql = StubProvider().generate_sql("anything", ctx)
    assert sql == "SELECT * FROM main.dim_teams"


def test_stub_raises_without_tables():
    import pytest

    with pytest.raises(RuntimeError):
        StubProvider().generate_sql("q", Retrieved(tables=[]))
