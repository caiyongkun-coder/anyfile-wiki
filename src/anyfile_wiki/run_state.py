from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import uuid


RUN_STATE_VERSION = 1
STAGE_ORDER = ("scan", "extract", "analyze", "review", "html")


def new_run_state(
    *,
    roots: list[str],
    out_dir: str | Path,
    privacy: str,
    excludes: str,
    inventory: str | Path | None = None,
    follow_symlinks: bool = False,
    analysis_method: str = "rules",
    llm_config: str = "configs/llm.example.yaml",
    tags_config: str = "configs/tags.example.yaml",
) -> dict[str, Any]:
    root = Path(out_dir)
    now = _utc_now()
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    return {
        "version": RUN_STATE_VERSION,
        "run_id": run_id,
        "created_at": now,
        "updated_at": now,
        "status": "paused",
        "current_stage": "scan",
        "roots": roots,
        "config": {
            "privacy": privacy,
            "excludes": excludes,
            "follow_symlinks": follow_symlinks,
            "analysis_method": analysis_method,
            "llm_config": llm_config,
            "tags_config": tags_config,
        },
        "paths": {
            "out_dir": str(root),
            "inventory": str(inventory or root / "inventory.sqlite"),
            "scan_dir": str(root / "scan"),
            "extract_dir": str(root / "extract"),
            "extract_manifest": str(root / "extract" / "extract-manifest.jsonl"),
            "analyze_dir": str(root / "analyze"),
            "analysis_manifest": str(root / "analyze" / "analysis-manifest.jsonl"),
            "knowledge_index": str(root / "analyze" / "knowledge-index.jsonl"),
            "review_dir": str(root / "review"),
            "html_dir": str(root / "html"),
        },
        "stages": {stage: _empty_stage() for stage in STAGE_ORDER},
        "last_step": None,
    }


def load_run_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    payload = json.loads(state_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("run state must be a JSON object")
    if int(payload.get("version", 0)) != RUN_STATE_VERSION:
        raise ValueError(f"unsupported run state version: {payload.get('version')!r}")
    return payload


def save_run_state(state: dict[str, Any], path: str | Path) -> None:
    state["updated_at"] = _utc_now()
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def next_stage(state: dict[str, Any]) -> str | None:
    stages = state.get("stages") or {}
    for stage in STAGE_ORDER:
        if (stages.get(stage) or {}).get("status") != "complete":
            return stage
    return None


def mark_stage_started(state: dict[str, Any], stage: str) -> None:
    stage_state = _stage(state, stage)
    stage_state["status"] = "running"
    stage_state["started_at"] = stage_state.get("started_at") or _utc_now()
    state["status"] = "running"
    state["current_stage"] = stage


def mark_stage_result(
    state: dict[str, Any],
    stage: str,
    *,
    status: str,
    message: str,
    stats: dict[str, Any] | None = None,
    outputs: dict[str, str] | None = None,
    cursor_path: str | None = None,
) -> None:
    stage_state = _stage(state, stage)
    stage_state["status"] = status
    stage_state["updated_at"] = _utc_now()
    stage_state["chunks"] = int(stage_state.get("chunks") or 0) + 1
    if status == "complete":
        stage_state["completed_at"] = _utc_now()
        stage_state["cursor_path"] = None
    elif cursor_path:
        stage_state["cursor_path"] = cursor_path
    if stats:
        _merge_totals(stage_state.setdefault("totals", {}), stats)
    if outputs:
        stage_state.setdefault("outputs", {}).update(outputs)
    state["last_step"] = {
        "stage": stage,
        "status": status,
        "message": message,
        "stats": stats or {},
        "outputs": outputs or {},
        "finished_at": _utc_now(),
    }
    next_name = next_stage(state)
    state["current_stage"] = next_name or "done"
    state["status"] = "complete" if next_name is None else "paused"


def format_run_state(state: dict[str, Any]) -> str:
    lines = [
        "run_state:",
        f"- run_id: {state.get('run_id')}",
        f"- status: {state.get('status')}",
        f"- current_stage: {state.get('current_stage')}",
        f"- roots: {len(state.get('roots') or [])}",
    ]
    lines.append("stages:")
    for name in STAGE_ORDER:
        stage = (state.get("stages") or {}).get(name) or {}
        cursor = stage.get("cursor_path")
        suffix = f" cursor={cursor}" if cursor else ""
        lines.append(
            f"- {name}: {stage.get('status', 'pending')} chunks={stage.get('chunks', 0)}{suffix}"
        )
    last = state.get("last_step")
    if last:
        lines.extend(
            [
                "last_step:",
                f"- stage: {last.get('stage')}",
                f"- status: {last.get('status')}",
                f"- message: {last.get('message')}",
            ]
        )
    return "\n".join(lines)


def _stage(state: dict[str, Any], stage: str) -> dict[str, Any]:
    return state.setdefault("stages", {}).setdefault(stage, _empty_stage())


def _empty_stage() -> dict[str, Any]:
    return {
        "status": "pending",
        "chunks": 0,
        "cursor_path": None,
        "totals": {},
        "outputs": {},
    }


def _merge_totals(target: dict[str, Any], stats: dict[str, Any]) -> None:
    for key, value in stats.items():
        if isinstance(value, bool):
            target[key] = value
        elif isinstance(value, int):
            target[key] = int(target.get(key) or 0) + value
        elif isinstance(value, dict):
            nested = target.setdefault(key, {})
            _merge_totals(nested, value)
        else:
            target[key] = value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
