from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re

from .scan import ScanEntry


TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".rst",
    ".log",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".html",
    ".htm",
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


@dataclass(frozen=True)
class ParseJob:
    path: Path
    parser: str
    reason: str
    embedding_allowed: bool
    source_policy: str = "allow"


@dataclass(frozen=True)
class ExtractResult:
    path: str
    parser: str
    status: str
    output_path: str | None
    error: str | None
    embedding_allowed: bool
    created_at: str


def build_parse_jobs(entries: list[ScanEntry]) -> list[ParseJob]:
    """Build parser jobs only for entries whose policy allows content reads."""

    jobs: list[ParseJob] = []
    for entry in entries:
        decision = entry.decision
        if entry.is_dir or not decision.is_read_allowed or not decision.is_extract_allowed:
            continue
        parser = choose_parser(entry.extension)
        if parser is None:
            continue
        jobs.append(
            ParseJob(
                path=Path(entry.path),
                parser=parser,
                reason=f"{decision.access_policy}: {decision.reason}",
                embedding_allowed=decision.is_embedding_allowed,
                source_policy=decision.access_policy,
            )
        )
    return jobs


def build_parse_jobs_from_records(records: list[dict]) -> list[ParseJob]:
    jobs: list[ParseJob] = []
    for record in records:
        if record.get("is_dir"):
            continue
        if not record.get("is_read_allowed") or not record.get("is_extract_allowed"):
            continue
        parser = choose_parser(str(record.get("extension", "")))
        if parser is None:
            continue
        jobs.append(
            ParseJob(
                path=Path(str(record["path"])),
                parser=parser,
                reason=f"{record.get('access_policy')}: {record.get('policy_reason', '')}",
                embedding_allowed=bool(record.get("is_embedding_allowed")),
                source_policy=str(record.get("access_policy", "allow")),
            )
        )
    return jobs


def choose_parser(extension: str) -> str | None:
    normalized = extension.lower()
    if normalized in TEXT_EXTENSIONS:
        return "direct_text"
    if normalized in {".pdf", ".docx", ".pptx", ".xlsx"}:
        return "markitdown"
    return None


def extract_jobs(jobs: list[ParseJob], output_dir: str | Path) -> list[ExtractResult]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    results: list[ExtractResult] = []
    for job in jobs:
        if job.parser == "direct_text":
            results.append(_extract_direct_text(job, root))
        elif job.parser == "markitdown":
            results.append(_extract_markitdown(job, root))
        else:
            results.append(_result(job, "skipped", None, f"unsupported parser: {job.parser}"))
    return results


def write_manifest(results: list[ExtractResult], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True) + "\n")


def _extract_direct_text(job: ParseJob, output_dir: Path) -> ExtractResult:
    try:
        text = _read_text(job.path)
        output = output_dir / "text" / _artifact_name(job.path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        return _result(job, "ok", output, None)
    except Exception as exc:  # noqa: BLE001 - manifest should capture parser failures.
        return _result(job, "error", None, str(exc))


def _extract_markitdown(job: ParseJob, output_dir: Path) -> ExtractResult:
    try:
        from markitdown import MarkItDown  # type: ignore
    except Exception as exc:  # noqa: BLE001 - optional dependency.
        return _result(job, "skipped", None, f"markitdown unavailable: {exc}")

    try:
        converter = MarkItDown()
        converted = converter.convert(str(job.path))
        text = getattr(converted, "text_content", None)
        if text is None:
            text = str(converted)
        output = output_dir / "markitdown" / _artifact_name(job.path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        return _result(job, "ok", output, None)
    except Exception as exc:  # noqa: BLE001 - manifest should capture parser failures.
        return _result(job, "error", None, str(exc))


def _result(job: ParseJob, status: str, output_path: Path | None, error: str | None) -> ExtractResult:
    return ExtractResult(
        path=str(job.path),
        parser=job.parser,
        status=status,
        output_path=str(output_path) if output_path else None,
        error=error,
        embedding_allowed=job.embedding_allowed,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return _normalize_newlines(data.decode(encoding))
        except UnicodeDecodeError:
            continue
    return _normalize_newlines(data.decode("utf-8", errors="replace"))


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _artifact_name(path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8", errors="ignore")).hexdigest()[:16]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._") or "file"
    return f"{digest}-{stem}.md"
