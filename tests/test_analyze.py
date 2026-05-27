from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from pfkb.analyze import analyze_extract_records, classify_content_type, infer_tags
from pfkb.cli import main as cli_main
from pfkb.inventory import Inventory
from pfkb.parse import ExtractResult


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
    assert "docs" in records[0]["tags"]
    assert "extract" in records[0]["tags"]
    assert "failed.md" not in index_md.read_text(encoding="utf-8")


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
