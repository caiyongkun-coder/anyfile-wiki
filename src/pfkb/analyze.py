from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json
import re

from .semantic import infer_semantic_understanding


SUMMARY_MAX_CHARS = 360
DEFAULT_MAX_TEXT_CHARS = 200_000

CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".scss",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
}

CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
DOC_EXTENSIONS = {".md", ".txt", ".rst", ".html", ".htm", ".pdf", ".docx", ".pptx", ".xlsx"}

TOPIC_KEYWORDS = {
    "privacy": ("privacy", "隐私", "deny", "metadata_only", "no_embedding", "secret"),
    "scan": ("scan", "扫描", "dry-run", "dry run"),
    "extract": ("extract", "extraction", "提取", "parse", "parser"),
    "analysis": ("analyze", "analysis", "摘要", "标签", "tag"),
    "inventory": ("inventory", "sqlite", "数据库"),
    "configuration": ("config", "configuration", "yaml", "配置"),
    "roots": ("roots", "目录", "onedrive", "documents", "downloads"),
    "cli": ("cli", "command", "命令", "argparse"),
    "tests": ("test", "pytest", "fixture"),
    "docs": ("readme", "docs", "文档", "guide"),
    "license": ("license", "apache"),
    "roadmap": ("roadmap", "mvp", "计划"),
}


@dataclass(frozen=True)
class AnalysisResult:
    path: str
    output_path: str
    status: str
    title: str
    summary: str
    tags: list[str]
    primary_tag: str
    content_type: str
    extension: str
    parser: str
    embedding_allowed: bool
    char_count: int
    word_count: int
    line_count: int
    analyzed_at: str
    source_extract_status: str
    analysis_method: str = "rules"
    confidence: float = 0.0
    needs_human_review: bool = True
    review_reason: str = "rules_only_no_llm"
    rule_title: str | None = None
    rule_summary: str | None = None
    rule_tags: list[str] | None = None
    key_points: list[str] | None = None
    model_notes: str | None = None
    error: str | None = None


def analyze_extract_records(
    records: Iterable[dict[str, Any]],
    *,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    analysis_method: str = "rules",
) -> list[AnalysisResult]:
    results: list[AnalysisResult] = []
    for record in records:
        if not _is_analyzable(record):
            continue
        results.append(
            analyze_extract_record(
                record,
                max_text_chars=max_text_chars,
                analysis_method=analysis_method,
            )
        )
    return results


def analyze_extract_record(
    record: dict[str, Any],
    *,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    analysis_method: str = "rules",
) -> AnalysisResult:
    if analysis_method not in {"rules", "codex-mock"}:
        raise ValueError(f"unsupported analysis method: {analysis_method}")

    output_path = Path(str(record.get("output_path") or ""))
    source_path = str(record.get("path") or "")
    parser = str(record.get("parser") or "")
    status = str(record.get("status") or "")
    analyzed_at = datetime.now(timezone.utc).isoformat()

    try:
        text = _read_text(output_path, max_chars=max_text_chars)
        extension = Path(source_path).suffix.lower()
        content_type = classify_content_type(source_path, extension)
        tags = infer_tags(source_path, text, content_type)
        title = infer_title(source_path, text)
        summary = summarize_text(text, title=title)
        confidence, review_reason = assess_rules_confidence(text, summary, tags, content_type)
        rule_title = title
        rule_summary = summary
        rule_tags = tags

        if analysis_method == "codex-mock":
            semantic = infer_semantic_understanding(
                source_path,
                text,
                content_type=content_type,
                rule_title=rule_title,
                rule_summary=rule_summary,
                rule_tags=rule_tags,
            )
            title = semantic.title
            summary = semantic.summary
            tags = semantic.tags
            confidence = semantic.confidence
            review_reason = semantic.review_reason
            needs_human_review = semantic.needs_human_review
            key_points = semantic.key_points
            model_notes = semantic.model_notes
        else:
            needs_human_review = confidence < 0.65
            key_points = None
            model_notes = None

        return AnalysisResult(
            path=source_path,
            output_path=str(output_path),
            status="ok",
            title=title,
            summary=summary,
            tags=tags,
            primary_tag=tags[0] if tags else content_type,
            content_type=content_type,
            extension=extension,
            parser=parser,
            embedding_allowed=bool(record.get("embedding_allowed")),
            char_count=len(text),
            word_count=count_words(text),
            line_count=text.count("\n") + (1 if text else 0),
            analyzed_at=analyzed_at,
            source_extract_status=status,
            analysis_method=analysis_method,
            confidence=confidence,
            needs_human_review=needs_human_review,
            review_reason=review_reason,
            rule_title=rule_title,
            rule_summary=rule_summary,
            rule_tags=rule_tags,
            key_points=key_points,
            model_notes=model_notes,
        )
    except Exception as exc:  # noqa: BLE001 - analysis manifest should capture failures.
        return AnalysisResult(
            path=source_path,
            output_path=str(output_path),
            status="error",
            title=Path(source_path).name or source_path,
            summary="",
            tags=[],
            primary_tag="error",
            content_type="unknown",
            extension=Path(source_path).suffix.lower(),
            parser=parser,
            embedding_allowed=bool(record.get("embedding_allowed")),
            char_count=0,
            word_count=0,
            line_count=0,
            analyzed_at=analyzed_at,
            source_extract_status=status,
            analysis_method=analysis_method,
            confidence=0.0,
            needs_human_review=True,
            review_reason="analysis_error",
            error=str(exc),
        )


def classify_content_type(path: str, extension: str | None = None) -> str:
    extension = (extension or Path(path).suffix).lower()
    lower_path = path.replace("\\", "/").lower()
    segments = [segment for segment in lower_path.split("/") if segment]
    if "tests" in segments or "test" in segments or Path(path).name.lower().startswith("test_"):
        return "test"
    if "/docs/" in lower_path or Path(path).name.lower().startswith("readme"):
        return "docs"
    if "/configs/" in lower_path or extension in CONFIG_EXTENSIONS:
        return "config"
    if extension in CODE_EXTENSIONS:
        return "code"
    if extension in DOC_EXTENSIONS:
        return "document"
    return "file"


def infer_tags(path: str, text: str, content_type: str) -> list[str]:
    haystack = f"{path}\n{text[:12000]}".lower()
    tags = [content_type]
    for tag, keywords in TOPIC_KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            tags.append(tag)
    if "readme" in Path(path).name.lower():
        tags.append("readme")
    if "license" in Path(path).name.lower():
        tags.append("license")
    return _dedupe(tags)[:12]


def infer_title(path: str, text: str) -> str:
    for line in text.splitlines()[:80]:
        stripped = line.strip()
        if not stripped:
            continue
        heading = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if heading:
            return _clean_inline(heading.group(1)) or Path(path).name
    return Path(path).name or path


def summarize_text(text: str, *, title: str = "") -> str:
    paragraphs = [
        _clean_paragraph(part)
        for part in re.split(r"\n\s*\n", text.strip())
        if _clean_paragraph(part)
    ]
    if not paragraphs:
        return ""
    summary = paragraphs[0]
    if title and summary.lower() == title.lower() and len(paragraphs) > 1:
        summary = paragraphs[1]
    return _truncate(summary, SUMMARY_MAX_CHARS)


def count_words(text: str) -> int:
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z0-9_]+(?:[-'][A-Za-z0-9_]+)?", text))
    return cjk_chars + latin_words


def assess_rules_confidence(
    text: str,
    summary: str,
    tags: list[str],
    content_type: str,
) -> tuple[float, str]:
    score = 0.25
    if summary:
        score += 0.15
    if len(summary) >= 80:
        score += 0.1
    if len(tags) >= 3:
        score += 0.1
    if len(tags) >= 6:
        score += 0.1
    if content_type in {"code", "config", "test", "docs"}:
        score += 0.05
    if len(text) >= 1000:
        score += 0.05
    score = min(round(score, 2), 0.75)
    if score < 0.4:
        return score, "rules_low_signal"
    if score < 0.65:
        return score, "rules_only_needs_semantic_review"
    return score, "rules_only_optional_review"


def write_analysis_outputs(results: list[AnalysisResult], output_dir: str | Path) -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "analysis-manifest.jsonl"
    index_jsonl_path = root / "knowledge-index.jsonl"
    index_md_path = root / "knowledge-index.md"
    tag_index_path = root / "tag-index.md"

    _write_jsonl(results, manifest_path)
    _write_jsonl([result for result in results if result.status == "ok"], index_jsonl_path)
    write_knowledge_index_md(results, index_md_path)
    write_tag_index_md(results, tag_index_path)
    return {
        "manifest": manifest_path,
        "knowledge_index_jsonl": index_jsonl_path,
        "knowledge_index_md": index_md_path,
        "tag_index_md": tag_index_path,
    }


def write_knowledge_index_md(results: list[AnalysisResult], path: str | Path) -> None:
    ok_results = [result for result in results if result.status == "ok"]
    semantic_mode = any(result.analysis_method != "rules" for result in ok_results)
    by_type: dict[str, list[AnalysisResult]] = defaultdict(list)
    for result in ok_results:
        by_type[result.content_type].append(result)

    method_note = (
        "当前版本是模拟 API/LLM 语义版：`codex-mock` 不调用外部服务，用来验证“模型理解、总结、打标签”的输出形态；粗标签仍会保留在每条记录里，方便和规则版对比。"
        if semantic_mode
        else "当前版本是全本地规则版：标题来自 Markdown 标题或文件名，摘要来自正文前几段，标签来自路径、扩展名和关键词匹配；还没有使用大模型做深度理解。"
    )
    lines = [
        "# 知识索引",
        "",
        "本文件由 `pfkb analyze` 生成，用来给人快速浏览“这批文件大概是什么”。",
        "",
        method_note,
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 概览",
        "",
        f"- 已分析文件：{len(ok_results)}",
        f"- 分析错误：{sum(1 for result in results if result.status == 'error')}",
    ]
    if ok_results:
        tag_counts = Counter(tag for result in ok_results for tag in result.tags)
        lines.append(
            "- 高频标签："
            + ", ".join(f"{_format_tag(tag)} {count}" for tag, count in tag_counts.most_common(10))
        )
        lines.append(
            f"- 需要人工复核：{sum(1 for result in ok_results if result.needs_human_review)}"
        )

    lines.extend(
        [
            "",
            "## 阅读说明",
            "",
            "- 这是给人先快速盘点文件的索引，不是最终结论。",
            "- `analysis_method: rules` 表示只使用文件路径、扩展名、标题和关键词规则。",
            "- `analysis_method: codex-mock` 表示这是模拟 API/LLM 语义版，用来先验证真实模型接入后的数据结构和阅读体验。",
            "- 语义版会保留 `保留粗标签` 和 `规则版摘要`，这样可以直接比较模型理解和规则粗标签的差异。",
            "- `规则/语义置信度` 不是最终真理，只表示当前方法掌握的线索是否足够清楚；低分文件建议进入人工待整理清单。",
            "- `需要人工复核` 为“是”时，代表系统不确定文件真实主题，后续可以由用户、本地 LLM 或显式授权的云端 LLM 复核。",
            "- 标签后面的英文 key 是稳定机器字段，方便 agent、脚本和后续 HTML 页面继续读取。",
            "",
            "## 字段说明",
            "",
            "- 原始路径：文件在电脑上的位置，用来回到源文件。",
            "- 内容类型：按扩展名和目录粗分出的类型，例如代码、配置、文档、测试。",
            "- 标签：当前分析方法产出的主题标签；语义版中代表模拟模型理解后的标签。",
            "- 保留粗标签：规则版结果原样保留，用来做回退、审计和对比。",
            "- 允许向量化：是否允许进入语义检索或 embedding 流程；隐私策略禁止时必须保持为“否”。",
            "- 摘要：当前取自正文开头或标题附近内容，适合作为预览，不适合作为精确总结。",
        ]
    )

    for content_type in sorted(by_type):
        lines.extend(["", f"## {_content_type_label(content_type)}", ""])
        for result in sorted(by_type[content_type], key=lambda item: item.path.lower()):
            tags = " ".join(_format_tag(tag) for tag in result.tags)
            rule_tags = " ".join(_format_tag(tag) for tag in (result.rule_tags or []))
            embedding = "是" if result.embedding_allowed else "否"
            human_review = "是" if result.needs_human_review else "否"
            review_reason = _review_reason_label(result.review_reason)
            confidence_label = "语义置信度" if result.analysis_method != "rules" else "规则置信度"
            summary_label = "语义摘要" if result.analysis_method != "rules" else "摘要"
            item_lines = [
                f"### {result.title}",
                "",
                f"- 原始路径：`{result.path}`",
                f"- 内容类型：`{result.content_type}`",
                f"- 标签：{tags}",
            ]
            if result.analysis_method != "rules":
                item_lines.append(f"- 保留粗标签：{rule_tags or '_无_'}")
                item_lines.append(f"- 规则版摘要：{result.rule_summary or '_无_'}")
            item_lines.extend(
                [
                    f"- 估算字数：{result.word_count}",
                    f"- 允许向量化：{embedding}",
                    f"- 分析方式：`{result.analysis_method}`",
                    f"- {confidence_label}：{result.confidence:.2f}",
                    f"- 需要人工复核：{human_review}（{review_reason}；`{result.review_reason}`）",
                ]
            )
            if result.key_points:
                item_lines.append("- 理解要点：" + "；".join(result.key_points))
            if result.model_notes:
                item_lines.append(f"- 模型说明：{result.model_notes}")
            item_lines.extend(
                [
                    "",
                    f"{summary_label}：",
                    "",
                    result.summary or "_暂未生成摘要。_",
                    "",
                ]
            )
            lines.extend(item_lines)

    errors = [result for result in results if result.status == "error"]
    if errors:
        lines.extend(["", "## 分析错误", ""])
        for result in errors:
            lines.append(f"- `{result.path}`: {result.error}")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_tag_index_md(results: list[AnalysisResult], path: str | Path) -> None:
    ok_results = [result for result in results if result.status == "ok"]
    by_tag: dict[str, list[AnalysisResult]] = defaultdict(list)
    for result in ok_results:
        for tag in result.tags:
            by_tag[tag].append(result)

    lines = [
        "# 标签索引",
        "",
        "本文件按标签反向列出文件，方便人从主题入口逐层查看。",
        "",
        "当前标签仍然是规则版标签：中文名称方便人阅读，括号中的英文 key 方便 agent 或脚本稳定引用。",
        "",
    ]
    for tag in sorted(by_tag):
        lines.extend(["", f"## {_format_tag(tag)}", ""])
        for result in sorted(by_tag[tag], key=lambda item: item.path.lower()):
            lines.append(f"- `{result.path}` - {result.title}")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_analysis_comparison_md(
    baseline_records: Iterable[dict[str, Any]],
    candidate_results: list[AnalysisResult],
    path: str | Path,
) -> None:
    baseline_by_path = {str(record.get("path") or ""): record for record in baseline_records}
    ok_candidates = [result for result in candidate_results if result.status == "ok"]
    lines = [
        "# 规则粗标签与语义理解对比",
        "",
        "本文件用于比较两次分析结果：一边是规则版粗标签，一边是模拟 API/LLM 的语义理解版。",
        "",
        "阅读时重点看三件事：语义标签是否更接近文件真实用途，语义摘要是否比规则摘要更像“理解后的说明”，以及哪些文件仍然需要人工复核。",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 概览",
        "",
        f"- 语义结果文件数：{len(ok_candidates)}",
        f"- 找到可对比的规则结果：{sum(1 for result in ok_candidates if result.path in baseline_by_path)}",
        "",
        "## 对比表",
        "",
        "| 文件 | 规则粗标签 | 语义标签 | 规则摘要 | 语义摘要 | 判断 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in sorted(ok_candidates, key=lambda item: item.path.lower()):
        baseline = baseline_by_path.get(result.path, {})
        rule_tags = [str(tag) for tag in baseline.get("tags") or result.rule_tags or []]
        rule_summary = str(baseline.get("summary") or result.rule_summary or "")
        semantic_tags = result.tags
        decision = _comparison_decision(rule_tags, semantic_tags, result)
        lines.append(
            "| "
            + " | ".join(
                [
                    _table_cell(Path(result.path).name or result.path),
                    _table_cell(" ".join(_format_tag(tag) for tag in rule_tags) or "无"),
                    _table_cell(" ".join(_format_tag(tag) for tag in semantic_tags) or "无"),
                    _table_cell(_truncate(rule_summary or "无", 120)),
                    _table_cell(_truncate(result.summary or "无", 160)),
                    _table_cell(decision),
                ]
            )
            + " |"
        )
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def analysis_stats(results: list[AnalysisResult]) -> dict[str, int]:
    stats: dict[str, int] = {}
    for result in results:
        stats[result.status] = stats.get(result.status, 0) + 1
    return stats


def _is_analyzable(record: dict[str, Any]) -> bool:
    return (
        str(record.get("status")) in {"ok", "up_to_date"}
        and bool(record.get("output_path"))
        and Path(str(record.get("output_path"))).exists()
    )


def _read_text(path: Path, *, max_chars: int) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[:max_chars] if max_chars > 0 else text


def _write_jsonl(items: Iterable[AnalysisResult], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True) + "\n")


def _clean_inline(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clean_paragraph(text: str) -> str:
    return _clean_inline(re.sub(r"^#{1,6}\s+", "", text.strip()))


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _content_type_label(content_type: str) -> str:
    labels = {
        "code": "代码",
        "config": "配置",
        "docs": "项目文档",
        "document": "文档",
        "test": "测试",
        "file": "文件",
        "unknown": "未知",
    }
    return labels.get(content_type, content_type)


def _comparison_decision(
    rule_tags: list[str],
    semantic_tags: list[str],
    result: AnalysisResult,
) -> str:
    if result.needs_human_review:
        return "语义线索仍不足，建议人工复核"
    if set(rule_tags) == set(semantic_tags):
        return "标签变化不大，语义摘要可作为补充"
    if len(semantic_tags) >= len(rule_tags):
        return "语义标签更具体，可优先用于知识库浏览"
    return "语义标签更收敛，可用于减少粗标签噪声"


def _table_cell(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|").strip()


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
        "configuration_file": "配置文件",
        "content_extraction": "正文提取",
        "docs": "文档",
        "document": "文档",
        "extract": "正文提取",
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
    }
    return labels.get(tag, tag)


def _review_reason_label(reason: str) -> str:
    labels = {
        "analysis_error": "分析过程出错，需要人工检查",
        "codex_mock_low_signal": "模拟语义层线索不足，需要人工复核",
        "codex_mock_semantic_reviewed": "模拟语义层已经给出较明确判断",
        "rules_low_signal": "规则线索不足，无法可靠判断主题",
        "rules_only_needs_semantic_review": "规则版结果需要语义复核",
        "rules_only_no_llm": "没有配置 LLM，只能给出规则版结果",
        "rules_only_optional_review": "规则版结果可用，但仍建议后续抽查",
    }
    return labels.get(reason, reason)
