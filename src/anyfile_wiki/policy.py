from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import fnmatch
import os

import yaml

from .defaults import load_default_yaml


POLICY_DENY = "deny"
POLICY_METADATA_ONLY = "metadata_only"
POLICY_NO_EMBEDDING = "no_embedding"
POLICY_ALLOW = "allow"
POLICY_ORDER = (POLICY_DENY, POLICY_METADATA_ONLY, POLICY_NO_EMBEDDING, POLICY_ALLOW)

RULE_GROUPS = {
    "paths": ("paths", "path"),
    "globs": ("path_globs", "globs", "glob"),
    "extensions": ("extensions", "extension", "dangerous_extensions"),
    "file_globs": ("file_globs", "files", "file_patterns"),
    "filenames": ("filenames", "file_names", "names"),
    "directory_names": ("dir_names", "directories", "directory_names"),
}

POLICY_HELP = {
    POLICY_DENY: {
        "title": "完全禁止",
        "effect": "不读取、不提取、不索引、不摘要、不 embedding。",
        "when_to_use": "密钥、密码库、钱包、浏览器登录数据，以及用户绝对不希望被打开的内容。",
        "questions": [
            "密码、密钥、钱包或私密导出文件存在哪里？",
            "哪些 app 数据目录应该完全禁止访问？",
        ],
        "examples": [".ssh", ".env", "wallet.dat", "KeePass 密码库", "浏览器 Login Data"],
    },
    POLICY_METADATA_ONLY: {
        "title": "只登记元数据",
        "effect": "只记录路径、文件名、大小、时间和类型，不打开文件正文。",
        "when_to_use": "知道文件存在有价值，但正文仍应保持私密的敏感领域。",
        "questions": [
            "哪些财务、医疗、身份或法律目录只应该被盘点？",
        ],
        "examples": ["税务目录", "银行流水", "医疗记录", "护照扫描件"],
    },
    POLICY_NO_EMBEDDING: {
        "title": "可读取但不向量化",
        "effect": "允许提取和摘要，但禁止写入向量/embedding 索引。",
        "when_to_use": "可以本地摘要，但不应该进入语义向量检索的内容。",
        "questions": [
            "哪些合同、客户资料或草稿可以本地读取，但不能进入语义索引？",
        ],
        "examples": ["合同", "NDA 目录", "客户资料", "法律草稿"],
    },
    POLICY_ALLOW: {
        "title": "允许进入知识库",
        "effect": "在通过更高优先级规则和默认排除后，允许读取、提取、索引和 embedding。",
        "when_to_use": "低风险知识目录，例如笔记、研究资料、文档和整理好的收件箱。",
        "questions": [
            "哪些目录应该成为第一批可检索知识来源？",
        ],
        "examples": ["Desktop", "Documents", "Notes", "Research", "Knowledge Inbox"],
    },
}


@dataclass(frozen=True)
class AccessDecision:
    path: str
    is_dir: bool
    access_policy: str
    policy_source: str
    reason: str
    is_read_allowed: bool
    is_extract_allowed: bool
    is_index_allowed: bool
    is_embedding_allowed: bool
    metadata_only: bool
    is_excluded: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "is_dir": self.is_dir,
            "access_policy": self.access_policy,
            "policy_source": self.policy_source,
            "reason": self.reason,
            "is_read_allowed": self.is_read_allowed,
            "is_extract_allowed": self.is_extract_allowed,
            "is_index_allowed": self.is_index_allowed,
            "is_embedding_allowed": self.is_embedding_allowed,
            "metadata_only": self.metadata_only,
            "is_excluded": self.is_excluded,
        }


@dataclass(frozen=True)
class RuleMatch:
    policy: str
    source: str
    reason: str


def load_policy(path: str | os.PathLike[str] | None) -> dict[str, Any]:
    return _load_yaml(path)


def load_excludes(path: str | os.PathLike[str] | None) -> dict[str, Any]:
    if path is None:
        return load_default_yaml("excludes.default.yaml")
    return _load_yaml(path)


def describe_privacy_policy(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a human/agent-readable view of a privacy policy config.

    The scanner ignores descriptive fields, but setup flows and agents can use
    this summary to explain existing rules before proposing machine-specific
    edits.
    """

    config = config or {}
    assistant = _as_mapping(config.get("assistant"))
    configured_priority = _string_list(assistant.get("priority"))
    priority = configured_priority or list(POLICY_ORDER)
    default_rule_fields = {
        "paths": "环境变量展开后的路径前缀匹配。",
        "globs": "全路径 glob 通配符，适合不同机器上位置不固定的目录。",
        "extensions": "文件扩展名，例如 .pdf 或 .pem。",
        "filenames": "精确文件名，例如 .env 或 wallet.dat。",
        "file_globs": "只匹配文件名的 glob 通配符。",
        "directory_names": "路径中任意一层目录名匹配。",
    }
    configured_rule_fields = {
        str(key): str(value)
        for key, value in _as_mapping(assistant.get("rule_fields")).items()
    }
    return {
        "version": config.get("version", 1),
        "purpose": str(
            assistant.get(
                "purpose",
                "配置 AnyFile Wiki 可以读取、提取、索引或只登记元数据的本地文件范围。",
            )
        ),
        "priority": priority,
        "require_allow": bool(config.get("require_allow", True)),
        "path_syntax": _string_list(assistant.get("path_syntax"))
        or [
            "跨平台路径建议使用 / 作为分隔符。",
            "${USERPROFILE}、${HOME} 等环境变量会在运行时展开。",
            "glob 规则可以使用 ** 匹配任意目录层级。",
        ],
        "setup_questions": _string_list(assistant.get("setup_questions")),
        "rule_fields": {**default_rule_fields, **configured_rule_fields},
        "policies": [_describe_policy_section(config, assistant, policy) for policy in POLICY_ORDER],
    }


def _load_yaml(path: str | os.PathLike[str] | None) -> dict[str, Any]:
    if path is None:
        return {}
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8-sig") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Config must be a mapping: {config_path}")
    return loaded


def _describe_policy_section(
    config: dict[str, Any],
    assistant: dict[str, Any],
    policy: str,
) -> dict[str, Any]:
    section = _as_mapping(config.get(policy))
    assistant_policies = _as_mapping(assistant.get("policies"))
    policy_help = {
        **POLICY_HELP[policy],
        **_as_mapping(assistant_policies.get(policy)),
        **_as_mapping(section.get("help")),
    }
    rules = {
        name: [str(value) for value in _list_values(section, *keys)]
        for name, keys in RULE_GROUPS.items()
    }
    rules = {name: values for name, values in rules.items() if values}
    return {
        "policy": policy,
        "title": str(policy_help.get("title", policy)),
        "effect": str(policy_help.get("effect", "")),
        "when_to_use": str(policy_help.get("when_to_use", "")),
        "questions": _string_list(policy_help.get("questions")),
        "examples": _string_list(policy_help.get("examples")),
        "rule_counts": {name: len(values) for name, values in rules.items()},
        "rules": rules,
    }


class PolicyEngine:
    """Decides whether scanner may read, extract, or index a path.

    The engine is intentionally path-first. It can decide on metadata from the
    path and directory entry before any file content is opened.
    """

    def __init__(
        self,
        privacy: dict[str, Any] | None = None,
        excludes: dict[str, Any] | None = None,
        *,
        require_allow: bool | None = None,
        policy: dict[str, Any] | None = None,
        default_excludes: dict[str, Any] | None = None,
    ) -> None:
        self.privacy = privacy or policy or {}
        self.excludes = excludes or default_excludes or {}
        configured_require_allow = self.privacy.get("require_allow", True)
        self.require_allow = bool(configured_require_allow if require_allow is None else require_allow)

    @classmethod
    def from_files(
        cls,
        privacy_path: str | os.PathLike[str] | None = None,
        excludes_path: str | os.PathLike[str] | None = None,
    ) -> "PolicyEngine":
        return cls(load_policy(privacy_path), load_excludes(excludes_path))

    def decide(self, path: str | os.PathLike[str], *, is_dir: bool = False) -> AccessDecision:
        raw_path = str(path)
        normalized = normalize_path(raw_path)
        extension = Path(raw_path).suffix.lower()
        name = Path(raw_path).name.lower()

        for match in self._matches_for_policy(POLICY_DENY, normalized, name, extension, is_dir):
            return self._decision(normalized, is_dir, match)

        exclude_match = self._match_excludes(normalized, name, extension, is_dir)
        if exclude_match:
            return self._decision(normalized, is_dir, exclude_match)

        for match in self._matches_for_policy(POLICY_METADATA_ONLY, normalized, name, extension, is_dir):
            return self._decision(normalized, is_dir, match)

        for match in self._matches_for_policy(POLICY_NO_EMBEDDING, normalized, name, extension, is_dir):
            return self._decision(normalized, is_dir, match)

        allow_match = next(
            iter(self._matches_for_policy(POLICY_ALLOW, normalized, name, extension, is_dir)),
            None,
        )
        if allow_match:
            return self._decision(normalized, is_dir, allow_match)

        if self.require_allow:
            return self._decision(
                normalized,
                is_dir,
                RuleMatch(POLICY_DENY, "privacy.require_allow", "No allow rule matched"),
            )

        return self._decision(
            normalized,
            is_dir,
            RuleMatch(POLICY_ALLOW, "default", "No deny or restrictive rule matched"),
        )

    def _decision(self, path: str, is_dir: bool, match: RuleMatch) -> AccessDecision:
        if match.policy == POLICY_DENY:
            return AccessDecision(
                path=path,
                is_dir=is_dir,
                access_policy=POLICY_DENY,
                policy_source=match.source,
                reason=match.reason,
                is_read_allowed=False,
                is_extract_allowed=False,
                is_index_allowed=False,
                is_embedding_allowed=False,
                metadata_only=False,
                is_excluded=True,
            )
        if match.policy == POLICY_METADATA_ONLY:
            return AccessDecision(
                path=path,
                is_dir=is_dir,
                access_policy=POLICY_METADATA_ONLY,
                policy_source=match.source,
                reason=match.reason,
                is_read_allowed=False,
                is_extract_allowed=False,
                is_index_allowed=False,
                is_embedding_allowed=False,
                metadata_only=True,
                is_excluded=False,
            )
        if match.policy == POLICY_NO_EMBEDDING:
            return AccessDecision(
                path=path,
                is_dir=is_dir,
                access_policy=POLICY_NO_EMBEDDING,
                policy_source=match.source,
                reason=match.reason,
                is_read_allowed=True,
                is_extract_allowed=True,
                is_index_allowed=True,
                is_embedding_allowed=False,
                metadata_only=False,
                is_excluded=False,
            )
        return AccessDecision(
            path=path,
            is_dir=is_dir,
            access_policy=POLICY_ALLOW,
            policy_source=match.source,
            reason=match.reason,
            is_read_allowed=True,
            is_extract_allowed=True,
            is_index_allowed=True,
            is_embedding_allowed=True,
            metadata_only=False,
            is_excluded=False,
        )

    def _matches_for_policy(
        self,
        policy: str,
        normalized: str,
        name: str,
        extension: str,
        is_dir: bool,
    ) -> Iterable[RuleMatch]:
        section = _as_mapping(self.privacy.get(policy))
        yield from self._matches_section(
            section,
            normalized,
            name,
            extension,
            is_dir,
            policy=policy,
            source=f"privacy.{policy}",
        )

    def _match_excludes(
        self,
        normalized: str,
        name: str,
        extension: str,
        is_dir: bool,
    ) -> RuleMatch | None:
        for source, section in _iter_rule_sections(self.excludes, "excludes"):
            for match in self._matches_section(
                section,
                normalized,
                name,
                extension,
                is_dir,
                policy=POLICY_DENY,
                source=source,
            ):
                return match
        return None

    def _matches_section(
        self,
        section: dict[str, Any],
        normalized: str,
        name: str,
        extension: str,
        is_dir: bool,
        *,
        policy: str,
        source: str,
    ) -> Iterable[RuleMatch]:
        for rule in _list_values(section, "paths", "path"):
            if _path_matches(normalized, str(rule)):
                yield RuleMatch(policy, source, f"path matched {rule}")

        for rule in _list_values(section, "path_globs", "globs", "glob"):
            if fnmatch.fnmatchcase(normalized.lower(), normalize_glob(str(rule)).lower()):
                yield RuleMatch(policy, source, f"path glob matched {rule}")

        for rule in _list_values(section, "extensions", "extension", "dangerous_extensions"):
            if extension and extension == _normalize_extension(str(rule)):
                yield RuleMatch(policy, source, f"extension matched {rule}")

        for rule in _list_values(section, "file_globs", "files", "file_patterns"):
            if fnmatch.fnmatchcase(name, str(rule).lower()):
                yield RuleMatch(policy, source, f"file glob matched {rule}")

        for rule in _list_values(section, "filenames", "file_names", "names"):
            if name == str(rule).lower():
                yield RuleMatch(policy, source, f"filename matched {rule}")

        for rule in _list_values(section, "dir_names", "directories", "directory_names"):
            if (is_dir and name == str(rule).lower()) or _path_has_segment(normalized, str(rule)):
                yield RuleMatch(policy, source, f"directory name matched {rule}")


def normalize_path(path: str) -> str:
    expanded = os.path.expandvars(os.path.expanduser(path))
    absolute = os.path.abspath(expanded)
    return absolute.replace("\\", "/")


def normalize_glob(pattern: str) -> str:
    return os.path.expandvars(os.path.expanduser(pattern)).replace("\\", "/")


def _path_matches(normalized_path: str, rule: str) -> bool:
    normalized_rule = normalize_path(rule).rstrip("/")
    path = normalized_path.rstrip("/")
    if os.name == "nt":
        path = path.lower()
        normalized_rule = normalized_rule.lower()
    return path == normalized_rule or path.startswith(normalized_rule + "/")


def _normalize_extension(value: str) -> str:
    value = value.strip().lower()
    if not value:
        return value
    return value if value.startswith(".") else f".{value}"


def _path_has_segment(normalized_path: str, segment: str) -> bool:
    wanted = segment.strip().lower().strip("/")
    if not wanted:
        return False
    parts = [part.lower() for part in normalized_path.replace("\\", "/").split("/") if part]
    return wanted in parts


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_values(section: dict[str, Any], *keys: str) -> list[Any]:
    values: list[Any] = []
    for key in keys:
        raw = section.get(key)
        if raw is None:
            continue
        if isinstance(raw, (str, int, float)):
            values.append(raw)
        elif isinstance(raw, list):
            values.extend(raw)
    return values


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _iter_rule_sections(config: dict[str, Any], source: str) -> Iterable[tuple[str, dict[str, Any]]]:
    if not isinstance(config, dict):
        return
    yield source, config
    for key, value in config.items():
        if key == "version":
            continue
        if isinstance(value, dict):
            yield from _iter_rule_sections(value, f"{source}.{key}")
