from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from .llm_config import cloud_allowed_for_path, describe_llm_config
from .parse import choose_parser
from .review_ui import write_human_review_html


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
                    reason="隐私策略为 `no_embedding`，禁止云端处理或语义向量化。",
                    action="保持本地处理；如确实需要云端复核，请先移动低敏副本到显式授权目录，并重新确认云端风险。",
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
                    reason=f"当前没有针对扩展名 `{record.get('extension') or '(none)'}` 的解析器。",
                    action="新增解析器或转换文件格式；短期内也可以由用户手动补充说明和标签。",
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
                    reason="隐私策略允许提取正文，但当前还没有提取结果。",
                    action="运行 `anyfile-wiki extract`；如果这个文件暂时不重要，可以先保留在待整理清单里。",
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
                    action="安装缺失解析依赖、重试提取、转换格式，或由用户手动补充说明和标签。",
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
                review_reason = str(analysis.get("review_reason") or "rules_only_no_llm")
                items.append(
                    ReviewItem(
                        path=path,
                        category="rules_only_or_low_confidence",
                        reason=f"{_analysis_review_reason_label(review_reason)}（`{review_reason}`）",
                        action="优先使用本地 LLM 复核；也可以人工确认摘要和标签。暂不处理时，保留规则版结果即可。",
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
                    reason="当前配置为云端模式，但这个路径没有被显式授权，正文不能发送到云端。",
                    action="保持本地处理；如果确认低敏且愿意承担风险，再把目录加入云端授权路径；也可以人工整理。",
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
    html_path = write_human_review_html(items, root, source_path=jsonl_path)
    return {"human_review_jsonl": jsonl_path, "human_review_md": md_path, "human_review_html": html_path}


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
        "## 阅读说明",
        "",
        "- 这个清单用于人工审核，不代表文件一定有问题。",
        "- `严重程度` 只是排序提示：high 优先看，medium 正常看，low 可以稍后抽查。",
        "- `原因` 说明系统为什么把文件放进清单；`建议动作` 说明下一步怎么处理。",
        "- `当前标签` 是规则版标签，不等于大模型已经理解文件内容。",
        "- 后续会保留 Markdown，同时增加 HTML 交互版；当前 Markdown 只负责记录和审阅，不会修改隐私配置。",
        "",
        "## 概览",
        "",
        f"- 待处理项：{len(items)}",
    ]
    for category, count in counts.most_common():
        lines.append(f"- {_category_label(category)}（`{category}`）：{count}")

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
                    f"- 严重程度：{_severity_label(item.severity)}（`{item.severity}`）",
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
                lines.append("- 当前标签：" + " ".join(_format_tag(tag) for tag in item.tags))
            lines.append("")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def review_stats(items: list[ReviewItem]) -> dict[str, int]:
    return dict(Counter(item.category for item in items))


def _policy_item(record: dict[str, Any], access_policy: str) -> ReviewItem:
    if access_policy == "deny":
        return ReviewItem(
            path=str(record.get("path") or ""),
            category="policy_blocked",
            reason="隐私策略明确拒绝读取这个文件。",
            action="保持阻止读取；如果需要纳入知识库，请在自动流程之外手动补充安全摘要或标签。",
            severity="high",
            access_policy=access_policy,
            policy_source=str(record.get("policy_source") or ""),
            policy_reason=str(record.get("policy_reason") or ""),
        )
    return ReviewItem(
        path=str(record.get("path") or ""),
        category="metadata_only",
        reason="隐私策略只允许登记元数据，不能打开正文。",
        action="确认保持 metadata-only；如果需要整理，只能手动添加不含敏感内容的安全标签。",
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


def _severity_label(severity: str) -> str:
    labels = {
        "high": "高",
        "medium": "中",
        "low": "低",
    }
    return labels.get(severity, severity)


def _analysis_review_reason_label(reason: str) -> str:
    labels = {
        "analysis_error": "分析过程出错，需要人工检查",
        "cloud_missing_policy_context": "缺少原始隐私策略上下文，禁止发送云端",
        "cloud_not_authorized": "云端 LLM 未获得此路径授权",
        "llm_api_error": "LLM API 调用失败或返回格式不可用",
        "llm_low_confidence": "LLM 语义判断置信度不足，需要人工复核",
        "llm_semantic_reviewed": "LLM 已给出较明确的语义判断",
        "local_llm_not_enabled": "本地 LLM 未启用或 endpoint 不是本机地址",
        "rules_low_signal": "规则线索不足，无法可靠判断主题",
        "rules_only_needs_semantic_review": "规则版结果需要语义复核",
        "rules_only_no_llm": "没有配置 LLM，只能给出规则版结果",
        "rules_only_optional_review": "规则版结果可用，但仍建议后续抽查",
    }
    return labels.get(reason, reason)


def _format_tag(tag: str) -> str:
    label = _tag_label(tag)
    if label == tag:
        return f"`{tag}`"
    return f"{label}（`{tag}`）"


def _tag_label(tag: str) -> str:
    labels = {
        "analysis": "分析/摘要",
        "cli": "命令行",
        "cli_workflow": "命令行流程",
        "code": "代码",
        "config": "配置",
        "configuration": "配置",
        "collection/archives": "归档",
        "collection/areas": "领域",
        "collection/projects": "项目",
        "collection/resources": "资源",
        "docs": "文档",
        "document": "文档",
        "document/configuration_file": "配置文件",
        "document/contract": "合同",
        "document/file": "普通文件",
        "document/general": "普通文档",
        "document/identity": "身份证件",
        "document/invoice": "发票",
        "document/note": "笔记",
        "document/project_documentation": "项目文档",
        "document/source_code": "源码",
        "document/test_file": "测试文件",
        "extract": "正文提取",
        "content_extraction": "正文提取",
        "file": "文件",
        "human_review": "人工复核",
        "html_review_ui": "HTML 交互审阅",
        "inventory": "文件清单",
        "inventory_db": "文件清单数据库",
        "license": "许可证",
        "llm_policy": "LLM 策略",
        "open_source": "开源治理",
        "privacy": "隐私/权限",
        "privacy_policy": "隐私策略",
        "project_documentation": "项目文档",
        "readme": "说明文档",
        "roadmap": "计划/路线图",
        "roots": "扫描目录",
        "scan": "扫描",
        "scan_planning": "扫描计划",
        "scan_reporting": "扫描报告",
        "scan_roots": "扫描目录",
        "semantic_analysis": "内容理解",
        "source_code": "源码",
        "test": "测试",
        "test_coverage": "测试覆盖",
        "test_file": "测试文件",
        "tests": "测试",
        "topic/cli_workflow": "命令行流程",
        "topic/configuration": "配置",
        "topic/content_extraction": "正文提取",
        "topic/html_review_ui": "HTML 交互审阅",
        "topic/human_review": "人工复核",
        "topic/inventory_db": "文件清单数据库",
        "topic/llm_policy": "LLM 策略",
        "topic/open_source": "开源治理",
        "topic/privacy_policy": "隐私策略",
        "topic/project_documentation": "项目文档",
        "topic/roadmap": "计划/路线图",
        "topic/scan_planning": "扫描计划",
        "topic/scan_reporting": "扫描报告",
        "topic/scan_roots": "扫描目录",
        "topic/semantic_analysis": "内容理解",
        "topic/test_coverage": "测试覆盖",
        "workflow/active": "活跃",
        "workflow/archive_candidate": "可归档",
        "workflow/ignored": "忽略",
        "workflow/inbox": "收件箱",
        "workflow/waiting_review": "待复核",
        "sensitivity/credential": "密钥凭证",
        "sensitivity/financial": "财务",
        "sensitivity/identity": "身份资料",
        "sensitivity/legal": "法律/合同",
        "sensitivity/medical": "医疗",
        "sensitivity/personal": "个人信息",
        "sensitivity/public": "公开",
    }
    return labels.get(tag, tag)


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
