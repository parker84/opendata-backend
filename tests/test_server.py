import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from opendata.api.server import create_app  # noqa: E402


def test_health(toy):
    client = TestClient(create_app(toy))
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_status(toy):
    client = TestClient(create_app(toy))
    body = client.get("/status").json()
    assert body["tables"] == 2
    assert body["metrics"] == 1
    assert body["goldens"] == 1
    assert "warehouse" in body["connections"]


def test_ask_golden(toy):
    client = TestClient(create_app(toy))
    r = client.post("/ask", json={"question": "weekly active teams last 8 weeks"})
    assert r.status_code == 200
    body = r.json()
    assert body["provenance"].startswith("golden:")
    assert body["columns"] == ["week", "active_teams"]
    assert body["rows"]
    assert body["error"] is None


def test_ask_rows_are_json_serializable(toy):
    # The 'week' column is a timestamp — must be stringified for JSON.
    client = TestClient(create_app(toy))
    body = client.post("/ask", json={"question": "weekly active teams last 8 weeks"}).json()
    assert all(isinstance(cell, (str, int, float, bool)) or cell is None
               for row in body["rows"] for cell in row)
