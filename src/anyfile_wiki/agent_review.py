from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from .analyze import AnalysisResult, write_analysis_outputs
from .assets import load_jsonl_records, write_asset_outputs_from_files
from .sidecars import asset_id_for_path
from .tags import load_tags_config, tag_definitions


TASK_SCHEMA_VERSION = 1
AGENT_REVIEW_METHOD = "agent-llm"
TASK_KIND_SEMANTIC_REVIEW = "semantic-review"

SEMANTIC_REVIEW_ACTIONS = {
    "queue_local_llm_review",
    "propose_cloud_llm_authorization",
}
BLOCKED_REVIEW_CATEGORIES = {"policy_blocked", "metadata_only"}
BLOCKED_ACCESS_POLICIES = {"deny", "metadata_only"}
REQUIRED_RESULT_FIELDS = {"asset_id", "path", "title", "summary", "tags", "confidence"}


def build_semantic_review_tasks(
    *,
    actions_path: str | Path,
    output_dir: str | Path,
    analysis_path: str | Path | None = None,
    review_items_path: str | Path | None = None,
    tags_config_path: str | Path | None = "configs/tags.example.yaml",
) -> dict[str, Any]:
    """Create host-agent semantic review tasks from human review actions.

    This command never reads original files. It only points the host agent at
    extraction outputs that already exist and passed the review/privacy gate.
    """

    actions_source = Path(actions_path)
    run_root = _infer_run_root_from_review_path(actions_source)
    analysis_source = Path(analysis_path) if analysis_path else _default_analysis_path(run_root)
    review_source = Path(review_items_path) if review_items_path else actions_source.parent / "human-review.jsonl"
    root = Path(output_dir)

    actions = load_jsonl_records(actions_source)
    analysis_records = load_jsonl_records(analysis_source)
    review_items = load_jsonl_records(review_source) if review_source.exists() else []
    allowed_tags = _allowed_tags(tags_config_path)
    analysis_by_path = {_path_key(record.get("path")): record for record in analysis_records}
    review_by_path = {_path_key(record.get("path")): record for record in review_items}

    tasks: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()
    for action in actions:
        if str(action.get("action") or "") not in SEMANTIC_REVIEW_ACTIONS:
            continue
        path = str(action.get("path") or "")
        asset_id = str(action.get("asset_id") or asset_id_for_path(path))
        analysis = analysis_by_path.get(_path_key(path))
        review_item = review_by_path.get(_path_key(path), {})
        skip_reason = _task_skip_reason(action, analysis, review_item)
        if skip_reason:
            skipped.append(_skip_record(action, asset_id=asset_id, reason=skip_reason))
            continue
        assert analysis is not None  # Narrowed by _task_skip_reason.
        extracted_text_path = str(analysis.get("output_path") or "")
        task_id = f"{TASK_KIND_SEMANTIC_REVIEW}:{asset_id}"
        if task_id in seen_task_ids:
            continue
        seen_task_ids.add(task_id)
        tasks.append(
            {
                "schema_version": TASK_SCHEMA_VERSION,
                "task_id": task_id,
                "kind": TASK_KIND_SEMANTIC_REVIEW,
                "asset_id": asset_id,
                "path": path,
                "extracted_text_path": extracted_text_path,
                "source_action": str(action.get("action") or ""),
                "source_decision": str(action.get("source_decision") or ""),
                "current_title": str(analysis.get("title") or ""),
                "current_summary": str(analysis.get("summary") or ""),
                "current_tags": _string_list(analysis.get("tags")),
                "current_confidence": _optional_float(analysis.get("confidence"), default=0.0),
                "current_review_reason": str(analysis.get("review_reason") or ""),
                "content_type": str(analysis.get("content_type") or ""),
                "extension": str(analysis.get("extension") or Path(path).suffix.lower()),
                "parser": str(analysis.get("parser") or ""),
                "allowed_tags": allowed_tags,
                "expected_output_schema": expected_result_schema(),
                "privacy_context": _privacy_context(action, review_item, analysis),
            }
        )

    outputs = {
        "semantic_review_tasks": root / "semantic-review-tasks.jsonl",
        "semantic_review_skipped": root / "semantic-review-skipped.jsonl",
        "expected_output_schema": root / "expected-output-schema.json",
        "instructions": root / "semantic-review-instructions.md",
    }
    root.mkdir(parents=True, exist_ok=True)
    _write_jsonl(tasks, outputs["semantic_review_tasks"])
    _write_jsonl(skipped, outputs["semantic_review_skipped"])
    outputs["expected_output_schema"].write_text(
        json.dumps(expected_result_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_task_instructions(outputs["instructions"], tasks_path=outputs["semantic_review_tasks"])
    return {
        "ok": True,
        "kind": TASK_KIND_SEMANTIC_REVIEW,
        "inputs": {
            "actions": str(actions_source),
            "analysis": str(analysis_source),
            "review_items": str(review_source) if review_source.exists() else "",
        },
        "outputs": {key: str(value) for key, value in outputs.items()},
        "stats": {
            "actions": len(actions),
            "tasks": len(tasks),
            "skipped": len(skipped),
        },
    }


def apply_semantic_review_results(
    *,
    results_path: str | Path,
    run_dir: str | Path | None = None,
    analysis_path: str | Path | None = None,
    tasks_path: str | Path | None = None,
    actions_path: str | Path | None = None,
    review_items_path: str | Path | None = None,
    tags_config_path: str | Path | None = "configs/tags.example.yaml",
) -> dict[str, Any]:
    """Validate host-agent semantic results and refresh analysis/assets/html."""

    source = Path(results_path)
    inferred_run_root = Path(run_dir) if run_dir else _infer_run_root_from_agent_review_path(source)
    agent_review_dir = source.parent
    analysis_source = Path(analysis_path) if analysis_path else _default_analysis_path(inferred_run_root)
    task_source = Path(tasks_path) if tasks_path else agent_review_dir / "semantic-review-tasks.jsonl"
    action_source = Path(actions_path) if actions_path else inferred_run_root / "review" / "next-actions.jsonl"
    review_source = Path(review_items_path) if review_items_path else inferred_run_root / "review" / "human-review.jsonl"

    if not source.exists():
        raise FileNotFoundError(f"agent review results not found: {source}")
    if not analysis_source.exists():
        raise FileNotFoundError(f"analysis manifest not found: {analysis_source}")

    analysis_records = load_jsonl_records(analysis_source)
    task_records = load_jsonl_records(task_source) if task_source.exists() else []
    result_records = load_jsonl_records(source)
    tasks_by_asset = {str(record.get("asset_id")): record for record in task_records}
    analysis_by_path = {_path_key(record.get("path")): record for record in analysis_records}
    updated_by_path: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []

    for result in result_records:
        try:
            normalized = _validate_result(result, tasks_by_asset)
            path_key = _path_key(normalized["path"])
            original = analysis_by_path.get(path_key)
            if original is None:
                raise ValueError("path is not present in the current analysis manifest")
            updated_by_path[path_key] = _apply_result_to_analysis(original, normalized)
        except ValueError as exc:
            rejected.append({"record": result, "error": str(exc)})

    refreshed: list[AnalysisResult] = []
    for record in analysis_records:
        replacement = updated_by_path.get(_path_key(record.get("path")))
        refreshed.append(_analysis_result_from_record(replacement or record))

    outputs = write_analysis_outputs(refreshed, analysis_source.parent)
    effective_actions_path = agent_review_dir / "agent-review-actions.jsonl"
    _write_jsonl(
        _effective_actions(load_jsonl_records(action_source) if action_source.exists() else [], updated_by_path.values()),
        effective_actions_path,
    )
    valid_results_path = agent_review_dir / "semantic-review-results.valid.jsonl"
    rejected_path = agent_review_dir / "semantic-review-results.rejected.jsonl"
    _write_jsonl(list(updated_by_path.values()), valid_results_path)
    _write_jsonl(rejected, rejected_path)

    asset_outputs: dict[str, Path] = {}
    knowledge_index = outputs["knowledge_index_jsonl"]
    if action_source.exists():
        tags_config = _load_tags_config_if_present(tags_config_path)
        asset_outputs = write_asset_outputs_from_files(
            analysis_path=knowledge_index,
            actions_path=effective_actions_path,
            review_items_path=review_source if review_source.exists() else None,
            output_dir=inferred_run_root / "assets",
            html_dir=inferred_run_root / "html",
            tags_config=tags_config,
        )

    return {
        "ok": not rejected,
        "analysis": {key: str(value) for key, value in outputs.items()},
        "agent_review": {
            "valid_results": str(valid_results_path),
            "rejected_results": str(rejected_path),
            "effective_actions": str(effective_actions_path),
        },
        "assets": {key: str(value) for key, value in asset_outputs.items()},
        "stats": {
            "input_results": len(result_records),
            "applied": len(updated_by_path),
            "rejected": len(rejected),
        },
    }


def expected_result_schema() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "required": sorted(REQUIRED_RESULT_FIELDS),
        "fields": {
            "asset_id": "asset id from semantic-review-tasks.jsonl",
            "path": "original file path from the task",
            "title": "short human-readable title",
            "summary": "Chinese summary, 1-3 sentences",
            "tags": "list of tags, prefer allowed_tags from the task",
            "confidence": "number from 0.0 to 1.0",
            "needs_human_review": "boolean, true if uncertain",
            "review_reason": "agent_llm_semantic_reviewed or agent_llm_low_confidence",
            "key_points": "optional list of short key points",
            "content_type": "optional refined content type",
            "primary_tag": "optional primary tag",
            "model_notes": "optional note for audit; do not include secrets",
        },
        "example": {
            "schema_version": 1,
            "asset_id": "asset:path-sha256:...",
            "path": "E:/docs/example.docx",
            "title": "项目预算测算说明",
            "summary": "这份文档说明项目预算测算口径、数据来源和核对流程。",
            "tags": ["topic/business_budgeting", "topic/data_reconciliation"],
            "confidence": 0.86,
            "needs_human_review": False,
            "review_reason": "agent_llm_semantic_reviewed",
            "key_points": ["预算口径", "数据来源", "核对流程"],
            "model_notes": "Host agent read only extracted_text_path from the task.",
        },
    }


def _task_skip_reason(action: dict[str, Any], analysis: dict[str, Any] | None, review_item: dict[str, Any]) -> str:
    category = str(action.get("category") or review_item.get("category") or "")
    access_policy = str(review_item.get("access_policy") or "")
    if category in BLOCKED_REVIEW_CATEGORIES:
        return f"blocked review category: {category}"
    if access_policy in BLOCKED_ACCESS_POLICIES:
        return f"blocked access policy: {access_policy}"
    if analysis is None:
        return "missing analysis record"
    output_path = Path(str(analysis.get("output_path") or ""))
    if not output_path.is_file():
        return "missing extracted text output"
    if str(analysis.get("source_extract_status") or "") not in {"ok", "up_to_date", ""}:
        return f"source extract status is {analysis.get('source_extract_status')}"
    return ""


def _skip_record(action: dict[str, Any], *, asset_id: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": TASK_SCHEMA_VERSION,
        "kind": TASK_KIND_SEMANTIC_REVIEW,
        "asset_id": asset_id,
        "path": str(action.get("path") or ""),
        "source_action": str(action.get("action") or ""),
        "skip_reason": reason,
    }


def _privacy_context(action: dict[str, Any], review_item: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "agent-llm",
        "source": "extracted_text_only",
        "access_policy": str(review_item.get("access_policy") or "unknown"),
        "review_category": str(action.get("category") or review_item.get("category") or ""),
        "privacy_level": str(action.get("privacy_level") or "local_extracted_text"),
        "embedding_allowed": bool(analysis.get("embedding_allowed")),
        "allowed_to_read_original": False,
        "must_not_read_original": True,
        "must_not_call_cloud_api_from_cli": True,
        "note": "Host agent may read extracted_text_path only; original path remains for citation and lookup.",
    }


def _validate_result(record: dict[str, Any], tasks_by_asset: dict[str, dict[str, Any]]) -> dict[str, Any]:
    missing = [field for field in sorted(REQUIRED_RESULT_FIELDS) if field not in record]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    asset_id = str(record.get("asset_id") or "")
    path = str(record.get("path") or "")
    task = tasks_by_asset.get(asset_id)
    if tasks_by_asset and task is None:
        raise ValueError("asset_id is not in semantic-review-tasks.jsonl")
    if task and _path_key(task.get("path")) != _path_key(path):
        raise ValueError("result path does not match the task path")
    tags = _string_list(record.get("tags"))
    if not tags:
        raise ValueError("tags must be a non-empty list")
    confidence = _optional_float(record.get("confidence"), default=-1.0)
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")
    needs_human_review = bool(record.get("needs_human_review", confidence < 0.7))
    review_reason = str(record.get("review_reason") or "")
    if not review_reason:
        review_reason = "agent_llm_low_confidence" if needs_human_review else "agent_llm_semantic_reviewed"
    normalized = dict(record)
    normalized.update(
        {
            "asset_id": asset_id,
            "path": path,
            "title": str(record.get("title") or Path(path).name),
            "summary": str(record.get("summary") or ""),
            "tags": tags,
            "confidence": confidence,
            "needs_human_review": needs_human_review,
            "review_reason": review_reason,
            "key_points": _string_list(record.get("key_points"))[:8],
            "model_notes": str(
                record.get("model_notes")
                or "Host agent semantic review. Original file was not read by AnyFile Wiki writeback."
            ),
        }
    )
    return normalized


def _apply_result_to_analysis(original: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    updated = dict(original)
    tags = _string_list(result.get("tags"))
    updated.update(
        {
            "status": "ok",
            "title": str(result.get("title") or original.get("title") or Path(str(original.get("path") or "")).name),
            "summary": str(result.get("summary") or original.get("summary") or ""),
            "tags": tags,
            "primary_tag": str(result.get("primary_tag") or (tags[0] if tags else original.get("primary_tag") or "")),
            "content_type": str(result.get("content_type") or original.get("content_type") or "document"),
            "analysis_method": AGENT_REVIEW_METHOD,
            "confidence": _optional_float(result.get("confidence"), default=0.0),
            "needs_human_review": bool(result.get("needs_human_review")),
            "review_reason": str(result.get("review_reason") or ""),
            "key_points": _string_list(result.get("key_points"))[:8],
            "model_notes": str(result.get("model_notes") or ""),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    if not updated.get("rule_title"):
        updated["rule_title"] = original.get("title")
    if not updated.get("rule_summary"):
        updated["rule_summary"] = original.get("summary")
    if not updated.get("rule_tags"):
        updated["rule_tags"] = _string_list(original.get("tags"))
    return updated


def _effective_actions(original_actions: list[dict[str, Any]], updated_records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    updated_by_path = {_path_key(record.get("path")): record for record in updated_records}
    actions: list[dict[str, Any]] = []
    for action in original_actions:
        key = _path_key(action.get("path"))
        if key in updated_by_path and str(action.get("action") or "") in SEMANTIC_REVIEW_ACTIONS:
            continue
        actions.append(dict(action))
    for record in updated_by_path.values():
        if bool(record.get("needs_human_review")):
            actions.append(
                {
                    "path": str(record.get("path") or ""),
                    "action": "defer_review",
                    "title": "Agent semantic review still needs human review",
                    "source_decision": "agent_semantic_review",
                    "category": "agent_semantic_review",
                    "severity": "medium",
                    "manual_tags": [],
                    "note": str(record.get("review_reason") or ""),
                    "privacy_level": "local_extracted_text",
                    "requires_confirmation": True,
                    "reason": "Host agent semantic result is still low confidence.",
                    "next_step": "Ask the user to manually confirm summary and tags.",
                    "decided_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        else:
            actions.append(
                {
                    "path": str(record.get("path") or ""),
                    "action": "accept_current_analysis",
                    "title": "Agent semantic review accepted",
                    "source_decision": "agent_semantic_review",
                    "category": "agent_semantic_review",
                    "severity": "low",
                    "manual_tags": [],
                    "note": "Semantic review was produced by the host agent from extracted text.",
                    "privacy_level": "local_extracted_text",
                    "requires_confirmation": False,
                    "reason": "Host agent semantic review produced a confident result.",
                    "next_step": "Use refreshed asset index for query and browsing.",
                    "decided_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    return actions


def _analysis_result_from_record(record: dict[str, Any]) -> AnalysisResult:
    allowed = {field.name for field in fields(AnalysisResult)}
    payload = {key: value for key, value in record.items() if key in allowed}
    defaults = {
        "path": "",
        "output_path": "",
        "status": "ok",
        "title": "",
        "summary": "",
        "tags": [],
        "primary_tag": "",
        "content_type": "document",
        "extension": Path(str(record.get("path") or "")).suffix.lower(),
        "parser": "",
        "embedding_allowed": False,
        "char_count": 0,
        "word_count": 0,
        "line_count": 0,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "source_extract_status": "",
    }
    for key, value in defaults.items():
        payload.setdefault(key, value)
    return AnalysisResult(**payload)


def _allowed_tags(tags_config_path: str | Path | None) -> list[str]:
    config = _load_tags_config_if_present(tags_config_path)
    return [definition.id for definition in tag_definitions(config)] if config else []


def _load_tags_config_if_present(tags_config_path: str | Path | None) -> dict[str, Any] | None:
    if not tags_config_path:
        return None
    path = Path(tags_config_path)
    if not path.exists():
        return None
    return load_tags_config(path)


def _default_analysis_path(run_root: Path) -> Path:
    manifest = run_root / "analyze" / "analysis-manifest.jsonl"
    if manifest.exists():
        return manifest
    return run_root / "analyze" / "knowledge-index.jsonl"


def _infer_run_root_from_review_path(path: Path) -> Path:
    parent = path.parent
    return parent.parent if parent.name == "review" else parent.parent


def _infer_run_root_from_agent_review_path(path: Path) -> Path:
    parent = path.parent
    return parent.parent if parent.name in {"agent-review", "agent_review"} else parent.parent


def _write_task_instructions(path: Path, *, tasks_path: Path) -> None:
    lines = [
        "# Agent Semantic Review Tasks",
        "",
        "宿主 agent 使用本文件夹中的 `semantic-review-tasks.jsonl` 做语义复核。",
        "",
        "规则：",
        "",
        "- 只读取每条任务里的 `extracted_text_path`。",
        "- 不读取 `path` 指向的原始文件，除非用户另行明确授权并且 privacy.yaml 允许。",
        "- 不需要配置 OPENAI_API_KEY；语义理解由宿主 agent 自己完成。",
        "- 输出 JSONL，每行一个对象，字段必须符合 `expected-output-schema.json`。",
        "",
        "建议输出位置：`results.jsonl`。",
        "",
        f"任务清单：`{tasks_path}`",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_jsonl(records: Iterable[dict[str, Any]], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    output.write_text("\n".join(lines).rstrip() + ("\n" if lines else ""), encoding="utf-8")


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _optional_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _path_key(value: Any) -> str:
    return str(value or "").replace("\\", "/").casefold()
