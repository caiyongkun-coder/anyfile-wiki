from __future__ import annotations

import contextlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from pfkb.analyze import analyze_extract_records, classify_content_type, infer_tags
from pfkb.cli import main as cli_main
from pfkb.inventory import Inventory
from pfkb.llm_client import LLMAnalysisRequest, LLMAnalysisResponse
from pfkb.parse import ExtractResult
from pfkb.policy import AccessDecision
from pfkb.scan import ScanEntry


def _extract_result(
    source: Path,
    output: Path | None,
    *,
    status: str = "ok",
    parser: str = "direct_text",
    created_at: str = "2026-05-27T10:00:00+00:00",
    embedding_allowed: bool = True,
) -> ExtractResult:
    return ExtractResult(
        path=str(source),
        parser=parser,
        status=status,
        output_path=str(output) if output else None,
        error=None,
        embedding_allowed=embedding_allowed,
        created_at=created_at,
    )


def _scan_entry(source: Path, *, access_policy: str = "allow") -> ScanEntry:
    read_allowed = access_policy in {"allow", "no_embedding"}
    extract_allowed = read_allowed
    embedding_allowed = access_policy == "allow"
    return ScanEntry(
        path=str(source),
        name=source.name,
        extension=source.suffix.lower(),
        is_dir=False,
        exists_now=True,
        size_bytes=source.stat().st_size if source.exists() else 0,
        mtime=source.stat().st_mtime if source.exists() else None,
        ctime=source.stat().st_ctime if source.exists() else None,
        decision=AccessDecision(
            path=str(source),
            is_dir=False,
            access_policy=access_policy,
            policy_source="test",
            reason=f"fixture policy: {access_policy}",
            is_read_allowed=read_allowed,
            is_extract_allowed=extract_allowed,
            is_index_allowed=access_policy != "metadata_only",
            is_embedding_allowed=embedding_allowed,
            metadata_only=access_policy == "metadata_only",
            is_excluded=access_policy == "deny",
        ),
        last_seen_at=datetime.now(timezone.utc).isoformat(),
        extra={},
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


def _write_llm_config(path: Path, *, mode: str, allowed_path: Path | None = None) -> None:
    allowed_paths = [str(allowed_path)] if allowed_path else []
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "llm:",
                f"  mode: {mode}",
                "local:",
                "  enabled: true",
                "  provider: ollama",
                "  model: fake-local",
                "  endpoint: http://localhost:11434",
                "cloud:",
                "  enabled: true",
                "  provider: compatible",
                "  model: fake-cloud",
                "  endpoint: https://example.invalid/v1",
                "  risk_acknowledged: true",
                "  allowed_policies: [allow]",
                "  forbidden_policies: [deny, metadata_only, no_embedding]",
                "  allowed_paths:",
                *[f"    - {item}" for item in allowed_paths],
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_tags_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "tags:",
                "  - id: topic/privacy_policy",
                "    zh: privacy",
                "    en: privacy",
                "    dimension: topic",
                "  - id: document/note",
                "    zh: note",
                "    en: note",
                "    dimension: document",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


class FakeLLMClient:
    def __init__(self) -> None:
        self.requests: list[LLMAnalysisRequest] = []

    def analyze(self, request_data: LLMAnalysisRequest) -> LLMAnalysisResponse:
        self.requests.append(request_data)
        return LLMAnalysisResponse(
            title="模型理解后的标题",
            summary="模型理解后的中文摘要。",
            tags=["topic/privacy_policy", "document/note"],
            confidence=0.91,
            needs_human_review=False,
            review_reason="llm_semantic_reviewed",
            key_points=["识别了正文主题", "保留了规则标签用于审计"],
            model_notes="fake llm fixture",
        )


def test_analyze_extract_records_generates_summary_tags_and_counts(tmp_path):
    source = tmp_path / "docs" / "privacy-guide.md"
    output = tmp_path / "extract" / "privacy-guide.md"
    output.parent.mkdir(parents=True)
    output.write_text(
        "# Privacy Guide\n\nThis document explains privacy scan rules and metadata_only handling.\n",
        encoding="utf-8",
    )

    results = analyze_extract_records(
        [
            {
                "path": str(source),
                "output_path": str(output),
                "status": "ok",
                "parser": "direct_text",
                "embedding_allowed": True,
            }
        ]
    )

    assert len(results) == 1
    result = results[0]
    assert result.status == "ok"
    assert result.title == "Privacy Guide"
    assert "privacy" in result.tags
    assert "scan" in result.tags
    assert result.content_type == "docs"
    assert result.word_count > 0
    assert result.analysis_method == "rules"
    assert result.confidence > 0
    assert result.review_reason.startswith("rules_")


def test_codex_mock_analysis_preserves_rule_tags_and_adds_semantic_fields(tmp_path):
    source = tmp_path / "src" / "pfkb" / "review.py"
    output = tmp_path / "extract" / "review.py"
    output.parent.mkdir(parents=True)
    output.write_text(
        "\n".join(
            [
                "def build_review_items(files, latest_extracts):",
                "    return []",
                "",
                "def write_review_outputs(items, output_dir):",
                "    return {'human_review_md': 'human-review.md'}",
            ]
        ),
        encoding="utf-8",
    )

    results = analyze_extract_records(
        [
            {
                "path": str(source),
                "output_path": str(output),
                "status": "ok",
                "parser": "direct_text",
                "embedding_allowed": True,
            }
        ],
        analysis_method="codex-mock",
    )

    result = results[0]
    assert result.analysis_method == "codex-mock"
    assert result.rule_tags
    assert "code" in result.rule_tags
    assert "topic/human_review" in result.tags
    assert result.key_points
    assert result.model_notes and "codex-mock" in result.model_notes


def test_local_llm_analysis_uses_extracted_text_and_fake_client(tmp_path):
    source = tmp_path / "notes.md"
    output = tmp_path / "extract" / "notes.md"
    output.parent.mkdir()
    output.write_text("# 隐私配置\n\n这里只是测试正文，不读取原始文件。", encoding="utf-8")
    fake = FakeLLMClient()

    results = analyze_extract_records(
        [
            {
                "path": str(source),
                "output_path": str(output),
                "status": "ok",
                "parser": "direct_text",
                "embedding_allowed": True,
            }
        ],
        analysis_method="local-llm",
        llm_config={
            "llm": {"mode": "local"},
            "local": {
                "enabled": True,
                "provider": "ollama",
                "model": "qwen2.5:7b",
                "endpoint": "http://localhost:11434",
            },
        },
        llm_client=fake,
        allowed_tags=["topic/privacy_policy", "document/note"],
    )

    result = results[0]
    assert result.status == "ok"
    assert result.analysis_method == "local-llm"
    assert result.title == "模型理解后的标题"
    assert result.tags == ["topic/privacy_policy", "document/note"]
    assert result.review_reason == "llm_semantic_reviewed"
    assert fake.requests and "测试正文" in fake.requests[0].text
    assert fake.requests[0].allowed_tags == ["topic/privacy_policy", "document/note"]


def test_local_llm_cli_with_enabled_config_writes_manifest_and_knowledge_index(
    tmp_path, monkeypatch
):
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n\nlocal llm source", encoding="utf-8")
    output = tmp_path / "extract" / "notes.md"
    output.parent.mkdir()
    output.write_text("# Notes\n\nprivacy policy and local llm text", encoding="utf-8")
    inventory_path = tmp_path / "inventory.sqlite"
    with Inventory(inventory_path) as inventory:
        inventory.upsert_entries([_scan_entry(source, access_policy="allow")])
        inventory.add_extract_results([_extract_result(source, output, status="ok")])

    llm_config = tmp_path / "llm.yaml"
    tags_config = tmp_path / "tags.yaml"
    _write_llm_config(llm_config, mode="local")
    _write_tags_config(tags_config)
    fake = FakeLLMClient()
    monkeypatch.setattr("pfkb.analyze.ConfiguredLLMClient", lambda config, method: fake)

    out_dir = tmp_path / "analysis"
    code, stdout, stderr = _run_cli(
        [
            "analyze",
            "--inventory",
            str(inventory_path),
            "--out",
            str(out_dir),
            "--method",
            "local-llm",
            "--llm-config",
            str(llm_config),
            "--tags-config",
            str(tags_config),
        ]
    )

    assert code == 0, stderr
    assert "method: local-llm" in stdout
    assert "ok: 1" in stdout
    assert len(fake.requests) == 1
    manifest = out_dir / "analysis-manifest.jsonl"
    index_jsonl = out_dir / "knowledge-index.jsonl"
    index_md = out_dir / "knowledge-index.md"
    assert manifest.exists()
    assert index_jsonl.exists()
    assert index_md.exists()
    manifest_records = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    index_records = [json.loads(line) for line in index_jsonl.read_text(encoding="utf-8").splitlines()]
    assert manifest_records[0]["analysis_method"] == "local-llm"
    assert manifest_records[0]["status"] == "ok"
    assert index_records[0]["analysis_method"] == "local-llm"


def test_cloud_llm_skips_without_policy_context_and_does_not_call_client(tmp_path):
    source = tmp_path / "allowed" / "notes.md"
    output = tmp_path / "extract" / "notes.md"
    output.parent.mkdir()
    output.write_text("# Cloud\n\nfixture", encoding="utf-8")
    fake = FakeLLMClient()

    results = analyze_extract_records(
        [
            {
                "path": str(source),
                "output_path": str(output),
                "status": "ok",
                "parser": "direct_text",
                "embedding_allowed": True,
            }
        ],
        analysis_method="cloud-llm",
        llm_config={
            "llm": {"mode": "cloud"},
            "cloud": {
                "enabled": True,
                "risk_acknowledged": True,
                "allowed_policies": ["allow"],
                "forbidden_policies": ["deny", "metadata_only", "no_embedding"],
                "allowed_paths": [(tmp_path / "allowed").as_posix()],
            },
        },
        llm_client=fake,
    )

    result = results[0]
    assert result.status == "skipped"
    assert result.review_reason == "cloud_missing_policy_context"
    assert fake.requests == []


def test_cloud_llm_requires_allowed_path_before_calling_client(tmp_path):
    source = tmp_path / "allowed" / "notes.md"
    output = tmp_path / "extract" / "notes.md"
    output.parent.mkdir(parents=True)
    output.write_text("# Cloud\n\nfixture", encoding="utf-8")
    fake = FakeLLMClient()

    results = analyze_extract_records(
        [
            {
                "path": str(source),
                "output_path": str(output),
                "status": "ok",
                "parser": "direct_text",
                "embedding_allowed": True,
                "access_policy": "allow",
            }
        ],
        analysis_method="cloud-llm",
        llm_config={
            "llm": {"mode": "cloud"},
            "cloud": {
                "enabled": True,
                "risk_acknowledged": True,
                "allowed_policies": ["allow"],
                "forbidden_policies": ["deny", "metadata_only", "no_embedding"],
                "allowed_paths": [(tmp_path / "allowed").as_posix()],
            },
        },
        llm_client=fake,
        allowed_tags=["topic/privacy_policy", "document/note"],
    )

    assert results[0].status == "ok"
    assert results[0].analysis_method == "cloud-llm"
    assert len(fake.requests) == 1


def test_cloud_llm_skips_for_forbidden_or_unauthorized_policies_without_client(tmp_path):
    allowed_root = tmp_path / "allowed"
    other_root = tmp_path / "other"
    allowed_root.mkdir()
    other_root.mkdir()
    cases = [
        (allowed_root / "contract.md", "no_embedding"),
        (allowed_root / "tax.md", "metadata_only"),
        (other_root / "notes.md", "allow"),
    ]
    records = []
    for source, access_policy in cases:
        output = tmp_path / "extract" / f"{source.stem}.md"
        output.parent.mkdir(exist_ok=True)
        output.write_text("# Cloud\n\nfixture", encoding="utf-8")
        records.append(
            {
                "path": str(source),
                "output_path": str(output),
                "status": "ok",
                "parser": "direct_text",
                "embedding_allowed": access_policy == "allow",
                "access_policy": access_policy,
            }
        )
    fake = FakeLLMClient()

    results = analyze_extract_records(
        records,
        analysis_method="cloud-llm",
        llm_config={
            "llm": {"mode": "cloud"},
            "cloud": {
                "enabled": True,
                "risk_acknowledged": True,
                "allowed_policies": ["allow"],
                "forbidden_policies": ["deny", "metadata_only", "no_embedding"],
                "allowed_paths": [allowed_root.as_posix()],
            },
        },
        llm_client=fake,
    )

    assert fake.requests == []
    assert [result.status for result in results] == ["skipped", "skipped", "skipped"]
    assert {result.review_reason for result in results} == {"cloud_not_authorized"}


def test_cloud_llm_cli_calls_fake_client_when_inventory_policy_and_path_are_allowed(
    tmp_path, monkeypatch
):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    source = allowed_root / "notes.md"
    source.write_text("# Notes\n\ncloud llm source", encoding="utf-8")
    output = tmp_path / "extract" / "notes.md"
    output.parent.mkdir()
    output.write_text("# Notes\n\ncloud allowed text", encoding="utf-8")
    inventory_path = tmp_path / "inventory.sqlite"
    with Inventory(inventory_path) as inventory:
        inventory.upsert_entries([_scan_entry(source, access_policy="allow")])
        inventory.add_extract_results([_extract_result(source, output, status="ok")])

    llm_config = tmp_path / "llm.yaml"
    tags_config = tmp_path / "tags.yaml"
    _write_llm_config(llm_config, mode="cloud", allowed_path=allowed_root)
    _write_tags_config(tags_config)
    fake = FakeLLMClient()
    monkeypatch.setattr("pfkb.analyze.ConfiguredLLMClient", lambda config, method: fake)

    out_dir = tmp_path / "analysis"
    code, stdout, stderr = _run_cli(
        [
            "analyze",
            "--inventory",
            str(inventory_path),
            "--out",
            str(out_dir),
            "--method",
            "cloud-llm",
            "--llm-config",
            str(llm_config),
            "--tags-config",
            str(tags_config),
        ]
    )

    assert code == 0, stderr
    assert "method: cloud-llm" in stdout
    assert "ok: 1" in stdout
    assert len(fake.requests) == 1
    manifest_records = [
        json.loads(line)
        for line in (out_dir / "analysis-manifest.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert manifest_records[0]["analysis_method"] == "cloud-llm"
    assert manifest_records[0]["status"] == "ok"


def test_classification_and_tags_use_path_and_content():
    assert classify_content_type("tests/test_policy.py", ".py") == "test"
    assert classify_content_type("configs/privacy.example.yaml", ".yaml") == "config"
    assert classify_content_type("src/pfkb/policy.py", ".py") == "code"

    tags = infer_tags("src/pfkb/cli.py", "argparse command scan extract inventory", "code")
    assert {"code", "cli", "scan", "extract", "inventory"} <= set(tags)


def test_analyze_cli_writes_knowledge_index_outputs(tmp_path):
    source = tmp_path / "README.md"
    output = tmp_path / "extract" / "README.md"
    output.parent.mkdir()
    output.write_text(
        "# Demo Knowledge Base\n\nPFKB scan extract analyze pipeline fixture.",
        encoding="utf-8",
    )
    failed = tmp_path / "failed.md"
    inventory_path = tmp_path / "inventory.sqlite"
    with Inventory(inventory_path) as inventory:
        inventory.add_extract_results(
            [
                _extract_result(source, output, status="ok"),
                _extract_result(failed, None, status="error"),
            ]
        )

    out_dir = tmp_path / "analysis"
    code, stdout, stderr = _run_cli(
        [
            "analyze",
            "--inventory",
            str(inventory_path),
            "--out",
            str(out_dir),
            "--limit",
            "20",
        ]
    )

    assert code == 0, stderr
    assert "knowledge_index_md" in stdout
    assert "ok: 1" in stdout

    manifest = out_dir / "analysis-manifest.jsonl"
    index_jsonl = out_dir / "knowledge-index.jsonl"
    index_md = out_dir / "knowledge-index.md"
    tag_index = out_dir / "tag-index.md"
    for path in (manifest, index_jsonl, index_md, tag_index):
        assert path.exists()

    records = [json.loads(line) for line in index_jsonl.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["title"] == "Demo Knowledge Base"
    assert records[0]["analysis_method"] == "rules"
    assert "confidence" in records[0]
    assert "needs_human_review" in records[0]
    assert "docs" in records[0]["tags"]
    assert "extract" in records[0]["tags"]
    index_text = index_md.read_text(encoding="utf-8")
    assert "# 知识索引" in index_text
    assert "当前版本是全本地规则版" in index_text
    assert "原始路径" in index_text
    assert "需要人工复核" in index_text
    assert "规则置信度" in index_text
    assert "摘要：" in index_text
    assert "failed.md" not in index_text
    assert "# 标签索引" in tag_index.read_text(encoding="utf-8")


def test_analyze_cli_writes_codex_mock_comparison(tmp_path):
    source = tmp_path / "docs" / "llm.md"
    output = tmp_path / "extract" / "llm.md"
    output.parent.mkdir()
    output.write_text(
        "# LLM Policy\n\nCloud allowed paths require risk acknowledgement and privacy review.",
        encoding="utf-8",
    )
    inventory_path = tmp_path / "inventory.sqlite"
    with Inventory(inventory_path) as inventory:
        inventory.add_extract_results([_extract_result(source, output, status="ok")])

    rules_dir = tmp_path / "rules"
    code, _stdout, stderr = _run_cli(
        [
            "analyze",
            "--inventory",
            str(inventory_path),
            "--out",
            str(rules_dir),
        ]
    )
    assert code == 0, stderr

    codex_dir = tmp_path / "codex"
    code, stdout, stderr = _run_cli(
        [
            "analyze",
            "--inventory",
            str(inventory_path),
            "--out",
            str(codex_dir),
            "--method",
            "codex-mock",
            "--compare-to",
            str(rules_dir / "analysis-manifest.jsonl"),
        ]
    )

    assert code == 0, stderr
    assert "method: codex-mock" in stdout
    assert "analysis_comparison_md" in stdout
    comparison = codex_dir / "analysis-comparison.md"
    assert comparison.exists()
    comparison_text = comparison.read_text(encoding="utf-8")
    assert "codex-mock" in (codex_dir / "knowledge-index.md").read_text(encoding="utf-8")
    assert "LLM" in comparison_text


def test_latest_analyzable_extracts_prefers_latest_usable_record(tmp_path):
    source = tmp_path / "notes.md"
    old_output = tmp_path / "extract" / "old.md"
    new_output = tmp_path / "extract" / "new.md"
    new_output.parent.mkdir()
    old_output.write_text("# Old\n", encoding="utf-8")
    new_output.write_text("# New\n", encoding="utf-8")

    with Inventory(tmp_path / "inventory.sqlite") as inventory:
        inventory.add_extract_results(
            [
                _extract_result(
                    source,
                    old_output,
                    status="ok",
                    created_at="2026-05-27T10:00:00+00:00",
                ),
                _extract_result(
                    source,
                    new_output,
                    status="up_to_date",
                    created_at="2026-05-27T11:00:00+00:00",
                ),
            ]
        )
        latest = inventory.latest_analyzable_extracts_by_path()

    assert latest[str(source)]["status"] == "up_to_date"
    assert latest[str(source)]["output_path"] == str(new_output)
