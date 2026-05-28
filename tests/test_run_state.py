from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from anyfile_wiki.cli import main as cli_main
from anyfile_wiki.inventory import Inventory


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


def test_run_command_progresses_to_complete_with_small_limits(tmp_path):
    source = tmp_path / "source"
    (source / "sub").mkdir(parents=True)
    (source / "a.txt").write_text("alpha privacy scan note", encoding="utf-8")
    (source / "sub" / "b.md").write_text("# Beta\n\nanalysis extract note", encoding="utf-8")
    out_dir = tmp_path / "run"
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
