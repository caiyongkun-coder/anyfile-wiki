from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from pfkb.cli import main as cli_main
from pfkb.html import load_browser_records, render_knowledge_browser_html, write_knowledge_browser_html


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


def _record(**overrides) -> dict:
    record = {
        "path": "C:/Users/me/Documents/privacy-note.md",
        "output_path": "data/extract/text/privacy-note.md",
        "status": "ok",
        "title": "隐私配置笔记",
        "summary": "这份文件记录了本地优先、云端授权和目录白名单的策略。",
        "tags": ["topic/privacy_policy", "document/note"],
        "primary_tag": "topic/privacy_policy",
        "content_type": "docs",
        "extension": ".md",
        "parser": "direct_text",
        "embedding_allowed": True,
        "char_count": 120,
        "word_count": 48,
        "line_count": 6,
        "analyzed_at": "2026-05-27T00:00:00+00:00",
        "source_extract_status": "ok",
        "analysis_method": "codex-mock",
        "confidence": 0.88,
        "needs_human_review": True,
        "review_reason": "codex_mock_semantic_reviewed",
        "rule_title": "privacy-note.md",
        "rule_summary": "规则版摘要",
        "rule_tags": ["docs", "privacy"],
        "key_points": ["识别隐私策略", "保留规则版标签"],
        "model_notes": "fixture",
    }
    record.update(overrides)
    return record


def _tags_config() -> dict:
    return {
        "dimensions": [
            {"id": "topic", "zh": "主题"},
            {"id": "document", "zh": "文档形态"},
        ],
        "tags": [
            {
                "id": "topic/privacy_policy",
                "zh": "隐私策略",
                "en": "Privacy policy",
                "dimension": "topic",
            },
            {
                "id": "document/note",
                "zh": "笔记",
                "en": "Note",
                "dimension": "document",
            },
        ],
    }


def test_render_knowledge_browser_html_uses_chinese_ui_and_embedded_data():
    html = render_knowledge_browser_html([_record()], tags_config=_tags_config(), source_path="analysis.jsonl")

    assert "PFKB 资产浏览" in html
    assert "标签树" in html
    assert "文件列表" in html
    assert "文件详情" in html
    assert "搜索文件名、路径、摘要或标签" in html
    assert "需要复核" in html
    assert "隐私策略" in html
    assert "topic/privacy_policy" in html


def test_render_knowledge_browser_html_escapes_script_endings_inside_json():
    html = render_knowledge_browser_html(
        [_record(title="关闭 </script> 标签")],
        tags_config=_tags_config(),
    )

    assert "关闭 <\\/script> 标签" in html
    assert "关闭 </script> 标签" not in html


def test_write_knowledge_browser_html_creates_static_asset_browser(tmp_path):
    out_dir = tmp_path / "html"
    outputs = write_knowledge_browser_html([_record()], out_dir, tags_config=_tags_config())

    html_path = outputs["knowledge_index_html"]
    assert html_path == out_dir / "knowledge-index.html"
    assert html_path.exists()
    text = html_path.read_text(encoding="utf-8")
    assert "PFKB_DATA" in text
    assert "复制路径" in text


def test_load_browser_records_filters_non_ok_analysis_records(tmp_path):
    analysis = tmp_path / "analysis-manifest.jsonl"
    skipped = _record(path="C:/private.md", status="skipped", title="跳过文件")
    analysis.write_text(
        "\n".join(
            [
                json.dumps(_record(), ensure_ascii=False),
                json.dumps(skipped, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = load_browser_records(analysis)

    assert len(records) == 1
    assert records[0]["title"] == "隐私配置笔记"


def test_html_cli_writes_browser_file(tmp_path):
    analysis = tmp_path / "knowledge-index.jsonl"
    analysis.write_text(json.dumps(_record(), ensure_ascii=False) + "\n", encoding="utf-8")
    tags = tmp_path / "tags.yaml"
    tags.write_text(
        "\n".join(
            [
                "version: 1",
                "dimensions:",
                "  - id: topic",
                "    zh: 主题",
                "tags:",
                "  - id: topic/privacy_policy",
                "    zh: 隐私策略",
                "    en: Privacy policy",
                "    dimension: topic",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "site"
    code, stdout, stderr = _run_cli(
        [
            "html",
            "--analysis",
            str(analysis),
            "--tags-config",
            str(tags),
            "--out",
            str(out_dir),
        ]
    )

    assert code == 0, stderr
    assert "records: 1" in stdout
    assert "knowledge_index_html" in stdout
    assert (out_dir / "knowledge-index.html").exists()
