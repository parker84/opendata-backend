import pytest

from opendata.sql.validate import UnsafeSQL, validate_and_prepare


@pytest.mark.parametrize(
    "bad",
    [
        "DROP TABLE events",
        "DELETE FROM events",
        "UPDATE events SET team_id = 1",
        "INSERT INTO events VALUES (1)",
        "CREATE TABLE x (a int)",
        "ALTER TABLE events ADD COLUMN z int",
        "TRUNCATE events",
        "GRANT SELECT ON events TO bob",
    ],
)
def test_blocks_non_select(bad):
    with pytest.raises(UnsafeSQL):
        validate_and_prepare(bad)


def test_allows_select_and_injects_limit():
    out = validate_and_prepare("select 1 as a")
    assert "LIMIT" in out.upper()


def test_keeps_existing_limit():
    out = validate_and_prepare("select 1 as a limit 5")
    assert out.upper().count("LIMIT") == 1
    assert "5" in out


def test_allows_cte():
    out = validate_and_prepare("with t as (select 1 as a) select * from t")
    assert out.upper().startswith("WITH")


def test_rejects_garbage():
    with pytest.raises(UnsafeSQL):
        validate_and_prepare("this is not sql ;;;")
