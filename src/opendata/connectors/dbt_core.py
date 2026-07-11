"""dbt Core connector — parses target/manifest.json.

Zero new auth: the manifest is a file already on disk. It delivers models,
their columns/docs, and metric definitions — the richest context, for free.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..context.models import Column, Metric, Table
from .base import DetectResult, Env, HealthCheck, register


def _manifest_path(root: Path, cfg: dict | None = None) -> Path:
    rel = (cfg or {}).get("manifest", "target/manifest.json")
    return root / rel


class DbtCoreConnector:
    key = "dbt_core"
    kind = "semantic"

    def detect(self, env: Env) -> Optional[DetectResult]:
        proj = env.root / "dbt_project.yml"
        if not proj.exists():
            return None
        manifest = _manifest_path(env.root)
        if not manifest.exists():
            return DetectResult(
                key=self.key,
                kind=self.kind,
                summary="dbt project found, but target/manifest.json is missing → run `dbt compile`",
                config={"project_dir": ".", "manifest": "target/manifest.json"},
                ok=False,
            )
        data = json.loads(manifest.read_text())
        n_models = sum(
            1 for n in data.get("nodes", {}).values() if n.get("resource_type") == "model"
        )
        n_metrics = len(data.get("metrics", {}))
        return DetectResult(
            key=self.key,
            kind=self.kind,
            summary=f"dbt project  ({n_models} models · {n_metrics} metrics)",
            config={"project_dir": ".", "manifest": "target/manifest.json"},
        )

    def validate(self, cfg: dict) -> list[HealthCheck]:
        # validate() is given the project root via cfg["_root"] by the engine/CLI.
        root = Path(cfg.get("_root", "."))
        manifest = _manifest_path(root, cfg)
        ok = manifest.exists()
        return [
            HealthCheck(
                name="dbt manifest",
                ok=ok,
                detail=str(manifest) if ok else "manifest.json not found",
                fix=None if ok else "dbt compile",
            )
        ]

    def grant_sql(self, cfg: dict) -> Optional[str]:
        return None

    def index(self, cfg: dict, store) -> dict:
        root = Path(cfg.get("_root", "."))
        data = json.loads(_manifest_path(root, cfg).read_text())
        n_tables = n_metrics = 0
        for node in data.get("nodes", {}).values():
            if node.get("resource_type") != "model":
                continue
            cols = [
                Column(
                    name=c["name"],
                    type=c.get("data_type") or "",
                    description=c.get("description", ""),
                )
                for c in node.get("columns", {}).values()
            ]
            store.add_table(
                Table(
                    connection=self.key,
                    schema=node.get("schema", ""),
                    name=node.get("name", ""),
                    description=node.get("description", ""),
                    columns=cols,
                )
            )
            n_tables += 1
        for m in data.get("metrics", {}).values():
            store.add_metric(
                Metric(
                    name=m.get("name", ""),
                    label=m.get("label", ""),
                    definition=m.get("description", ""),
                    sql=(m.get("meta") or {}).get("opendata_sql", ""),
                    owner=(m.get("meta") or {}).get("owner", ""),
                    source="dbt",
                )
            )
            n_metrics += 1
        return {"tables": n_tables, "metrics": n_metrics}


register(DbtCoreConnector())
