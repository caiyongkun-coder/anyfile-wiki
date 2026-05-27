from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from pfkb.cli import main as cli_main
from pfkb.inventory import Inventory
from pfkb.llm_config import cloud_allowed_for_path, describe_llm_config
from pfkb.parse import ExtractResult
from pfkb.policy import AccessDecision
from pfkb.review import build_review_items
from pfkb.scan import ScanEntry


def _decision(path: Path, access_policy: str) -> AccessDecision:
    is_excluded = access_policy == "deny"
    read_allowed = access_policy in {"allow", "no_embedding"}
    return AccessDecision(
        path=path.resolve().as_posix(),
        is_dir=False,
        access_policy=access_policy,
        policy_source=f"test.{access_policy}",
        reason=f"{access_policy} fixture",
        is_read_allowed=read_allowed,
        is_extract_allowed=read_allowed,
        is_index_allowed=not is_excluded and access_policy != "metadata_only",
        is_embedding_allowed=access_policy == "allow",
        metadata_only=access_policy == "metadata_only",
        is_excluded=is_excluded,
    )


def _entry(path: Path, access_policy: str) -> ScanEntry:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\nfixture", encoding="utf-8")
    return ScanEntry(
        path=str(path),
        name=path.name,
        extension=path.suffix.lower(),
        is_dir=False,
        exists_now=True,
        size_bytes=path.stat().st_size,
        mtime=1.0,
        ctime=1.0,
        decision=_decision(path, access_policy),
        last_seen_at="2026-05-27T12:00:00+00:00",
        extra={},
    )


def _extract_result(source: Path, output: Path, status: str = "ok") -> ExtractResult:
    return ExtractResult(
        path=str(source),
        parser="direct_text",
        status=status,
        output_path=str(output),
        error=None if status == "ok" else "fixture extraction problem",
        embedding_allowed=True,
        created_at="2026-05-27T12:30:00+00:00",
    )


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            result = cli_main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        else:
            code = int(result)
    return code, stdout.getvalue(), stderr.getvalue()


def test_cloud_policy_requires_explicit_ack_and_allowed_path(tmp_path):
    allowed_dir = tmp_path / "allowed"
    allowed_file = allowed_dir / "note.md"
    config = {
        "llm": {"mode": "cloud", "provider": "openai"},
        "cloud": {
            "enabled": True,
            "risk_acknowledged": True,
            "allowed_policies": ["allow"],
            "forbidden_policies": ["deny", "metadata_only", "no_embedding"],
            "allowed_paths": [allowed_dir.as_posix()],
        },
    }

    assert cloud_allowed_for_path(str(allowed_file), "allow", config) is True
    assert cloud_allowed_for_path(str(allowed_file), "no_embedding", config) is False
    assert cloud_allowed_for_path(str(tmp_path / "other.md"), "allow", config) is False

    blocked = {**config, "cloud": {**config["cloud"], "risk_acknowledged": False}}
    assert cloud_allowed_for_path(str(allowed_file), "allow", blocked) is False


def test_review_items_include_policy_blocks_extraction_gaps_and_rules_only(tmp_path):
    allowed = tmp_path / "allowed.md"
    denied = tmp_path / "secret.pem"
    metadata = tmp_path / "tax.md"
    unsupported = tmp_path / "design.psd"
    output = tmp_path / "extract" / "allowed.md"
    output.parent.mkdir()
    output.write_text("# Allowed\n\nfixture", encoding="utf-8")

    files = [
        _entry(allowed, "allow"),
        _entry(denied, "deny"),
        _entry(metadata, "metadata_only"),
        _entry(unsupported, "allow"),
    ]
    file_records = [
        {
            "path": entry.path,
            "extension": entry.extension,
            "is_dir": entry.is_dir,
            "access_policy": entry.access_policy,
            "policy_source": entry.decision.policy_source,
            "policy_reason": entry.decision.reason,
            "is_read_allowed": entry.decision.is_read_allowed,
            "is_extract_allowed": entry.decision.is_extract_allowed,
        }
        for entry in files
    ]
    latest_extracts = {str(allowed): {"status": "ok", "output_path": str(output)}}
    analysis_records = [
        {
            "path": str(allowed),
            "analysis_method": "rules",
            "needs_human_review": True,
            "review_reason": "rules_only_needs_semantic_review",
            "confidence": 0.45,
            "tags": ["document"],
        }
    ]

    items = build_review_items(file_records, latest_extracts, analysis_records=analysis_records)
    categories = {item.category for item in items}

    assert "policy_blocked" in categories
    assert "metadata_only" in categories
    assert "unsupported_format" in categories
    assert "rules_only_or_low_confidence" in categories


def test_review_cli_writes_human_review_outputs(tmp_path):
    allowed = tmp_path / "allowed.md"
    denied = tmp_path / "secret.pem"
    output = tmp_path / "extract" / "allowed.md"
    output.parent.mkdir()
    output.write_text("# Allowed\n\nfixture", encoding="utf-8")
    inventory_path = tmp_path / "inventory.sqlite"
    with Inventory(inventory_path) as inventory:
        inventory.upsert_entries([_entry(allowed, "allow"), _entry(denied, "deny")])
        inventory.add_extract_results([_extract_result(allowed, output)])

    analysis_path = tmp_path / "analysis-manifest.jsonl"
    analysis_path.write_text(
        json.dumps(
            {
                "path": str(allowed),
                "analysis_method": "rules",
                "needs_human_review": True,
                "review_reason": "rules_only_needs_semantic_review",
                "confidence": 0.4,
                "tags": ["document"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "review"
    code, stdout, stderr = _run_cli(
        [
            "review",
            "--inventory",
            str(inventory_path),
            "--analysis",
            str(analysis_path),
            "--out",
            str(out_dir),
        ]
    )

    assert code == 0, stderr
    assert "human_review_md" in stdout
    review_md = out_dir / "human-review.md"
    review_jsonl = out_dir / "human-review.jsonl"
    assert review_md.exists()
    assert review_jsonl.exists()
    text = review_md.read_text(encoding="utf-8")
    assert "# 人工待整理清单" in text
    assert "规则版标签或低置信度结果" in text
    assert "隐私策略阻止读取" in text


def test_llm_cli_explains_default_config(tmp_path):
    llm_config = tmp_path / "llm.yaml"
    llm_config.write_text(
        "\n".join(
            [
                "version: 1",
                "assistant:",
                '  purpose: "llm fixture"',
                "llm:",
                "  mode: rules",
                "  provider: none",
                "cloud:",
                "  enabled: false",
                "  risk_acknowledged: false",
                "  allowed_paths: []",
                "",
            ]
        ),
        encoding="utf-8",
    )

    code, stdout, stderr = _run_cli(["llm", "--llm-config", str(llm_config)])
    assert code == 0, stderr
    assert "llm_config:" in stdout
    assert "mode: rules" in stdout
    assert describe_llm_config({"llm": {"mode": "rules"}})["mode"] == "rules"
