from __future__ import annotations

import builtins
import importlib
import os
from collections.abc import Iterable, Mapping
from enum import Enum
from pathlib import Path

import pytest


def _scan_module():
    try:
        return importlib.import_module("anyfile_wiki.scan")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected anyfile_wiki.scan to be importable for MVP0 scan tests: {exc}")


def _to_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        value = value.value
    elif hasattr(value, "value") and not isinstance(value, (str, bool, int, float)):
        value = value.value
    return str(value).split(".")[-1].lower().replace("-", "_").replace(" ", "_")


def _field(obj, *names):
    if isinstance(obj, Mapping):
        for name in names:
            if name in obj:
                return obj[name]
        return None

    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _kind(obj) -> str | None:
    raw = _field(obj, "action", "access_policy", "policy", "decision", "kind")
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
    }
    if kind in aliases:
        return aliases[kind]
    if kind in {"deny", "allow"}:
        return kind
    if _field(obj, "denied", "is_denied", "excluded", "is_excluded") is True:
        return "deny"
    if _field(obj, "metadata_only", "is_metadata_only") is True:
        return "metadata_only"
    if _field(obj, "no_embedding", "is_no_embedding") is True:
        return "no_embedding"
    if _field(obj, "allowed", "is_allowed") is True:
        return "allow"
    return kind


def _bool_field(obj, default: bool, *names) -> bool:
    raw = _field(obj, *names)
    if raw is None:
        return default
    return bool(raw)


def _allows_metadata(obj) -> bool:
    return _bool_field(
        obj,
        _kind(obj) in {"allow", "metadata_only", "no_embedding"},
        "record_metadata",
        "metadata_allowed",
        "can_record_metadata",
        "write_metadata",
    )


def _allows_content_read(obj) -> bool:
    return _bool_field(
        obj,
        _kind(obj) in {"allow", "no_embedding"},
        "read_content",
        "content_allowed",
        "can_read_content",
        "read_allowed",
        "should_read_content",
    )


def _allows_embedding(obj) -> bool:
    return _bool_field(
        obj,
        _kind(obj) == "allow",
        "embedding_allowed",
        "embed",
        "can_embed",
        "should_embed",
        "vector_index",
        "index_content",
    )


def _has_inline_content(obj) -> bool:
    content = _field(obj, "content", "text", "body", "raw_content", "document_text")
    return content not in (None, "")


def _path_value(obj):
    return _field(obj, "path", "file_path", "filepath", "name", "file")


def _flatten_records(obj) -> list:
    if obj is None:
        return []
    if isinstance(obj, Mapping):
        if _path_value(obj) is not None:
            return [obj]
        records = []
        for key in (
            "entries",
            "items",
            "records",
            "files",
            "results",
            "plan",
            "scanned",
        ):
            if key in obj:
                records.extend(_flatten_records(obj[key]))
        if records:
            return records
        for value in obj.values():
            records.extend(_flatten_records(value))
        return records
    if isinstance(obj, (str, bytes, Path)):
        return []
    if hasattr(obj, "__dict__"):
        if _path_value(obj) is not None:
            return [obj]
        return _flatten_records(vars(obj))
    if isinstance(obj, Iterable):
        records = []
        for item in obj:
            records.extend(_flatten_records(item))
        return records
    return []


def _norm_path(value) -> str:
    return str(Path(value)).replace("\\", "/").lower()


def _find_record(records: list, target: Path):
    wanted = _norm_path(target)
    for record in records:
        record_path = _path_value(record)
        if record_path is not None and _norm_path(record_path) == wanted:
            return record
    return None


class RecordingInventory:
    def __init__(self):
        self.records = []

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def recorder(*args, **kwargs):
            record = {"_method": name, **kwargs}
            if args:
                first = args[0]
                if isinstance(first, Mapping):
                    record.update(first)
                else:
                    record.setdefault("path", first)
                if len(args) > 1:
                    record["_args"] = args[1:]
            self.records.append(record)
            return record

        return recorder


class StubPolicyEngine:
    def __init__(self, by_name: Mapping[str, str] | None = None, default: str = "allow"):
        self.by_name = dict(by_name or {})
        self.default = default
        self.calls = []

    def decide(self, path, is_dir=False):
        path_obj = Path(path)
        self.calls.append({"path": path_obj, "is_dir": is_dir})
        action = self.by_name.get(path_obj.name, self.default)
        return {
            "path": path_obj,
            "action": action,
            "record_metadata": action != "deny",
            "read_content": action in {"allow", "no_embedding"},
            "embedding_allowed": action == "allow",
        }


def _collect_scan_result(result, inventory: RecordingInventory) -> list:
    return [*inventory.records, *_flatten_records(result)]


def _guard_content_reads(monkeypatch, watched_paths: set[Path]) -> list[str]:
    watched = {path.resolve() for path in watched_paths}
    attempts = []
    real_open = builtins.open
    real_path_open = Path.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes

    def is_watched(file) -> bool:
        try:
            return Path(file).resolve() in watched
        except TypeError:
            return False

    def guarded_open(file, *args, **kwargs):
        if is_watched(file):
            attempts.append(str(file))
            raise AssertionError(f"scan_paths must not read file content: {file}")
        return real_open(file, *args, **kwargs)

    def guarded_path_open(self, *args, **kwargs):
        if is_watched(self):
            attempts.append(str(self))
            raise AssertionError(f"scan_paths must not read file content: {self}")
        return real_path_open(self, *args, **kwargs)

    def guarded_read_text(self, *args, **kwargs):
        if is_watched(self):
            attempts.append(str(self))
            raise AssertionError(f"scan_paths must not read file content: {self}")
        return real_read_text(self, *args, **kwargs)

    def guarded_read_bytes(self, *args, **kwargs):
        if is_watched(self):
            attempts.append(str(self))
            raise AssertionError(f"scan_paths must not read file content: {self}")
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    return attempts


def test_scan_paths_dry_run_never_reads_file_content(tmp_path, monkeypatch):
    scan_mod = _scan_module()
    note = tmp_path / "notes.md"
    note.write_text("content that dry-run must not read", encoding="utf-8")
    attempts = _guard_content_reads(monkeypatch, {note})
    inventory = RecordingInventory()

    result = scan_mod.scan_paths(
        [tmp_path],
        StubPolicyEngine(default="allow"),
        inventory=inventory,
        dry_run=True,
    )

    records = _collect_scan_result(result, inventory)
    record = _find_record(records, note)
    assert attempts == []
    assert record is not None
    assert _kind(record) == "allow"
    assert _has_inline_content(record) is False


def test_scan_paths_metadata_only_records_metadata_without_content_read(
    tmp_path, monkeypatch
):
    scan_mod = _scan_module()
    finance_file = tmp_path / "tax-return.txt"
    finance_file.write_text("sensitive financial details", encoding="utf-8")
    attempts = _guard_content_reads(monkeypatch, {finance_file})
    inventory = RecordingInventory()

    result = scan_mod.scan_paths(
        [finance_file],
        StubPolicyEngine({"tax-return.txt": "metadata_only"}),
        inventory=inventory,
        dry_run=False,
    )

    records = _collect_scan_result(result, inventory)
    record = _find_record(records, finance_file)
    assert attempts == []
    assert record is not None
    assert _kind(record) == "metadata_only"
    assert _allows_metadata(record) is True
    assert _allows_content_read(record) is False
    assert _has_inline_content(record) is False


def test_scan_paths_preserves_policy_actions_in_plan(tmp_path):
    scan_mod = _scan_module()
    allowed = tmp_path / "notes.md"
    metadata_only = tmp_path / "tax-return.txt"
    no_embedding = tmp_path / "contract.md"
    denied = tmp_path / "private-key.pem"
    for file_path in (allowed, metadata_only, no_embedding, denied):
        file_path.write_text(file_path.name, encoding="utf-8")
    inventory = RecordingInventory()

    result = scan_mod.scan_paths(
        [tmp_path],
        StubPolicyEngine(
            {
                "notes.md": "allow",
                "tax-return.txt": "metadata_only",
                "contract.md": "no_embedding",
                "private-key.pem": "deny",
            }
        ),
        inventory=inventory,
        dry_run=True,
    )

    records = _collect_scan_result(result, inventory)
    allowed_record = _find_record(records, allowed)
    metadata_record = _find_record(records, metadata_only)
    no_embedding_record = _find_record(records, no_embedding)
    denied_record = _find_record(records, denied)

    assert allowed_record is not None
    assert _kind(allowed_record) == "allow"
    assert _allows_content_read(allowed_record) is True
    assert _allows_embedding(allowed_record) is True

    assert metadata_record is not None
    assert _kind(metadata_record) == "metadata_only"
    assert _allows_metadata(metadata_record) is True
    assert _allows_content_read(metadata_record) is False

    assert no_embedding_record is not None
    assert _kind(no_embedding_record) == "no_embedding"
    assert _allows_content_read(no_embedding_record) is True
    assert _allows_embedding(no_embedding_record) is False

    assert denied_record is not None
    assert _kind(denied_record) == "deny"


def test_scan_paths_denies_symlink_files_by_default(tmp_path):
    scan_mod = _scan_module()
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("secret target", encoding="utf-8")
    scan_root = tmp_path / "scan-root"
    scan_root.mkdir()
    link = scan_root / "linked-secret.txt"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    result = scan_mod.scan_paths(
        [scan_root],
        StubPolicyEngine(default="allow"),
        dry_run=True,
        follow_symlinks=False,
    )

    records = _flatten_records(result)
    link_record = _find_record(records, link)
    assert link_record is not None
    assert _kind(link_record) == "deny"
    assert _allows_content_read(link_record) is False
    assert _field(link_record, "extra")["is_symlink"] is True
