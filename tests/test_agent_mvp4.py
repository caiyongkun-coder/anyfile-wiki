from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys

import yaml

from anyfile_wiki.cli import main as cli_main
from anyfile_wiki.sidecars import asset_id_for_path


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


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n", encoding="utf-8")


def _write_profile(path: Path, asset_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "workspace": {"default_run_dir": str(asset_dir.parent)},
                "indexes": {
                    "asset_index": str(asset_dir / "asset-index.jsonl"),
                    "collection_index": str(asset_dir / "collection-index.jsonl"),
                    "asset_score": str(asset_dir / "asset-score.jsonl"),
                    "asset_usage_events": str(asset_dir / "asset-usage-events.jsonl"),
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_agent_init_creates_agent_readable_configs_without_overwriting(tmp_path):
    profile = tmp_path / "configs" / "agent-profile.yaml"
    run_dir = tmp_path / "data" / "daily-run"

    code, stdout, stderr = _run_cli(["agent-init", "--profile", str(profile), "--out", str(run_dir), "--json"])

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["profile"]["status"] == "created"
    assert (tmp_path / "configs" / "privacy.yaml").exists()
    assert (tmp_path / "configs" / "roots.yaml").exists()
    assert (tmp_path / "configs" / "schedule.yaml").exists()
    profile_payload = yaml.safe_load(profile.read_text(encoding="utf-8"))
    assert profile_payload["safety"]["allow_delete"] is False
    assert profile_payload["indexes"]["asset_index"].endswith("asset-index.jsonl")

    original = profile.read_text(encoding="utf-8")
    code, stdout, stderr = _run_cli(["agent-init", "--profile", str(profile), "--out", str(run_dir), "--json"])

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["profile"]["status"] == "exists"
    assert profile.read_text(encoding="utf-8") == original


def test_query_searches_asset_sidecars_without_reading_original_files(tmp_path):
    asset_dir = tmp_path / "run" / "assets"
    profile = tmp_path / "configs" / "agent-profile.yaml"
    asset_id = asset_id_for_path("C:/docs/budget-plan.md")
    _write_profile(profile, asset_dir)
    _write_jsonl(
        asset_dir / "asset-index.jsonl",
        [
            {
                "asset_id": asset_id,
                "path": "C:/docs/budget-plan.md",
                "title": "Budget plan",
                "summary": "FTP budget measurement and project plan",
                "tags": ["topic/budget", "document"],
                "asset_status": "confirmed",
                "needs_human_review": False,
            }
        ],
    )
    _write_jsonl(
        asset_dir / "collection-index.jsonl",
        [
            {
                "asset_id": asset_id,
                "collection_title": "Budget plan",
                "virtual_path": "02_FTP预算测算与取数/Budget plan",
                "relation_type": "master",
                "canonical_asset_id": asset_id,
                "review_required": False,
            }
        ],
    )
    _write_jsonl(
        asset_dir / "asset-score.jsonl",
        [
            {
                "asset_id": asset_id,
                "archive_policy": "local",
                "usage_score": 0.2,
                "retention_score": 0.8,
                "archive_score": 0.1,
                "delete_risk_score": 0.9,
            }
        ],
    )

    code, stdout, stderr = _run_cli(["query", "budget", "--profile", str(profile), "--json"])

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["ok"] is True
    assert payload["results"][0]["asset_id"] == asset_id
    assert payload["results"][0]["path"] == "C:/docs/budget-plan.md"
    assert payload["results"][0]["virtual_path"].startswith("02_FTP")
    assert payload["results"][0]["delete_risk_score"] == 0.9


def test_query_missing_index_explains_next_steps(tmp_path):
    profile = tmp_path / "configs" / "agent-profile.yaml"
    _write_profile(profile, tmp_path / "missing" / "assets")

    code, stdout, stderr = _run_cli(["query", "budget", "--profile", str(profile), "--json"])

    assert code == 2
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["ok"] is False
    assert "agent-init" in " ".join(payload["next_steps"])


def test_usage_event_appends_and_sidecars_turn_it_into_usage_score(tmp_path):
    asset_dir = tmp_path / "run" / "assets"
    profile = tmp_path / "configs" / "agent-profile.yaml"
    asset_id = asset_id_for_path("C:/docs/budget-plan.md")
    _write_profile(profile, asset_dir)
    _write_jsonl(
        asset_dir / "asset-index.jsonl",
        [
            {
                "asset_id": asset_id,
                "path": "C:/docs/budget-plan.md",
                "title": "Budget plan",
                "summary": "FTP budget measurement",
                "tags": ["topic/budget"],
                "extension": ".md",
                "source_extract_status": "ok",
                "confidence": 0.9,
                "needs_human_review": False,
            }
        ],
    )

    code, stdout, stderr = _run_cli(
        ["usage-event", "--asset-id", asset_id, "--event", "cited", "--query", "budget", "--profile", str(profile), "--json"]
    )

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["event_written"] is True
    assert (asset_dir / "asset-usage-events.jsonl").read_text(encoding="utf-8").count("\n") == 1

    code, stdout, stderr = _run_cli(["sidecars", "--asset-index", str(asset_dir / "asset-index.jsonl"), "--out", str(asset_dir)])

    assert code == 0, stderr
    score = json.loads((asset_dir / "asset-score.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert score["citation_count"] == 1
    assert score["usage_score"] > 0

    code, stdout, stderr = _run_cli(
        ["usage-event", "--asset-id", "missing", "--event", "cited", "--profile", str(profile), "--json"]
    )

    assert code == 2
    assert json.loads(stdout)["event_written"] is False
    assert (asset_dir / "asset-usage-events.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_anyfile_wiki_skill_has_required_agent_workflows():
    skill = Path("skills/anyfile-wiki/SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]
    metadata = yaml.safe_load(frontmatter)

    assert metadata["name"] == "anyfile-wiki"
    assert "agent-init" in skill
    assert "anyfile-wiki query" in skill
    assert "usage-event" in skill
    assert "Never move, delete, rename" in skill
    assert "human-review.html" in skill


def test_install_agent_skill_dry_run_and_skill_only_preserve_existing_files(tmp_path):
    codex_home = tmp_path / ".codex"
    script = Path("scripts/install_agent_skill.py")

    dry = subprocess.run(
        [sys.executable, str(script), "--dry-run", "--skill-only", "--codex-home", str(codex_home)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert dry.returncode == 0, dry.stderr
    assert "dry_run: True" in dry.stdout
    assert not (codex_home / "skills" / "anyfile-wiki").exists()

    target = codex_home / "skills" / "anyfile-wiki"
    target.mkdir(parents=True)
    user_file = target / "user-note.txt"
    user_file.write_text("keep me", encoding="utf-8")
    real = subprocess.run(
        [sys.executable, str(script), "--skill-only", "--codex-home", str(codex_home)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert real.returncode == 0, real.stderr
    assert (target / "SKILL.md").exists()
    assert user_file.read_text(encoding="utf-8") == "keep me"
