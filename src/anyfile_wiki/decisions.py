from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json


VALID_DECISIONS = {
    "confirm_current",
    "allow_local_llm",
    "allow_cloud_llm",
    "mark_manual",
    "ignore",
    "later",
    "keep_private",
}


@dataclass(frozen=True)
class ReviewDecision:
    path: str
    decision: str
    category: str = ""
    severity: str = ""
    manual_tags: tuple[str, ...] = ()
    note: str = ""
    decided_at: str = ""
    source_reason: str = ""
    source_action: str = ""


def load_review_decisions(path: str | Path) -> list[ReviewDecision]:
    source = Path(path)
    decisions: list[ReviewDecision] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON: {exc}") from exc
        decisions.append(_coerce_decision(payload, line_number=line_number))
    return decisions


def decision_stats(decisions: list[ReviewDecision]) -> dict[str, dict[str, int]]:
    return {
        "by_decision": dict(Counter(decision.decision for decision in decisions).most_common()),
        "by_category": dict(Counter(decision.category or "unknown" for decision in decisions).most_common()),
        "by_severity": dict(Counter(decision.severity or "unknown" for decision in decisions).most_common()),
    }


def decisions_as_dicts(decisions: list[ReviewDecision]) -> list[dict[str, Any]]:
    return [
        {
            "path": decision.path,
            "decision": decision.decision,
            "category": decision.category,
            "severity": decision.severity,
            "manual_tags": list(decision.manual_tags),
            "note": decision.note,
            "decided_at": decision.decided_at,
            "source_reason": decision.source_reason,
            "source_action": decision.source_action,
        }
        for decision in decisions
    ]


def format_decisions_summary(decisions: list[ReviewDecision]) -> str:
    stats = decision_stats(decisions)
    lines = [
        "review_decisions:",
        f"- total: {len(decisions)}",
    ]
    lines.append("by_decision:")
    _append_counts(lines, stats["by_decision"])
    lines.append("by_category:")
    _append_counts(lines, stats["by_category"])
    lines.append("by_severity:")
    _append_counts(lines, stats["by_severity"])
    return "\n".join(lines)


def write_decisions_summary_md(decisions: list[ReviewDecision], path: str | Path) -> None:
    stats = decision_stats(decisions)
    lines = [
        "# 人工批复结果摘要",
        "",
        "本文件由 `anyfile-wiki decisions` 读取 `review-decisions.jsonl` 后生成。",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        f"- 批复总数：{len(decisions)}",
        "",
        "## 按批复动作统计",
        "",
    ]
    lines.extend(_md_counts(stats["by_decision"]))
    lines.extend(["", "## 按复核类别统计", ""])
    lines.extend(_md_counts(stats["by_category"]))
    lines.extend(["", "## 批复明细", ""])
    for decision in decisions:
        lines.extend(
            [
                f"### {Path(decision.path).name or decision.path}",
                "",
                f"- 路径：`{decision.path}`",
                f"- 批复动作：`{decision.decision}`",
                f"- 复核类别：`{decision.category or 'unknown'}`",
                f"- 优先级：`{decision.severity or 'unknown'}`",
            ]
        )
        if decision.manual_tags:
            lines.append("- 人工标签：" + " ".join(f"`{tag}`" for tag in decision.manual_tags))
        if decision.note:
            lines.append(f"- 备注：{decision.note}")
        lines.append("")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _coerce_decision(payload: dict[str, Any], *, line_number: int) -> ReviewDecision:
    if not isinstance(payload, dict):
        raise ValueError(f"line {line_number}: decision record must be an object")
    path = str(payload.get("path") or "").strip()
    if not path:
        raise ValueError(f"line {line_number}: missing path")
    decision = str(payload.get("decision") or "").strip()
    if decision not in VALID_DECISIONS:
        valid = ", ".join(sorted(VALID_DECISIONS))
        raise ValueError(f"line {line_number}: unsupported decision {decision!r}; expected one of {valid}")
    manual_tags = payload.get("manual_tags") or payload.get("tags") or []
    if not isinstance(manual_tags, list):
        manual_tags = [manual_tags]
    return ReviewDecision(
        path=path,
        decision=decision,
        category=str(payload.get("category") or ""),
        severity=str(payload.get("severity") or ""),
        manual_tags=tuple(str(tag) for tag in manual_tags if str(tag)),
        note=str(payload.get("note") or ""),
        decided_at=str(payload.get("decided_at") or ""),
        source_reason=str(payload.get("source_reason") or ""),
        source_action=str(payload.get("source_action") or ""),
    )


def _append_counts(lines: list[str], counts: dict[str, int]) -> None:
    if not counts:
        lines.append("- empty: 0")
        return
    for key, count in counts.items():
        lines.append(f"- {key}: {count}")


def _md_counts(counts: dict[str, int]) -> list[str]:
    if not counts:
        return ["- empty：0"]
    return [f"- `{key}`：{count}" for key, count in counts.items()]
