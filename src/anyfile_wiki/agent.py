from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json
import shutil
import uuid

import yaml

from .assets import load_jsonl_records


AGENT_PROFILE_VERSION = 1
USAGE_EVENT_TYPES = {"selected", "opened", "cited", "search_hit"}


def default_agent_profile(*, profile_path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    profile = Path(profile_path)
    run_dir = Path(out_dir)
    return {
        "version": AGENT_PROFILE_VERSION,
        "assistant": {
            "purpose": "Agent-readable AnyFile Wiki profile. It points agents to configs, run state, indexes, review pages, and safety limits.",
            "safe_defaults": [
                "Read indexes before opening original files.",
                "Never move, delete, or rename original files from this profile.",
                "Cloud LLM access must be explicitly authorized in llm/privacy config.",
            ],
            "query_order": [
                "agent-profile.yaml",
                "run-state.json",
                "asset-index.jsonl",
                "collection-index.jsonl",
                "asset-score.jsonl",
                "original file only when privacy allows and the task requires it",
            ],
        },
        "workspace": {
            "default_run_dir": _posix(run_dir),
            "default_profile": _posix(profile),
        },
        "configs": {
            "privacy": _posix(profile.parent / "privacy.yaml"),
            "roots": _posix(profile.parent / "roots.yaml"),
            "schedule": _posix(profile.parent / "schedule.yaml"),
            "llm": _posix(profile.parent / "llm.yaml"),
            "tags": "configs/tags.example.yaml",
            "excludes": "configs/excludes.default.yaml",
        },
        "run_state": _posix(run_dir / "run-state.json"),
        "indexes": {
            "asset_index": _posix(run_dir / "assets" / "asset-index.jsonl"),
            "collection_index": _posix(run_dir / "assets" / "collection-index.jsonl"),
            "asset_signature": _posix(run_dir / "assets" / "asset-signature.jsonl"),
            "asset_score": _posix(run_dir / "assets" / "asset-score.jsonl"),
            "asset_usage_events": _posix(run_dir / "assets" / "asset-usage-events.jsonl"),
        },
        "review": {
            "review_dir": _posix(run_dir / "review"),
            "html_path": _posix(run_dir / "review" / "human-review.html"),
            "decisions_path": _posix(run_dir / "review" / "review-decisions.jsonl"),
        },
        "schedule": {
            "enabled": False,
            "mode": "manual",
            "max_scan_entries": 500,
            "extract_limit": 100,
            "analyze_limit": 100,
        },
        "safety": {
            "allow_move": False,
            "allow_delete": False,
            "allow_rename": False,
        },
    }


def load_agent_profile(path: str | Path) -> dict[str, Any]:
    profile_path = Path(path)
    if not profile_path.exists():
        return default_agent_profile(profile_path=profile_path, out_dir="data/daily-run")
    data = yaml.safe_load(profile_path.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"agent profile must be a mapping: {profile_path}")
    return data


def initialize_agent_workspace(
    *,
    profile_path: str | Path,
    out_dir: str | Path,
    roots_config: str | Path | None = None,
    privacy_config: str | Path | None = None,
    schedule_config: str | Path | None = None,
) -> dict[str, Any]:
    profile = Path(profile_path)
    config_dir = profile.parent
    run_dir = Path(out_dir)
    repo_configs = Path(__file__).resolve().parents[2] / "configs"
    targets = {
        "privacy": Path(privacy_config) if privacy_config else config_dir / "privacy.yaml",
        "roots": Path(roots_config) if roots_config else config_dir / "roots.yaml",
        "schedule": Path(schedule_config) if schedule_config else config_dir / "schedule.yaml",
    }
    templates = {
        "privacy": repo_configs / "privacy.example.yaml",
        "roots": repo_configs / "roots.example.yaml",
        "schedule": repo_configs / "schedule.example.yaml",
    }
    config_results = {
        name: _copy_template_if_missing(source=templates[name], target=target)
        for name, target in targets.items()
    }
    profile_result = _write_profile_if_missing(profile, default_agent_profile(profile_path=profile, out_dir=run_dir))
    return {
        "profile": profile_result,
        "configs": config_results,
        "run_dir": _posix(run_dir),
        "run_state": _posix(run_dir / "run-state.json"),
        "indexes": default_agent_profile(profile_path=profile, out_dir=run_dir)["indexes"],
        "review": default_agent_profile(profile_path=profile, out_dir=run_dir)["review"],
        "next_commands": [
            f'anyfile-wiki run "<scan-root>" --privacy "{_posix(targets["privacy"])}" --out "{_posix(run_dir)}"',
            f'anyfile-wiki run --out "{_posix(run_dir)}"',
            f'anyfile-wiki query "<keyword>" --profile "{_posix(profile)}" --json',
        ],
    }


def query_assets(
    query: str,
    *,
    profile_path: str | Path = "configs/agent-profile.yaml",
    limit: int = 10,
) -> dict[str, Any]:
    profile = load_agent_profile(profile_path)
    paths = profile_index_paths(profile)
    asset_index = paths["asset_index"]
    if not asset_index.exists():
        return {
            "ok": False,
            "error": f"asset index not found: {asset_index}",
            "next_steps": [
                "Run anyfile-wiki agent-init first if this workspace has not been initialized.",
                "Run anyfile-wiki run with an approved scan root to generate asset indexes.",
            ],
            "results": [],
        }
    assets = load_jsonl_records(asset_index)
    collections = _by_asset_id(load_jsonl_records(paths["collection_index"]))
    scores = _by_asset_id(load_jsonl_records(paths["asset_score"]))
    terms = _query_terms(query)
    results = []
    for asset in assets:
        collection = collections.get(str(asset.get("asset_id")), {})
        score = scores.get(str(asset.get("asset_id")), {})
        relevance = _relevance(asset, collection, score, terms)
        if relevance <= 0 and terms:
            continue
        results.append(_query_result(asset, collection, score, relevance))
    results.sort(
        key=lambda item: (
            -float(item.get("relevance") or 0),
            -float(item.get("usage_score") or 0),
            str(item.get("path") or "").casefold(),
        )
    )
    return {
        "ok": True,
        "query": query,
        "profile": _posix(Path(profile_path)),
        "asset_index": _posix(asset_index),
        "count": len(results[:limit]),
        "total_matches": len(results),
        "results": results[:limit],
    }


def append_usage_event(
    *,
    asset_id: str,
    event_type: str,
    profile_path: str | Path = "configs/agent-profile.yaml",
    query: str = "",
    note: str = "",
) -> dict[str, Any]:
    if event_type not in USAGE_EVENT_TYPES:
        raise ValueError(f"unsupported usage event: {event_type}")
    profile = load_agent_profile(profile_path)
    paths = profile_index_paths(profile)
    asset_index = paths["asset_index"]
    events_path = paths["asset_usage_events"]
    assets = load_jsonl_records(asset_index)
    asset = next((item for item in assets if str(item.get("asset_id")) == asset_id), None)
    if asset is None:
        return {
            "ok": False,
            "error": f"asset_id not found: {asset_id}",
            "asset_index": _posix(asset_index),
            "event_written": False,
        }
    event = {
        "schema_version": 1,
        "event_id": f"usage:{uuid.uuid4().hex}",
        "event_at": datetime.now(timezone.utc).isoformat(),
        "actor": "agent",
        "event_type": event_type,
        "asset_id": asset_id,
        "path": str(asset.get("path") or ""),
        "query": query,
        "note": note,
    }
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "ok": True,
        "event_written": True,
        "event_path": _posix(events_path),
        "event": event,
    }


def profile_index_paths(profile: dict[str, Any]) -> dict[str, Path]:
    indexes = _as_mapping(profile.get("indexes"))
    workspace = _as_mapping(profile.get("workspace"))
    default_run = Path(str(workspace.get("default_run_dir") or "data/daily-run"))
    asset_index = _path_from_profile(indexes.get("asset_index"), default_run / "assets" / "asset-index.jsonl")
    asset_dir = asset_index.parent
    return {
        "asset_index": asset_index,
        "collection_index": _path_from_profile(indexes.get("collection_index"), asset_dir / "collection-index.jsonl"),
        "asset_score": _path_from_profile(indexes.get("asset_score"), asset_dir / "asset-score.jsonl"),
        "asset_usage_events": _path_from_profile(indexes.get("asset_usage_events"), asset_dir / "asset-usage-events.jsonl"),
    }


def format_agent_init_summary(summary: dict[str, Any]) -> str:
    lines = ["agent_init:"]
    profile = summary["profile"]
    lines.append(f"- profile: {profile['path']} ({profile['status']})")
    lines.append(f"- run_dir: {summary['run_dir']}")
    lines.append("configs:")
    for name, result in summary["configs"].items():
        lines.append(f"- {name}: {result['path']} ({result['status']})")
    lines.append("indexes:")
    for name, path in summary["indexes"].items():
        lines.append(f"- {name}: {path}")
    lines.append("review:")
    for name, path in summary["review"].items():
        lines.append(f"- {name}: {path}")
    lines.append("next_commands:")
    lines.extend(f"- {command}" for command in summary["next_commands"])
    return "\n".join(lines)


def format_query_results(payload: dict[str, Any]) -> str:
    if not payload.get("ok"):
        lines = [f"query_error: {payload.get('error')}"]
        lines.extend(f"- {step}" for step in payload.get("next_steps", []))
        return "\n".join(lines)
    lines = [
        "query_results:",
        f"- query: {payload.get('query')}",
        f"- matches: {payload.get('count')} / {payload.get('total_matches')}",
    ]
    for result in payload.get("results", []):
        lines.extend(
            [
                f"- title: {result.get('title')}",
                f"  asset_id: {result.get('asset_id')}",
                f"  path: {result.get('path')}",
                f"  virtual_path: {result.get('virtual_path')}",
                f"  review_required: {result.get('review_required')}",
                f"  archive_policy: {result.get('archive_policy')}",
            ]
        )
    return "\n".join(lines)


def _copy_template_if_missing(*, source: Path, target: Path) -> dict[str, str]:
    if target.exists():
        return {"path": _posix(target), "status": "exists", "source": _posix(source)}
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return {"path": _posix(target), "status": "created", "source": _posix(source)}


def _write_profile_if_missing(path: Path, profile: dict[str, Any]) -> dict[str, str]:
    if path.exists():
        return {"path": _posix(path), "status": "exists"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"path": _posix(path), "status": "created"}


def _query_terms(query: str) -> list[str]:
    return [part.casefold() for part in query.replace("/", " ").replace("\\", " ").split() if part.strip()]


def _relevance(asset: dict[str, Any], collection: dict[str, Any], score: dict[str, Any], terms: list[str]) -> float:
    if not terms:
        return 1.0
    haystacks = {
        "file_name": Path(str(asset.get("path") or "")).name,
        "title": str(asset.get("title") or ""),
        "summary": str(asset.get("summary") or ""),
        "tags": " ".join(str(tag) for tag in asset.get("tags") or []),
        "virtual_path": str(collection.get("virtual_path") or ""),
        "collection_title": str(collection.get("collection_title") or ""),
        "asset_status": str(asset.get("asset_status") or ""),
        "archive_policy": str(score.get("archive_policy") or ""),
    }
    weights = {
        "file_name": 4.0,
        "title": 3.0,
        "summary": 1.4,
        "tags": 2.0,
        "virtual_path": 2.2,
        "collection_title": 2.5,
        "asset_status": 1.0,
        "archive_policy": 0.6,
    }
    relevance = 0.0
    for term in terms:
        for name, text in haystacks.items():
            lowered = text.casefold()
            if term and term in lowered:
                relevance += weights[name]
    if bool(asset.get("needs_human_review")):
        relevance += 0.1
    relevance += min(float(score.get("usage_score") or 0.0), 1.0)
    return round(relevance, 3)


def _query_result(
    asset: dict[str, Any],
    collection: dict[str, Any],
    score: dict[str, Any],
    relevance: float,
) -> dict[str, Any]:
    return {
        "asset_id": str(asset.get("asset_id") or ""),
        "path": str(asset.get("path") or ""),
        "title": str(asset.get("title") or Path(str(asset.get("path") or "")).name),
        "summary": str(asset.get("summary") or ""),
        "tags": list(asset.get("tags") or []),
        "asset_status": str(asset.get("asset_status") or ""),
        "needs_human_review": bool(asset.get("needs_human_review")),
        "virtual_path": str(collection.get("virtual_path") or ""),
        "collection_title": str(collection.get("collection_title") or ""),
        "relation_type": str(collection.get("relation_type") or ""),
        "canonical_asset_id": str(collection.get("canonical_asset_id") or ""),
        "review_required": bool(collection.get("review_required") or asset.get("needs_human_review")),
        "archive_policy": str(score.get("archive_policy") or ""),
        "usage_score": float(score.get("usage_score") or 0.0),
        "retention_score": float(score.get("retention_score") or 0.0),
        "archive_score": float(score.get("archive_score") or 0.0),
        "delete_risk_score": float(score.get("delete_risk_score") or 0.0),
        "relevance": relevance,
    }


def _by_asset_id(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(record.get("asset_id")): record for record in records if record.get("asset_id")}


def _path_from_profile(value: Any, default: Path) -> Path:
    raw = str(value or "")
    return Path(raw) if raw else default


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _posix(path: str | Path) -> str:
    return Path(path).as_posix()
