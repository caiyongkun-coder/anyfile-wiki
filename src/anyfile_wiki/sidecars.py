from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import re


SIDECAR_SCHEMA_VERSION = 1
ASSET_ID_STRATEGY = "path_sha256_v1"
SIDECAR_LEVELS = {"light", "text"}

_ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".gz", ".tar"}

_VIRTUAL_DIRECTORIES = (
    ("00", "00_总览与待处理", ()),
    ("01", "01_业务方案与需求", ("方案", "需求", "说明书", "产品手册", "业务", "requirement")),
    ("02", "02_FTP预算测算与取数", ("ftp", "预算", "测算", "取数", "成本", "估算")),
    ("03", "03_财务数据与核对", ("财务", "金融", "核对", "数据问题", "余额", "科目", "流水")),
    ("04", "04_报表表样与模板", ("报表", "表样", "模板", "样表", "台账")),
    ("05", "05_定价规则与曲线", ("定价", "曲线", "利率", "收益率")),
    ("06", "06_技术设计与接口", ("技术", "接口", "etl", "设计", "表结构", "数据库", "脚本", "开发")),
    ("07", "07_项目管理与交付", ("项目", "交付", "计划", "进度", "工作分配", "排期")),
    ("08", "08_培训汇报材料", ("培训", "汇报", "演示", "ppt", "宣讲")),
    ("09", "09_压缩包_不可解析_待复核", ()),
)


def attach_asset_ids(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item["asset_id"] = _text(item.get("asset_id")) or asset_id_for_path(item.get("path"))
        item["asset_id_strategy"] = _text(item.get("asset_id_strategy")) or ASSET_ID_STRATEGY
        assets.append(item)
    return assets


def asset_id_for_path(path: Any) -> str:
    digest = hashlib.sha256(_path_key(path).encode("utf-8")).hexdigest()
    return f"asset:path-sha256:{digest}"


def write_sidecar_outputs(
    records: Iterable[dict[str, Any]],
    output_dir: str | Path,
    *,
    sidecar_level: str = "text",
    dry_run: bool = False,
    asset_index_path: str | Path | None = None,
) -> tuple[dict[str, Path], dict[str, Any]]:
    if sidecar_level not in SIDECAR_LEVELS:
        raise ValueError(f"unsupported sidecar level: {sidecar_level!r}")
    root = Path(output_dir)
    assets = attach_asset_ids(records)
    generated_at = datetime.now(timezone.utc).isoformat()
    usage_events_path = root / "asset-usage-events.jsonl"
    usage_events = _load_jsonl_records(usage_events_path)
    signatures = build_asset_signature_records(assets, sidecar_level=sidecar_level, generated_at=generated_at)
    collections = build_collection_records(assets, signatures, generated_at=generated_at)
    scores = build_asset_score_records(
        assets,
        signatures,
        collections,
        usage_events,
        generated_at=generated_at,
    )
    stats = sidecar_stats(assets, signatures, collections, scores)
    outputs = {
        "asset_signature_jsonl": root / "asset-signature.jsonl",
        "collection_index_jsonl": root / "collection-index.jsonl",
        "asset_usage_events_jsonl": usage_events_path,
        "asset_score_jsonl": root / "asset-score.jsonl",
        "asset_sidecar_report_md": root / "asset-sidecar-report.md",
    }
    if dry_run:
        return outputs, stats

    root.mkdir(parents=True, exist_ok=True)
    write_jsonl_records(signatures, outputs["asset_signature_jsonl"])
    write_jsonl_records(collections, outputs["collection_index_jsonl"])
    if not usage_events_path.exists():
        usage_events_path.write_text("", encoding="utf-8")
    write_jsonl_records(scores, outputs["asset_score_jsonl"])
    write_sidecar_report(
        stats,
        outputs["asset_sidecar_report_md"],
        asset_index_path=asset_index_path,
        sidecar_level=sidecar_level,
    )
    return outputs, stats


def build_asset_signature_records(
    records: Iterable[dict[str, Any]],
    *,
    sidecar_level: str = "text",
    generated_at: str | None = None,
) -> list[dict[str, Any]]:
    now = generated_at or datetime.now(timezone.utc).isoformat()
    signatures: list[dict[str, Any]] = []
    for record in attach_asset_ids(records):
        path = _text(record.get("path"))
        file_name = _file_name(path)
        base_name = Path(file_name).stem if file_name else ""
        stat = _safe_stat(path)
        output_path = _text(record.get("output_path"))
        text_hash, text_status = _text_hash_for_output(output_path, sidecar_level=sidecar_level)
        signature = {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "asset_id": record["asset_id"],
            "asset_id_strategy": record["asset_id_strategy"],
            "path": path,
            "path_key": _path_key(path),
            "path_hash": _hash_label(_path_key(path)),
            "output_path": output_path,
            "file_name": file_name,
            "base_name": base_name,
            "base_name_norm": normalize_base_name(base_name),
            "extension": _text(record.get("extension") or Path(file_name).suffix).lower(),
            "file_size": stat.st_size if stat else _optional_int(record.get("file_size") or record.get("size_bytes")),
            "modified_at": _mtime_iso(stat) if stat else _text(record.get("modified_at")),
            "content_hash": None,
            "content_hash_status": "not_requested",
            "text_hash": text_hash,
            "text_hash_status": text_status,
            "extract_quality_score": extract_quality_score(record, text_status),
            "parser": _text(record.get("parser")),
            "source_extract_status": _text(record.get("source_extract_status")),
            "generated_at": now,
        }
        signatures.append(signature)
    return sorted(signatures, key=lambda item: _path_key(item.get("path")))


def build_collection_records(
    records: Iterable[dict[str, Any]],
    signatures: Iterable[dict[str, Any]],
    *,
    generated_at: str | None = None,
) -> list[dict[str, Any]]:
    now = generated_at or datetime.now(timezone.utc).isoformat()
    assets = attach_asset_ids(records)
    signature_by_id = {str(item.get("asset_id")): item for item in signatures}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in assets:
        signature = signature_by_id.get(record["asset_id"], {})
        directory_id, directory_title = classify_virtual_directory(record)
        collection_key = _collection_key(record, signature, directory_id)
        grouped[collection_key].append(
            {
                "record": record,
                "signature": signature,
                "directory_id": directory_id,
                "directory_title": directory_title,
                "collection_key": collection_key,
            }
        )

    rows: list[dict[str, Any]] = []
    for collection_key, members in grouped.items():
        canonical = _choose_canonical_member(members)
        canonical_id = str(canonical["record"].get("asset_id"))
        collection_id = f"collection:path-sha256:{_sha256(collection_key)}"
        collection_title = _collection_title(canonical)
        for member in sorted(members, key=lambda item: _path_key(item["record"].get("path"))):
            record = member["record"]
            signature = member["signature"]
            relation = _relation_for_member(member, canonical, members)
            duplicate_confidence, duplicate_reason = _duplicate_signal(member, canonical, members)
            review_required = _review_required(record)
            rows.append(
                {
                    "schema_version": SIDECAR_SCHEMA_VERSION,
                    "collection_id": collection_id,
                    "collection_title": collection_title,
                    "virtual_path": f"{member['directory_title']}/{collection_title}",
                    "asset_id": record["asset_id"],
                    "path": _text(record.get("path")),
                    "relation_type": "unknown" if review_required else relation,
                    "canonical_asset_id": record["asset_id"] if review_required else canonical_id,
                    "sort_key": _sort_key(member, collection_title),
                    "merge_reason": _merge_reason(member, members, review_required),
                    "merge_confidence": 0.0 if review_required else _merge_confidence(relation, duplicate_confidence, len(members)),
                    "duplicate_confidence": 0.0 if review_required else duplicate_confidence,
                    "duplicate_reason": "" if review_required else duplicate_reason,
                    "review_required": review_required,
                    "review_note": _review_note(record) if review_required else "",
                    "base_name_norm": _text(signature.get("base_name_norm")),
                    "directory_id": member["directory_id"],
                    "generated_at": now,
                }
            )
    return sorted(rows, key=lambda item: str(item.get("sort_key")))


def build_asset_score_records(
    records: Iterable[dict[str, Any]],
    signatures: Iterable[dict[str, Any]],
    collections: Iterable[dict[str, Any]],
    usage_events: Iterable[dict[str, Any]],
    *,
    generated_at: str | None = None,
) -> list[dict[str, Any]]:
    now = generated_at or datetime.now(timezone.utc).isoformat()
    assets = attach_asset_ids(records)
    signatures_by_id = {str(item.get("asset_id")): item for item in signatures}
    collection_by_id = {str(item.get("asset_id")): item for item in collections}
    events_by_asset = _usage_events_by_asset(usage_events)
    scores: list[dict[str, Any]] = []
    for record in assets:
        asset_id = str(record.get("asset_id"))
        signature = signatures_by_id.get(asset_id, {})
        collection = collection_by_id.get(asset_id, {})
        events = events_by_asset.get(asset_id, [])
        usage = _usage_signals(events)
        user_pinned = bool(record.get("user_pinned"))
        never_delete = bool(record.get("never_delete"))
        retention, retention_reasons = _retention_score(record, signature, collection)
        archive, archive_reasons = _archive_score(record, collection, usage["usage_score"], retention)
        delete_risk, delete_reasons = _delete_risk_score(record, collection, retention, archive, never_delete)
        archive_policy = _archive_policy(record, collection, archive, retention, delete_risk, never_delete)
        scores.append(
            {
                "schema_version": SIDECAR_SCHEMA_VERSION,
                "asset_id": asset_id,
                "path": _text(record.get("path")),
                "last_accessed_at": usage["last_accessed_at"],
                "access_count_30d": usage["access_count_30d"],
                "access_count_180d": usage["access_count_180d"],
                "agent_selected_count": usage["agent_selected_count"],
                "search_hit_count": usage["search_hit_count"],
                "citation_count": usage["citation_count"],
                "usage_score": usage["usage_score"],
                "retention_score": retention,
                "archive_score": archive,
                "delete_risk_score": delete_risk,
                "user_pinned": user_pinned,
                "never_delete": never_delete,
                "archive_policy": archive_policy,
                "score_reasons": _unique_strings([*retention_reasons, *archive_reasons, *delete_reasons]),
                "generated_at": now,
            }
        )
    return sorted(scores, key=lambda item: _path_key(item.get("path")))


def sidecar_stats(
    records: Iterable[dict[str, Any]],
    signatures: Iterable[dict[str, Any]],
    collections: Iterable[dict[str, Any]],
    scores: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    assets = list(attach_asset_ids(records))
    collection_rows = list(collections)
    score_rows = list(scores)
    collection_ids = {str(row.get("collection_id")) for row in collection_rows}
    duplicate_collections = {
        str(row.get("collection_id"))
        for row in collection_rows
        if float(row.get("duplicate_confidence") or 0) >= 0.7
    }
    by_policy = Counter(str(row.get("archive_policy") or "local") for row in score_rows)
    return {
        "total_assets": len(assets),
        "signature_records": len(list(signatures)),
        "collection_count": len(collection_ids),
        "duplicate_group_count": len(duplicate_collections),
        "review_required_count": sum(1 for item in assets if _review_required(item)),
        "archive_candidate_count": sum(
            1 for row in score_rows if str(row.get("archive_policy")) in {"nas", "cold", "delete_candidate"}
        ),
        "archive_policy_counts": dict(by_policy),
    }


def write_sidecar_report(
    stats: dict[str, Any],
    path: str | Path,
    *,
    asset_index_path: str | Path | None = None,
    sidecar_level: str = "text",
) -> None:
    lines = [
        "# 资产 Sidecar 统计报告",
        "",
        "本报告只描述索引层建议，不会移动、删除或重命名任何原始文件。",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        f"Sidecar 层级：`{sidecar_level}`",
    ]
    if asset_index_path:
        lines.append(f"来源资产索引：`{asset_index_path}`")
    lines.extend(
        [
            "",
            "## 概览",
            "",
            f"- 总文件数：{stats.get('total_assets', 0)}",
            f"- 资料族数量：{stats.get('collection_count', 0)}",
            f"- 疑似重复组数量：{stats.get('duplicate_group_count', 0)}",
            f"- 待复核数量：{stats.get('review_required_count', 0)}",
            f"- 可归档候选数量：{stats.get('archive_candidate_count', 0)}",
            "",
            "## 归档策略统计",
            "",
        ]
    )
    for policy, count in sorted((stats.get("archive_policy_counts") or {}).items()):
        lines.append(f"- `{policy}`：{count}")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_jsonl_records(records: list[dict[str, Any]], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    output.write_text("\n".join(lines).rstrip() + ("\n" if lines else ""), encoding="utf-8")


def normalize_base_name(value: Any) -> str:
    text = _text(value).casefold()
    text = re.sub(r"[\(\（\[]\s*\d+\s*[\)\）\]]$", "", text)
    text = re.sub(r"([_\-\s])?[a-f0-9]{8,}$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"([_\-\s])?v\d+(?:\.\d+)*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"([_\-\s])?(?:20\d{6}|20\d{4}|(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))$", "", text)
    text = re.sub(r"(副本|copy)$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\s\(\)（）\[\]【】]+", "", text)
    text = re.sub(r"[_\-—–]+", "_", text)
    return text.strip("_-. ")


def extract_quality_score(record: dict[str, Any], text_hash_status: str) -> float:
    status = _text(record.get("source_extract_status"))
    score = 0.15
    if status in {"ok", "up_to_date"}:
        score += 0.3
    if text_hash_status == "ok":
        score += 0.2
    if _optional_int(record.get("char_count")) and int(record.get("char_count") or 0) > 0:
        score += 0.1
    if _string_list(record.get("tags")):
        score += 0.05
    score += min(max(_optional_float(record.get("confidence")) or 0.0, 0.0), 1.0) * 0.2
    if status in {"review_only", "error", "skipped"} or bool(record.get("needs_human_review")):
        score = min(score, 0.35)
    return round(_clamp(score), 2)


def classify_virtual_directory(record: dict[str, Any]) -> tuple[str, str]:
    extension = _text(record.get("extension")).lower()
    status = _text(record.get("source_extract_status"))
    if _review_required(record) or extension in _ARCHIVE_EXTENSIONS or status in {"review_only", "error", "skipped"}:
        return "09", "09_压缩包_不可解析_待复核"
    text = " ".join(
        [
            _file_name(record.get("path")),
            _text(record.get("title")),
            _text(record.get("rule_title")),
            _text(record.get("summary")),
            " ".join(_string_list(record.get("tags"))),
        ]
    ).casefold()
    for directory_id, title, keywords in _VIRTUAL_DIRECTORIES[5:9]:
        if any(keyword.casefold() in text for keyword in keywords):
            return directory_id, title
    if "ftp" in text or "预算" in text or "测算" in text or "取数" in text:
        return "02", "02_FTP预算测算与取数"
    if any(keyword.casefold() in text for keyword in _VIRTUAL_DIRECTORIES[3][2]):
        return "03", "03_财务数据与核对"
    if any(keyword.casefold() in text for keyword in _VIRTUAL_DIRECTORIES[4][2]):
        return "04", "04_报表表样与模板"
    if any(keyword.casefold() in text for keyword in _VIRTUAL_DIRECTORIES[1][2]):
        return "01", "01_业务方案与需求"
    return "00", "00_总览与待处理"


def _collection_key(record: dict[str, Any], signature: dict[str, Any], directory_id: str) -> str:
    if _review_required(record):
        return f"{directory_id}/{record.get('asset_id')}"
    base_name_norm = _text(signature.get("base_name_norm")) or normalize_base_name(_file_name(record.get("path")))
    return f"{directory_id}/{base_name_norm or record.get('asset_id')}"


def _choose_canonical_member(members: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(members, key=_canonical_sort_key, reverse=True)[0]


def _canonical_sort_key(member: dict[str, Any]) -> tuple[float, int, int, int, str]:
    record = member["record"]
    facts = _name_facts(member["signature"].get("base_name"))
    clean_name = 0 if facts["hash_suffix"] or facts["copy_marker"] else 1
    status_bonus = 1 if _text(record.get("source_extract_status")) in {"ok", "up_to_date"} else 0
    review_bonus = 0 if _review_required(record) else 1
    confidence = _optional_float(record.get("confidence")) or 0.0
    return (
        confidence,
        clean_name,
        status_bonus,
        review_bonus,
        _text(record.get("path")),
    )


def _collection_title(member: dict[str, Any]) -> str:
    base_name = _text(member["signature"].get("base_name"))
    norm = _text(member["signature"].get("base_name_norm"))
    return _strip_known_suffixes(base_name) or norm or _file_name(member["record"].get("path")) or "未命名资料"


def _relation_for_member(member: dict[str, Any], canonical: dict[str, Any], members: list[dict[str, Any]]) -> str:
    if member["record"].get("asset_id") == canonical["record"].get("asset_id"):
        return "master"
    facts = _name_facts(member["signature"].get("base_name"))
    duplicate_confidence, _reason = _duplicate_signal(member, canonical, members)
    if duplicate_confidence >= 0.7:
        return "duplicate_candidate"
    if facts["version"] or facts["date"]:
        return "history"
    if "附件" in _text(member["signature"].get("base_name")) or "attachment" in _text(member["signature"].get("base_name")).casefold():
        return "attachment"
    if len(members) > 1:
        return "batch"
    return "unknown"


def _duplicate_signal(
    member: dict[str, Any],
    canonical: dict[str, Any],
    members: list[dict[str, Any]],
) -> tuple[float, str]:
    if member["record"].get("asset_id") == canonical["record"].get("asset_id"):
        return 0.0, ""
    text_hash = _text(member["signature"].get("text_hash"))
    canonical_text_hash = _text(canonical["signature"].get("text_hash"))
    if text_hash and text_hash == canonical_text_hash:
        return 0.95, "抽取文本 hash 完全相同"
    facts = _name_facts(member["signature"].get("base_name"))
    if facts["hash_suffix"] or facts["copy_marker"]:
        return 0.75, "文件名包含 hash 或副本后缀"
    member_size = member["signature"].get("file_size")
    canonical_size = canonical["signature"].get("file_size")
    if member_size and canonical_size and member_size == canonical_size and len(members) > 1:
        return 0.65, "同一资料族且文件大小相同"
    return 0.0, ""


def _merge_reason(member: dict[str, Any], members: list[dict[str, Any]], review_required: bool) -> str:
    if review_required:
        return "待复核或抽取异常文件不强行合并"
    if len(members) <= 1:
        return "单文件资料族"
    facts = _name_facts(member["signature"].get("base_name"))
    if facts["hash_suffix"]:
        return "同一 base_name_norm，文件名包含 hash 后缀"
    if facts["version"] or facts["date"]:
        return "同一 base_name_norm，文件名包含日期或版本线索"
    return "同一 base_name_norm，作为批次资料候选"


def _merge_confidence(relation: str, duplicate_confidence: float, group_size: int) -> float:
    if group_size <= 1:
        return 0.6
    if duplicate_confidence >= 0.9:
        return 0.95
    if relation == "duplicate_candidate":
        return 0.8
    if relation == "history":
        return 0.75
    if relation == "batch":
        return 0.55
    return 0.4


def _sort_key(member: dict[str, Any], collection_title: str) -> str:
    facts = _name_facts(member["signature"].get("base_name"))
    suffix = facts["date"] or facts["version"] or _file_name(member["record"].get("path"))
    return f"{member['directory_id']}/{normalize_base_name(collection_title)}/{suffix}".casefold()


def _retention_score(
    record: dict[str, Any],
    signature: dict[str, Any],
    collection: dict[str, Any],
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.25
    confidence = _optional_float(record.get("confidence")) or 0.0
    quality = _optional_float(signature.get("extract_quality_score")) or 0.0
    score += confidence * 0.25
    score += quality * 0.2
    if _text(signature.get("text_hash")):
        score += 0.08
        reasons.append("has_extracted_text")
    if _text(record.get("summary")):
        score += 0.07
        reasons.append("has_summary")
    tag_count = len(_string_list(record.get("tags")))
    if tag_count:
        score += min(tag_count, 5) * 0.025
        reasons.append("has_tags")
    relation = _text(collection.get("relation_type"))
    if relation == "master":
        score += 0.08
        reasons.append("master")
    elif relation == "duplicate_candidate":
        score -= 0.12
        reasons.append("duplicate_candidate")
    elif relation == "history":
        score -= 0.05
        reasons.append("history")
    if _review_required(record):
        score -= 0.08
        reasons.append("review_required")
    if confidence >= 0.8:
        reasons.append("high_confidence")
    return round(_clamp(score), 2), reasons


def _archive_score(
    record: dict[str, Any],
    collection: dict[str, Any],
    usage_score: float,
    retention_score: float,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.15 + (0.12 if usage_score == 0 else -usage_score * 0.2)
    relation = _text(collection.get("relation_type"))
    if relation == "duplicate_candidate":
        score += 0.3
        reasons.append("duplicate_candidate")
    elif relation == "history":
        score += 0.25
        reasons.append("history")
    elif relation == "batch":
        score += 0.1
        reasons.append("batch")
    if retention_score < 0.45:
        score += 0.15
        reasons.append("low_retention")
    if _review_required(record):
        score -= 0.2
        reasons.append("review_first")
    return round(_clamp(score), 2), reasons


def _delete_risk_score(
    record: dict[str, Any],
    collection: dict[str, Any],
    retention_score: float,
    archive_score: float,
    never_delete: bool,
) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.35 + retention_score * 0.4 - archive_score * 0.1
    relation = _text(collection.get("relation_type"))
    if _review_required(record):
        score += 0.25
        reasons.append("review_required")
    if relation == "master":
        score += 0.1
        reasons.append("master")
    if relation == "duplicate_candidate":
        score -= 0.18
    if never_delete:
        score += 0.5
        reasons.append("never_delete")
    return round(_clamp(score), 2), reasons


def _archive_policy(
    record: dict[str, Any],
    collection: dict[str, Any],
    archive_score: float,
    retention_score: float,
    delete_risk_score: float,
    never_delete: bool,
) -> str:
    if never_delete:
        return "local"
    if _review_required(record):
        return "review"
    duplicate_confidence = _optional_float(collection.get("duplicate_confidence")) or 0.0
    if (
        duplicate_confidence >= 0.9
        and retention_score < 0.45
        and delete_risk_score < 0.35
        and not bool(record.get("user_pinned"))
    ):
        return "delete_candidate"
    if archive_score >= 0.75:
        return "cold"
    if archive_score >= 0.55:
        return "nas"
    return "local"


def _usage_events_by_asset(events: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        asset_id = _text(event.get("asset_id"))
        if asset_id:
            grouped[asset_id].append(event)
    return grouped


def _usage_signals(events: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=30)
    cutoff_180 = now - timedelta(days=180)
    parsed = [(event, _parse_datetime(event.get("event_at"))) for event in events]
    access_30 = sum(1 for _event, event_at in parsed if event_at and event_at >= cutoff_30)
    access_180 = sum(1 for _event, event_at in parsed if event_at and event_at >= cutoff_180)
    agent_selected = sum(
        1
        for event, _event_at in parsed
        if _text(event.get("actor")) == "agent" and _text(event.get("event_type")) in {"selected", "agent_selected", "used"}
    )
    search_hits = sum(1 for event, _event_at in parsed if _text(event.get("event_type")) == "search_hit")
    citations = sum(1 for event, _event_at in parsed if _text(event.get("event_type")) in {"citation", "cited"})
    latest = max((event_at for _event, event_at in parsed if event_at), default=None)
    usage_score = min(1.0, access_30 * 0.03 + agent_selected * 0.1 + search_hits * 0.06 + citations * 0.12)
    return {
        "last_accessed_at": latest.isoformat() if latest else None,
        "access_count_30d": access_30,
        "access_count_180d": access_180,
        "agent_selected_count": agent_selected,
        "search_hit_count": search_hits,
        "citation_count": citations,
        "usage_score": round(usage_score, 2),
    }


def _name_facts(value: Any) -> dict[str, str]:
    text = _text(value)
    hash_match = re.search(r"(?:[_\-\s])([A-Fa-f0-9]{8,})$", text)
    version_match = re.search(r"(?i)v\d+(?:\.\d+)*", text)
    date_match = re.search(r"20\d{6}|20\d{4}|(?<!\d)(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d)", text)
    copy_match = re.search(r"[\(\（\[]\s*\d+\s*[\)\）\]]$|副本$|copy$", text, flags=re.IGNORECASE)
    return {
        "hash_suffix": hash_match.group(1) if hash_match else "",
        "version": version_match.group(0) if version_match else "",
        "date": date_match.group(0) if date_match else "",
        "copy_marker": copy_match.group(0) if copy_match else "",
    }


def _strip_known_suffixes(value: Any) -> str:
    text = _text(value).strip()
    text = re.sub(r"[\(\（\[]\s*\d+\s*[\)\）\]]$", "", text)
    text = re.sub(r"([_\-\s])?[A-Fa-f0-9]{8,}$", "", text)
    text = re.sub(r"([_\-\s])?v\d+(?:\.\d+)*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"([_\-\s])?(?:20\d{6}|20\d{4}|(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))$", "", text)
    return text.strip("_-. ")


def _text_hash_for_output(output_path: str, *, sidecar_level: str) -> tuple[str | None, str]:
    if sidecar_level == "light":
        return None, "not_requested"
    if not output_path:
        return None, "missing_output"
    candidate = Path(output_path)
    candidates = [candidate]
    if not candidate.is_absolute():
        candidates.append(Path.cwd() / output_path)
    for path in candidates:
        try:
            if path.is_file():
                return _hash_label(path.read_bytes()), "ok"
        except OSError:
            return None, "read_error"
    return None, "missing_output"


def _safe_stat(path: str) -> Any:
    if not path:
        return None
    try:
        candidate = Path(path)
        if candidate.exists():
            return candidate.stat()
    except OSError:
        return None
    return None


def _mtime_iso(stat: Any) -> str:
    return datetime.fromtimestamp(float(stat.st_mtime), timezone.utc).isoformat()


def _load_jsonl_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            payload = json.loads(line)
            if isinstance(payload, dict):
                records.append(payload)
    return records


def _review_required(record: dict[str, Any]) -> bool:
    return (
        bool(record.get("needs_human_review"))
        or bool(record.get("review_requires_confirmation"))
        or _text(record.get("asset_status")) == "review_required"
        or _text(record.get("source_extract_status")) in {"review_only", "error", "skipped"}
    )


def _review_note(record: dict[str, Any]) -> str:
    status = _text(record.get("source_extract_status"))
    if status in {"review_only", "error", "skipped"}:
        return "抽取状态需要复核，暂不强行合并到其他资料族。"
    return "资产状态需要复核，文件管理建议需等待人工确认。"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_label(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _path_key(value: Any) -> str:
    return _text(value).replace("\\", "/").casefold()


def _file_name(value: Any) -> str:
    path = _text(value).replace("\\", "/")
    return Path(path).name


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


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
