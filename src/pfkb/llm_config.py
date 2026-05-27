from __future__ import annotations

from pathlib import Path
from typing import Any
import os

import yaml


def load_llm_config(path: str | os.PathLike[str] | None) -> dict[str, Any]:
    if path is None:
        return default_llm_config()
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"LLM config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8-sig") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"LLM config must be a mapping: {config_path}")
    return loaded


def default_llm_config() -> dict[str, Any]:
    return {
        "version": 1,
        "llm": {"mode": "rules", "provider": "none", "model": "", "endpoint": ""},
        "local": {"enabled": False},
        "cloud": {
            "enabled": False,
            "risk_acknowledged": False,
            "allowed_policies": ["allow"],
            "forbidden_policies": ["deny", "metadata_only", "no_embedding"],
            "allowed_paths": [],
        },
    }


def describe_llm_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = config or default_llm_config()
    assistant = _mapping(config.get("assistant"))
    llm = _mapping(config.get("llm"))
    local = _mapping(config.get("local"))
    cloud = _mapping(config.get("cloud"))
    return {
        "version": config.get("version", 1),
        "purpose": str(
            assistant.get(
                "purpose",
                "配置内容理解阶段是否使用规则、本地模型或云端模型。",
            )
        ),
        "mode": str(llm.get("mode", "rules")),
        "provider": str(llm.get("provider", "none")),
        "local_enabled": bool(local.get("enabled", False)),
        "cloud_enabled": bool(cloud.get("enabled", False)),
        "cloud_risk_acknowledged": bool(cloud.get("risk_acknowledged", False)),
        "cloud_allowed_paths": _string_list(cloud.get("allowed_paths")),
        "cloud_allowed_policies": _string_list(cloud.get("allowed_policies")) or ["allow"],
        "cloud_forbidden_policies": _string_list(cloud.get("forbidden_policies"))
        or ["deny", "metadata_only", "no_embedding"],
        "setup_questions": _string_list(assistant.get("setup_questions")),
        "privacy_notes": _string_list(assistant.get("privacy_notes")),
    }


def cloud_allowed_for_path(path: str, access_policy: str, config: dict[str, Any] | None) -> bool:
    config = config or default_llm_config()
    llm = _mapping(config.get("llm"))
    cloud = _mapping(config.get("cloud"))
    if str(llm.get("mode", "rules")) != "cloud":
        return False
    if not bool(cloud.get("enabled", False)):
        return False
    if not bool(cloud.get("risk_acknowledged", False)):
        return False
    allowed_policies = set(_string_list(cloud.get("allowed_policies")) or ["allow"])
    forbidden_policies = set(
        _string_list(cloud.get("forbidden_policies")) or ["deny", "metadata_only", "no_embedding"]
    )
    if access_policy in forbidden_policies or access_policy not in allowed_policies:
        return False
    allowed_paths = _string_list(cloud.get("allowed_paths"))
    if not allowed_paths:
        return False
    return any(_path_is_under(path, allowed_path) for allowed_path in allowed_paths)


def _path_is_under(path: str, root: str) -> bool:
    normalized_path = _normalize(path)
    normalized_root = _normalize(root).rstrip("/")
    if os.name == "nt":
        normalized_path = normalized_path.lower()
        normalized_root = normalized_root.lower()
    return normalized_path == normalized_root or normalized_path.startswith(normalized_root + "/")


def _normalize(path: str) -> str:
    return os.path.abspath(os.path.expandvars(os.path.expanduser(path))).replace("\\", "/")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []
