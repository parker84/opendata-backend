"""Shared dbt profile resolution.

Both the Postgres and Snowflake connectors reuse the same logic: find the profile
named in the project's `dbt_project.yml`, read `~/.dbt/profiles.yml` (honoring
`DBT_PROFILES_DIR`), pick the active target's output, and interpolate dbt-style
`{{ env_var('X', 'default') }}`. Nothing new is typed — dbt's own creds are reused.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml

_ENV_VAR = re.compile(
    r"\{\{\s*env_var\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]([^'\"]*)['\"]\s*)?\)\s*\}\}"
)


def interp(value, environ: dict):
    """Resolve dbt-style {{ env_var('X', 'default') }} in a profile value."""
    if not isinstance(value, str):
        return value
    return _ENV_VAR.sub(lambda m: environ.get(m.group(1), m.group(2) or ""), value)


def profiles_path(environ: dict) -> Path:
    base = environ.get("DBT_PROFILES_DIR") or str(Path.home() / ".dbt")
    return Path(base) / "profiles.yml"


def dbt_profile_name(root: Path) -> Optional[str]:
    proj = root / "dbt_project.yml"
    if not proj.exists():
        return None
    try:
        data = yaml.safe_load(proj.read_text()) or {}
    except Exception:  # noqa: BLE001
        return None
    return data.get("profile")


def load_output(root: Path, environ: dict, types: tuple[str, ...]) -> Optional[dict]:
    """Return {"output": <interpolated dict>, "profile", "target"} for the active
    target if its `type` is one of `types`, else None."""
    name = dbt_profile_name(root)
    p = profiles_path(environ)
    if not name or not p.exists():
        return None
    try:
        profiles = yaml.safe_load(p.read_text()) or {}
    except Exception:  # noqa: BLE001
        return None
    prof = profiles.get(name)
    if not isinstance(prof, dict):
        return None
    target = prof.get("target")
    output = (prof.get("outputs") or {}).get(target)
    if not isinstance(output, dict):
        return None
    if str(output.get("type", "")).lower() not in types:
        return None
    resolved = {k: interp(v, environ) for k, v in output.items()}
    return {"output": resolved, "profile": name, "target": target}
