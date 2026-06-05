from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import re

from .sidecars import attach_asset_ids


CLEANUP_PLAN_SCHEMA_VERSION = 1
CLEANUP_DECISION_SCHEMA_VERSION = 1

VALID_CLEANUP_DECISIONS = {"approve_recommendation", "reject", "defer", "keep"}


@dataclass(frozen=True)
class CleanupDecision:
    plan_id: str
    decision: str
    note: str = ""
    decided_at: str = ""
    target_path: str = ""


def build_archive_plan(
    asset_records: Iterable[dict[str, Any]],
    collection_records: Iterable[dict[str, Any]],
    score_records: Iterable[dict[str, Any]],
    *,
    generated_at: str | None = None,
    min_duplicate_confidence: float = 0.7,
    min_archive_score: float = 0.55,
    max_delete_risk: float = 0.35,
    include_review_required: bool = False,
) -> list[dict[str, Any]]:
    """Build a reviewable cleanup plan from sidecar signals.

    The returned records are proposals only. They never represent filesystem
    actions that can be executed without a separate human-confirmed workflow.
    """
    now = generated_at or datetime.now(timezone.utc).isoformat()
    assets = attach_asset_ids(asset_records)
    assets_by_id = {str(record.get("asset_id")): record for record in assets}
    collections_by_id = {str(record.get("asset_id")): record for record in collection_records}
    scores_by_id = {str(record.get("asset_id")): record for record in score_records}

    plan: list[dict[str, Any]] = []
    for asset in assets:
        asset_id = str(asset.get("asset_id"))
        collection = collections_by_id.get(asset_id, {})
        score = scores_by_id.get(asset_id, {})
        decision = _cleanup_decision(
            asset,
            collection,
            score,
            min_duplicate_confidence=min_duplicate_confidence,
            min_archive_score=min_archive_score,
            max_delete_risk=max_delete_risk,
            include_review_required=include_review_required,
        )
        if decision is None:
            continue
        candidate_type, recommended_action = decision
        plan.append(
            _plan_record(
                asset,
                collection,
                score,
                assets_by_id,
                candidate_type=candidate_type,
                recommended_action=recommended_action,
                generated_at=now,
            )
        )
    return sorted(
        plan,
        key=lambda item: (
            -float(item.get("priority_score") or 0.0),
            str(item.get("candidate_type") or ""),
            _path_key(item.get("path")),
        ),
    )


def write_archive_plan_outputs(
    plan_records: Iterable[dict[str, Any]],
    output_dir: str | Path,
    *,
    asset_index_path: str | Path | None = None,
    collection_index_path: str | Path | None = None,
    asset_score_path: str | Path | None = None,
) -> tuple[dict[str, Path], dict[str, Any]]:
    records = list(plan_records)
    root = Path(output_dir)
    outputs = {
        "archive_plan_jsonl": root / "archive-plan.jsonl",
        "archive_plan_md": root / "archive-plan.md",
        "archive_plan_summary_json": root / "archive-plan-summary.json",
    }
    stats = archive_plan_stats(records)
    root.mkdir(parents=True, exist_ok=True)
    _write_jsonl(records, outputs["archive_plan_jsonl"])
    write_archive_plan_report(
        records,
        outputs["archive_plan_md"],
        stats=stats,
        asset_index_path=asset_index_path,
        collection_index_path=collection_index_path,
        asset_score_path=asset_score_path,
    )
    summary = {
        "schema_version": CLEANUP_PLAN_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "sources": {
            "asset_index": str(asset_index_path) if asset_index_path else "",
            "collection_index": str(collection_index_path) if collection_index_path else "",
            "asset_score": str(asset_score_path) if asset_score_path else "",
        },
        "outputs": {name: str(path) for name, path in outputs.items()},
        "safety": {
            "proposed_only": True,
            "executes_filesystem_actions": False,
            "requires_human_confirmation": True,
        },
    }
    outputs["archive_plan_summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return outputs, stats


def load_cleanup_decisions(path: str | Path) -> list[CleanupDecision]:
    source = Path(path)
    decisions: list[CleanupDecision] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
        decisions.append(_coerce_cleanup_decision(payload, line_number=line_number))
    return decisions


def cleanup_decisions_as_dicts(decisions: Iterable[CleanupDecision]) -> list[dict[str, Any]]:
    return [
        {
            "plan_id": decision.plan_id,
            "decision": decision.decision,
            "note": decision.note,
            "decided_at": decision.decided_at,
            "target_path": decision.target_path,
        }
        for decision in decisions
    ]


def build_cleanup_decision_actions(
    plan_records: Iterable[dict[str, Any]],
    decisions: Iterable[CleanupDecision],
    *,
    generated_at: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    now = generated_at or datetime.now(timezone.utc).isoformat()
    plans = list(plan_records)
    plan_by_id = {_text(plan.get("plan_id")): plan for plan in plans}
    actions: list[dict[str, Any]] = []
    rollback_manifest: list[dict[str, Any]] = []

    for decision in decisions:
        plan = plan_by_id.get(decision.plan_id)
        if plan is None:
            raise ValueError(f"cleanup decision references unknown plan_id: {decision.plan_id}")
        action = _cleanup_action_record(plan, decision, generated_at=now)
        actions.append(action)
        if decision.decision == "approve_recommendation":
            rollback_manifest.append(_rollback_manifest_draft(plan, action, generated_at=now))
    return actions, rollback_manifest


def cleanup_decision_stats(actions: Iterable[dict[str, Any]], rollback_manifest: Iterable[dict[str, Any]]) -> dict[str, Any]:
    action_items = list(actions)
    manifest_items = list(rollback_manifest)
    by_action = Counter(_text(action.get("action")) or "unknown" for action in action_items)
    by_decision = Counter(_text(action.get("cleanup_decision")) or "unknown" for action in action_items)
    by_candidate_type = Counter(_text(action.get("candidate_type")) or "unknown" for action in action_items)
    return {
        "total_actions": len(action_items),
        "rollback_manifest_drafts": len(manifest_items),
        "requires_confirmation": sum(1 for action in action_items if bool(action.get("requires_confirmation"))),
        "execution_allowed": sum(1 for action in action_items if bool(action.get("execution_allowed"))),
        "by_action": dict(by_action),
        "by_decision": dict(by_decision),
        "by_candidate_type": dict(by_candidate_type),
    }


def write_cleanup_decision_outputs(
    plan_records: Iterable[dict[str, Any]],
    decisions: Iterable[CleanupDecision],
    output_dir: str | Path,
    *,
    plan_path: str | Path | None = None,
    decisions_path: str | Path | None = None,
) -> tuple[dict[str, Path], dict[str, Any]]:
    decision_items = list(decisions)
    actions, rollback_manifest = build_cleanup_decision_actions(plan_records, decision_items)
    root = Path(output_dir)
    outputs = {
        "cleanup_actions_jsonl": root / "cleanup-actions.jsonl",
        "rollback_manifest_draft_jsonl": root / "rollback-manifest-draft.jsonl",
        "cleanup_decision_plan_md": root / "cleanup-decision-plan.md",
        "cleanup_decisions_summary_json": root / "cleanup-decisions-summary.json",
    }
    root.mkdir(parents=True, exist_ok=True)
    _write_jsonl(actions, outputs["cleanup_actions_jsonl"])
    _write_jsonl(rollback_manifest, outputs["rollback_manifest_draft_jsonl"])
    stats = cleanup_decision_stats(actions, rollback_manifest)
    write_cleanup_decision_plan(
        actions,
        rollback_manifest,
        outputs["cleanup_decision_plan_md"],
        stats=stats,
        plan_path=plan_path,
        decisions_path=decisions_path,
    )
    summary = {
        "schema_version": CLEANUP_DECISION_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decisions": cleanup_decisions_as_dicts(decision_items),
        "stats": stats,
        "sources": {
            "archive_plan": str(plan_path) if plan_path else "",
            "cleanup_decisions": str(decisions_path) if decisions_path else "",
        },
        "outputs": {name: str(path) for name, path in outputs.items()},
        "safety": {
            "draft_only": True,
            "executes_filesystem_actions": False,
            "requires_final_confirmation": True,
        },
    }
    outputs["cleanup_decisions_summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return outputs, stats


def write_cleanup_decision_plan(
    actions: Iterable[dict[str, Any]],
    rollback_manifest: Iterable[dict[str, Any]],
    path: str | Path,
    *,
    stats: dict[str, Any] | None = None,
    plan_path: str | Path | None = None,
    decisions_path: str | Path | None = None,
) -> None:
    action_items = list(actions)
    manifest_items = list(rollback_manifest)
    summary = stats or cleanup_decision_stats(action_items, manifest_items)
    lines = [
        "# 清理候选批复执行草案",
        "",
        "本文件由 `anyfile-wiki cleanup-decisions` 读取清理候选批复后生成。",
        "它只生成执行草案和回滚 manifest 草案，不会移动、删除、重命名任何原始文件。",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
    ]
    if plan_path:
        lines.append(f"候选计划：`{plan_path}`")
    if decisions_path:
        lines.append(f"批复文件：`{decisions_path}`")
    lines.extend(
        [
            "",
            "## 安全边界",
            "",
            "- 所有动作都是 `draft_only`，`execution_allowed` 必须是 `false`。",
            "- 任何真实移动、删除、重命名都必须二次确认。",
            "- 已批复的归档/删除也只会进入 `rollback-manifest-draft.jsonl`，不是可执行脚本。",
            "- 回滚草案会记录 `original_path`、`target_path` 和 `intended_operation`，但 `rollback_ready` 仍为 `false`。",
            "",
            "## 概览",
            "",
            f"- 草案动作总数：{summary.get('total_actions', 0)}",
            f"- 回滚 manifest 草案：{summary.get('rollback_manifest_drafts', 0)}",
            f"- 需要最终确认：{summary.get('requires_confirmation', 0)}",
            f"- 允许执行动作：{summary.get('execution_allowed', 0)}",
            "",
            "## 按动作统计",
            "",
        ]
    )
    for action, count in sorted((summary.get("by_action") or {}).items()):
        lines.append(f"- `{action}`：{count}")
    lines.extend(["", "## 草案动作明细", ""])
    if not action_items:
        lines.append("暂无批复动作。")
    for index, action in enumerate(action_items, start=1):
        lines.extend(
            [
                f"### {index}. {_text(action.get('title')) or _file_name(action.get('path')) or _text(action.get('plan_id'))}",
                "",
                f"- 路径：`{_text(action.get('path'))}`",
                f"- 候选类型：`{_text(action.get('candidate_type'))}`",
                f"- 人工批复：`{_text(action.get('cleanup_decision'))}`",
                f"- 草案动作：`{_text(action.get('action'))}`",
                f"- 来源建议：`{_text(action.get('source_recommended_action'))}`",
                f"- 真实文件操作：`{_text(action.get('proposed_operation'))}`",
                f"- 安全状态：`{_text(action.get('safety_status'))}`",
                f"- 允许执行：{'是' if bool(action.get('execution_allowed')) else '否'}",
                f"- 需要最终确认：{'是' if bool(action.get('requires_confirmation')) else '否'}",
                f"- 回滚 manifest：`{_text(action.get('rollback_manifest_id'))}`",
                f"- 目标提示：`{_text(action.get('target_path'))}`",
                f"- 下一步：{_text(action.get('next_step'))}",
            ]
        )
        if action.get("note"):
            lines.append(f"- 备注：{_text(action.get('note'))}")
        lines.append("")
    lines.extend(["## 回滚 manifest 草案", ""])
    if not manifest_items:
        lines.append("暂无需要回滚草案的已批复动作。")
    for item in manifest_items:
        lines.extend(
            [
                f"### {_text(item.get('manifest_id'))}",
                "",
                f"- 原路径：`{_text(item.get('original_path'))}`",
                f"- 目标路径：`{_text(item.get('target_path'))}`",
                f"- 预期动作：`{_text(item.get('intended_operation'))}`",
                f"- 允许执行：{'是' if bool(item.get('execution_allowed')) else '否'}",
                f"- 回滚就绪：{'是' if bool(item.get('rollback_ready')) else '否'}",
                "",
            ]
        )
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def archive_plan_stats(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(records)
    by_type = Counter(str(record.get("candidate_type") or "unknown") for record in items)
    by_action = Counter(str(record.get("recommended_action") or "unknown") for record in items)
    by_policy = Counter(str(record.get("archive_policy") or "unknown") for record in items)
    return {
        "total_candidates": len(items),
        "duplicate_candidates": sum(1 for item in items if float(item.get("duplicate_confidence") or 0.0) >= 0.7),
        "archive_candidates": by_type.get("archive", 0),
        "delete_candidates": by_type.get("delete", 0),
        "review_first_candidates": by_type.get("review_first", 0),
        "requires_confirmation": sum(1 for item in items if bool(item.get("requires_confirmation"))),
        "by_candidate_type": dict(by_type),
        "by_recommended_action": dict(by_action),
        "by_archive_policy": dict(by_policy),
    }


def write_archive_plan_report(
    records: Iterable[dict[str, Any]],
    path: str | Path,
    *,
    stats: dict[str, Any] | None = None,
    asset_index_path: str | Path | None = None,
    collection_index_path: str | Path | None = None,
    asset_score_path: str | Path | None = None,
) -> None:
    items = list(records)
    summary = stats or archive_plan_stats(items)
    lines = [
        "# 安全清理候选计划",
        "",
        "本计划只整理索引层建议，不会移动、删除、重命名任何原始文件。",
        "所有候选都需要人工复核；如果未来执行真实文件动作，必须先生成独立回滚 manifest。",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
    ]
    if asset_index_path:
        lines.append(f"资产索引：`{asset_index_path}`")
    if collection_index_path:
        lines.append(f"资料族索引：`{collection_index_path}`")
    if asset_score_path:
        lines.append(f"评分索引：`{asset_score_path}`")
    lines.extend(
        [
            "",
            "## 概览",
            "",
            f"- 候选总数：{summary.get('total_candidates', 0)}",
            f"- 疑似重复信号：{summary.get('duplicate_candidates', 0)}",
            f"- 归档候选：{summary.get('archive_candidates', 0)}",
            f"- 删除复核候选：{summary.get('delete_candidates', 0)}",
            f"- 先复核候选：{summary.get('review_first_candidates', 0)}",
            "",
            "## 建议动作统计",
            "",
        ]
    )
    for action, count in sorted((summary.get("by_recommended_action") or {}).items()):
        lines.append(f"- `{action}`：{count}")
    if not items:
        lines.extend(["", "## 候选明细", "", "暂无候选。"])
    else:
        lines.extend(["", "## 候选明细", ""])
        for item in items:
            title = _text(item.get("title")) or _file_name(item.get("path")) or _text(item.get("asset_id"))
            lines.extend(
                [
                    f"### {title}",
                    "",
                    f"- 路径：`{_text(item.get('path'))}`",
                    f"- 候选类型：`{_text(item.get('candidate_type'))}`",
                    f"- 建议动作：`{_text(item.get('recommended_action'))}`",
                    f"- 真实文件操作：`{_text(item.get('proposed_operation'))}`",
                    f"- 归档策略：`{_text(item.get('archive_policy'))}`",
                    (
                        "- 分数："
                        f"archive={item.get('archive_score')}，"
                        f"retention={item.get('retention_score')}，"
                        f"delete_risk={item.get('delete_risk_score')}，"
                        f"duplicate={item.get('duplicate_confidence')}"
                    ),
                ]
            )
            virtual_path = _text(item.get("virtual_path"))
            if virtual_path:
                lines.append(f"- 虚拟路径：`{virtual_path}`")
            canonical_path = _text(item.get("canonical_path"))
            if canonical_path and canonical_path != _text(item.get("path")):
                lines.append(f"- 参考主文件：`{canonical_path}`")
            destination_hint = _text(item.get("destination_hint"))
            if destination_hint:
                lines.append(f"- 目标提示：`{destination_hint}`")
            reasons = _string_list(item.get("reasons"))
            if reasons:
                lines.append("- 原因：" + "；".join(reasons))
            lines.append(f"- 回滚要求：{_text(item.get('rollback_hint'))}")
            lines.append("")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _cleanup_decision(
    asset: dict[str, Any],
    collection: dict[str, Any],
    score: dict[str, Any],
    *,
    min_duplicate_confidence: float,
    min_archive_score: float,
    max_delete_risk: float,
    include_review_required: bool,
) -> tuple[str, str] | None:
    if _bool(asset.get("never_delete")) or _bool(score.get("never_delete")):
        return None
    review_required = (
        _bool(asset.get("needs_human_review"))
        or _bool(asset.get("review_requires_confirmation"))
        or _bool(collection.get("review_required"))
        or _text(score.get("archive_policy")) == "review"
    )
    if review_required:
        return ("review_first", "manual_review_before_cleanup") if include_review_required else None

    duplicate_confidence = _float(collection.get("duplicate_confidence"))
    archive_policy = _text(score.get("archive_policy"))
    archive_score = _float(score.get("archive_score"))
    delete_risk = _float(score.get("delete_risk_score"), default=1.0)

    if (
        duplicate_confidence >= min_duplicate_confidence
        and archive_policy == "delete_candidate"
        and delete_risk <= max_delete_risk
    ):
        return "delete", "review_delete_duplicate"
    if duplicate_confidence >= min_duplicate_confidence:
        return "duplicate", "review_duplicate_candidate"
    if archive_policy == "delete_candidate" and delete_risk <= max_delete_risk:
        return "delete", "review_delete_candidate"
    if archive_policy in {"nas", "cold"} and archive_score >= min_archive_score:
        return "archive", f"propose_{archive_policy}_archive"
    return None


def _plan_record(
    asset: dict[str, Any],
    collection: dict[str, Any],
    score: dict[str, Any],
    assets_by_id: dict[str, dict[str, Any]],
    *,
    candidate_type: str,
    recommended_action: str,
    generated_at: str,
) -> dict[str, Any]:
    asset_id = _text(asset.get("asset_id"))
    canonical_asset_id = _text(collection.get("canonical_asset_id"))
    canonical_asset = assets_by_id.get(canonical_asset_id, {})
    archive_score = _float(score.get("archive_score"))
    retention_score = _float(score.get("retention_score"))
    delete_risk_score = _float(score.get("delete_risk_score"), default=1.0)
    duplicate_confidence = _float(collection.get("duplicate_confidence"))
    priority = _priority_score(candidate_type, archive_score, delete_risk_score, duplicate_confidence)
    destination_hint = _destination_hint(candidate_type, recommended_action, asset, collection)
    reasons = _unique_strings(
        [
            *_string_list(score.get("score_reasons")),
            _text(collection.get("duplicate_reason")),
            _text(collection.get("merge_reason")),
            f"archive_policy:{_text(score.get('archive_policy'))}" if score.get("archive_policy") else "",
        ]
    )
    return {
        "schema_version": CLEANUP_PLAN_SCHEMA_VERSION,
        "plan_id": _plan_id(asset_id, recommended_action),
        "asset_id": asset_id,
        "path": _text(asset.get("path")),
        "title": _text(asset.get("title")) or _file_name(asset.get("path")),
        "candidate_type": candidate_type,
        "recommended_action": recommended_action,
        "proposed_operation": "none",
        "safety_status": "proposed_only",
        "execution_allowed": False,
        "requires_confirmation": True,
        "rollback_manifest_required": True,
        "rollback_hint": "未来若执行真实移动/删除，必须先记录 original_path、target_path、action 和确认人。",
        "archive_policy": _text(score.get("archive_policy")),
        "usage_score": _float(score.get("usage_score")),
        "retention_score": retention_score,
        "archive_score": archive_score,
        "delete_risk_score": delete_risk_score,
        "duplicate_confidence": duplicate_confidence,
        "priority_score": priority,
        "reasons": reasons,
        "collection_id": _text(collection.get("collection_id")),
        "collection_title": _text(collection.get("collection_title")),
        "virtual_path": _text(collection.get("virtual_path")),
        "relation_type": _text(collection.get("relation_type")),
        "canonical_asset_id": canonical_asset_id,
        "canonical_path": _text(canonical_asset.get("path")),
        "destination_hint": destination_hint,
        "generated_at": generated_at,
    }


def _priority_score(candidate_type: str, archive_score: float, delete_risk_score: float, duplicate_confidence: float) -> float:
    score = archive_score * 0.4 + duplicate_confidence * 0.35 + (1.0 - delete_risk_score) * 0.25
    if candidate_type == "delete":
        score += 0.12
    elif candidate_type == "duplicate":
        score += 0.08
    return round(max(0.0, min(score, 1.0)), 2)


def _destination_hint(
    candidate_type: str,
    recommended_action: str,
    asset: dict[str, Any],
    collection: dict[str, Any],
) -> str:
    file_name = _file_name(asset.get("path")) or _text(asset.get("asset_id"))
    collection_title = _safe_segment(collection.get("collection_title")) or "uncategorized"
    if recommended_action == "propose_cold_archive":
        return f"cold-archive/{collection_title}/{file_name}"
    if recommended_action == "propose_nas_archive":
        return f"nas-archive/{collection_title}/{file_name}"
    if candidate_type == "duplicate":
        return f"manual-review/duplicates/{collection_title}/{file_name}"
    if candidate_type == "delete":
        return f"manual-review/delete-candidates/{collection_title}/{file_name}"
    if candidate_type == "review_first":
        return f"manual-review/needs-context/{collection_title}/{file_name}"
    return ""


def _plan_id(asset_id: str, recommended_action: str) -> str:
    digest = hashlib.sha256(f"{asset_id}|{recommended_action}".encode("utf-8")).hexdigest()
    return f"cleanup:plan-sha256:{digest}"


def _coerce_cleanup_decision(payload: dict[str, Any], *, line_number: int) -> CleanupDecision:
    if not isinstance(payload, dict):
        raise ValueError(f"line {line_number}: cleanup decision record must be an object")
    plan_id = _text(payload.get("plan_id")).strip()
    if not plan_id:
        raise ValueError(f"line {line_number}: missing plan_id")
    decision = _text(payload.get("decision")).strip()
    if decision not in VALID_CLEANUP_DECISIONS:
        valid = ", ".join(sorted(VALID_CLEANUP_DECISIONS))
        raise ValueError(f"line {line_number}: unsupported cleanup decision {decision!r}; expected one of {valid}")
    return CleanupDecision(
        plan_id=plan_id,
        decision=decision,
        note=_text(payload.get("note")),
        decided_at=_text(payload.get("decided_at")),
        target_path=_text(payload.get("target_path")),
    )


def _cleanup_action_record(
    plan: dict[str, Any],
    decision: CleanupDecision,
    *,
    generated_at: str,
) -> dict[str, Any]:
    action = _cleanup_action_name(plan, decision.decision)
    target_path = decision.target_path or _text(plan.get("destination_hint"))
    rollback_manifest_id = ""
    if decision.decision == "approve_recommendation":
        rollback_manifest_id = _rollback_manifest_id(decision.plan_id)
    return {
        "schema_version": CLEANUP_DECISION_SCHEMA_VERSION,
        "action_id": _cleanup_action_id(decision.plan_id, decision.decision),
        "plan_id": decision.plan_id,
        "asset_id": _text(plan.get("asset_id")),
        "path": _text(plan.get("path")),
        "title": _text(plan.get("title")) or _file_name(plan.get("path")),
        "candidate_type": _text(plan.get("candidate_type")),
        "cleanup_decision": decision.decision,
        "action": action,
        "source_recommended_action": _text(plan.get("recommended_action")),
        "proposed_operation": "none",
        "safety_status": "draft_only",
        "execution_allowed": False,
        "requires_confirmation": True,
        "rollback_manifest_required": True,
        "rollback_manifest_id": rollback_manifest_id,
        "target_path": target_path,
        "destination_hint": _text(plan.get("destination_hint")),
        "reason": _cleanup_action_reason(plan, decision.decision),
        "next_step": _cleanup_next_step(action),
        "note": decision.note,
        "decided_at": decision.decided_at,
        "generated_at": generated_at,
    }


def _cleanup_action_name(plan: dict[str, Any], decision: str) -> str:
    if decision == "reject":
        return "reject_cleanup_candidate"
    if decision == "defer":
        return "defer_cleanup_candidate"
    if decision == "keep":
        return "keep_asset"
    candidate_type = _text(plan.get("candidate_type"))
    if candidate_type == "archive":
        return "draft_archive"
    if candidate_type == "delete":
        return "draft_delete_review"
    if candidate_type == "duplicate":
        return "draft_duplicate_resolution"
    if candidate_type == "review_first":
        return "draft_manual_review_before_cleanup"
    return "draft_cleanup_recommendation"


def _cleanup_action_reason(plan: dict[str, Any], decision: str) -> str:
    if decision == "reject":
        return "人类拒绝该清理候选；后续不应自动归档、删除或去重。"
    if decision == "defer":
        return "人类选择稍后处理；该候选应保留在下一轮复核上下文中。"
    if decision == "keep":
        return "人类确认保留该资产；后续应降低清理建议优先级。"
    recommended = _text(plan.get("recommended_action"))
    return f"人类批准把 `{recommended}` 转成执行草案；仍需最终确认，不能直接操作源文件。"


def _cleanup_next_step(action: str) -> str:
    if action == "reject_cleanup_candidate":
        return "记录拒绝原因，并在后续清理计划中降低该候选优先级。"
    if action == "defer_cleanup_candidate":
        return "保留候选，等待下一次人工复核。"
    if action == "keep_asset":
        return "把该资产作为保留信号写入后续评分或人工标签。"
    return "复核 rollback-manifest-draft.jsonl；确认 original_path、target_path、intended_operation 后，再进入单独的最终确认流程。"


def _rollback_manifest_draft(
    plan: dict[str, Any],
    action: dict[str, Any],
    *,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": CLEANUP_DECISION_SCHEMA_VERSION,
        "manifest_id": _text(action.get("rollback_manifest_id")),
        "plan_id": _text(plan.get("plan_id")),
        "asset_id": _text(plan.get("asset_id")),
        "original_path": _text(plan.get("path")),
        "target_path": _text(action.get("target_path")),
        "intended_operation": _intended_operation(plan),
        "source_recommended_action": _text(plan.get("recommended_action")),
        "proposed_operation": "none",
        "safety_status": "draft_only",
        "execution_allowed": False,
        "requires_final_confirmation": True,
        "rollback_ready": False,
        "confirmed_by": "",
        "confirmed_at": "",
        "created_at": generated_at,
        "rollback_hint": "最终确认前必须补齐执行人、确认时间和真实目标路径；本草案不能直接执行。",
    }


def _intended_operation(plan: dict[str, Any]) -> str:
    candidate_type = _text(plan.get("candidate_type"))
    if candidate_type == "archive":
        return "archive"
    if candidate_type == "delete":
        return "delete"
    if candidate_type == "duplicate":
        return "deduplicate"
    if candidate_type == "review_first":
        return "manual_review"
    return "cleanup"


def _cleanup_action_id(plan_id: str, decision: str) -> str:
    digest = hashlib.sha256(f"{plan_id}|{decision}|cleanup-action".encode("utf-8")).hexdigest()
    return f"cleanup:action-sha256:{digest}"


def _rollback_manifest_id(plan_id: str) -> str:
    digest = hashlib.sha256(f"{plan_id}|rollback-manifest-draft".encode("utf-8")).hexdigest()
    return f"cleanup:rollback-sha256:{digest}"


def _write_jsonl(records: list[dict[str, Any]], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    output.write_text("\n".join(lines).rstrip() + ("\n" if lines else ""), encoding="utf-8")


def _safe_segment(value: Any) -> str:
    text = _text(value).strip() or "untitled"
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    return text.strip("._ ")[:80]


def _file_name(value: Any) -> str:
    path = _text(value).replace("\\", "/")
    return Path(path).name


def _path_key(value: Any) -> str:
    return _text(value).replace("\\", "/").casefold()


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


def _float(value: Any, *, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "y"}
    return bool(value)
