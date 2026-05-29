from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from .html import write_knowledge_browser_html
from .sidecars import ASSET_ID_STRATEGY, asset_id_for_path, attach_asset_ids, write_sidecar_outputs
from .tags import load_tags_config


ASSET_SCHEMA_VERSION = 1

ASSET_STATUS_LABELS = {
    "active": "正常资产 / Active",
    "confirmed": "人工确认 / Confirmed",
    "manual_reviewed": "人工整理 / Manual reviewed",
    "local_llm_queue": "本地 LLM 队列 / Local LLM queue",
    "cloud_candidate": "云端候选 / Cloud candidate",
    "cloud_authorization_conflict": "云端授权冲突 / Cloud conflict",
    "ignore_candidate": "忽略候选 / Ignore candidate",
    "deferred": "稍后复核 / Deferred",
    "private_metadata_only": "仅保留私有元数据 / Private metadata only",
    "review_required": "需要复核 / Review required",
}

_PRIMARY_REVIEW_ACTIONS = {
    "accept_current_analysis",
    "queue_local_llm_review",
    "propose_cloud_llm_authorization",
    "apply_manual_metadata",
    "add_to_ignore_candidates",
    "defer_review",
    "keep_private_metadata_only",
}

_CLOUD_BLOCKED_CATEGORIES = {"policy_blocked", "metadata_only"}


def load_jsonl_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    records: list[dict[str, Any]] = []
    if not source.exists():
        return records
    for line_number, line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{source}:{line_number}: JSONL record must be an object")
        records.append(payload)
    return records


def build_asset_index(
    analysis_records: Iterable[dict[str, Any]],
    review_actions: Iterable[dict[str, Any]] | None = None,
    review_items: Iterable[dict[str, Any]] | None = None,
    *,
    generated_at: str | None = None,
) -> list[dict[str, Any]]:
    """Merge analysis records and human review actions into an agent-readable asset index."""
    now = generated_at or datetime.now(timezone.utc).isoformat()
    actions_by_path = _group_by_path(review_actions or [])
    items_by_path = _dedupe_by_path(review_items or [])
    seen: set[str] = set()
    assets: list[dict[str, Any]] = []

    for source_record in analysis_records:
        path = _text(source_record.get("path"))
        if not path:
            continue
        key = _path_key(path)
        item = items_by_path.get(key)
        actions = actions_by_path.get(key, [])
        assets.append(_asset_from_analysis(source_record, actions, item, generated_at=now))
        seen.add(key)

    for key, item in items_by_path.items():
        if key in seen:
            continue
        actions = actions_by_path.get(key, [])
        assets.append(_asset_from_review_item(item, actions, generated_at=now))
        seen.add(key)

    for key, actions in actions_by_path.items():
        if key in seen:
            continue
        assets.append(_asset_from_action_only(actions, generated_at=now))

    return sorted(assets, key=lambda record: _path_key(record.get("path")))


def write_asset_outputs(
    records: Iterable[dict[str, Any]],
    output_dir: str | Path,
    *,
    html_dir: str | Path | None = None,
    tags_config: dict[str, Any] | None = None,
    source_path: str | Path | None = None,
    write_sidecars: bool = True,
    sidecar_level: str = "text",
) -> dict[str, Path]:
    assets = attach_asset_ids(records)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    jsonl_path = root / "asset-index.jsonl"
    md_path = root / "asset-index.md"
    _write_jsonl(assets, jsonl_path)
    write_asset_summary_md(assets, md_path, source_path=source_path)
    outputs = {
        "asset_index_jsonl": jsonl_path,
        "asset_index_md": md_path,
    }
    if write_sidecars:
        sidecar_outputs, _stats = write_sidecar_outputs(
            assets,
            root,
            sidecar_level=sidecar_level,
            asset_index_path=jsonl_path,
        )
        outputs.update(sidecar_outputs)
    if html_dir is not None:
        outputs.update(
            write_knowledge_browser_html(
                assets,
                html_dir,
                tags_config=tags_config,
                source_path=jsonl_path,
            )
        )
    return outputs


def write_asset_outputs_from_files(
    *,
    analysis_path: str | Path,
    actions_path: str | Path,
    output_dir: str | Path,
    review_items_path: str | Path | None = None,
    html_dir: str | Path | None = None,
    tags_config: dict[str, Any] | None = None,
    write_sidecars: bool = True,
    sidecar_level: str = "text",
) -> dict[str, Path]:
    analysis_records = load_jsonl_records(analysis_path)
    review_actions = load_jsonl_records(actions_path)
    review_items = load_jsonl_records(review_items_path) if review_items_path else []
    records = build_asset_index(analysis_records, review_actions, review_items)
    return write_asset_outputs(
        records,
        output_dir,
        html_dir=html_dir,
        tags_config=tags_config,
        source_path=analysis_path,
        write_sidecars=write_sidecars,
        sidecar_level=sidecar_level,
    )


def apply_review_outputs_for_run(review_dir: str | Path) -> dict[str, str]:
    """Best-effort hook used by review-server after a human submit.

    It only activates for the standard run layout:
    <run>/analyze/knowledge-index.jsonl + <run>/review/next-actions.jsonl.
    """
    review_root = Path(review_dir)
    run_root = review_root.parent
    analysis_path = run_root / "analyze" / "knowledge-index.jsonl"
    actions_path = review_root / "next-actions.jsonl"
    review_items_path = review_root / "human-review.jsonl"
    if not analysis_path.exists() or not actions_path.exists():
        return {}

    tags_path = Path("configs/tags.example.yaml")
    tags_config = load_tags_config(str(tags_path)) if tags_path.exists() else None
    outputs = write_asset_outputs_from_files(
        analysis_path=analysis_path,
        actions_path=actions_path,
        review_items_path=review_items_path if review_items_path.exists() else None,
        output_dir=run_root / "assets",
        html_dir=run_root / "html",
        tags_config=tags_config,
    )
    return {f"applied_{name}": str(path) for name, path in outputs.items()}


def write_asset_summary_md(records: list[dict[str, Any]], path: str | Path, *, source_path: str | Path | None = None) -> None:
    by_status = Counter(_text(record.get("asset_status") or "active") for record in records)
    by_action = Counter(_text(record.get("review_action") or "none") for record in records)
    needs_confirmation = sum(1 for record in records if bool(record.get("review_requires_confirmation")))
    lines = [
        "# 数据资产索引",
        "",
        "本文件由 `anyfile-wiki assets` 生成，用来把分析结果和人工批复合并成当前资产状态。",
        "",
        "它不会移动、删除或重命名源文件；真正的文件管理动作仍需要用户或 agent 另行确认。",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
    ]
    if source_path:
        lines.append(f"来源索引：`{source_path}`")
    lines.extend(
        [
            "",
            "## 概览",
            "",
            f"- 资产总数：{len(records)}",
            f"- 需要复核：{sum(1 for record in records if bool(record.get('needs_human_review')))}",
            f"- 需要二次确认：{needs_confirmation}",
            "",
            "## 按资产状态统计",
            "",
        ]
    )
    lines.extend(_md_counts(by_status, labeler=lambda key: ASSET_STATUS_LABELS.get(key, key)))
    lines.extend(["", "## 按批复动作统计", ""])
    lines.extend(_md_counts(by_action))
    lines.extend(["", "## 资产明细", ""])
    for record in records:
        status = _text(record.get("asset_status") or "active")
        title = _text(record.get("title") or _file_name(record.get("path")) or record.get("path"))
        lines.extend(
            [
                f"### {title}",
                "",
                f"- 路径：`{_text(record.get('path'))}`",
                f"- 资产状态：{ASSET_STATUS_LABELS.get(status, status)} (`{status}`)",
                f"- 摘要：{_text(record.get('summary')) or '暂无摘要'}",
            ]
        )
        tags = _string_list(record.get("tags"))
        if tags:
            lines.append("- 标签：" + " ".join(f"`{tag}`" for tag in tags))
        if record.get("review_decision"):
            lines.append(f"- 人工批复：`{record.get('review_decision')}`")
        if record.get("review_action"):
            lines.append(f"- 后续动作：`{record.get('review_action')}`")
        if record.get("review_warning"):
            lines.append(f"- 风险提示：{record.get('review_warning')}")
        if record.get("review_next_step"):
            lines.append(f"- 下一步：{record.get('review_next_step')}")
        lines.append("")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _asset_from_analysis(
    source_record: dict[str, Any],
    actions: list[dict[str, Any]],
    review_item: dict[str, Any] | None,
    *,
    generated_at: str,
) -> dict[str, Any]:
    record = dict(source_record)
    record.setdefault("status", "ok")
    record.setdefault("title", _file_name(record.get("path")))
    record.setdefault("summary", "")
    record.setdefault("tags", [])
    record.setdefault("needs_human_review", False)
    return _apply_action_fields(record, actions, review_item, asset_source="analysis", generated_at=generated_at)


def _asset_from_review_item(
    item: dict[str, Any],
    actions: list[dict[str, Any]],
    *,
    generated_at: str,
) -> dict[str, Any]:
    path = _text(item.get("path"))
    extension = _extension(path)
    tags = _string_list(item.get("tags"))
    record = {
        "path": path,
        "output_path": "",
        "status": "ok",
        "title": _file_name(path) or path,
        "summary": _review_only_summary(item, actions),
        "tags": tags,
        "primary_tag": tags[0] if tags else "",
        "content_type": _content_type_from_extension(extension),
        "extension": extension,
        "parser": "metadata_only",
        "embedding_allowed": False,
        "char_count": 0,
        "word_count": 0,
        "line_count": 0,
        "analyzed_at": "",
        "source_extract_status": _text(item.get("extraction_status") or "review_only"),
        "analysis_method": _text(item.get("analysis_method") or "human-review"),
        "confidence": item.get("confidence") or 0,
        "needs_human_review": True,
        "review_reason": _text(item.get("category") or "review_required"),
        "rule_title": "",
        "rule_summary": "",
        "rule_tags": [],
        "key_points": [],
        "model_notes": "",
        "error": "",
    }
    return _apply_action_fields(record, actions, item, asset_source="review_only", generated_at=generated_at)


def _asset_from_action_only(actions: list[dict[str, Any]], *, generated_at: str) -> dict[str, Any]:
    primary = _primary_action(actions)
    path = _text(primary.get("path"))
    item = {
        "path": path,
        "category": _text(primary.get("category") or "action_only"),
        "severity": _text(primary.get("severity")),
        "reason": _text(primary.get("reason")),
        "action": _text(primary.get("next_step")),
        "tags": [],
    }
    return _asset_from_review_item(item, actions, generated_at=generated_at)


def _apply_action_fields(
    record: dict[str, Any],
    actions: list[dict[str, Any]],
    review_item: dict[str, Any] | None,
    *,
    asset_source: str,
    generated_at: str,
) -> dict[str, Any]:
    primary = _primary_action(actions)
    manual_tags = _manual_tags(actions)
    category = _text(primary.get("category") or (review_item or {}).get("category"))
    status, warning = _status_for_action(primary, category)
    fallback_needs_review = bool(record.get("needs_human_review"))
    needs_review = _needs_review_for_status(status, fallback=fallback_needs_review)
    all_tags = _unique_strings(
        [
            *_string_list(record.get("tags")),
            *manual_tags,
            *_review_tags(status, category),
        ]
    )

    record["tags"] = all_tags
    record["primary_tag"] = _text(record.get("primary_tag") or (all_tags[0] if all_tags else ""))
    record["asset_id"] = _text(record.get("asset_id")) or asset_id_for_path(record.get("path"))
    record["asset_id_strategy"] = _text(record.get("asset_id_strategy")) or ASSET_ID_STRATEGY
    record["asset_schema_version"] = ASSET_SCHEMA_VERSION
    record["asset_generated_at"] = generated_at
    record["asset_source"] = asset_source
    record["asset_status"] = status
    record["asset_status_label"] = ASSET_STATUS_LABELS.get(status, status)
    record["needs_human_review"] = needs_review
    if status != "active":
        record["review_reason"] = _review_reason_for_status(status, record.get("review_reason"))
    record["review_decision"] = _text(primary.get("source_decision"))
    record["review_action"] = _text(primary.get("action"))
    record["review_action_title"] = _text(primary.get("title"))
    record["review_category"] = category
    record["review_severity"] = _text(primary.get("severity") or (review_item or {}).get("severity"))
    record["review_privacy_level"] = _text(primary.get("privacy_level"))
    record["review_requires_confirmation"] = bool(primary.get("requires_confirmation")) or bool(warning)
    record["review_note"] = _text(primary.get("note"))
    record["review_decided_at"] = _text(primary.get("decided_at"))
    record["review_next_step"] = _text(primary.get("next_step"))
    record["review_warning"] = warning
    record["manual_tags"] = manual_tags
    record["review_source_reason"] = _text((review_item or {}).get("reason"))
    record["review_source_action"] = _text((review_item or {}).get("action"))
    record["accepted_tags"] = all_tags if status in {"confirmed", "manual_reviewed"} else []
    return record


def _status_for_action(action: dict[str, Any], category: str) -> tuple[str, str]:
    name = _text(action.get("action"))
    if not name:
        return "review_required" if category else "active", ""
    if name == "accept_current_analysis":
        return "confirmed", ""
    if name == "queue_local_llm_review":
        return "local_llm_queue", ""
    if name == "propose_cloud_llm_authorization":
        if category in _CLOUD_BLOCKED_CATEGORIES:
            return "cloud_authorization_conflict", "隐私策略阻止读取的文件不能直接进入云端候选；必须先修改隐私配置，并再次确认风险。"
        return "cloud_candidate", ""
    if name in {"apply_manual_metadata", "record_manual_tags"}:
        return "manual_reviewed", ""
    if name == "add_to_ignore_candidates":
        return "ignore_candidate", ""
    if name == "defer_review":
        return "deferred", ""
    if name == "keep_private_metadata_only":
        return "private_metadata_only", ""
    return "review_required", ""


def _needs_review_for_status(status: str, *, fallback: bool) -> bool:
    if status in {"confirmed", "manual_reviewed", "private_metadata_only"}:
        return False
    if status == "active":
        return fallback
    return True


def _review_reason_for_status(status: str, fallback: Any) -> str:
    reasons = {
        "confirmed": "human_confirmed_current_analysis",
        "manual_reviewed": "human_manual_metadata",
        "local_llm_queue": "queued_for_local_llm_review",
        "cloud_candidate": "cloud_llm_authorization_candidate",
        "cloud_authorization_conflict": "cloud_llm_authorization_conflicts_with_privacy_policy",
        "ignore_candidate": "human_ignore_candidate_requires_confirmation",
        "deferred": "human_deferred_review",
        "private_metadata_only": "human_keep_private_metadata_only",
        "review_required": "human_review_required",
    }
    return reasons.get(status) or _text(fallback)


def _review_tags(status: str, category: str) -> list[str]:
    tags = ["topic/human_review"] if status != "active" else []
    if status in {"local_llm_queue", "cloud_candidate", "cloud_authorization_conflict", "ignore_candidate", "deferred", "review_required"}:
        tags.append("workflow/waiting_review")
    elif status in {"confirmed", "manual_reviewed", "private_metadata_only"}:
        tags.append("workflow/active")
    if status == "cloud_authorization_conflict":
        tags.append("topic/llm_policy")
    if category == "policy_blocked":
        tags.append("sensitivity/credential")
    return tags


def _review_only_summary(item: dict[str, Any], actions: list[dict[str, Any]]) -> str:
    primary = _primary_action(actions)
    status, warning = _status_for_action(primary, _text(item.get("category")))
    pieces = []
    if status != "review_required":
        pieces.append(f"人工批复状态：{ASSET_STATUS_LABELS.get(status, status)}。")
    reason = _text(item.get("reason"))
    if reason:
        pieces.append(f"进入复核的原因：{reason}")
    next_step = _text(primary.get("next_step") or item.get("action"))
    if next_step:
        pieces.append(f"下一步：{next_step}")
    if warning:
        pieces.append(f"风险提示：{warning}")
    return " ".join(pieces).strip()


def _group_by_path(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        path = _text(record.get("path"))
        if path:
            grouped[_path_key(path)].append(record)
    return dict(grouped)


def _dedupe_by_path(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for record in records:
        path = _text(record.get("path"))
        if path:
            deduped[_path_key(path)] = record
    return deduped


def _primary_action(actions: list[dict[str, Any]]) -> dict[str, Any]:
    for action in actions:
        if _text(action.get("action")) in _PRIMARY_REVIEW_ACTIONS:
            return action
    return actions[0] if actions else {}


def _manual_tags(actions: list[dict[str, Any]]) -> list[str]:
    tags: list[str] = []
    for action in actions:
        tags.extend(_string_list(action.get("manual_tags")))
    return _unique_strings(tags)


def _write_jsonl(records: list[dict[str, Any]], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    output.write_text("\n".join(lines).rstrip() + ("\n" if lines else ""), encoding="utf-8")


def _md_counts(counts: Counter, *, labeler=None) -> list[str]:
    if not counts:
        return ["- 空：0"]
    lines: list[str] = []
    for key, count in counts.most_common():
        label = labeler(key) if labeler else key
        lines.append(f"- {label} (`{key}`)：{count}")
    return lines


def _path_key(value: Any) -> str:
    return _text(value).replace("\\", "/").casefold()


def _file_name(value: Any) -> str:
    path = _text(value).replace("\\", "/")
    return Path(path).name


def _extension(value: Any) -> str:
    return Path(_text(value).replace("\\", "/")).suffix.lower()


def _content_type_from_extension(extension: str) -> str:
    if extension in {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".cs", ".cpp", ".c", ".h"}:
        return "code"
    if extension in {".yaml", ".yml", ".json", ".toml", ".ini", ".env"}:
        return "config"
    if extension in {".md", ".txt", ".doc", ".docx", ".pdf", ".rtf"}:
        return "document"
    return "file"


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_text(item).strip() for item in value if _text(item).strip()]
    text = _text(value).strip()
    return [text] if text else []


def _unique_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
