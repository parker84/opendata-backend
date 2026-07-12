import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from opendata.cli import app

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def toy(tmp_path):
    """A freshly `init`-ed copy of examples/toy in a tmp dir (hermetic)."""
    dst = tmp_path / "toy"
    shutil.copytree(REPO / "examples" / "toy", dst)
    for stale in ("warehouse.duckdb", ".opendata/config.yml", ".opendata/context.json"):
        p = dst / stale
        if p.exists():
            p.unlink()
    result = CliRunner().invoke(app, ["init", "--yes", "--path", str(dst)])
    assert result.exit_code == 0, result.output
    return dst


@pytest.fixture(autouse=True)
def _offline_defaults(monkeypatch):
    """Keep the engine on the offline stub + lexical retrieval during tests."""
    for var in ("ANTHROPIC_API_KEY", "OPENDATA_MODEL", "OPENDATA_EMBEDDINGS", "VOYAGE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
