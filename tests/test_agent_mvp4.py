from __future__ import annotations

import contextlib
import io
import json
from importlib import resources
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


def test_default_configs_are_available_as_package_resources():
    config_root = resources.files("anyfile_wiki.configs")

    for name in (
        "privacy.example.yaml",
        "roots.example.yaml",
        "schedule.example.yaml",
        "excludes.default.yaml",
    ):
        assert config_root.joinpath(name).is_file()


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
    assert profile_payload["setup_contract"]["first_run_must_be_guided"] is True
    assert profile_payload["setup_contract"]["do_not_stop_after_directory_prompt"] is True
    assert profile_payload["review"]["preferred_mode"] == "service"
    assert "review-server" in profile_payload["review"]["service_command"]
    assert profile_payload["review"]["html_fallback_path"].endswith("human-review.html")
    assert profile_payload["analysis"]["mode"] == "rules"
    assert profile_payload["analysis"]["semantic_scope"] == "review_only"
    assert payload["analysis"]["mode"] == "rules"
    assert payload["review"]["preferred_mode"] == "service"
    assert any("review-server" in command for command in payload["next_commands"])

    original = profile.read_text(encoding="utf-8")
    code, stdout, stderr = _run_cli(["agent-init", "--profile", str(profile), "--out", str(run_dir), "--json"])

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["profile"]["status"] == "exists"
    assert profile.read_text(encoding="utf-8") == original


def test_agent_init_can_choose_agent_llm_index_understanding_mode(tmp_path):
    profile = tmp_path / "configs" / "agent-profile.yaml"
    run_dir = tmp_path / "data" / "daily-run"

    code, stdout, stderr = _run_cli(
        [
            "agent-init",
            "--profile",
            str(profile),
            "--out",
            str(run_dir),
            "--analysis-mode",
            "agent-llm",
            "--semantic-scope",
            "all_extractable",
            "--json",
        ]
    )

    assert code == 0, stderr
    payload = json.loads(stdout)
    profile_payload = yaml.safe_load(profile.read_text(encoding="utf-8"))
    assert profile_payload["analysis"]["mode"] == "agent-llm"
    assert profile_payload["analysis"]["semantic_scope"] == "all_extractable"
    assert "不需要额外 API key" in profile_payload["analysis"]["mode_notes"]["agent-llm"]
    assert payload["analysis"]["mode"] == "agent-llm"


def test_agent_init_supplements_existing_profile_without_overwriting_user_values(tmp_path):
    profile = tmp_path / "configs" / "agent-profile.yaml"
    run_dir = tmp_path / "data" / "daily-run"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "workspace": {"default_run_dir": "custom/run"},
                "review": {"html_path": "old/static/human-review.html"},
                "safety": {"allow_delete": False},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    code, stdout, stderr = _run_cli(["agent-init", "--profile", str(profile), "--out", str(run_dir), "--json"])

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["profile"]["status"] == "updated"
    profile_payload = yaml.safe_load(profile.read_text(encoding="utf-8"))
    assert profile_payload["workspace"]["default_run_dir"] == "custom/run"
    assert profile_payload["review"]["html_path"] == "old/static/human-review.html"
    assert profile_payload["review"]["preferred_mode"] == "service"
    assert "review-server" in profile_payload["review"]["service_command"]
    assert profile_payload["setup_contract"]["do_not_stop_after_directory_prompt"] is True


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


def test_agent_task_builds_privacy_gated_semantic_review_tasks(tmp_path):
    run_dir = tmp_path / "run"
    source = tmp_path / "docs" / "budget-plan.md"
    extracted = run_dir / "extract" / "budget-plan.md.txt"
    source.parent.mkdir(parents=True)
    source.write_text("# Budget\n\nFTP budget plan", encoding="utf-8")
    extracted.parent.mkdir(parents=True)
    extracted.write_text("# Budget\n\nFTP budget plan", encoding="utf-8")
    asset_id = asset_id_for_path(str(source))
    _write_jsonl(
        run_dir / "analyze" / "analysis-manifest.jsonl",
        [
            {
                "path": str(source),
                "output_path": str(extracted),
                "status": "ok",
                "title": "Budget plan",
                "summary": "Rule summary",
                "tags": ["document"],
                "primary_tag": "document",
                "content_type": "document",
                "extension": ".md",
                "parser": "direct_text",
                "embedding_allowed": True,
                "char_count": 24,
                "word_count": 4,
                "line_count": 3,
                "analyzed_at": "2026-05-29T00:00:00+00:00",
                "source_extract_status": "ok",
                "analysis_method": "rules",
                "confidence": 0.42,
                "needs_human_review": True,
                "review_reason": "rules_only_needs_semantic_review",
            }
        ],
    )
    _write_jsonl(
        run_dir / "review" / "next-actions.jsonl",
        [
            {
                "path": str(source),
                "action": "queue_agent_semantic_review",
                "source_decision": "request_agent_review",
                "category": "rules_only_or_low_confidence",
                "privacy_level": "local_extracted_text",
            },
            {
                "path": str(tmp_path / "private.md"),
                "action": "queue_agent_semantic_review",
                "source_decision": "request_agent_review",
                "category": "metadata_only",
                "privacy_level": "local_extracted_text",
            },
        ],
    )
    _write_jsonl(
        run_dir / "review" / "human-review.jsonl",
        [
            {"path": str(source), "access_policy": "allow", "category": "rules_only_or_low_confidence"},
            {"path": str(tmp_path / "private.md"), "access_policy": "metadata_only", "category": "metadata_only"},
        ],
    )

    code, stdout, stderr = _run_cli(
        ["agent-task", "--kind", "semantic-review", "--in", str(run_dir / "review" / "next-actions.jsonl"), "--out", str(run_dir / "agent-review"), "--json"]
    )

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["stats"]["tasks"] == 1
    assert payload["stats"]["skipped"] == 1
    tasks = [json.loads(line) for line in (run_dir / "agent-review" / "semantic-review-tasks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert tasks[0]["asset_id"] == asset_id
    assert tasks[0]["extracted_text_path"] == str(extracted)
    assert tasks[0]["privacy_context"]["allowed_to_read_original"] is False
    assert tasks[0]["expected_output_schema"]["required"]
    skipped = (run_dir / "agent-review" / "semantic-review-skipped.jsonl").read_text(encoding="utf-8")
    assert "blocked review category" in skipped


def test_agent_task_semantic_index_all_extractable_without_review_actions(tmp_path):
    run_dir = tmp_path / "run"
    function_file = tmp_path / "docs" / "函数：FUNC_GET_CURVE_MIDVAL.md"
    private_file = tmp_path / "private" / "secret.md"
    denied_file = tmp_path / "private" / "denied.md"
    extracted = run_dir / "extract" / "FUNC_GET_CURVE_MIDVAL.md.txt"
    private_extracted = run_dir / "extract" / "secret.md.txt"
    denied_extracted = run_dir / "extract" / "denied.md.txt"
    for path in (function_file, private_file, denied_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    for path in (extracted, private_extracted, denied_extracted):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture extracted text", encoding="utf-8")
    asset_id = asset_id_for_path(str(function_file))
    _write_jsonl(
        run_dir / "analyze" / "analysis-manifest.jsonl",
        [
            {
                "path": str(function_file),
                "output_path": str(extracted),
                "status": "ok",
                "title": "函数：FUNC_GET_CURVE_MIDVAL.md",
                "summary": "函数开头定义了 FUNC_GET_CURVE_MIDVAL。",
                "tags": ["document", "docs"],
                "primary_tag": "document",
                "content_type": "document",
                "extension": ".md",
                "parser": "direct_text",
                "embedding_allowed": True,
                "access_policy": "allow",
                "char_count": 240,
                "word_count": 40,
                "line_count": 8,
                "analyzed_at": "2026-05-29T00:00:00+00:00",
                "source_extract_status": "ok",
                "analysis_method": "rules",
                "confidence": 0.7,
                "needs_human_review": False,
                "review_reason": "rules_only_optional_review",
                "rule_title": "函数：FUNC_GET_CURVE_MIDVAL.md",
                "rule_summary": "函数开头定义了 FUNC_GET_CURVE_MIDVAL。",
                "rule_tags": ["document", "docs"],
            },
            {
                "path": str(private_file),
                "output_path": str(private_extracted),
                "status": "ok",
                "title": "secret.md",
                "summary": "metadata only fixture",
                "tags": ["document"],
                "primary_tag": "document",
                "content_type": "document",
                "extension": ".md",
                "parser": "direct_text",
                "embedding_allowed": False,
                "access_policy": "metadata_only",
                "char_count": 10,
                "word_count": 2,
                "line_count": 1,
                "analyzed_at": "2026-05-29T00:00:00+00:00",
                "source_extract_status": "ok",
                "analysis_method": "rules",
                "confidence": 0.2,
                "needs_human_review": True,
                "review_reason": "metadata_only",
            },
            {
                "path": str(denied_file),
                "output_path": str(denied_extracted),
                "status": "ok",
                "title": "denied.md",
                "summary": "deny fixture",
                "tags": ["document"],
                "primary_tag": "document",
                "content_type": "document",
                "extension": ".md",
                "parser": "direct_text",
                "embedding_allowed": False,
                "access_policy": "deny",
                "char_count": 10,
                "word_count": 2,
                "line_count": 1,
                "analyzed_at": "2026-05-29T00:00:00+00:00",
                "source_extract_status": "ok",
                "analysis_method": "rules",
                "confidence": 0.2,
                "needs_human_review": True,
                "review_reason": "policy_blocked",
            },
        ],
    )

    code, stdout, stderr = _run_cli(
        [
            "agent-task",
            "--kind",
            "semantic-index",
            "--scope",
            "all-extractable",
            "--analysis",
            str(run_dir / "analyze" / "analysis-manifest.jsonl"),
            "--out",
            str(run_dir / "agent-review"),
            "--json",
        ]
    )

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["kind"] == "semantic-index"
    assert payload["stats"]["tasks"] == 1
    assert payload["stats"]["skipped"] == 2
    tasks = [json.loads(line) for line in (run_dir / "agent-review" / "semantic-index-tasks.jsonl").read_text(encoding="utf-8").splitlines()]
    assert tasks[0]["asset_id"] == asset_id
    assert tasks[0]["path"] == str(function_file)
    assert tasks[0]["extracted_text_path"] == str(extracted)
    assert tasks[0]["privacy_context"]["must_not_read_original"] is True
    skipped = (run_dir / "agent-review" / "semantic-index-skipped.jsonl").read_text(encoding="utf-8")
    assert "blocked access policy: metadata_only" in skipped
    assert "blocked access policy: deny" in skipped

    _write_jsonl(
        run_dir / "agent-review" / "results.jsonl",
        [
            {
                "asset_id": asset_id,
                "path": str(function_file),
                "title": "函数：FUNC_GET_CURVE_MIDVAL",
                "summary": "这个函数用于根据指定日期、曲线、币种和期限，计算收益率曲线中的中间期限利率值。",
                "tags": ["document", "docs"],
                "confidence": 0.86,
                "needs_human_review": False,
                "review_reason": "agent_llm_semantic_reviewed",
                "key_points": ["收益率曲线", "中间期限", "利率计算"],
                "model_notes": "Host agent read extracted text only.",
            }
        ],
    )

    code, stdout, stderr = _run_cli(["agent-review-apply", "--in", str(run_dir / "agent-review" / "results.jsonl"), "--json"])

    assert code == 0, stderr
    manifest = [json.loads(line) for line in (run_dir / "analyze" / "analysis-manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    by_path = {record["path"]: record for record in manifest}
    assert by_path[str(function_file)]["analysis_method"] == "agent-llm"
    assert by_path[str(function_file)]["summary"] == "这个函数用于根据指定日期、曲线、币种和期限，计算收益率曲线中的中间期限利率值。"
    assert by_path[str(function_file)]["rule_summary"] == "函数开头定义了 FUNC_GET_CURVE_MIDVAL。"
    asset = json.loads((run_dir / "assets" / "asset-index.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert asset["analysis_method"] == "agent-llm"
    assert asset["summary"] == "这个函数用于根据指定日期、曲线、币种和期限，计算收益率曲线中的中间期限利率值。"
    assert (run_dir / "html" / "knowledge-index.html").exists()


def test_agent_task_semantic_index_cloud_mode_requires_explicit_llm_authorization(tmp_path):
    run_dir = tmp_path / "run"
    source = tmp_path / "docs" / "cloud-candidate.md"
    extracted = run_dir / "extract" / "cloud-candidate.md.txt"
    source.parent.mkdir(parents=True)
    source.write_text("fixture", encoding="utf-8")
    extracted.parent.mkdir(parents=True)
    extracted.write_text("fixture extracted text", encoding="utf-8")
    _write_jsonl(
        run_dir / "analyze" / "analysis-manifest.jsonl",
        [
            {
                "path": str(source),
                "output_path": str(extracted),
                "status": "ok",
                "title": "cloud-candidate.md",
                "summary": "fixture",
                "tags": ["document"],
                "primary_tag": "document",
                "content_type": "document",
                "extension": ".md",
                "parser": "direct_text",
                "embedding_allowed": True,
                "access_policy": "allow",
                "char_count": 10,
                "word_count": 2,
                "line_count": 1,
                "analyzed_at": "2026-05-29T00:00:00+00:00",
                "source_extract_status": "ok",
                "analysis_method": "rules",
                "confidence": 0.6,
                "needs_human_review": False,
                "review_reason": "rules_only_optional_review",
            }
        ],
    )

    code, stdout, stderr = _run_cli(
        [
            "agent-task",
            "--kind",
            "semantic-index",
            "--scope",
            "all-extractable",
            "--mode",
            "cloud-llm",
            "--analysis",
            str(run_dir / "analyze" / "analysis-manifest.jsonl"),
            "--out",
            str(run_dir / "agent-review"),
            "--json",
        ]
    )

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["stats"]["tasks"] == 0
    assert payload["stats"]["skipped"] == 1
    skipped = (run_dir / "agent-review" / "semantic-index-skipped.jsonl").read_text(encoding="utf-8")
    assert "cloud_not_authorized" in skipped


def test_agent_review_apply_refreshes_analysis_assets_and_html(tmp_path):
    run_dir = tmp_path / "run"
    source = tmp_path / "docs" / "budget-plan.md"
    extracted = run_dir / "extract" / "budget-plan.md.txt"
    source.parent.mkdir(parents=True)
    source.write_text("# Budget\n\nFTP budget plan", encoding="utf-8")
    extracted.parent.mkdir(parents=True)
    extracted.write_text("# Budget\n\nFTP budget plan", encoding="utf-8")
    asset_id = asset_id_for_path(str(source))
    _write_jsonl(
        run_dir / "analyze" / "analysis-manifest.jsonl",
        [
            {
                "path": str(source),
                "output_path": str(extracted),
                "status": "ok",
                "title": "Budget plan",
                "summary": "Rule summary",
                "tags": ["document"],
                "primary_tag": "document",
                "content_type": "document",
                "extension": ".md",
                "parser": "direct_text",
                "embedding_allowed": True,
                "char_count": 24,
                "word_count": 4,
                "line_count": 3,
                "analyzed_at": "2026-05-29T00:00:00+00:00",
                "source_extract_status": "ok",
                "analysis_method": "rules",
                "confidence": 0.42,
                "needs_human_review": True,
                "review_reason": "rules_only_needs_semantic_review",
            }
        ],
    )
    _write_jsonl(
        run_dir / "review" / "next-actions.jsonl",
        [
            {
                "path": str(source),
                "action": "queue_agent_semantic_review",
                "source_decision": "request_agent_review",
                "category": "rules_only_or_low_confidence",
                "privacy_level": "local_extracted_text",
            }
        ],
    )
    _write_jsonl(
        run_dir / "review" / "human-review.jsonl",
        [{"path": str(source), "access_policy": "allow", "category": "rules_only_or_low_confidence"}],
    )
    code, stdout, stderr = _run_cli(
        ["agent-task", "--in", str(run_dir / "review" / "next-actions.jsonl"), "--out", str(run_dir / "agent-review"), "--json"]
    )
    assert code == 0, stderr
    _write_jsonl(
        run_dir / "agent-review" / "results.jsonl",
        [
            {
                "asset_id": asset_id,
                "path": str(source),
                "title": "FTP budget measurement plan",
                "summary": "This document explains FTP budget measurement assumptions and workflow.",
                "tags": ["topic/business_budgeting", "topic/data_reconciliation"],
                "confidence": 0.88,
                "needs_human_review": False,
                "review_reason": "agent_llm_semantic_reviewed",
                "key_points": ["assumptions", "workflow"],
            }
        ],
    )

    code, stdout, stderr = _run_cli(["agent-review-apply", "--in", str(run_dir / "agent-review" / "results.jsonl"), "--json"])

    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["stats"]["applied"] == 1
    assert payload["stats"]["rejected"] == 0
    manifest = [json.loads(line) for line in (run_dir / "analyze" / "analysis-manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert manifest[0]["analysis_method"] == "agent-llm"
    assert manifest[0]["needs_human_review"] is False
    asset = json.loads((run_dir / "assets" / "asset-index.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert asset["asset_id"] == asset_id
    assert asset["asset_status"] == "confirmed"
    assert "topic/business_budgeting" in asset["tags"]
    assert (run_dir / "html" / "knowledge-index.html").exists()


def test_anyfile_wiki_skill_has_required_agent_workflows():
    skill = Path("skills/anyfile-wiki/SKILL.md").read_text(encoding="utf-8")
    frontmatter = skill.split("---", 2)[1]
    metadata = yaml.safe_load(frontmatter)

    assert metadata["name"] == "anyfile-wiki"
    assert "agent-init" in skill
    assert "anyfile-wiki query" in skill
    assert "agent-task" in skill
    assert "agent-review-apply" in skill
    assert "usage-event" in skill
    assert "Never move, delete, rename" in skill
    assert "do not stop after asking for scan folders" in skill
    assert "start `review-server`, open the printed `review_url`" in skill
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
