"""Connector registry. Importing this package registers the built-in connectors."""

from . import dbt_core, warehouse_duckdb  # noqa: F401  (side effect: register)
from .base import REGISTRY, Connector, DetectResult, Env, HealthCheck

__all__ = ["REGISTRY", "Connector", "DetectResult", "Env", "HealthCheck"]
