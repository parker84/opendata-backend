"""Connector registry.

Built-in connectors self-register on import. Community connectors are discovered
via the `opendata.connectors` entry-point group — so `pip install
opendata-connector-<x>` makes a new source available with no core change.

A third-party package advertises its connector in pyproject.toml:

    [project.entry-points."opendata.connectors"]
    posthog = "opendata_connector_posthog:PostHogConnector"

The entry point resolves to a Connector class or instance; we instantiate and
register it. See docs/connectors.md.
"""

from __future__ import annotations

from importlib.metadata import entry_points

from . import dbt_core, warehouse_duckdb  # noqa: F401  built-ins self-register
from .base import REGISTRY, Connector, DetectResult, Env, HealthCheck, register

__all__ = ["REGISTRY", "Connector", "DetectResult", "Env", "HealthCheck", "register"]


def _load_entrypoint_connectors() -> None:
    try:
        eps = entry_points(group="opendata.connectors")
    except Exception:  # noqa: BLE001 — never let discovery break the CLI
        return
    for ep in eps:
        try:
            obj = ep.load()
            register(obj() if isinstance(obj, type) else obj)
        except Exception:  # noqa: BLE001 — one bad plugin shouldn't break the rest
            continue


_load_entrypoint_connectors()
