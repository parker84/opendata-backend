"""Read-only HTTP API — the transport `opendata-web` (and agents) call.

Same engine, thin FastAPI wrapper (architecture §1: one core, two transports).
Bind to a project root (a directory an `opendata init` has run in). Read-only:
every answer still goes through the parse-time SQL guard.

Optional dependency: `pip install "opendata[server]"`.
"""

# NB: no `from __future__ import annotations` here — FastAPI must see the real
# Pydantic model class on the endpoint annotation to treat it as a request body.

import os
from pathlib import Path

from .. import __version__
from ..config import load_config
from ..context.store import ContextStore
from ..engine import ask as engine_ask
from ..golden.store import load_goldens


def create_app(root: Path):
    from fastapi import FastAPI
    from pydantic import BaseModel

    from fastapi.middleware.cors import CORSMiddleware

    root = Path(root).resolve()
    app = FastAPI(title="opendata", version=__version__)

    # Read-only local API — permissive CORS so a browser (opendata-web) can call
    # it directly. Restrict with OPENDATA_CORS_ORIGINS="https://app.example.com,…".
    origins = [o.strip() for o in os.getenv("OPENDATA_CORS_ORIGINS", "*").split(",")]
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"]
    )

    class AskRequest(BaseModel):
        question: str

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "version": __version__}

    @app.get("/status")
    def status() -> dict:
        cfg = load_config(root) or {}
        store = ContextStore.load(root)
        return {
            "project": cfg.get("project", root.name),
            "connections": list((cfg.get("connections") or {}).keys()),
            "tables": len(store.tables),
            "metrics": len(store.metrics),
            "goldens": len(load_goldens(root)),
        }

    @app.post("/ask")
    def ask(req: AskRequest) -> dict:
        return engine_ask(root, req.question).to_dict()

    return app


def serve(root: Path, host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(create_app(root), host=host, port=port)
