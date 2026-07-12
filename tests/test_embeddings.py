import math

from opendata.context.embeddings import HashingEmbedder, cosine, get_embedder
from opendata.context.models import Column, Metric, Table
from opendata.context.retrieve import retrieve_context
from opendata.context.store import ContextStore


def _store(tmp_path):
    s = ContextStore(tmp_path)
    s.add_table(Table("duckdb", "main", "events", "product events per team",
                       [Column("team_id", "int"), Column("occurred_at", "timestamp")]))
    s.add_table(Table("duckdb", "main", "dim_teams", "one row per team, its plan",
                       [Column("team_id", "int"), Column("team_name", "varchar"),
                        Column("plan", "varchar")]))
    s.add_metric(Metric("active_team", "Active Teams", "distinct teams with an event",
                        sql="SELECT count(DISTINCT team_id) FROM main.events"))
    return s


def test_cosine():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert abs(cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9
    assert cosine([0.0], [0.0]) == 0.0


def test_hashing_embedder_deterministic_and_normalized():
    e = HashingEmbedder(dim=256)
    a1 = e.embed(["weekly active teams"])[0]
    a2 = e.embed(["weekly active teams"])[0]
    assert a1 == a2  # deterministic across calls (and processes: hashlib, not builtin hash)
    assert len(a1) == 256
    assert abs(math.sqrt(sum(x * x for x in a1)) - 1.0) < 1e-6
    assert e.embed(["completely different"])[0] != a1


def test_get_embedder_selection():
    assert get_embedder("none") is None
    assert get_embedder("hash").name == "hash"
    # default (no env, nothing installed in CI) → None → lexical
    assert get_embedder(None) is None or get_embedder(None).name in {"fastembed", "voyage"}


def test_embed_catalog_and_vector_retrieve(tmp_path):
    s = _store(tmp_path)
    n = s.embed_catalog(HashingEmbedder(dim=512))
    assert n == 3  # 2 tables + 1 metric
    assert "table:main.dim_teams" in s.vectors
    qvec = HashingEmbedder(dim=512).embed(["teams and their plan"], input_type="query")[0]
    r = s.vector_retrieve(qvec)
    assert r.tables[0].name == "dim_teams"


def test_retrieve_context_uses_vectors_when_available(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENDATA_EMBEDDINGS", "hash")
    s = _store(tmp_path)
    s.embed_catalog(HashingEmbedder(dim=512))
    r = retrieve_context(s, "teams by plan")
    assert any(t.name == "dim_teams" for t in r.tables)


def test_retrieve_context_falls_back_to_lexical(tmp_path):
    s = _store(tmp_path)  # no embeddings, no env → lexical
    r = retrieve_context(s, "teams by plan")
    assert r.tables  # still returns something


def test_vectors_persist_roundtrip(tmp_path):
    s = _store(tmp_path)
    s.embed_catalog(HashingEmbedder(dim=128))
    s.save()
    loaded = ContextStore.load(tmp_path)
    assert loaded.embedder == "hash"
    assert loaded.vectors.keys() == s.vectors.keys()
