from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os

import yaml


@dataclass(frozen=True)
class CandidateRoot:
    name: str
    path: Path
    exists: bool
    source: str
    enabled: bool = True
    resolver: str = "path"
    description: str = ""
    risk: str = "medium"
    recommended_policy: str = "allow"
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "exists": self.exists,
            "source": self.source,
            "enabled": self.enabled,
            "resolver": self.resolver,
            "description": self.description,
            "risk": self.risk,
            "recommended_policy": self.recommended_policy,
            "tags": list(self.tags),
        }


def load_roots_config(path: str | os.PathLike[str] | None) -> dict[str, Any]:
    if path is None:
        return _default_roots_config()
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Roots config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8-sig") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Roots config must be a mapping: {config_path}")
    return loaded


def describe_roots_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or _default_roots_config()
    assistant = _as_mapping(config.get("assistant"))
    return {
        "version": config.get("version", 1),
        "purpose": str(
            assistant.get(
                "purpose",
                "配置推荐扫描入口，供用户和 agent 在初始化时选择从哪些本机目录开始盘点。",
            )
        ),
        "setup_questions": _string_list(assistant.get("setup_questions")),
        "selection_notes": _string_list(assistant.get("selection_notes")),
        "root_fields": {
            "name": "稳定的目录标识。",
            "enabled": "是否默认参与推荐列表。",
            "resolver": "解析方式：home、home_child、env 或 path。",
            "risk": "扫描风险提示：low、medium、high。",
            "recommended_policy": "建议配合的隐私策略，通常是 allow、metadata_only 或 no_embedding。",
            "tags": "给初始化向导或 UI 使用的目录标签。",
        },
        "roots": [_describe_root_definition(item) for item in _root_items(config)],
    }


def discover_candidate_roots(
    *,
    existing_only: bool = True,
    config: dict[str, Any] | None = None,
    include_disabled: bool = False,
) -> list[CandidateRoot]:
    config = config or _default_roots_config()
    candidates = [
        candidate
        for item in _root_items(config)
        for candidate in [_candidate_from_definition(item)]
        if candidate is not None and (include_disabled or candidate.enabled)
    ]

    seen: set[str] = set()
    result: list[CandidateRoot] = []
    for candidate in candidates:
        key = str(candidate.path).lower()
        if key in seen:
            continue
        seen.add(key)
        if existing_only and not candidate.exists:
            continue
        result.append(candidate)
    return result


def _default_roots_config() -> dict[str, Any]:
    return {
        "version": 1,
        "assistant": {
            "purpose": "配置推荐扫描入口，供用户和 agent 在初始化时选择从哪些本机目录开始盘点。",
            "setup_questions": [
                "这台电脑的主要个人资料放在桌面、文档、下载、OneDrive，还是其他目录？",
                "是否要把整个用户主目录作为候选？如果是，应先确认隐私规则足够保守。",
                "是否有外接盘、同步盘或专门的知识收件箱需要加入？",
            ],
            "selection_notes": [
                "第一次建议从 Documents、Desktop 或 Knowledge Inbox 这类范围较小的目录开始。",
                "home 范围较大，适合 dry-run 盘点，不建议作为第一次正文提取入口。",
                "Downloads 噪声较多，通常要配合 installer/cache 默认排除规则。",
            ],
        },
        "roots": [
            {
                "name": "home",
                "enabled": True,
                "resolver": "home",
                "description": "当前系统用户主目录，范围最大。",
                "risk": "high",
                "recommended_policy": "allow",
                "tags": ["broad", "user-profile"],
            },
            {
                "name": "desktop",
                "enabled": True,
                "resolver": "home_child",
                "child": "Desktop",
                "description": "桌面，常放临时资料和近期工作文件。",
                "risk": "medium",
                "recommended_policy": "allow",
                "tags": ["personal", "recent"],
            },
            {
                "name": "documents",
                "enabled": True,
                "resolver": "home_child",
                "child": "Documents",
                "description": "文档目录，通常是第一批个人知识来源。",
                "risk": "medium",
                "recommended_policy": "allow",
                "tags": ["personal", "documents"],
            },
            {
                "name": "downloads",
                "enabled": True,
                "resolver": "home_child",
                "child": "Downloads",
                "description": "下载目录，价值和噪声都较高。",
                "risk": "medium",
                "recommended_policy": "allow",
                "tags": ["personal", "inbox", "noisy"],
            },
            {
                "name": "onedrive",
                "enabled": True,
                "resolver": "env",
                "env": "OneDrive",
                "description": "OneDrive 同步目录。",
                "risk": "medium",
                "recommended_policy": "allow",
                "tags": ["cloud-sync", "personal"],
            },
            {
                "name": "onedrive_consumer",
                "enabled": True,
                "resolver": "env",
                "env": "OneDriveConsumer",
                "description": "个人版 OneDrive 同步目录。",
                "risk": "medium",
                "recommended_policy": "allow",
                "tags": ["cloud-sync", "personal"],
            },
            {
                "name": "onedrive_commercial",
                "enabled": True,
                "resolver": "env",
                "env": "OneDriveCommercial",
                "description": "组织版 OneDrive 同步目录，可能包含工作资料。",
                "risk": "high",
                "recommended_policy": "no_embedding",
                "tags": ["cloud-sync", "work"],
            },
        ],
    }


def _candidate_from_definition(item: dict[str, Any]) -> CandidateRoot | None:
    name = str(item.get("name", "")).strip()
    if not name:
        return None
    enabled = bool(item.get("enabled", True))
    resolver = str(item.get("resolver", "path"))
    path, source = _resolve_path(item, resolver)
    if path is None:
        return None
    return CandidateRoot(
        name=name,
        path=path,
        exists=path.exists(),
        source=source,
        enabled=enabled,
        resolver=resolver,
        description=str(item.get("description", "")),
        risk=str(item.get("risk", "medium")),
        recommended_policy=str(item.get("recommended_policy", "allow")),
        tags=tuple(_string_list(item.get("tags"))),
    )


def _resolve_path(item: dict[str, Any], resolver: str) -> tuple[Path | None, str]:
    home = Path.home()
    if resolver == "home":
        return home, "Path.home"
    if resolver == "home_child":
        child = str(item.get("child", "")).strip()
        if not child:
            return None, "home_child:missing-child"
        return home / child, f"home_child:{child}"
    if resolver == "env":
        env_name = str(item.get("env", "")).strip()
        if not env_name:
            return None, "env:missing-name"
        raw = os.environ.get(env_name)
        if not raw:
            return Path(f"${{{env_name}}}"), f"env:{env_name}:unset"
        return Path(raw), f"env:{env_name}"
    raw_path = item.get("path")
    if raw_path is None:
        return None, "path:missing"
    expanded = os.path.expandvars(os.path.expanduser(str(raw_path)))
    return Path(expanded), "config:path"


def _describe_root_definition(item: dict[str, Any]) -> dict[str, Any]:
    candidate = _candidate_from_definition(item)
    payload = {
        "name": str(item.get("name", "")),
        "enabled": bool(item.get("enabled", True)),
        "resolver": str(item.get("resolver", "path")),
        "description": str(item.get("description", "")),
        "risk": str(item.get("risk", "medium")),
        "recommended_policy": str(item.get("recommended_policy", "allow")),
        "tags": _string_list(item.get("tags")),
        "raw": {
            key: value
            for key, value in item.items()
            if key
            in {
                "path",
                "child",
                "env",
                "platforms",
                "notes",
            }
        },
    }
    if candidate is not None:
        payload["resolved"] = candidate.as_dict()
    return payload


def _root_items(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get("roots", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []
