from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import os

from .policy import AccessDecision, PolicyEngine


@dataclass(frozen=True)
class ScanEntry:
    path: str
    name: str
    extension: str
    is_dir: bool
    exists_now: bool
    size_bytes: int | None
    mtime: float | None
    ctime: float | None
    decision: AccessDecision
    last_seen_at: str
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def access_policy(self) -> str:
        return self.decision.access_policy

    @property
    def is_excluded(self) -> bool:
        return self.decision.is_excluded

    @property
    def record_metadata(self) -> bool:
        return not self.decision.is_excluded

    @property
    def read_content(self) -> bool:
        return self.decision.is_read_allowed

    @property
    def embedding_allowed(self) -> bool:
        return self.decision.is_embedding_allowed


@dataclass
class ScanStats:
    roots: int = 0
    entries_seen: int = 0
    files_seen: int = 0
    dirs_seen: int = 0
    allowed: int = 0
    denied: int = 0
    metadata_only: int = 0
    no_embedding: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "roots": self.roots,
            "entries_seen": self.entries_seen,
            "files_seen": self.files_seen,
            "dirs_seen": self.dirs_seen,
            "allowed": self.allowed,
            "denied": self.denied,
            "metadata_only": self.metadata_only,
            "no_embedding": self.no_embedding,
            "errors": self.errors,
        }


@dataclass
class ScanResult:
    entries: list[ScanEntry]
    stats: ScanStats
    errors: list[str]


def scan_paths(
    paths: Iterable[str | os.PathLike[str]],
    policy_engine: PolicyEngine,
    *,
    inventory: Any | None = None,
    dry_run: bool = True,
    follow_symlinks: bool = False,
    max_entries: int | None = None,
    resume_after: str | os.PathLike[str] | None = None,
    sort_entries: bool = False,
) -> ScanResult:
    """Scan paths without opening file contents.

    `dry_run` is kept as an explicit argument because future scan modes may
    parse content. MVP0 treats both dry-run and inventory scans as metadata-only
    filesystem traversal.
    """

    del dry_run, inventory
    stats = ScanStats()
    entries: list[ScanEntry] = []
    errors: list[str] = []
    resume_key = _scan_order_key(Path(resume_after)) if resume_after else None

    root_paths = [Path(raw_path) for raw_path in paths]
    if sort_entries:
        root_paths.sort(key=_scan_order_key)

    for root in root_paths:
        stats.roots += 1
        if not root.exists():
            errors.append(f"Root does not exist: {root}")
            stats.errors += 1
            continue
        for entry in _scan_one(
            root,
            policy_engine,
            follow_symlinks=follow_symlinks,
            errors=errors,
            stats=stats,
            resume_key=resume_key,
            sort_entries=sort_entries,
        ):
            entries.append(entry)
            _count_policy(stats, entry.decision)
            if max_entries is not None and len(entries) >= max_entries:
                return ScanResult(entries=entries, stats=stats, errors=errors)

    return ScanResult(entries=entries, stats=stats, errors=errors)


def _scan_one(
    path: Path,
    policy_engine: PolicyEngine,
    *,
    follow_symlinks: bool,
    errors: list[str],
    stats: ScanStats,
    resume_key: str | None,
    sort_entries: bool,
) -> Iterable[ScanEntry]:
    try:
        is_dir = path.is_dir()
        entry = _entry_from_path(path, is_dir, policy_engine)
        should_yield = resume_key is None or _scan_order_key(path) > resume_key
        if should_yield:
            yield entry
            stats.entries_seen += 1
            if is_dir:
                stats.dirs_seen += 1
            else:
                stats.files_seen += 1

        if not is_dir:
            return
        if entry.decision.is_excluded:
            return
        if path.is_symlink() and not follow_symlinks:
            return

        with os.scandir(path) as iterator:
            children = list(iterator)
            if sort_entries:
                children.sort(key=lambda child: _scan_order_key(Path(child.path)))
            for child in children:
                child_path = Path(child.path)
                try:
                    child_is_dir = child.is_dir(follow_symlinks=follow_symlinks)
                except OSError as exc:
                    errors.append(f"Cannot inspect {child_path}: {exc}")
                    stats.errors += 1
                    continue
                yield from _scan_one(
                    child_path,
                    policy_engine,
                    follow_symlinks=follow_symlinks,
                    errors=errors,
                    stats=stats,
                    resume_key=resume_key,
                    sort_entries=sort_entries,
                )
    except OSError as exc:
        errors.append(f"Cannot scan {path}: {exc}")
        stats.errors += 1


def _entry_from_path(path: Path, is_dir: bool, policy_engine: PolicyEngine) -> ScanEntry:
    raw_decision = policy_engine.decide(path, is_dir=is_dir)
    decision = _coerce_decision(raw_decision, path, is_dir)
    stat = path.stat()
    now = datetime.now(timezone.utc).isoformat()
    return ScanEntry(
        path=str(path),
        name=path.name,
        extension=path.suffix.lower(),
        is_dir=is_dir,
        exists_now=True,
        size_bytes=None if is_dir else stat.st_size,
        mtime=stat.st_mtime,
        ctime=stat.st_ctime,
        decision=decision,
        last_seen_at=now,
        extra={"is_symlink": path.is_symlink()},
    )


def _scan_order_key(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").casefold()


def _count_policy(stats: ScanStats, decision: AccessDecision) -> None:
    if decision.is_excluded:
        stats.denied += 1
    elif decision.metadata_only:
        stats.metadata_only += 1
    elif not decision.is_embedding_allowed:
        stats.no_embedding += 1
    else:
        stats.allowed += 1


def _coerce_decision(raw: Any, path: Path, is_dir: bool) -> AccessDecision:
    if isinstance(raw, AccessDecision):
        return raw
    if isinstance(raw, dict):
        action = str(raw.get("access_policy", raw.get("action", raw.get("policy", "allow")))).lower()
        normalized_action = {
            "denied": "deny",
            "excluded": "deny",
            "skip": "deny",
            "skipped": "deny",
            "allowed": "allow",
            "metadata": "metadata_only",
            "metadataonly": "metadata_only",
        }.get(action, action)
        read_allowed = bool(raw.get("is_read_allowed", raw.get("read_content", normalized_action in {"allow", "no_embedding"})))
        embedding_allowed = bool(
            raw.get("is_embedding_allowed", raw.get("embedding_allowed", normalized_action == "allow"))
        )
        is_excluded = normalized_action == "deny" or bool(raw.get("is_excluded", False))
        return AccessDecision(
            path=str(raw.get("path", path)),
            is_dir=is_dir,
            access_policy=normalized_action,
            policy_source=str(raw.get("policy_source", "policy_engine")),
            reason=str(raw.get("reason", "")),
            is_read_allowed=False if is_excluded else read_allowed,
            is_extract_allowed=False if is_excluded else read_allowed,
            is_index_allowed=not is_excluded and normalized_action != "metadata_only",
            is_embedding_allowed=False if is_excluded else embedding_allowed,
            metadata_only=normalized_action == "metadata_only",
            is_excluded=is_excluded,
        )
    raise TypeError(f"Unsupported policy decision type: {type(raw)!r}")
