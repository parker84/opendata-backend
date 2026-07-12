from pathlib import Path

from opendata.golden.store import Golden, best_match, load_goldens, save_golden, slug


def test_slug():
    assert slug("Weekly Active Teams, last 8 weeks!") == "weekly_active_teams_last_8_weeks"
    assert slug("") == "golden"


def test_match_score_alias_coverage():
    g = Golden(id="x", question="weekly active teams", sql="select 1", aliases=["WAT by week"])
    assert g.match_score("weekly active teams") == 1.0
    assert g.match_score("completely unrelated question") < 0.6


def test_save_and_load_roundtrip(tmp_path: Path):
    p = save_golden(
        tmp_path,
        "how many teams",
        "SELECT count(*) AS n FROM teams",
        owner="@me",
        expects={"columns": ["n"], "min_rows": 1},
    )
    assert p.exists()
    goldens = load_goldens(tmp_path)
    assert len(goldens) == 1
    g = goldens[0]
    assert g.id == "how_many_teams"
    assert g.owner == "@me"
    assert g.expects["columns"] == ["n"]
    assert "count(*)" in g.sql


def test_best_match_threshold(tmp_path: Path):
    save_golden(tmp_path, "weekly active teams", "SELECT 1", id="wat")
    assert best_match(tmp_path, "weekly active teams") is not None
    assert best_match(tmp_path, "revenue by region") is None
