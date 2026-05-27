from __future__ import annotations

import json
from pathlib import Path

from pfkb.inventory import Inventory
from pfkb.parse import build_parse_jobs_from_records, extract_jobs, write_manifest
from pfkb.policy import PolicyEngine
from pfkb.scan import scan_paths


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
