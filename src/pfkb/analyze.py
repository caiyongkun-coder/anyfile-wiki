from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json
import re


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
    error: str | None = None


def analyze_extract_records(
    records: Iterable[dict[str, Any]],
    *,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
) -> list[AnalysisResult]:
    results: list[AnalysisResult] = []
    for record in records:
        if not _is_analyzable(record):
            continue
        results.append(analyze_extract_record(record, max_text_chars=max_text_chars))
    return results


def analyze_extract_record(
    record: dict[str, Any],
    *,
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
) -> AnalysisResult:
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
    by_type: dict[str, list[AnalysisResult]] = defaultdict(list)
    for result in ok_results:
        by_type[result.content_type].append(result)

    lines = [
        "# Knowledge Index",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        f"- analyzed: {len(ok_results)}",
        f"- errors: {sum(1 for result in results if result.status == 'error')}",
    ]
    if ok_results:
        tag_counts = Counter(tag for result in ok_results for tag in result.tags)
        lines.append(
            "- top_tags: "
            + ", ".join(f"`{tag}` {count}" for tag, count in tag_counts.most_common(10))
        )

    for content_type in sorted(by_type):
        lines.extend(["", f"## {content_type.title()}", ""])
        for result in sorted(by_type[content_type], key=lambda item: item.path.lower()):
            tags = " ".join(f"`{tag}`" for tag in result.tags)
            lines.extend(
                [
                    f"### {result.title}",
                    "",
                    f"- path: `{result.path}`",
                    f"- tags: {tags}",
                    f"- words: {result.word_count}",
                    "",
                    result.summary or "_No summary generated._",
                    "",
                ]
            )

    errors = [result for result in results if result.status == "error"]
    if errors:
        lines.extend(["", "## Errors", ""])
        for result in errors:
            lines.append(f"- `{result.path}`: {result.error}")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_tag_index_md(results: list[AnalysisResult], path: str | Path) -> None:
    ok_results = [result for result in results if result.status == "ok"]
    by_tag: dict[str, list[AnalysisResult]] = defaultdict(list)
    for result in ok_results:
        for tag in result.tags:
            by_tag[tag].append(result)

    lines = ["# Tag Index", ""]
    for tag in sorted(by_tag):
        lines.extend(["", f"## {tag}", ""])
        for result in sorted(by_tag[tag], key=lambda item: item.path.lower()):
            lines.append(f"- `{result.path}` - {result.title}")
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
