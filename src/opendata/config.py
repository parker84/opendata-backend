"""Project config — `.opendata/config.yml`.

Written by `opendata init`, committed to share with the team. Contains
connection *references* only — never secrets (those live in env / keychain).
"""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_DIR = ".opendata"
CONFIG_FILE = "config.yml"


def config_dir(root: Path) -> Path:
    return root / CONFIG_DIR


def config_path(root: Path) -> Path:
    return config_dir(root) / CONFIG_FILE


def load_config(root: Path) -> dict | None:
    p = config_path(root)
    if not p.exists():
        return None
    return yaml.safe_load(p.read_text()) or {}


def write_config(root: Path, cfg: dict) -> Path:
    config_dir(root).mkdir(parents=True, exist_ok=True)
    p = config_path(root)
    p.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return p
