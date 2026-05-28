from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from anyfile_wiki.assets import build_asset_index, write_asset_outputs_from_files
from anyfile_wiki.cli import main as cli_main


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


def _analysis(path: str, **overrides) -> dict:
    record = {
        "path": path,
        "output_path": "data/extract/text/file.md",
        "status": "ok",
        "title": Path(path).name,
        "summary": f"{Path(path).name} summary",
        "tags": ["document"],
        "primary_tag": "document",
        "content_type": "document",
        "extension": Path(path).suffix,
        "parser": "direct_text",
        "embedding_allowed": True,
        "char_count": 80,
        "word_count": 20,
        "line_count": 3,
        "analyzed_at": "2026-05-28T00:00:00+00:00",
        "source_extract_status": "ok",
        "analysis_method": "rules",
        "confidence": 0.4,
        "needs_human_review": True,
        "review_reason": "rules_only_needs_semantic_review",
        "rule_title": Path(path).name,
        "rule_summary": "rule summary",
        "rule_tags": ["document"],
        "key_points": [],
        "model_notes": "",
        "error": "",
    }
    record.update(overrides)
    return record


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")


def test_build_asset_index_applies_review_actions_and_keeps_review_only_assets():
    analysis_records = [
        _analysis("C:/docs/project-note.md"),
        _analysis("C:/docs/short-note.txt"),
        _analysis("C:/docs/manual.md"),
    ]
    review_items = [
        {
            "path": "C:/docs/project-note.md",
            "category": "rules_only_or_low_confidence",
            "severity": "medium",
            "reason": "rules result needs review",
            "action": "review",
            "tags": ["document"],
        },
        {
            "path": "C:/docs/short-note.txt",
            "category": "rules_only_or_low_confidence",
            "severity": "medium",
            "reason": "rules result needs review",
            "action": "review",
            "tags": ["document"],
        },
        {
            "path": "C:/docs/private-key.pem",
            "category": "policy_blocked",
            "severity": "high",
            "reason": "privacy policy denies reading",
            "action": "keep blocked",
            "access_policy": "deny",
        },
        {
            "path": "C:/docs/mock-design.psd",
            "category": "unsupported_format",
            "severity": "medium",
            "reason": "unsupported parser",
            "action": "review later",
        },
    ]
    actions = [
        {
            "path": "C:/docs/project-note.md",
            "action": "add_to_ignore_candidates",
            "title": "加入忽略候选",
            "source_decision": "ignore",
            "category": "rules_only_or_low_confidence",
            "severity": "medium",
            "manual_tags": ["topic/test_coverage"],
            "privacy_level": "local_metadata",
            "requires_confirmation": True,
            "next_step": "等待确认后再建议加入忽略配置。",
        },
        {
            "path": "C:/docs/short-note.txt",
            "action": "keep_private_metadata_only",
            "title": "保持隐私",
            "source_decision": "keep_private",
            "category": "rules_only_or_low_confidence",
            "severity": "medium",
            "privacy_level": "private",
            "requires_confirmation": False,
        },
        {
            "path": "C:/docs/manual.md",
            "action": "apply_manual_metadata",
            "title": "应用人工整理",
            "source_decision": "mark_manual",
            "category": "rules_only_or_low_confidence",
            "severity": "medium",
            "manual_tags": ["topic/semantic_analysis"],
            "privacy_level": "local_metadata",
            "requires_confirmation": False,
        },
        {
            "path": "C:/docs/private-key.pem",
            "action": "propose_cloud_llm_authorization",
            "title": "云端候选",
            "source_decision": "allow_cloud_llm",
            "category": "policy_blocked",
            "severity": "high",
            "privacy_level": "cloud_candidate",
            "requires_confirmation": True,
        },
        {
            "path": "C:/docs/mock-design.psd",
            "action": "defer_review",
            "title": "稍后复核",
            "source_decision": "later",
            "category": "unsupported_format",
            "severity": "medium",
            "privacy_level": "local_metadata",
            "requires_confirmation": False,
        },
    ]

    records = build_asset_index(analysis_records, actions, review_items, generated_at="2026-05-28T00:00:00+00:00")
    by_name = {Path(record["path"]).name: record for record in records}

    assert len(records) == 5
    assert by_name["project-note.md"]["asset_status"] == "ignore_candidate"
    assert by_name["project-note.md"]["review_requires_confirmation"] is True
    assert "topic/test_coverage" in by_name["project-note.md"]["tags"]
    assert "workflow/waiting_review" in by_name["project-note.md"]["tags"]
    assert by_name["short-note.txt"]["asset_status"] == "private_metadata_only"
    assert by_name["short-note.txt"]["needs_human_review"] is False
    assert by_name["manual.md"]["asset_status"] == "manual_reviewed"
    assert by_name["manual.md"]["accepted_tags"] == by_name["manual.md"]["tags"]
    assert "topic/semantic_analysis" in by_name["manual.md"]["manual_tags"]
    assert by_name["private-key.pem"]["asset_source"] == "review_only"
    assert by_name["private-key.pem"]["asset_status"] == "cloud_authorization_conflict"
    assert by_name["private-key.pem"]["review_warning"]
    assert "sensitivity/credential" in by_name["private-key.pem"]["tags"]
    assert by_name["mock-design.psd"]["asset_source"] == "review_only"
    assert by_name["mock-design.psd"]["asset_status"] == "deferred"


def test_write_asset_outputs_from_files_refreshes_agent_json_markdown_and_html(tmp_path):
    analysis_path = tmp_path / "run" / "analyze" / "knowledge-index.jsonl"
    actions_path = tmp_path / "run" / "review" / "next-actions.jsonl"
    review_items_path = tmp_path / "run" / "review" / "human-review.jsonl"
    _write_jsonl(analysis_path, [_analysis("C:/docs/manual.md")])
    _write_jsonl(
        actions_path,
        [
            {
                "path": "C:/docs/manual.md",
                "action": "apply_manual_metadata",
                "title": "应用人工整理",
                "source_decision": "mark_manual",
                "category": "rules_only_or_low_confidence",
                "severity": "medium",
                "manual_tags": ["topic/semantic_analysis"],
                "privacy_level": "local_metadata",
                "requires_confirmation": False,
                "next_step": "使用人工标签作为已确认结果。",
            }
        ],
    )
    _write_jsonl(
        review_items_path,
        [
            {
                "path": "C:/docs/manual.md",
                "category": "rules_only_or_low_confidence",
                "severity": "medium",
                "reason": "rules result needs review",
                "action": "review",
                "tags": ["document"],
            }
        ],
    )

    outputs = write_asset_outputs_from_files(
        analysis_path=analysis_path,
        actions_path=actions_path,
        review_items_path=review_items_path,
        output_dir=tmp_path / "run" / "assets",
        html_dir=tmp_path / "run" / "html",
        tags_config={
            "dimensions": [{"id": "topic", "zh": "主题"}],
            "tags": [
                {
                    "id": "topic/semantic_analysis",
                    "zh": "内容理解",
                    "en": "Semantic analysis",
                    "dimension": "topic",
                }
            ],
        },
    )

    assert outputs["asset_index_jsonl"].exists()
    assert outputs["asset_index_md"].exists()
    assert outputs["knowledge_index_html"].exists()
    asset_record = json.loads(outputs["asset_index_jsonl"].read_text(encoding="utf-8").splitlines()[0])
    assert asset_record["asset_status"] == "manual_reviewed"
    assert "topic/semantic_analysis" in asset_record["tags"]
    markdown = outputs["asset_index_md"].read_text(encoding="utf-8")
    assert "数据资产索引" in markdown
    assert "人工整理" in markdown
    html = outputs["knowledge_index_html"].read_text(encoding="utf-8")
    assert "资产状态 / Asset status" in html
    assert "人工批复 / Human decision" in html
    assert "topic/semantic_analysis" in html


def test_assets_cli_writes_closed_loop_outputs(tmp_path):
    analysis_path = tmp_path / "knowledge-index.jsonl"
    actions_path = tmp_path / "next-actions.jsonl"
    _write_jsonl(analysis_path, [_analysis("C:/docs/confirmed.md", needs_human_review=True)])
    _write_jsonl(
        actions_path,
        [
            {
                "path": "C:/docs/confirmed.md",
                "action": "accept_current_analysis",
                "title": "确认当前分析",
                "source_decision": "confirm_current",
                "category": "rules_only_or_low_confidence",
                "severity": "low",
                "privacy_level": "local_metadata",
                "requires_confirmation": False,
            }
        ],
    )
    out_dir = tmp_path / "assets"
    html_dir = tmp_path / "html"

    code, stdout, stderr = _run_cli(
        [
            "assets",
            "--analysis",
            str(analysis_path),
            "--actions",
            str(actions_path),
            "--out",
            str(out_dir),
            "--html-out",
            str(html_dir),
        ]
    )

    assert code == 0, stderr
    assert "records: 1" in stdout
    assert "asset_index_jsonl" in stdout
    assert (out_dir / "asset-index.jsonl").exists()
    assert (html_dir / "knowledge-index.html").exists()
    record = json.loads((out_dir / "asset-index.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["asset_status"] == "confirmed"
    assert record["needs_human_review"] is False
