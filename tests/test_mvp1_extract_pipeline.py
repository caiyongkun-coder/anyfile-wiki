from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

from pfkb.cli import main as cli_main
from pfkb.inventory import Inventory
from pfkb.parse import (
    ParseJob,
    build_parse_jobs_from_records,
    extract_jobs,
    write_manifest,
)
from pfkb.policy import AccessDecision
from pfkb.scan import ScanEntry


def _decision(
    path: Path,
    access_policy: str,
    *,
    is_read_allowed: bool | None = None,
    is_extract_allowed: bool | None = None,
) -> AccessDecision:
    is_excluded = access_policy == "deny"
    default_read = access_policy in {"allow", "no_embedding"}
    read_allowed = default_read if is_read_allowed is None else is_read_allowed
    extract_allowed = read_allowed if is_extract_allowed is None else is_extract_allowed
    return AccessDecision(
        path=path.resolve().as_posix(),
        is_dir=False,
        access_policy=access_policy,
        policy_source=f"test.{access_policy}",
        reason=f"{access_policy} fixture",
        is_read_allowed=False if is_excluded else read_allowed,
        is_extract_allowed=False if is_excluded else extract_allowed,
        is_index_allowed=not is_excluded and access_policy != "metadata_only",
        is_embedding_allowed=access_policy == "allow",
        metadata_only=access_policy == "metadata_only",
        is_excluded=is_excluded,
    )


def _entry(
    path: Path,
    access_policy: str,
    *,
    is_read_allowed: bool | None = None,
    is_extract_allowed: bool | None = None,
    is_dir: bool = False,
) -> ScanEntry:
    if is_dir:
        path.mkdir(exist_ok=True)
        size = None
    else:
        path.write_text(f"fixture for {path.name}", encoding="utf-8")
        size = path.stat().st_size
    return ScanEntry(
        path=str(path),
        name=path.name,
        extension=path.suffix.lower(),
        is_dir=is_dir,
        exists_now=True,
        size_bytes=size,
        mtime=1.0,
        ctime=1.0,
        decision=_decision(
            path,
            access_policy,
            is_read_allowed=is_read_allowed,
            is_extract_allowed=is_extract_allowed,
        ),
        last_seen_at=f"2026-05-27T12:00:0{len(path.name) % 10}+00:00",
        extra={"fixture": "mvp1"},
    )


def _seed_inventory(tmp_path: Path, entries: list[ScanEntry]) -> Path:
    inventory_path = tmp_path / "inventory.sqlite"
    with Inventory(inventory_path) as inventory:
        assert inventory.upsert_entries(entries) == len(entries)
    return inventory_path


def _manifest_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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


def _guard_content_reads(monkeypatch, watched_paths: set[Path]) -> list[str]:
    watched = {path.resolve() for path in watched_paths}
    attempts: list[str] = []
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes
    real_open = Path.open

    def is_watched(path: Path) -> bool:
        return path.resolve() in watched

    def guarded_read_text(self: Path, *args, **kwargs):
        if is_watched(self):
            attempts.append(str(self))
            raise AssertionError(f"extract must not read policy-blocked content: {self}")
        return real_read_text(self, *args, **kwargs)

    def guarded_read_bytes(self: Path, *args, **kwargs):
        if is_watched(self):
            attempts.append(str(self))
            raise AssertionError(f"extract must not read policy-blocked content: {self}")
        return real_read_bytes(self, *args, **kwargs)

    def guarded_open(self: Path, *args, **kwargs):
        if is_watched(self):
            attempts.append(str(self))
            raise AssertionError(f"extract must not open policy-blocked content: {self}")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    monkeypatch.setattr(Path, "open", guarded_open)
    return attempts


def test_inventory_records_generate_jobs_only_when_read_and_extract_allowed(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    entries = [
        _entry(root / "allowed.md", "allow"),
        _entry(root / "no-embedding.txt", "no_embedding"),
        _entry(root / "metadata-only.md", "metadata_only"),
        _entry(root / "denied.md", "deny"),
        _entry(root / "read-but-no-extract.md", "allow", is_extract_allowed=False),
        _entry(root / "extract-but-no-read.md", "allow", is_read_allowed=False),
        _entry(root / "folder", "allow", is_dir=True),
    ]
    inventory_path = _seed_inventory(tmp_path, entries)

    with Inventory(inventory_path) as inventory:
        records = inventory.list_files(limit=20)
    jobs = build_parse_jobs_from_records(records)
    by_name = {job.path.name: job for job in jobs}

    assert set(by_name) == {"allowed.md", "no-embedding.txt"}
    assert by_name["allowed.md"].parser == "direct_text"
    assert by_name["allowed.md"].embedding_allowed is True
    assert by_name["no-embedding.txt"].parser == "direct_text"
    assert by_name["no-embedding.txt"].embedding_allowed is False


def test_direct_text_extract_writes_markdown_artifacts_and_manifest_jsonl(tmp_path):
    notes = tmp_path / "notes.txt"
    guide = tmp_path / "guide.md"
    notes.write_text("plain text note\n", encoding="utf-8")
    guide.write_text("# Guide\n\nmarkdown body\n", encoding="utf-8")
    output_dir = tmp_path / "extract"
    manifest_path = output_dir / "extract-manifest.jsonl"

    results = extract_jobs(
        [
            ParseJob(notes, "direct_text", "allow fixture", True),
            ParseJob(guide, "direct_text", "allow fixture", True),
        ],
        output_dir,
    )
    write_manifest(results, manifest_path)

    assert [result.status for result in results] == ["ok", "ok"]
    artifact_text = {
        Path(result.path).name: Path(str(result.output_path)).read_text(encoding="utf-8")
        for result in results
    }
    assert artifact_text["notes.txt"] == "plain text note\n"
    assert artifact_text["guide.md"] == "# Guide\n\nmarkdown body\n"
    assert all(Path(str(result.output_path)).suffix == ".md" for result in results)

    records = _manifest_records(manifest_path)
    assert len(records) == 2
    for record in records:
        assert {"path", "parser", "status", "output_path", "error"} <= set(record)
        assert record["parser"] == "direct_text"
        assert record["status"] == "ok"
        assert record["output_path"]
        assert record["error"] is None


def test_extract_cli_reads_inventory_writes_manifest_and_never_reads_blocked_files(
    tmp_path, monkeypatch
):
    root = tmp_path / "root"
    root.mkdir()
    allowed = root / "allowed.md"
    no_embedding = root / "summary.txt"
    metadata_only = root / "metadata-only.md"
    denied = root / "denied.md"
    inventory_path = _seed_inventory(
        tmp_path,
        [
            _entry(allowed, "allow"),
            _entry(no_embedding, "no_embedding"),
            _entry(metadata_only, "metadata_only"),
            _entry(denied, "deny"),
        ],
    )
    attempts = _guard_content_reads(monkeypatch, {metadata_only, denied})
    output_dir = tmp_path / "extract"
    manifest_path = output_dir / "manifest.jsonl"

    code, stdout, stderr = _run_cli(
        [
            "extract",
            "--inventory",
            str(inventory_path),
            "--out",
            str(output_dir),
            "--manifest",
            str(manifest_path),
            "--limit",
            "20",
        ]
    )

    assert code == 0, stderr
    assert attempts == []
    assert "manifest:" in stdout
    records = _manifest_records(manifest_path)
    by_name = {Path(record["path"]).name: record for record in records}
    assert set(by_name) == {"allowed.md", "summary.txt"}
    for record in by_name.values():
        assert record["status"] == "ok"
        assert record["parser"] == "direct_text"
        assert record["output_path"]
        assert Path(record["output_path"]).exists()
    assert "metadata-only.md" not in stdout
    assert "denied.md" not in stdout


def test_markitdown_jobs_skip_gracefully_when_optional_dependency_is_missing(
    tmp_path, monkeypatch
):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 placeholder")
    monkeypatch.setitem(sys.modules, "markitdown", None)

    result = extract_jobs(
        [ParseJob(pdf, "markitdown", "allow fixture", True)],
        tmp_path / "extract",
    )[0]

    assert result.path == str(pdf)
    assert result.parser == "markitdown"
    assert result.status == "skipped"
    assert result.output_path is None
    assert result.error is not None
    assert "markitdown" in result.error.lower()
