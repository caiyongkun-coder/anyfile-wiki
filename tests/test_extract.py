from __future__ import annotations

import json
from pathlib import Path
import sys
import types

from anyfile_wiki import parse as parse_mod
from anyfile_wiki.inventory import Inventory
from anyfile_wiki.parse import build_parse_jobs_from_records, extract_jobs, write_manifest
from anyfile_wiki.policy import PolicyEngine
from anyfile_wiki.scan import scan_paths


def test_parse_jobs_from_inventory_records_are_policy_gated(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    allowed = root / "allowed.md"
    metadata = root / "metadata.md"
    denied = root / "denied.md"
    for path in (allowed, metadata, denied):
        path.write_text(path.name, encoding="utf-8")

    engine = PolicyEngine(
        {
            "deny": {"paths": [str(denied)]},
            "metadata_only": {"paths": [str(metadata)]},
            "allow": {"paths": [str(root)]},
        }
    )
    result = scan_paths([root], engine)
    inventory_path = tmp_path / "inventory.sqlite"
    with Inventory(inventory_path) as inventory:
        inventory.upsert_entries(result.entries)
        records = inventory.list_files(limit=20, include_dirs=False)

    jobs = build_parse_jobs_from_records(records)
    assert [job.path.name for job in jobs] == ["allowed.md"]


def test_direct_text_extract_writes_artifact_and_manifest(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Hello\n\nlocal knowledge", encoding="utf-8")
    job_records = [
        {
            "path": str(source),
            "extension": ".md",
            "is_dir": False,
            "is_read_allowed": True,
            "is_extract_allowed": True,
            "is_embedding_allowed": True,
            "access_policy": "allow",
            "policy_reason": "test",
        }
    ]
    jobs = build_parse_jobs_from_records(job_records)
    output_dir = tmp_path / "extract"
    results = extract_jobs(jobs, output_dir)

    assert len(results) == 1
    result = results[0]
    assert result.status == "ok"
    assert result.parser == "direct_text"
    assert result.output_path is not None
    assert Path(result.output_path).read_text(encoding="utf-8") == "# Hello\n\nlocal knowledge"

    manifest = tmp_path / "manifest.jsonl"
    write_manifest(results, manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8").strip())
    assert payload["path"] == str(source)
    assert payload["status"] == "ok"
    assert payload["output_path"] == result.output_path


def test_markitdown_job_skips_gracefully_when_dependency_missing(tmp_path, monkeypatch):
    source = tmp_path / "paper.pdf"
    source.write_text("not really pdf", encoding="utf-8")
    job_records = [
        {
            "path": str(source),
            "extension": ".pdf",
            "is_dir": False,
            "is_read_allowed": True,
            "is_extract_allowed": True,
            "is_embedding_allowed": True,
            "access_policy": "allow",
            "policy_reason": "test",
        }
    ]
    jobs = build_parse_jobs_from_records(job_records)

    real_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name == "markitdown":
            raise ModuleNotFoundError("markitdown")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    results = extract_jobs(jobs, tmp_path / "extract")

    assert results[0].parser == "markitdown"
    assert results[0].status == "skipped"
    assert "markitdown unavailable" in (results[0].error or "")


def test_image_extract_uses_ocr_parser(tmp_path, monkeypatch):
    source = tmp_path / "contract.jpg"
    source.write_bytes(b"fake image bytes")
    job_records = [
        {
            "path": str(source),
            "extension": ".jpg",
            "is_dir": False,
            "is_read_allowed": True,
            "is_extract_allowed": True,
            "is_embedding_allowed": True,
            "access_policy": "allow",
            "policy_reason": "test",
        }
    ]

    class FakeRapidOCR:
        def __call__(self, path: str):
            return types.SimpleNamespace(txts=("合同编号", "还款计划"), scores=(0.91, 0.89))

    monkeypatch.setitem(sys.modules, "rapidocr", types.SimpleNamespace(RapidOCR=FakeRapidOCR))

    results = extract_jobs(build_parse_jobs_from_records(job_records), tmp_path / "extract")

    assert results[0].parser == "ocr"
    assert results[0].status == "ok"
    assert results[0].output_path is not None
    text = Path(results[0].output_path).read_text(encoding="utf-8")
    assert "parser: rapidocr" in text
    assert "合同编号" in text


def test_image_extract_skips_when_ocr_dependency_missing(tmp_path, monkeypatch):
    source = tmp_path / "contract.png"
    source.write_bytes(b"fake image bytes")
    job_records = [
        {
            "path": str(source),
            "extension": ".png",
            "is_dir": False,
            "is_read_allowed": True,
            "is_extract_allowed": True,
            "is_embedding_allowed": True,
            "access_policy": "allow",
            "policy_reason": "test",
        }
    ]
    monkeypatch.setitem(sys.modules, "rapidocr", None)

    results = extract_jobs(build_parse_jobs_from_records(job_records), tmp_path / "extract")

    assert results[0].parser == "ocr"
    assert results[0].status == "skipped"
    assert "rapidocr unavailable" in (results[0].error or "")


def test_xlsx_extract_uses_spreadsheet_preview_parser(tmp_path, monkeypatch):
    source = tmp_path / "budget.xlsx"
    source.write_bytes(b"fake xlsx bytes")
    job_records = [
        {
            "path": str(source),
            "extension": ".xlsx",
            "is_dir": False,
            "is_read_allowed": True,
            "is_extract_allowed": True,
            "is_embedding_allowed": True,
            "access_policy": "allow",
            "policy_reason": "test",
        }
    ]

    class FakeSheet:
        max_row = 2
        max_column = 2

        def iter_rows(self, max_row: int, max_col: int, values_only: bool):
            return iter([("科目", "金额"), ("贷款", 123)])

    class FakeWorkbook:
        sheetnames = ["预算"]

        def __getitem__(self, name: str):
            return FakeSheet()

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "openpyxl", types.SimpleNamespace(load_workbook=lambda *args, **kwargs: FakeWorkbook()))

    results = extract_jobs(build_parse_jobs_from_records(job_records), tmp_path / "extract")

    assert results[0].parser == "spreadsheet"
    assert results[0].status == "ok"
    assert results[0].output_path is not None
    text = Path(results[0].output_path).read_text(encoding="utf-8")
    assert "parser: spreadsheet_preview" in text
    assert "工作表: 预算" in text
    assert "贷款" in text


def test_direct_text_extract_skips_files_above_safety_limit(tmp_path, monkeypatch):
    source = tmp_path / "large.md"
    source.write_text("abcdef", encoding="utf-8")
    monkeypatch.setattr(parse_mod, "MAX_DIRECT_TEXT_BYTES", 4, raising=False)
    job_records = [
        {
            "path": str(source),
            "extension": ".md",
            "is_dir": False,
            "is_read_allowed": True,
            "is_extract_allowed": True,
            "is_embedding_allowed": True,
            "access_policy": "allow",
            "policy_reason": "test",
            "size_bytes": source.stat().st_size,
            "mtime": source.stat().st_mtime,
        }
    ]

    results = parse_mod.extract_jobs(build_parse_jobs_from_records(job_records), tmp_path / "extract")

    assert results[0].parser == "direct_text"
    assert results[0].status == "skipped"
    assert results[0].output_path is None
    assert "too large" in (results[0].error or "")
