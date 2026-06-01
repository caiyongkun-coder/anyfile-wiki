from __future__ import annotations

import importlib
from collections.abc import Mapping
from enum import Enum
from pathlib import Path

import pytest


def _policy_module():
    try:
        return importlib.import_module("anyfile_wiki.policy")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected anyfile_wiki.policy to be importable for MVP0 policy tests: {exc}")


def _as_config_path(path: Path) -> str:
    return path.resolve().as_posix()


def _make_engine(policy_mod, policy_data=None, excludes=None):
    engine_cls = policy_mod.PolicyEngine
    attempts = []

    if policy_data is not None and excludes is not None:
        attempts.extend(
            [
                lambda: engine_cls(policy=policy_data, excludes=excludes),
                lambda: engine_cls(policy_data, excludes),
                lambda: engine_cls(policy_data, default_excludes=excludes),
            ]
        )
    if policy_data is not None:
        attempts.extend(
            [
                lambda: engine_cls(policy=policy_data),
                lambda: engine_cls(policy_data),
            ]
        )
    if excludes is not None:
        attempts.extend(
            [
                lambda: engine_cls(excludes=excludes),
                lambda: engine_cls(default_excludes=excludes),
                lambda: engine_cls(None, excludes),
            ]
        )

    last_error = None
    for build in attempts:
        try:
            return build()
        except TypeError as exc:
            last_error = exc

    pytest.fail(f"Could not construct PolicyEngine with policy/excludes data: {last_error}")


def _value(decision, *names):
    if isinstance(decision, Mapping):
        for name in names:
            if name in decision:
                return decision[name]
        return None

    for name in names:
        if hasattr(decision, name):
            return getattr(decision, name)
    return None


def _to_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        value = value.value
    elif hasattr(value, "value") and not isinstance(value, (str, bool, int, float)):
        value = value.value
    return str(value).split(".")[-1].lower().replace("-", "_").replace(" ", "_")


def _decision_kind(decision) -> str | None:
    raw = _value(decision, "action", "access_policy", "policy", "decision", "kind")
    kind = _to_text(raw)
    aliases = {
        "denied": "deny",
        "exclude": "deny",
        "excluded": "deny",
        "skip": "deny",
        "skipped": "deny",
        "read": "allow",
        "allowed": "allow",
        "metadata": "metadata_only",
        "metadataonly": "metadata_only",
        "metadata_only": "metadata_only",
        "no_embedding": "no_embedding",
        "noembeddings": "no_embedding",
        "no_embedding_allowed": "no_embedding",
    }
    if kind in aliases:
        return aliases[kind]
    if kind in {"deny", "allow"}:
        return kind

    if _value(decision, "denied", "is_denied", "excluded", "is_excluded") is True:
        return "deny"
    if _value(decision, "metadata_only", "is_metadata_only") is True:
        return "metadata_only"
    if _value(decision, "no_embedding", "is_no_embedding") is True:
        return "no_embedding"
    if _value(decision, "allowed", "is_allowed") is True:
        return "allow"
    return kind


def _flag(decision, default: bool, *names) -> bool:
    raw = _value(decision, *names)
    if raw is None:
        return default
    return bool(raw)


def _allows_metadata(decision) -> bool:
    kind = _decision_kind(decision)
    return _flag(
        decision,
        kind in {"allow", "metadata_only", "no_embedding"},
        "record_metadata",
        "metadata_allowed",
        "can_record_metadata",
        "write_metadata",
    )


def _allows_content_read(decision) -> bool:
    kind = _decision_kind(decision)
    return _flag(
        decision,
        kind in {"allow", "no_embedding"},
        "read_content",
        "content_allowed",
        "can_read_content",
        "read_allowed",
        "should_read_content",
    )


def _allows_summary(decision) -> bool:
    kind = _decision_kind(decision)
    return _flag(
        decision,
        kind in {"allow", "no_embedding"},
        "summary_allowed",
        "summarize",
        "can_summarize",
        "should_summarize",
    )


def _allows_embedding(decision) -> bool:
    kind = _decision_kind(decision)
    return _flag(
        decision,
        kind == "allow",
        "embedding_allowed",
        "embed",
        "can_embed",
        "should_embed",
        "vector_index",
        "index_content",
    )


def _assert_kind(decision, expected: str) -> None:
    assert _decision_kind(decision) == expected, decision


def test_load_policy_and_decide_deny_wins_over_allow_and_weaker_rules(tmp_path):
    policy_mod = _policy_module()
    root = tmp_path / "knowledge"
    private = root / "Private"
    finance = private / "Finance"
    contracts = private / "Contracts"
    root.mkdir()
    finance.mkdir(parents=True)
    contracts.mkdir(parents=True)

    policy_file = tmp_path / "privacy.yaml"
    policy_file.write_text(
        "\n".join(
            [
                "deny:",
                "  paths:",
                f'    - "{_as_config_path(private)}"',
                "  extensions:",
                '    - ".pem"',
                "metadata_only:",
                "  paths:",
                f'    - "{_as_config_path(finance)}"',
                "no_embedding:",
                "  paths:",
                f'    - "{_as_config_path(contracts)}"',
                "allow:",
                "  paths:",
                f'    - "{_as_config_path(root)}"',
                "  extensions:",
                '    - ".pem"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    loaded_policy = policy_mod.load_policy(policy_file)
    engine = _make_engine(policy_mod, policy_data=loaded_policy)

    _assert_kind(engine.decide(finance / "taxes.md"), "deny")
    _assert_kind(engine.decide(contracts / "nda.md"), "deny")
    _assert_kind(engine.decide(root / "public-key.PEM"), "deny")
    _assert_kind(engine.decide(root / "notes.md"), "allow")


def test_metadata_only_records_metadata_but_disallows_content_read(tmp_path):
    policy_mod = _policy_module()
    root = tmp_path / "knowledge"
    finance = root / "Finance"
    finance.mkdir(parents=True)
    policy_file = tmp_path / "privacy.yaml"
    policy_file.write_text(
        "\n".join(
            [
                "metadata_only:",
                "  paths:",
                f'    - "{_as_config_path(finance)}"',
                "allow:",
                "  paths:",
                f'    - "{_as_config_path(root)}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    loaded_policy = policy_mod.load_policy(policy_file)
    decision = _make_engine(policy_mod, policy_data=loaded_policy).decide(
        finance / "tax-return.xlsx"
    )

    _assert_kind(decision, "metadata_only")
    assert _allows_metadata(decision) is True
    assert _allows_content_read(decision) is False


def test_no_embedding_allows_reading_and_summary_but_blocks_embedding(tmp_path):
    policy_mod = _policy_module()
    root = tmp_path / "knowledge"
    contracts = root / "Contracts"
    contracts.mkdir(parents=True)
    policy_file = tmp_path / "privacy.yaml"
    policy_file.write_text(
        "\n".join(
            [
                "no_embedding:",
                "  paths:",
                f'    - "{_as_config_path(contracts)}"',
                "allow:",
                "  paths:",
                f'    - "{_as_config_path(root)}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    loaded_policy = policy_mod.load_policy(policy_file)
    decision = _make_engine(policy_mod, policy_data=loaded_policy).decide(
        contracts / "vendor-agreement.pdf"
    )

    _assert_kind(decision, "no_embedding")
    assert _allows_content_read(decision) is True
    assert _allows_summary(decision) is True
    assert _allows_embedding(decision) is False


def test_load_excludes_default_rules_deny_common_noise_and_dangerous_files():
    policy_mod = _policy_module()
    excludes = policy_mod.load_excludes(None)
    engine = _make_engine(policy_mod, excludes=excludes)

    denied_paths = [
        "C:/Users/Alice/project/node_modules/react/index.js",
        "C:/Users/Alice/project/.venv/Lib/site-packages/example.py",
        "C:/Program Files/Example/app.ini",
        "C:/Windows/System32/drivers/etc/hosts",
        "C:/Users/Alice/project/.env",
        "C:/Users/Alice/Documents/private-key.pem",
        "C:/Users/Alice/Documents/license.KEY",
    ]

    for candidate in denied_paths:
        _assert_kind(engine.decide(candidate), "deny")


def test_descriptive_privacy_fields_are_agent_readable_and_do_not_change_rules(tmp_path):
    policy_mod = _policy_module()
    root = tmp_path / "knowledge"
    private = root / "Private"
    root.mkdir()
    private.mkdir()
    policy_data = {
        "version": 1,
        "assistant": {
            "purpose": "fixture purpose",
            "setup_questions": ["Where are secrets?"],
            "policies": {
                "deny": {
                    "title": "Do not touch",
                    "effect": "Never open matched content.",
                    "questions": ["Which folders are secret?"],
                    "examples": ["Private"],
                }
            },
        },
        "deny": {
            "help": {
                "title": "Strict deny",
                "when_to_use": "Secrets",
            },
            "paths": [_as_config_path(private)],
        },
        "allow": {
            "help": {"title": "Allowed knowledge"},
            "paths": [_as_config_path(root)],
        },
    }

    summary = policy_mod.describe_privacy_policy(policy_data)
    deny_summary = next(item for item in summary["policies"] if item["policy"] == "deny")

    assert summary["purpose"] == "fixture purpose"
    assert summary["setup_questions"] == ["Where are secrets?"]
    assert deny_summary["title"] == "Strict deny"
    assert deny_summary["rule_counts"]["paths"] == 1
    assert deny_summary["rules"]["paths"] == [_as_config_path(private)]

    engine = _make_engine(policy_mod, policy_data=policy_data)
    _assert_kind(engine.decide(private / "secret.md"), "deny")
    _assert_kind(engine.decide(root / "note.md"), "allow")


def test_policy_requires_explicit_allow_by_default(tmp_path):
    policy_mod = _policy_module()
    engine = _make_engine(policy_mod, policy_data={})

    decision = engine.decide(tmp_path / "unlisted.md")

    _assert_kind(decision, "deny")
    assert _value(decision, "policy_source") == "privacy.require_allow"
