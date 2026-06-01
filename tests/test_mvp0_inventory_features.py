from __future__ import annotations

import contextlib
import importlib
import io
import json
import re
from collections.abc import Iterable, Mapping
from enum import Enum
from pathlib import Path

import pytest

from anyfile_wiki.policy import AccessDecision
from anyfile_wiki.scan import ScanEntry, ScanResult, ScanStats


POLICIES = ("allow", "metadata_only", "no_embedding", "deny")


def _inventory_module():
    try:
        return importlib.import_module("anyfile_wiki.inventory")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected anyfile_wiki.inventory to be importable: {exc}")


def _cli_module():
    try:
        return importlib.import_module("anyfile_wiki.cli")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected anyfile_wiki.cli to be importable: {exc}")


def _report_module():
    try:
        return importlib.import_module("anyfile_wiki.report")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected anyfile_wiki.report to be importable: {exc}")


def _roots_module():
    try:
        return importlib.import_module("anyfile_wiki.roots")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Expected anyfile_wiki.roots to expose candidate root discovery: {exc}")


def _decision(path: Path, access_policy: str) -> AccessDecision:
    is_excluded = access_policy == "deny"
    is_read_allowed = access_policy in {"allow", "no_embedding"}
    return AccessDecision(
        path=path.resolve().as_posix(),
        is_dir=False,
        access_policy=access_policy,
        policy_source=f"test.{access_policy}",
        reason=f"{access_policy} fixture",
        is_read_allowed=False if is_excluded else is_read_allowed,
        is_extract_allowed=False if is_excluded else is_read_allowed,
        is_index_allowed=not is_excluded and access_policy != "metadata_only",
        is_embedding_allowed=access_policy == "allow",
        metadata_only=access_policy == "metadata_only",
        is_excluded=is_excluded,
    )


def _entry(root: Path, name: str, access_policy: str, last_seen_at: str) -> ScanEntry:
    path = root / name
    return ScanEntry(
        path=str(path),
        name=path.name,
        extension=path.suffix.lower(),
        is_dir=False,
        exists_now=True,
        size_bytes=123,
        mtime=1.0,
        ctime=1.0,
        decision=_decision(path, access_policy),
        last_seen_at=last_seen_at,
        extra={"fixture": True},
    )


def _sample_entries(root: Path) -> list[ScanEntry]:
    return [
        _entry(root, "old-allow.md", "allow", "2026-05-27T08:00:00+00:00"),
        _entry(root, "middle-metadata.txt", "metadata_only", "2026-05-27T09:00:00+00:00"),
        _entry(root, "new-no-embedding.pdf", "no_embedding", "2026-05-27T10:00:00+00:00"),
        _entry(root, "newest-deny.pem", "deny", "2026-05-27T11:00:00+00:00"),
    ]


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


def _to_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        value = value.value
    elif hasattr(value, "value") and not isinstance(value, (str, bool, int, float)):
        value = value.value
    return str(value).split(".")[-1].lower().replace("-", "_").replace(" ", "_")


def _access_policy(record) -> str | None:
    decision = _field(record, "decision")
    raw = _field(record, "access_policy", "policy", "action", "kind")
    if raw is None and decision is not None:
        raw = _field(decision, "access_policy", "policy", "action", "kind")
    return _to_text(raw)


def _path_text(record) -> str:
    return str(_field(record, "path", "file_path", "filepath", "name", "file") or "")


def _name_set(records: Iterable) -> set[str]:
    return {Path(_path_text(record)).name for record in records}


def _as_records(value) -> list:
    if value is None:
        return []
    if isinstance(value, (str, bytes, Mapping)):
        return [value] if isinstance(value, Mapping) else []
    return list(value)


def _call_policy_stats(inventory) -> dict[str, int]:
    for method_name in (
        "stats_by_policy",
        "policy_stats",
        "summary_by_policy",
        "stats",
    ):
        method = getattr(inventory, method_name, None)
        if method is None:
            continue
        result = method()
        if isinstance(result, Mapping):
            return {str(key): int(value) for key, value in result.items()}
        return {str(key): int(value) for key, value in result}
    pytest.fail("Inventory should expose policy counts after records are written")


def _call_all_records(inventory) -> list:
    attempts = [
        lambda: inventory.list_records(),
        lambda: inventory.list_records(limit=100),
        lambda: inventory.list_files(limit=100),
        lambda: inventory.all_records(),
        lambda: inventory.records(),
    ]
    return _first_successful_records(attempts, "all inventory records")


def _call_recent_records(inventory, limit: int) -> list:
    attempts = [
        lambda: inventory.list_recent(limit=limit),
        lambda: inventory.recent_records(limit=limit),
        lambda: inventory.recent(limit=limit),
        lambda: inventory.list_records(limit=limit, recent=True),
        lambda: inventory.list_records(limit=limit, order="recent"),
        lambda: inventory.list_records(limit=limit, sort="recent"),
        lambda: inventory.list_files(limit=limit),
    ]
    return _first_successful_records(attempts, "recent inventory records")


def _first_successful_records(attempts, description: str) -> list:
    last_error: Exception | None = None
    for attempt in attempts:
        try:
            records = _as_records(attempt())
        except (AttributeError, TypeError) as exc:
            last_error = exc
            continue
        if records:
            return records
    pytest.fail(f"Inventory should expose {description}; last error: {last_error}")


def _call_record_by_path(inventory, path: Path):
    for method_name in (
        "get_file",
        "get_record",
        "get_by_path",
        "get_path",
        "find",
        "lookup",
    ):
        method = getattr(inventory, method_name, None)
        if method is None:
            continue
        for value in (path, str(path), path.resolve().as_posix()):
            try:
                record = method(value)
            except TypeError:
                continue
            if record is not None:
                return record
    pytest.fail("Inventory should return a stored record by path")


def _seed_inventory(tmp_path: Path) -> tuple[Path, list[ScanEntry]]:
    inventory_mod = _inventory_module()
    entries = _sample_entries(tmp_path)
    inventory_path = tmp_path / "inventory.sqlite"
    with inventory_mod.Inventory(inventory_path) as inventory:
        inserted = inventory.upsert_entries(entries)
    assert inserted == len(entries)
    return inventory_path, entries


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    cli_mod = _cli_module()
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            result = cli_mod.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
        else:
            code = int(result)
    return code, stdout.getvalue(), stderr.getvalue()


def _assert_policy_count(text: str, policy: str, expected: int) -> None:
    assert re.search(rf"\b{re.escape(policy)}\b[^\n\d]*{expected}\b", text), text


def test_inventory_counts_lists_recent_and_finds_records_by_path(tmp_path):
    inventory_mod = _inventory_module()
    inventory_path, entries = _seed_inventory(tmp_path)

    with inventory_mod.Inventory(inventory_path) as inventory:
        stats = _call_policy_stats(inventory)
        for policy in POLICIES:
            assert stats.get(policy) == 1

        all_records = _call_all_records(inventory)
        assert _name_set(all_records) == {entry.name for entry in entries}
        assert {_access_policy(record) for record in all_records} == set(POLICIES)

        recent = _call_recent_records(inventory, limit=2)
        assert [Path(_path_text(record)).name for record in recent[:2]] == [
            "newest-deny.pem",
            "new-no-embedding.pdf",
        ]

        metadata_record = _call_record_by_path(inventory, tmp_path / "middle-metadata.txt")
        assert Path(_path_text(metadata_record)).name == "middle-metadata.txt"
        assert _access_policy(metadata_record) == "metadata_only"


def test_inventory_marks_records_missing_after_full_rescan(tmp_path):
    inventory_mod = _inventory_module()
    inventory_path, entries = _seed_inventory(tmp_path)
    current_paths = [entry.path for entry in entries[1:]]

    with inventory_mod.Inventory(inventory_path) as inventory:
        marked = inventory.mark_missing_under_roots([tmp_path], current_paths)
        stats = _call_policy_stats(inventory)
        all_records = _call_all_records(inventory)
        missing_record = _call_record_by_path(inventory, tmp_path / "old-allow.md")

    assert marked == 1
    assert stats.get("allow", 0) == 0
    assert "old-allow.md" not in _name_set(all_records)
    assert missing_record["exists_now"] is False


def test_cli_status_list_and_show_read_inventory(tmp_path):
    inventory_path, _entries = _seed_inventory(tmp_path)

    status_code, status_out, status_err = _run_cli(
        ["status", "--inventory", str(inventory_path)]
    )
    assert status_code == 0, status_err
    for policy in POLICIES:
        _assert_policy_count(status_out, policy, 1)

    list_code, list_out, list_err = _run_cli(
        ["list", "--inventory", str(inventory_path), "--limit", "10"]
    )
    assert list_code == 0, list_err
    assert "old-allow.md" in list_out
    assert "middle-metadata.txt" in list_out
    assert "new-no-embedding.pdf" in list_out
    assert "newest-deny.pem" in list_out
    assert "metadata_only" in list_out

    filtered_code, filtered_out, filtered_err = _run_cli(
        [
            "list",
            "--inventory",
            str(inventory_path),
            "--policy",
            "metadata_only",
            "--limit",
            "10",
        ]
    )
    assert filtered_code == 0, filtered_err
    assert "middle-metadata.txt" in filtered_out
    assert "old-allow.md" not in filtered_out

    show_path = tmp_path / "middle-metadata.txt"
    show_code, show_out, show_err = _run_cli(
        ["show", str(show_path), "--inventory", str(inventory_path)]
    )
    assert show_code == 0, show_err
    assert "middle-metadata.txt" in show_out or str(show_path) in show_out
    assert "metadata_only" in show_out


def test_cli_privacy_explains_policy_for_humans_and_agents(tmp_path):
    privacy_path = tmp_path / "privacy.yaml"
    privacy_path.write_text(
        "\n".join(
            [
                "version: 1",
                "assistant:",
                '  purpose: "privacy setup fixture"',
                "  setup_questions:",
                '    - "Where are private files?"',
                "deny:",
                "  help:",
                '    title: "Strict deny"',
                "  filenames:",
                '    - ".env"',
                "allow:",
                "  paths:",
                f'    - "{tmp_path.as_posix()}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    text_code, text_out, text_err = _run_cli(["privacy", "--privacy", str(privacy_path)])
    assert text_code == 0, text_err
    assert "privacy_policy:" in text_out
    assert "privacy setup fixture" in text_out
    assert "Strict deny" in text_out
    assert "filenames: .env" in text_out

    json_code, json_out, json_err = _run_cli(
        ["privacy", "--privacy", str(privacy_path), "--json"]
    )
    assert json_code == 0, json_err
    payload = json.loads(json_out)
    assert payload["purpose"] == "privacy setup fixture"
    deny = next(item for item in payload["policies"] if item["policy"] == "deny")
    assert deny["rules"]["filenames"] == [".env"]


def test_scan_report_contains_policy_count_summary_before_entries(tmp_path):
    report_mod = _report_module()
    entries = _sample_entries(tmp_path)
    result = ScanResult(
        entries=entries,
        stats=ScanStats(
            roots=1,
            entries_seen=len(entries),
            files_seen=len(entries),
            allowed=1,
            denied=1,
            metadata_only=1,
            no_embedding=1,
        ),
        errors=[],
    )

    report_path = tmp_path / "scan-plan.md"
    report_mod.write_scan_plan(result, report_path)
    text = report_path.read_text(encoding="utf-8")
    summary_text = text.split("old-allow.md", 1)[0]

    for policy in POLICIES:
        _assert_policy_count(summary_text, policy, 1)


def test_roots_discovery_returns_standard_candidates_and_filters_missing(
    tmp_path, monkeypatch
):
    roots_mod = _roots_module()
    home = tmp_path / "home"
    desktop = home / "Desktop"
    documents = home / "Documents"
    downloads = home / "Downloads"
    desktop.mkdir(parents=True)
    documents.mkdir()

    monkeypatch.setattr(roots_mod.Path, "home", lambda: home)
    for env_name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        monkeypatch.delenv(env_name, raising=False)

    all_candidates = roots_mod.discover_candidate_roots(existing_only=False)
    by_name = {str(_field(candidate, "name")).lower(): candidate for candidate in all_candidates}
    assert {"desktop", "documents", "downloads"} <= set(by_name)
    assert Path(_field(by_name["desktop"], "path")) == desktop
    assert Path(_field(by_name["documents"], "path")) == documents
    assert Path(_field(by_name["downloads"], "path")) == downloads
    assert _field(by_name["downloads"], "exists") is False

    existing_candidates = roots_mod.discover_candidate_roots(existing_only=True)
    existing_names = {str(_field(candidate, "name")).lower() for candidate in existing_candidates}
    assert "desktop" in existing_names
    assert "documents" in existing_names
    assert "downloads" not in existing_names


def test_roots_config_is_agent_readable_and_controls_candidates(tmp_path):
    roots_mod = _roots_module()
    knowledge = tmp_path / "Knowledge"
    archive = tmp_path / "Archive"
    knowledge.mkdir()
    config = {
        "version": 1,
        "assistant": {
            "purpose": "root setup fixture",
            "setup_questions": ["Where is knowledge?"],
            "selection_notes": ["Start small."],
        },
        "roots": [
            {
                "name": "knowledge",
                "enabled": True,
                "resolver": "path",
                "path": knowledge.as_posix(),
                "description": "Curated notes",
                "risk": "low",
                "recommended_policy": "allow",
                "tags": ["curated"],
            },
            {
                "name": "archive",
                "enabled": False,
                "resolver": "path",
                "path": archive.as_posix(),
                "description": "Old archive",
                "risk": "high",
                "recommended_policy": "metadata_only",
            },
        ],
    }

    summary = roots_mod.describe_roots_config(config)
    assert summary["purpose"] == "root setup fixture"
    assert summary["setup_questions"] == ["Where is knowledge?"]
    first_root = summary["roots"][0]
    assert first_root["name"] == "knowledge"
    assert first_root["resolved"]["exists"] is True
    assert first_root["resolved"]["tags"] == ["curated"]

    candidates = roots_mod.discover_candidate_roots(config=config, existing_only=False)
    assert [candidate.name for candidate in candidates] == ["knowledge"]

    candidates_with_disabled = roots_mod.discover_candidate_roots(
        config=config,
        existing_only=False,
        include_disabled=True,
    )
    assert [candidate.name for candidate in candidates_with_disabled] == [
        "knowledge",
        "archive",
    ]


def test_cli_roots_explains_config_for_humans_and_agents(tmp_path):
    roots_config = tmp_path / "roots.yaml"
    root = tmp_path / "Knowledge"
    root.mkdir()
    roots_config.write_text(
        "\n".join(
            [
                "version: 1",
                "assistant:",
                '  purpose: "roots setup fixture"',
                "roots:",
                "  - name: knowledge",
                "    enabled: true",
                "    resolver: path",
                f'    path: "{root.as_posix()}"',
                '    description: "Curated notes"',
                "    risk: low",
                "    recommended_policy: allow",
                "",
            ]
        ),
        encoding="utf-8",
    )

    text_code, text_out, text_err = _run_cli(
        ["roots", "--roots-config", str(roots_config), "--explain"]
    )
    assert text_code == 0, text_err
    assert "roots_config:" in text_out
    assert "roots setup fixture" in text_out
    assert "knowledge" in text_out

    json_code, json_out, json_err = _run_cli(
        ["roots", "--roots-config", str(roots_config), "--explain", "--json"]
    )
    assert json_code == 0, json_err
    payload = json.loads(json_out)
    assert payload["purpose"] == "roots setup fixture"
    assert payload["roots"][0]["resolved"]["path"] == str(root)
