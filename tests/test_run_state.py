from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from anyfile_wiki.cli import main as cli_main
from anyfile_wiki.inventory import Inventory
from anyfile_wiki.run_state import new_run_state, save_run_state


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


def _write_allow_configs(tmp_path: Path, source: Path) -> tuple[Path, Path]:
    privacy = tmp_path / "privacy.yaml"
    privacy.write_text(
        "\n".join(
            [
                "version: 1",
                "require_allow: true",
                "deny: {}",
                "metadata_only: {}",
                "no_embedding: {}",
                "allow:",
                "  paths:",
                f"    - {source.as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    excludes = tmp_path / "excludes.yaml"
    excludes.write_text("version: 1\n", encoding="utf-8")
    return privacy, excludes


def test_run_command_progresses_to_complete_with_small_limits(tmp_path):
    source = tmp_path / "source"
    (source / "sub").mkdir(parents=True)
    (source / "a.txt").write_text("alpha privacy scan note", encoding="utf-8")
    (source / "sub" / "b.md").write_text("# Beta\n\nanalysis extract note", encoding="utf-8")
    out_dir = tmp_path / "run"
    privacy, excludes = _write_allow_configs(tmp_path, source)

    last_stdout = ""
    for index in range(12):
        argv = [
            "run",
            "--out",
            str(out_dir),
            "--privacy",
            str(privacy),
            "--excludes",
            str(excludes),
            "--max-scan-entries",
            "2",
            "--extract-limit",
            "1",
            "--analyze-limit",
            "1",
        ]
        if index == 0:
            argv.insert(1, str(source))
        code, stdout, stderr = _run_cli(argv)
        assert code == 0, stderr
        last_stdout = stdout
        state = json.loads((out_dir / "run-state.json").read_text(encoding="utf-8"))
        if state["status"] == "complete":
            break

    assert "status: complete" in last_stdout
    state = json.loads((out_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["current_stage"] == "done"
    assert all(stage["status"] == "complete" for stage in state["stages"].values())
    assert (out_dir / "extract" / "extract-manifest.jsonl").exists()
    assert (out_dir / "analyze" / "analysis-manifest.jsonl").exists()
    assert (out_dir / "analyze" / "knowledge-index.jsonl").exists()
    assert (out_dir / "review" / "human-review.html").exists()
    assert (out_dir / "html" / "knowledge-index.html").exists()
    assert len((out_dir / "analyze" / "analysis-manifest.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    with Inventory(out_dir / "inventory.sqlite") as inventory:
        assert len(inventory.list_files(limit=10)) == 4

    code, stdout, stderr = _run_cli(["run", "--out", str(out_dir), "--status"])
    assert code == 0, stderr
    assert "current_stage: done" in stdout


def test_run_command_requires_roots_for_new_state(tmp_path):
    code, stdout, stderr = _run_cli(["run", "--out", str(tmp_path / "missing")])

    assert code == 2
    assert stdout == ""
    assert "roots are required" in stderr


def test_run_status_json_outputs_existing_state_without_roots(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "note.md").write_text("# Note\n\nstatus json fixture", encoding="utf-8")
    out_dir = tmp_path / "run"
    privacy, excludes = _write_allow_configs(tmp_path, source)

    code, stdout, stderr = _run_cli(
        [
            "run",
            str(source),
            "--out",
            str(out_dir),
            "--privacy",
            str(privacy),
            "--excludes",
            str(excludes),
            "--max-scan-entries",
            "20",
        ]
    )
    assert code == 0, stderr
    assert "current_stage: extract" in stdout

    code, stdout, stderr = _run_cli(["run", "--out", str(out_dir), "--status", "--json"])

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["status"] == "paused"
    assert payload["current_stage"] == "extract"
    assert payload["roots"] == [str(source)]
    assert payload["paths"]["out_dir"] == str(out_dir)
    assert payload["stages"]["scan"]["status"] == "complete"
    assert "result" not in payload


def test_run_stage_argument_runs_named_stage_from_existing_state_without_roots(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "note.md").write_text("# Note\n\nstage fixture", encoding="utf-8")
    out_dir = tmp_path / "run"
    privacy, excludes = _write_allow_configs(tmp_path, source)

    code, stdout, stderr = _run_cli(
        [
            "run",
            str(source),
            "--out",
            str(out_dir),
            "--privacy",
            str(privacy),
            "--excludes",
            str(excludes),
            "--max-scan-entries",
            "20",
        ]
    )
    assert code == 0, stderr
    state = json.loads((out_dir / "run-state.json").read_text(encoding="utf-8"))
    assert state["current_stage"] == "extract"
    assert state["stages"]["scan"]["chunks"] == 1

    code, stdout, stderr = _run_cli(
        [
            "run",
            "--out",
            str(out_dir),
            "--stage",
            "scan",
            "--max-scan-entries",
            "20",
            "--json",
        ]
    )

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["result"]["stage"] == "scan"
    assert payload["state"]["current_stage"] == "extract"
    assert payload["state"]["roots"] == [str(source)]
    assert payload["state"]["stages"]["scan"]["status"] == "complete"
    assert payload["state"]["stages"]["scan"]["chunks"] == 2


def test_run_html_stage_infers_asset_index_for_legacy_state(tmp_path):
    out_dir = tmp_path / "run"
    state = new_run_state(
        roots=[str(tmp_path / "source")],
        out_dir=out_dir,
        privacy="configs/privacy.example.yaml",
        excludes="configs/excludes.default.yaml",
    )
    del state["paths"]["asset_index"]
    del state["paths"]["asset_dir"]
    state_path = out_dir / "run-state.json"
    knowledge_path = out_dir / "analyze" / "knowledge-index.jsonl"
    asset_path = out_dir / "assets" / "asset-index.jsonl"
    knowledge_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    knowledge_path.write_text(
        json.dumps({"path": "C:/raw.md", "status": "ok", "title": "raw", "tags": []}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    asset_path.write_text(
        "\n".join(
            [
                json.dumps({"path": "C:/asset-a.md", "status": "ok", "title": "asset a", "tags": [], "asset_status": "confirmed"}, ensure_ascii=False),
                json.dumps({"path": "C:/asset-b.md", "status": "ok", "title": "asset b", "tags": [], "asset_status": "deferred"}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    save_run_state(state, state_path)

    code, stdout, stderr = _run_cli(["run", "--state", str(state_path), "--out", str(out_dir), "--stage", "html"])

    assert code == 0, stderr
    assert "wrote HTML browser for 2 records" in stdout
    html = (out_dir / "html" / "knowledge-index.html").read_text(encoding="utf-8")
    assert "asset-index.jsonl" in html
    assert "asset a" in html
    assert "asset b" in html
    assert "raw" not in html
