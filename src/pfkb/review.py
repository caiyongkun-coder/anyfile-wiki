from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from .llm_config import cloud_allowed_for_path, describe_llm_config
from .parse import choose_parser


@dataclass(frozen=True)
class ReviewItem:
    path: str
    category: str
    reason: str
    action: str
    severity: str
    access_policy: str | None = None
    policy_source: str | None = None
    policy_reason: str | None = None
    extraction_status: str | None = None
    analysis_method: str | None = None
    confidence: float | None = None
    tags: list[str] | None = None


def load_analysis_manifest(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    manifest = Path(path)
    if not manifest.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def build_review_items(
    files: Iterable[dict[str, Any]],
    latest_extracts: dict[str, dict[str, Any]],
    *,
    analysis_records: Iterable[dict[str, Any]] = (),
    llm_config: dict[str, Any] | None = None,
) -> list[ReviewItem]:
    analysis_by_path = {str(record.get("path")): record for record in analysis_records}
    llm_summary = describe_llm_config(llm_config)
    items: list[ReviewItem] = []
    for record in files:
        if record.get("is_dir"):
            continue
        path = str(record.get("path") or "")
        access_policy = str(record.get("access_policy") or "")
        latest = latest_extracts.get(path)

        if access_policy in {"deny", "metadata_only"}:
            items.append(_policy_item(record, access_policy))
            continue

        if access_policy == "no_embedding" and llm_summary["mode"] == "cloud":
            items.append(
                ReviewItem(
                    path=path,
                    category="cloud_forbidden_by_policy",
                    reason="no_embedding policy forbids cloud/semantic processing",
                    action="Use local-only review or move a less sensitive copy to an explicitly cloud-allowed folder.",
                    severity="high",
                    access_policy=access_policy,
                    policy_source=str(record.get("policy_source") or ""),
                    policy_reason=str(record.get("policy_reason") or ""),
                )
            )

        parser = choose_parser(str(record.get("extension") or ""))
        if parser is None and bool(record.get("is_read_allowed")):
            items.append(
                ReviewItem(
                    path=path,
                    category="unsupported_format",
                    reason=f"No parser is configured for extension {record.get('extension') or '(none)'}.",
                    action="Add a parser/adapter, convert the file, or tag it manually.",
                    severity="medium",
                    access_policy=access_policy,
                    policy_source=str(record.get("policy_source") or ""),
                    policy_reason=str(record.get("policy_reason") or ""),
                )
            )
            continue

        if bool(record.get("is_extract_allowed")) and latest is None:
            items.append(
                ReviewItem(
                    path=path,
                    category="not_extracted",
                    reason="File is allowed for extraction but no extraction result exists yet.",
                    action="Run pfkb extract, or decide whether this file should be skipped.",
                    severity="medium",
                    access_policy=access_policy,
                    policy_source=str(record.get("policy_source") or ""),
                    policy_reason=str(record.get("policy_reason") or ""),
                )
            )
            continue

        if latest and latest.get("status") in {"error", "skipped"}:
            items.append(
                ReviewItem(
                    path=path,
                    category="extraction_problem",
                    reason=str(latest.get("error") or latest.get("skip_reason") or latest.get("status")),
                    action="Install the needed parser, retry extraction, convert the file, or tag it manually.",
                    severity="high" if latest.get("status") == "error" else "medium",
                    access_policy=access_policy,
                    policy_source=str(record.get("policy_source") or ""),
                    policy_reason=str(record.get("policy_reason") or ""),
                    extraction_status=str(latest.get("status") or ""),
                )
            )

        analysis = analysis_by_path.get(path)
        if analysis:
            needs_human_review = bool(analysis.get("needs_human_review"))
            method = str(analysis.get("analysis_method") or "")
            if needs_human_review or method == "rules":
                items.append(
                    ReviewItem(
                        path=path,
                        category="rules_only_or_low_confidence",
                        reason=str(analysis.get("review_reason") or "rules_only_no_llm"),
                        action="Use a local LLM, manually confirm tags/summary, or leave as rules-only.",
                        severity="low" if not needs_human_review else "medium",
                        access_policy=access_policy,
                        policy_source=str(record.get("policy_source") or ""),
                        policy_reason=str(record.get("policy_reason") or ""),
                        extraction_status=str(latest.get("status") if latest else ""),
                        analysis_method=method,
                        confidence=_optional_float(analysis.get("confidence")),
                        tags=[str(tag) for tag in analysis.get("tags") or []],
                    )
                )

        if llm_summary["mode"] == "cloud" and not cloud_allowed_for_path(path, access_policy, llm_config):
            items.append(
                ReviewItem(
                    path=path,
                    category="cloud_not_authorized",
                    reason="Cloud mode is configured, but this path is not explicitly allowed for cloud processing.",
                    action="Keep it local, add an explicit cloud allowed path after risk review, or tag manually.",
                    severity="medium",
                    access_policy=access_policy,
                    policy_source=str(record.get("policy_source") or ""),
                    policy_reason=str(record.get("policy_reason") or ""),
                )
            )
    return _dedupe_items(items)


def write_review_outputs(items: list[ReviewItem], output_dir: str | Path) -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    jsonl_path = root / "human-review.jsonl"
    md_path = root / "human-review.md"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True) + "\n")
    write_review_md(items, md_path)
    return {"human_review_jsonl": jsonl_path, "human_review_md": md_path}


def write_review_md(items: list[ReviewItem], path: str | Path) -> None:
    by_category: dict[str, list[ReviewItem]] = defaultdict(list)
    for item in items:
        by_category[item.category].append(item)
    counts = Counter(item.category for item in items)
    lines = [
        "# 人工待整理清单",
        "",
        "本文件列出系统无法可靠自动处理、需要用户确认或后续模型处理的文件。",
        "",
        "它不是错误报告，而是一个诚实的工作清单：哪些文件没法读取、没法提取、只是粗标签、或者不允许发云端。",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 概览",
        "",
        f"- 待处理项：{len(items)}",
    ]
    for category, count in counts.most_common():
        lines.append(f"- `{category}`：{count}")

    for category in sorted(by_category):
        lines.extend(["", f"## {_category_label(category)}", ""])
        lines.append(_category_hint(category))
        lines.append("")
        for item in sorted(by_category[category], key=lambda entry: entry.path.lower()):
            lines.extend(
                [
                    f"### {Path(item.path).name or item.path}",
                    "",
                    f"- 路径：`{item.path}`",
                    f"- 严重程度：`{item.severity}`",
                    f"- 原因：{item.reason}",
                    f"- 建议动作：{item.action}",
                ]
            )
            if item.access_policy:
                lines.append(f"- 隐私策略：`{item.access_policy}`")
            if item.extraction_status:
                lines.append(f"- 提取状态：`{item.extraction_status}`")
            if item.analysis_method:
                lines.append(f"- 分析方式：`{item.analysis_method}`")
            if item.confidence is not None:
                lines.append(f"- 置信度：{item.confidence:.2f}")
            if item.tags:
                lines.append("- 当前标签：" + " ".join(f"`{tag}`" for tag in item.tags))
            lines.append("")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def review_stats(items: list[ReviewItem]) -> dict[str, int]:
    return dict(Counter(item.category for item in items))


def _policy_item(record: dict[str, Any], access_policy: str) -> ReviewItem:
    if access_policy == "deny":
        return ReviewItem(
            path=str(record.get("path") or ""),
            category="policy_blocked",
            reason="Privacy policy denies reading this file.",
            action="Leave it blocked, or manually tag/describe it outside the automated pipeline.",
            severity="high",
            access_policy=access_policy,
            policy_source=str(record.get("policy_source") or ""),
            policy_reason=str(record.get("policy_reason") or ""),
        )
    return ReviewItem(
        path=str(record.get("path") or ""),
        category="metadata_only",
        reason="Privacy policy allows metadata only; content must not be opened.",
        action="Confirm metadata-only treatment, or manually add safe tags without reading content.",
        severity="medium",
        access_policy=access_policy,
        policy_source=str(record.get("policy_source") or ""),
        policy_reason=str(record.get("policy_reason") or ""),
    )


def _category_label(category: str) -> str:
    labels = {
        "policy_blocked": "隐私策略阻止读取",
        "metadata_only": "只允许登记元数据",
        "cloud_forbidden_by_policy": "隐私策略禁止云端处理",
        "unsupported_format": "暂不支持的文件格式",
        "not_extracted": "尚未提取正文",
        "extraction_problem": "正文提取失败或跳过",
        "rules_only_or_low_confidence": "规则版标签或低置信度结果",
        "cloud_not_authorized": "云端未授权目录",
    }
    return labels.get(category, category)


def _category_hint(category: str) -> str:
    hints = {
        "policy_blocked": "这些文件被明确拒绝读取，系统不会打开正文。",
        "metadata_only": "这些文件只记录存在和基础属性，不读取正文。",
        "cloud_forbidden_by_policy": "这些文件即使本地可读，也不允许进入云端或语义向量处理。",
        "unsupported_format": "这些文件需要新增解析器、转换格式，或由用户手动整理。",
        "not_extracted": "这些文件理论上可提取，但还没有提取记录。",
        "extraction_problem": "这些文件提取失败或被跳过，通常需要安装解析依赖或人工处理。",
        "rules_only_or_low_confidence": "这些结果来自规则版分析，不等于大模型理解，需要用户或本地 LLM 复核。",
        "cloud_not_authorized": "云端模式下，这些路径没有显式授权，不能发送正文。",
    }
    return hints.get(category, "")


def _dedupe_items(items: list[ReviewItem]) -> list[ReviewItem]:
    seen: set[tuple[str, str]] = set()
    result: list[ReviewItem] = []
    for item in items:
        key = (item.path, item.category)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
