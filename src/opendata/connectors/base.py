"""Connector contract + registry (see docs/architecture.md §5).

Adding a source = implementing detect / validate / grant_sql / index and
calling @register.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


@dataclass
class Env:
    root: Path
    environ: dict = field(default_factory=dict)


@dataclass
class DetectResult:
    key: str
    kind: str
    summary: str  # human line shown in the init checklist
    config: dict = field(default_factory=dict)
    ok: bool = True  # False → detected-but-needs-attention (shown as ⚠)


@dataclass
class HealthCheck:
    name: str
    ok: bool
    detail: str = ""
    fix: Optional[str] = None


@runtime_checkable
class Connector(Protocol):
    key: str
    kind: str

    def detect(self, env: Env) -> Optional[DetectResult]:
        """Fast, side-effect-free scan of cwd + standard locations + env."""

    def validate(self, cfg: dict) -> list[HealthCheck]:
        """Read-only connectivity/permission check. Powers `doctor`."""

    def grant_sql(self, cfg: dict) -> Optional[str]:
        """Least-privilege setup to copy-paste (warehouses). None if N/A."""

    def index(self, cfg: dict, store) -> dict:
        """Pull metadata into the context store. Returns stats."""


REGISTRY: list[Connector] = []


def register(c: Connector) -> Connector:
    REGISTRY.append(c)
    return c
