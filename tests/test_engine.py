from opendata.engine import ask
from opendata.eval.harness import run as run_eval
from opendata.golden.store import save_golden
from opendata.golden.verify import verify_all


def test_golden_path(toy):
    ans = ask(toy, "weekly active teams last 8 weeks")
    assert ans.error is None
    assert ans.provenance.startswith("golden:")
    assert len(ans.rows) > 0
    assert ans.columns == ["week", "active_teams"]


def test_metric_path(toy):
    ans = ask(toy, "count distinct active team")
    assert ans.error is None
    assert ans.provenance == "metric:active_team"
    assert ans.rows[0][0] == 5  # five teams in the seed


def test_generated_path_stub(toy):
    ans = ask(toy, "show me the teams")
    assert ans.error is None
    assert ans.provenance == "generated"
    assert "team_name" in ans.columns


def test_read_only_limit_injected(toy):
    ans = ask(toy, "show me the teams")
    assert "LIMIT" in ans.sql.upper()


def test_eval_accuracy_perfect_on_toy(toy):
    report = run_eval(toy)
    assert report.accuracy == 1.0
    assert all(c.ok for c in report.cases)


def test_verify_all_pass_on_toy(toy):
    results = verify_all(toy)
    assert results and all(r.ok for r in results)


def test_verify_flags_broken_golden(toy):
    # A golden that references a non-existent table should fail verification.
    save_golden(toy, "broken example", "SELECT * FROM main.does_not_exist", id="broken")
    results = {r.golden.id: r for r in verify_all(toy)}
    assert results["broken"].ok is False
    assert results["weekly_active_teams"].ok is True
