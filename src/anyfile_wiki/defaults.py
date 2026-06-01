from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml


CONFIG_PACKAGE = "anyfile_wiki.configs"


def default_config_text(name: str) -> str:
    repo_path = Path(__file__).resolve().parents[2] / "configs" / name
    if repo_path.exists():
        return repo_path.read_text(encoding="utf-8-sig")
    return resources.files(CONFIG_PACKAGE).joinpath(name).read_text(encoding="utf-8-sig")


def copy_default_config(name: str, target: str | Path) -> None:
    output = Path(target)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(default_config_text(name), encoding="utf-8")


def load_default_yaml(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load(default_config_text(name)) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Default config must be a mapping: {name}")
    return loaded
