from opendata.context.models import Column, Metric, Table
from opendata.context.store import ContextStore


def _store(tmp_path):
    s = ContextStore(tmp_path)
    s.add_table(Table("duckdb", "main", "events", "product events",
                       [Column("team_id", "int"), Column("occurred_at", "timestamp")]))
    s.add_table(Table("duckdb", "main", "dim_teams", "one row per team",
                       [Column("team_id", "int"), Column("plan", "varchar")]))
    s.add_metric(Metric("active_team", "Active Teams", "distinct teams with an event",
                        sql="SELECT count(DISTINCT team_id) FROM main.events"))
    return s


def test_retrieve_ranks_relevant_table(tmp_path):
    s = _store(tmp_path)
    r = s.retrieve("how many teams by plan")
    assert r.tables[0].name == "dim_teams"


def test_find_metric_requires_overlap(tmp_path):
    s = _store(tmp_path)
    assert s.find_metric("count distinct active team").name == "active_team"
    assert s.find_metric("what is the weather") is None


def test_save_and_load(tmp_path):
    _store(tmp_path).save()
    loaded = ContextStore.load(tmp_path)
    assert {t.name for t in loaded.tables} == {"events", "dim_teams"}
    assert loaded.metrics[0].name == "active_team"


def test_add_table_dedupes_by_fqn(tmp_path):
    s = _store(tmp_path)
    n = len(s.tables)
    s.add_table(Table("duckdb", "main", "events", "updated", []))
    assert len(s.tables) == n  # replaced, not appended
