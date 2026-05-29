from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from .tags import tag_definitions


def load_browser_records(path: str | Path) -> list[dict[str, Any]]:
    """Load analysis JSONL records that can be shown in the HTML asset browser."""
    source = Path(path)
    records: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        status = str(record.get("status") or "ok")
        if status != "ok":
            continue
        records.append(_normalize_record(record))
    return records


def write_knowledge_browser_html(
    records: Iterable[dict[str, Any]],
    output_dir: str | Path,
    *,
    tags_config: dict[str, Any] | None = None,
    source_path: str | Path | None = None,
) -> dict[str, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    html_path = root / "knowledge-index.html"
    html_path.write_text(
        render_knowledge_browser_html(records, tags_config=tags_config, source_path=source_path),
        encoding="utf-8",
    )
    return {"knowledge_index_html": html_path}


def render_knowledge_browser_html(
    records: Iterable[dict[str, Any]],
    *,
    tags_config: dict[str, Any] | None = None,
    source_path: str | Path | None = None,
) -> str:
    normalized = [_normalize_record(record) for record in records]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path or ""),
        "records": normalized,
        "tags": [definition.as_dict() for definition in tag_definitions(tags_config)],
        "dimensions": _dimension_payload(tags_config),
        "stats": _stats_payload(normalized),
    }
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("__ANYFILE_WIKI_DATA__", data_json)


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    tags = _string_list(record.get("tags"))
    rule_tags = _string_list(record.get("rule_tags"))
    key_points = _string_list(record.get("key_points"))
    manual_tags = _string_list(record.get("manual_tags"))
    accepted_tags = _string_list(record.get("accepted_tags"))
    return {
        "path": _text(record.get("path")),
        "output_path": _text(record.get("output_path")),
        "status": _text(record.get("status") or "ok"),
        "title": _text(record.get("title") or Path(_text(record.get("path"))).name),
        "summary": _text(record.get("summary")),
        "tags": tags,
        "primary_tag": _text(record.get("primary_tag") or (tags[0] if tags else "")),
        "content_type": _text(record.get("content_type") or "file"),
        "extension": _text(record.get("extension")),
        "parser": _text(record.get("parser")),
        "embedding_allowed": bool(record.get("embedding_allowed")),
        "char_count": _int(record.get("char_count")),
        "word_count": _int(record.get("word_count")),
        "line_count": _int(record.get("line_count")),
        "analyzed_at": _text(record.get("analyzed_at")),
        "source_extract_status": _text(record.get("source_extract_status")),
        "analysis_method": _text(record.get("analysis_method") or "rules"),
        "confidence": _float(record.get("confidence")),
        "needs_human_review": bool(record.get("needs_human_review")),
        "review_reason": _text(record.get("review_reason")),
        "rule_title": _text(record.get("rule_title")),
        "rule_summary": _text(record.get("rule_summary")),
        "rule_tags": rule_tags,
        "key_points": key_points,
        "model_notes": _text(record.get("model_notes")),
        "error": _text(record.get("error")),
        "asset_schema_version": _int(record.get("asset_schema_version")),
        "asset_generated_at": _text(record.get("asset_generated_at")),
        "asset_source": _text(record.get("asset_source")),
        "asset_status": _text(record.get("asset_status") or "active"),
        "asset_status_label": _text(record.get("asset_status_label")),
        "review_decision": _text(record.get("review_decision")),
        "review_action": _text(record.get("review_action")),
        "review_action_title": _text(record.get("review_action_title")),
        "review_category": _text(record.get("review_category")),
        "review_severity": _text(record.get("review_severity")),
        "review_privacy_level": _text(record.get("review_privacy_level")),
        "review_requires_confirmation": bool(record.get("review_requires_confirmation")),
        "review_note": _text(record.get("review_note")),
        "review_decided_at": _text(record.get("review_decided_at")),
        "review_next_step": _text(record.get("review_next_step")),
        "review_warning": _text(record.get("review_warning")),
        "manual_tags": manual_tags,
        "accepted_tags": accepted_tags,
        "review_source_reason": _text(record.get("review_source_reason")),
        "review_source_action": _text(record.get("review_source_action")),
    }


def _dimension_payload(config: dict[str, Any] | None) -> list[dict[str, str]]:
    config = config or {}
    dimensions = config.get("dimensions")
    if not isinstance(dimensions, list):
        return []
    payload: list[dict[str, str]] = []
    for item in dimensions:
        if not isinstance(item, dict):
            continue
        dimension_id = _text(item.get("id"))
        if not dimension_id:
            continue
        payload.append(
            {
                "id": dimension_id,
                "zh": _text(item.get("zh") or dimension_id),
                "en": _text(item.get("en")),
                "purpose": _text(item.get("purpose")),
            }
        )
    return payload


def _stats_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    tag_counts = Counter(tag for record in records for tag in record["tags"])
    type_counts = Counter(record["content_type"] for record in records)
    method_counts = Counter(record["analysis_method"] for record in records)
    asset_status_counts = Counter(record["asset_status"] for record in records)
    return {
        "record_count": len(records),
        "needs_review_count": sum(1 for record in records if record["needs_human_review"]),
        "tag_counts": dict(tag_counts.most_common()),
        "content_type_counts": dict(type_counts.most_common()),
        "analysis_method_counts": dict(method_counts.most_common()),
        "asset_status_counts": dict(asset_status_counts.most_common()),
    }


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AnyFile Wiki 资产浏览</title>
  <style>
    :root {
      --bg: #f5f7fa;
      --panel: #ffffff;
      --panel-soft: #f9fafb;
      --text: #18202f;
      --muted: #667085;
      --faint: #98a2b3;
      --border: #d9e0ea;
      --accent: #0f766e;
      --accent-soft: #d9f4ef;
      --accent-strong: #115e59;
      --blue: #2563eb;
      --amber: #b45309;
      --red: #b42318;
      --green: #047857;
      --shadow: 0 10px 28px rgba(24, 32, 47, 0.08);
    }

    * {
      box-sizing: border-box;
    }

    html,
    body {
      height: 100%;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "Noto Sans CJK SC", Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      letter-spacing: 0;
    }

    button,
    input,
    select {
      font: inherit;
      letter-spacing: 0;
    }

    button {
      cursor: pointer;
    }

    code {
      font-family: "Cascadia Mono", "Consolas", monospace;
      font-size: 12px;
      color: #475467;
      overflow-wrap: anywhere;
    }

    .app {
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto auto 1fr;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 20px;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
    }

    .brand {
      min-width: 0;
    }

    .brand h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
      font-weight: 700;
    }

    .source {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      max-width: 62vw;
    }

    .metrics {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .metric {
      min-width: 90px;
      padding: 7px 10px;
      border: 1px solid var(--border);
      background: var(--panel-soft);
      border-radius: 8px;
    }

    .metric strong {
      display: block;
      font-size: 17px;
      line-height: 1.1;
    }

    .metric span {
      color: var(--muted);
      font-size: 12px;
    }

    .toolbar {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) auto auto auto;
      gap: 10px;
      align-items: center;
      padding: 12px 20px;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
    }

    .search {
      min-width: 0;
      width: 100%;
      height: 38px;
      padding: 0 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
    }

    .select {
      height: 38px;
      padding: 0 34px 0 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
    }

    .ghost-button {
      height: 38px;
      padding: 0 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
    }

    .ghost-button:hover,
    .facet-button:hover,
    .row:hover {
      border-color: #aab7c7;
      background: #f8fbff;
    }

    .active-filters {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      padding: 0 20px 12px;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
    }

    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 28px;
      max-width: 100%;
      padding: 3px 8px;
      border: 1px solid #9fd5ce;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent-strong);
      font-size: 12px;
    }

    .chip button {
      width: 18px;
      height: 18px;
      padding: 0;
      border: 0;
      border-radius: 50%;
      background: transparent;
      color: inherit;
      line-height: 18px;
    }

    .main {
      min-height: 0;
      display: grid;
      grid-template-columns: 280px minmax(360px, 1fr) 380px;
    }

    .sidebar,
    .detail {
      min-height: 0;
      overflow: auto;
      background: var(--panel);
    }

    .sidebar {
      border-right: 1px solid var(--border);
    }

    .detail {
      border-left: 1px solid var(--border);
    }

    .pane-title {
      position: sticky;
      top: 0;
      z-index: 2;
      padding: 14px 16px 10px;
      background: rgba(255, 255, 255, 0.96);
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(8px);
    }

    .pane-title h2 {
      margin: 0;
      font-size: 15px;
      line-height: 1.3;
    }

    .title-en {
      margin-left: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
    }

    .pane-title p {
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 12px;
    }

    .facet-section {
      padding: 12px 12px 4px;
      border-bottom: 1px solid #edf1f6;
    }

    .facet-heading {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 8px;
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }

    .facet-tree {
      display: grid;
      gap: 4px;
    }

    .tree-group {
      display: flex;
      align-items: center;
      width: 100%;
      height: 30px;
      padding: 0 8px;
      border: 0;
      background: transparent;
      color: var(--text);
      text-align: left;
      border-radius: 6px;
    }

    .tree-group:hover {
      background: #f1f5f9;
    }

    .tree-caret {
      width: 18px;
      color: var(--faint);
      flex: 0 0 auto;
    }

    .tree-label {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1 1 auto;
    }

    .count {
      flex: 0 0 auto;
      color: var(--muted);
      font-size: 12px;
    }

    .facet-button {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      min-height: 30px;
      padding: 4px 8px;
      border: 1px solid transparent;
      border-radius: 7px;
      background: transparent;
      color: var(--text);
      text-align: left;
    }

    .facet-button.is-active {
      border-color: #9fd5ce;
      background: var(--accent-soft);
      color: var(--accent-strong);
    }

    .facet-main {
      min-width: 0;
      flex: 1 1 auto;
    }

    .facet-label {
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 600;
    }

    .facet-key {
      display: block;
      margin-top: 1px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--muted);
      font-size: 11px;
    }

    .results {
      min-height: 0;
      overflow: auto;
      padding: 12px;
    }

    .result-meta {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 12px;
    }

    .meta-stack {
      display: grid;
      gap: 2px;
      min-width: 0;
    }

    .pager {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }

    .pager-button {
      min-height: 30px;
      padding: 2px 9px;
      border: 1px solid var(--border);
      border-radius: 7px;
      background: #fff;
      color: var(--text);
    }

    .pager-button:disabled {
      cursor: not-allowed;
      opacity: 0.45;
      background: #f2f4f7;
    }

    .page-line {
      color: var(--muted);
      white-space: nowrap;
    }

    .row-list {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .row {
      width: 100%;
      min-width: 0;
      padding: 11px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 2px 8px rgba(24, 32, 47, 0.03);
      text-align: left;
    }

    .row.is-selected {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.16);
    }

    .row-head {
      display: flex;
      gap: 8px;
      align-items: start;
      justify-content: space-between;
      min-width: 0;
    }

    .row-badges {
      display: inline-flex;
      gap: 6px;
      align-items: center;
      flex: 0 0 auto;
      flex-wrap: wrap;
      justify-content: flex-end;
      max-width: 46%;
    }

    .row-title {
      margin: 0;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 15px;
      font-weight: 700;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      background: #eef2f7;
      color: #344054;
      font-size: 12px;
      white-space: nowrap;
    }

    .badge.review {
      background: #fff4e5;
      color: var(--amber);
    }

    .badge.ok {
      background: #e8f6ef;
      color: var(--green);
    }

    .badge.warning {
      background: #fff4e5;
      color: var(--amber);
    }

    .badge.danger {
      background: #fee4e2;
      color: var(--red);
    }

    .badge.neutral {
      background: #eef2f7;
      color: #344054;
    }

    .row-path {
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .row-summary {
      margin: 8px 0 0;
      color: #344054;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .tag-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 9px;
    }

    .tag {
      max-width: 100%;
      display: inline-flex;
      gap: 5px;
      align-items: center;
      min-height: 24px;
      padding: 2px 7px;
      border-radius: 999px;
      background: #eef7ff;
      color: #1d4ed8;
      font-size: 12px;
    }

    .tag code {
      color: #475467;
      font-size: 11px;
    }

    .detail-body {
      padding: 16px;
    }

    .detail-empty {
      padding: 40px 18px;
      color: var(--muted);
      text-align: center;
    }

    .detail-title {
      margin: 0;
      font-size: 20px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }

    .detail-path {
      margin-top: 8px;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel-soft);
      color: #344054;
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .detail-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 10px;
    }

    .detail-section {
      margin-top: 18px;
      padding-top: 14px;
      border-top: 1px solid #edf1f6;
    }

    .detail-section h3 {
      margin: 0 0 8px;
      font-size: 14px;
    }

    .summary {
      margin: 0;
      color: #344054;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }

    .kv {
      display: grid;
      grid-template-columns: 96px minmax(0, 1fr);
      gap: 7px 10px;
      margin: 0;
    }

    .kv dt {
      color: var(--muted);
    }

    .kv dd {
      margin: 0;
      min-width: 0;
      overflow-wrap: anywhere;
    }

    .points {
      margin: 0;
      padding-left: 18px;
      color: #344054;
    }

    .points li + li {
      margin-top: 4px;
    }

    .empty-state {
      padding: 48px 20px;
      color: var(--muted);
      text-align: center;
      border: 1px dashed var(--border);
      border-radius: 8px;
      background: var(--panel);
    }

    @media (max-width: 1120px) {
      .main {
        grid-template-columns: 250px minmax(320px, 1fr);
      }

      .detail {
        grid-column: 1 / -1;
        border-left: 0;
        border-top: 1px solid var(--border);
        max-height: 48vh;
      }
    }

    @media (max-width: 760px) {
      .topbar,
      .toolbar {
        grid-template-columns: 1fr;
      }

      .topbar {
        align-items: flex-start;
        flex-direction: column;
      }

      .source {
        max-width: 100%;
      }

      .toolbar {
        display: grid;
      }

      .main {
        grid-template-columns: 1fr;
      }

      .sidebar,
      .detail {
        border-left: 0;
        border-right: 0;
        max-height: none;
      }

      .metrics {
        justify-content: flex-start;
      }

      .result-meta {
        align-items: flex-start;
        flex-direction: column;
      }

      .pager {
        justify-content: flex-start;
      }
    }
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <h1>AnyFile Wiki 资产浏览 <span class="title-en">Asset browser</span></h1>
        <div class="source" id="sourceLine"></div>
      </div>
      <div class="metrics" aria-label="知识库统计 / Knowledge base statistics">
        <div class="metric"><strong id="totalCount">0</strong><span>全部文件 / Total</span></div>
        <div class="metric"><strong id="visibleCount">0</strong><span>筛选结果 / Filtered</span></div>
        <div class="metric"><strong id="reviewCount">0</strong><span>需要复核 / Review</span></div>
      </div>
    </header>

    <section class="toolbar" aria-label="筛选工具栏 / Filter toolbar">
      <input class="search" id="searchInput" type="search" placeholder="搜索文件名、路径、摘要或标签 / Search name, path, summary, tags" autocomplete="off">
      <select class="select" id="sortSelect" aria-label="排序方式 / Sort order">
        <option value="title">按标题排序 / Title</option>
        <option value="path">按路径排序 / Path</option>
        <option value="confidence">按置信度排序 / Confidence</option>
        <option value="review">需要复核优先 / Review first</option>
      </select>
      <select class="select" id="pageSizeSelect" aria-label="每页条数 / Page size">
        <option value="10">每页 10 条 / 10 per page</option>
        <option value="15">每页 15 条 / 15 per page</option>
        <option value="30">每页 30 条 / 30 per page</option>
      </select>
      <button class="ghost-button" id="clearFilters" type="button">清空筛选 / Clear</button>
    </section>
    <div class="active-filters" id="activeFilters" aria-label="当前筛选 / Active filters"></div>

    <main class="main">
      <aside class="sidebar">
        <div class="pane-title">
          <h2>标签树 <span class="title-en">Tag tree</span></h2>
          <p>按层级逐步展开 / Browse by hierarchy</p>
        </div>
        <div id="facets"></div>
      </aside>

      <section class="results" aria-label="文件列表 / File list">
        <div class="result-meta">
          <div class="meta-stack">
            <span id="resultLine">文件列表 / File list</span>
            <span id="filterLine"></span>
          </div>
          <div class="pager" aria-label="分页 / Pagination">
            <button class="pager-button" id="prevPage" type="button">上一页 / Prev</button>
            <span class="page-line" id="pageLine">第 1 页 / Page 1</span>
            <button class="pager-button" id="nextPage" type="button">下一页 / Next</button>
          </div>
        </div>
        <ul class="row-list" id="assetList"></ul>
      </section>

      <aside class="detail" aria-label="文件详情 / File details">
        <div class="pane-title">
          <h2>文件详情 <span class="title-en">File details</span></h2>
          <p>摘要、标签和分析来源 / Summary, tags, analysis source</p>
        </div>
        <div id="detailPanel"></div>
      </aside>
    </main>
  </div>

  <script>
    const ANYFILE_WIKI_DATA = __ANYFILE_WIKI_DATA__;

    const labels = {
      dimensions: {
        document: "文档身份",
        topic: "主题",
        workflow: "处理状态",
        sensitivity: "敏感度",
        collection: "浏览层级",
        source: "来源",
        other: "其他标签"
      },
      dimensionEnglish: {
        document: "Document",
        topic: "Topic",
        workflow: "Workflow",
        sensitivity: "Sensitivity",
        collection: "Collection",
        source: "Source",
        other: "Other tags"
      },
      contentTypes: {
        code: "代码",
        config: "配置",
        docs: "项目文档 / Docs",
        document: "普通文档 / Document",
        test: "测试",
        file: "文件",
        unknown: "未知"
      },
      methods: {
        rules: "本地规则",
        "codex-mock": "模拟语义",
        "agent-llm": "宿主 Agent",
        "local-llm": "本地 LLM",
        "cloud-llm": "云端 LLM",
        "human-review": "人工复核"
      },
      review: {
        true: "需要复核",
        false: "暂不复核"
      },
      assetStatus: {
        active: "正常资产 / Active",
        confirmed: "人工确认 / Confirmed",
        manual_reviewed: "人工整理 / Manual reviewed",
        local_llm_queue: "本地 LLM 队列 / Local LLM queue",
        cloud_candidate: "云端候选 / Cloud candidate",
        cloud_authorization_conflict: "云端授权冲突 / Cloud conflict",
        ignore_candidate: "忽略候选 / Ignore candidate",
        deferred: "稍后复核 / Deferred",
        private_metadata_only: "仅保留私有元数据 / Private",
        review_required: "需要复核 / Review"
      }
    };

    const fallbackTags = {
      analysis: { zh: "内容分析", en: "Analysis", dimension: "topic" },
      cli: { zh: "命令行", en: "CLI", dimension: "topic" },
      code: { zh: "代码", en: "Code", dimension: "document" },
      config: { zh: "配置", en: "Config", dimension: "document" },
      configuration: { zh: "配置", en: "Configuration", dimension: "topic" },
      document: { zh: "普通文档", en: "Document", dimension: "document" },
      docs: { zh: "项目文档", en: "Docs", dimension: "document" },
      extract: { zh: "正文提取", en: "Extraction", dimension: "topic" },
      file: { zh: "普通文件", en: "File", dimension: "document" },
      inventory: { zh: "清单数据库", en: "Inventory", dimension: "topic" },
      license: { zh: "许可证", en: "License", dimension: "topic" },
      privacy: { zh: "隐私", en: "Privacy", dimension: "sensitivity" },
      readme: { zh: "说明文档", en: "README", dimension: "document" },
      review: { zh: "人工复核", en: "Review", dimension: "workflow" },
      roadmap: { zh: "路线图", en: "Roadmap", dimension: "topic" },
      roots: { zh: "扫描目录", en: "Roots", dimension: "topic" },
      scan: { zh: "扫描", en: "Scan", dimension: "topic" },
      tests: { zh: "测试", en: "Tests", dimension: "document" },
      "topic/business_budgeting": { zh: "预算测算", en: "Budgeting", dimension: "topic" },
      "topic/financial_data": { zh: "金融财务数据", en: "Financial data", dimension: "topic" },
      "topic/data_reconciliation": { zh: "数据核对", en: "Data reconciliation", dimension: "topic" },
      "topic/contract_agreement": { zh: "合同协议", en: "Contract", dimension: "topic" },
      "topic/project_delivery": { zh: "项目交付", en: "Project delivery", dimension: "topic" },
      "topic/reporting_material": { zh: "汇报培训材料", en: "Reporting", dimension: "topic" },
      "topic/template_form": { zh: "模板表样", en: "Template", dimension: "topic" }
    };

    const tagById = new Map((ANYFILE_WIKI_DATA.tags || []).map((tag) => [tag.id, tag]));
    const dimensionById = new Map((ANYFILE_WIKI_DATA.dimensions || []).map((dimension) => [dimension.id, dimension]));
    const state = {
      query: "",
      sort: "title",
      page: 1,
      pageSize: 10,
      filters: [],
      selectedPath: "",
      collapsed: new Set()
    };

    function escapeHtml(value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function normalize(value) {
      return String(value ?? "").toLowerCase();
    }

    function tagInfo(tag) {
      const fallback = fallbackTags[tag] || {};
      const meta = tagById.get(tag) || fallback;
      const dimension = meta.dimension || fallback.dimension || (String(tag).includes("/") ? String(tag).split("/", 1)[0] : "other");
      return {
        id: tag,
        zh: tagDisplayLabel(tag, meta, fallback),
        en: meta.en || fallback.en || tag,
        dimension
      };
    }

    function localName(tag) {
      const parts = String(tag).split("/");
      return parts[parts.length - 1].replace(/_/g, " ");
    }

    function tagDisplayLabel(tag, meta, fallback) {
      const zh = meta.zh || fallback.zh || localName(tag);
      const en = meta.en || fallback.en || "";
      if (!en || en === tag || zh.includes(" / ")) return zh;
      return `${zh} / ${en}`;
    }

    function dimensionLabel(dimension) {
      const meta = dimensionById.get(dimension) || {};
      const zh = meta.zh || labels.dimensions[dimension] || dimension;
      const en = meta.en || labels.dimensionEnglish[dimension] || "";
      if (!en || zh.includes(" / ")) return zh;
      return `${zh} / ${en}`;
    }

    function contentTypeLabel(value) {
      return labels.contentTypes[value] || value || "未知";
    }

    function methodLabel(value) {
      return labels.methods[value] || value || "未知";
    }

    function reviewLabel(value) {
      return labels.review[String(value)] || String(value);
    }

    function assetStatusLabel(value) {
      return labels.assetStatus[String(value)] || String(value || "active");
    }

    function assetStatusClass(value, needsConfirmation) {
      const status = String(value || "active");
      if (status === "cloud_authorization_conflict") return "danger";
      if (needsConfirmation || ["local_llm_queue", "cloud_candidate", "ignore_candidate", "deferred", "review_required"].includes(status)) return "warning";
      if (["confirmed", "manual_reviewed", "private_metadata_only"].includes(status)) return "ok";
      return "neutral";
    }

    function tagBadge(tag) {
      const meta = tagInfo(tag);
      return `<span class="tag" title="${escapeHtml(meta.en)}">${escapeHtml(meta.zh)} <code>${escapeHtml(meta.id)}</code></span>`;
    }

    function makeFilter(kind, value, label) {
      return { kind, value: String(value), label: String(label) };
    }

    function sameFilter(a, b) {
      return a.kind === b.kind && a.value === b.value;
    }

    function hasFilter(kind, value) {
      return state.filters.some((filter) => filter.kind === kind && filter.value === String(value));
    }

    function toggleFilter(kind, value, label) {
      const next = makeFilter(kind, value, label);
      const index = state.filters.findIndex((filter) => sameFilter(filter, next));
      if (index >= 0) {
        state.filters.splice(index, 1);
      } else {
        state.filters.push(next);
      }
      state.page = 1;
      render();
    }

    function removeFilter(kind, value) {
      state.filters = state.filters.filter((filter) => !(filter.kind === kind && filter.value === String(value)));
      state.page = 1;
      render();
    }

    function clearFilters() {
      state.query = "";
      state.filters = [];
      state.page = 1;
      document.getElementById("searchInput").value = "";
      render();
    }

    function searchText(record) {
      return normalize([
        record.title,
        record.path,
        record.summary,
        record.content_type,
        record.analysis_method,
        record.asset_status,
        record.review_decision,
        record.review_action,
        record.review_category,
        record.review_reason,
        record.review_next_step,
        record.review_warning,
        ...(record.tags || []),
        ...(record.rule_tags || []),
        ...(record.manual_tags || [])
      ].join(" "));
    }

    function matchesFilter(record, filter) {
      if (filter.kind === "tag") return (record.tags || []).includes(filter.value);
      if (filter.kind === "content_type") return record.content_type === filter.value;
      if (filter.kind === "analysis_method") return record.analysis_method === filter.value;
      if (filter.kind === "review") return String(Boolean(record.needs_human_review)) === filter.value;
      if (filter.kind === "asset_status") return String(record.asset_status || "active") === filter.value;
      return true;
    }

    function visibleRecords() {
      const query = normalize(state.query).trim();
      const grouped = new Map();
      for (const filter of state.filters) {
        if (!grouped.has(filter.kind)) grouped.set(filter.kind, []);
        grouped.get(filter.kind).push(filter);
      }
      const records = (ANYFILE_WIKI_DATA.records || []).filter((record) => {
        if (query && !searchText(record).includes(query)) return false;
        for (const filters of grouped.values()) {
          if (!filters.some((filter) => matchesFilter(record, filter))) return false;
        }
        return true;
      });
      return records.sort(compareRecords);
    }

    function compareRecords(a, b) {
      if (state.sort === "confidence") {
        return (b.confidence || 0) - (a.confidence || 0) || normalize(a.title).localeCompare(normalize(b.title));
      }
      if (state.sort === "review") {
        return Number(Boolean(b.review_requires_confirmation)) - Number(Boolean(a.review_requires_confirmation))
          || Number(Boolean(b.needs_human_review)) - Number(Boolean(a.needs_human_review))
          || normalize(a.title).localeCompare(normalize(b.title));
      }
      if (state.sort === "path") {
        return normalize(a.path).localeCompare(normalize(b.path));
      }
      return normalize(a.title).localeCompare(normalize(b.title));
    }

    function render() {
      const records = visibleRecords();
      const pageCount = Math.max(1, Math.ceil(records.length / state.pageSize));
      state.page = Math.min(Math.max(state.page, 1), pageCount);
      const startIndex = (state.page - 1) * state.pageSize;
      const pageRecords = records.slice(startIndex, startIndex + state.pageSize);
      if (pageRecords.length && !pageRecords.some((record) => record.path === state.selectedPath)) {
        state.selectedPath = pageRecords[0].path;
      }
      if (!records.length) {
        state.selectedPath = "";
      }
      renderHeader(records, pageRecords, pageCount);
      renderFilters();
      renderFacets(records);
      renderList(pageRecords);
      renderDetail(pageRecords.find((record) => record.path === state.selectedPath));
    }

    function renderHeader(records, pageRecords, pageCount) {
      const total = (ANYFILE_WIKI_DATA.records || []).length;
      const reviewTotal = (ANYFILE_WIKI_DATA.records || []).filter((record) => record.needs_human_review).length;
      const firstItem = records.length ? (state.page - 1) * state.pageSize + 1 : 0;
      const lastItem = records.length ? firstItem + pageRecords.length - 1 : 0;
      document.getElementById("totalCount").textContent = total;
      document.getElementById("visibleCount").textContent = records.length;
      document.getElementById("reviewCount").textContent = reviewTotal;
      const source = ANYFILE_WIKI_DATA.source_path ? `来源 / Source：${ANYFILE_WIKI_DATA.source_path}` : "来源 / Source：当前 HTML 内嵌知识索引数据";
      document.getElementById("sourceLine").textContent = `${source} · 生成时间 / Generated：${ANYFILE_WIKI_DATA.generated_at || ""}`;
      document.getElementById("resultLine").textContent = `文件列表 / File list：${firstItem}-${lastItem} / ${records.length}（全部 / Total ${total}）`;
      document.getElementById("filterLine").textContent = state.filters.length ? `已选筛选 / Active filters：${state.filters.length}` : `每页 / Page size：${state.pageSize}`;
      document.getElementById("pageLine").textContent = `第 ${state.page} / ${pageCount} 页 · Page ${state.page} of ${pageCount}`;
      document.getElementById("prevPage").disabled = state.page <= 1;
      document.getElementById("nextPage").disabled = state.page >= pageCount;
    }

    function renderFilters() {
      const root = document.getElementById("activeFilters");
      if (!state.filters.length && !state.query) {
        root.innerHTML = "";
        return;
      }
      const chips = [];
      if (state.query) {
        chips.push(`<span class="chip">搜索 / Search：${escapeHtml(state.query)} <button type="button" data-clear-query aria-label="清除搜索 / Clear search">×</button></span>`);
      }
      for (const filter of state.filters) {
        chips.push(`<span class="chip">${escapeHtml(filter.label)} <button type="button" data-kind="${escapeHtml(filter.kind)}" data-value="${escapeHtml(filter.value)}" aria-label="移除筛选 / Remove filter">×</button></span>`);
      }
      root.innerHTML = chips.join("");
      root.querySelectorAll("button[data-kind]").forEach((button) => {
        button.addEventListener("click", () => removeFilter(button.dataset.kind, button.dataset.value));
      });
      const clearQuery = root.querySelector("button[data-clear-query]");
      if (clearQuery) {
        clearQuery.addEventListener("click", () => {
          state.query = "";
          state.page = 1;
          document.getElementById("searchInput").value = "";
          render();
        });
      }
    }

    function renderFacets(filteredRecords) {
      const allRecords = ANYFILE_WIKI_DATA.records || [];
      const tagCounts = new CounterLike();
      const typeCounts = new CounterLike();
      const methodCounts = new CounterLike();
      const reviewCounts = new CounterLike();
      const assetStatusCounts = new CounterLike();
      for (const record of allRecords) {
        for (const tag of record.tags || []) tagCounts.add(tag);
        typeCounts.add(record.content_type || "unknown");
        methodCounts.add(record.analysis_method || "rules");
        reviewCounts.add(String(Boolean(record.needs_human_review)));
        assetStatusCounts.add(record.asset_status || "active");
      }

      const dimensions = new Map();
      for (const tag of tagCounts.keys()) {
        const info = tagInfo(tag);
        if (!dimensions.has(info.dimension)) dimensions.set(info.dimension, []);
        dimensions.get(info.dimension).push(tag);
      }

      const sections = [];
      sections.push(renderSimpleFacet("内容类型 / Content type", "content_type", typeCounts.entries(), contentTypeLabel));
      sections.push(renderSimpleFacet("资产状态 / Asset status", "asset_status", assetStatusCounts.entries(), assetStatusLabel));
      sections.push(renderSimpleFacet("分析方式 / Analysis method", "analysis_method", methodCounts.entries(), methodLabel));
      sections.push(renderSimpleFacet("复核状态 / Review status", "review", reviewCounts.entries(), reviewLabel));
      for (const [dimension, tags] of [...dimensions.entries()].sort((a, b) => dimensionLabel(a[0]).localeCompare(dimensionLabel(b[0])))) {
        sections.push(renderTagSection(dimension, tags.sort((a, b) => tagInfo(a).zh.localeCompare(tagInfo(b).zh)), tagCounts));
      }
      document.getElementById("facets").innerHTML = sections.join("");

      document.querySelectorAll("[data-filter-kind]").forEach((button) => {
        button.addEventListener("click", () => {
          toggleFilter(button.dataset.filterKind, button.dataset.filterValue, button.dataset.filterLabel);
        });
      });
      document.querySelectorAll("[data-collapse-id]").forEach((button) => {
        button.addEventListener("click", () => {
          const id = button.dataset.collapseId;
          if (state.collapsed.has(id)) state.collapsed.delete(id);
          else state.collapsed.add(id);
          render();
        });
      });
    }

    function renderSimpleFacet(title, kind, entries, labeler) {
      const buttons = entries
        .sort((a, b) => String(labeler(a[0])).localeCompare(String(labeler(b[0]))))
        .map(([value, count]) => {
          const label = labeler(value);
          const active = hasFilter(kind, value) ? " is-active" : "";
          return `<button class="facet-button${active}" type="button" data-filter-kind="${escapeHtml(kind)}" data-filter-value="${escapeHtml(value)}" data-filter-label="${escapeHtml(label)}">
            <span class="facet-main"><span class="facet-label">${escapeHtml(label)}</span><span class="facet-key">${escapeHtml(value)}</span></span>
            <span class="count">${count}</span>
          </button>`;
        })
        .join("");
      return `<section class="facet-section"><h3 class="facet-heading"><span>${escapeHtml(title)}</span></h3><div class="facet-tree">${buttons}</div></section>`;
    }

    function renderTagSection(dimension, tags, counts) {
      const tree = buildTagTree(dimension, tags, counts);
      return `<section class="facet-section">
        <h3 class="facet-heading"><span>${escapeHtml(dimensionLabel(dimension))}</span><code>${escapeHtml(dimension)}</code></h3>
        <div class="facet-tree">${renderTreeChildren(tree.children, dimension, 0)}</div>
      </section>`;
    }

    function buildTagTree(dimension, tags, counts) {
      const root = { children: new Map(), count: 0 };
      for (const tag of tags) {
        const parts = tag.split("/");
        const localParts = parts[0] === dimension ? parts.slice(1) : parts;
        if (!localParts.length) localParts.push(tag);
        let node = root;
        node.count += counts.get(tag);
        let prefix = dimension;
        localParts.forEach((part, index) => {
          prefix = `${prefix}/${part}`;
          if (!node.children.has(part)) node.children.set(part, { key: prefix, label: part, children: new Map(), count: 0, tag: "" });
          node = node.children.get(part);
          node.count += counts.get(tag);
          if (index === localParts.length - 1) node.tag = tag;
        });
      }
      return root;
    }

    function renderTreeChildren(children, sectionId, depth) {
      return [...children.values()]
        .sort((a, b) => displayNodeLabel(a).localeCompare(displayNodeLabel(b)))
        .map((node) => renderTreeNode(node, sectionId, depth))
        .join("");
    }

    function displayNodeLabel(node) {
      return node.tag ? tagInfo(node.tag).zh : node.label.replace(/_/g, " ");
    }

    function renderTreeNode(node, sectionId, depth) {
      const indent = depth * 14;
      if (node.children.size && !node.tag) {
        const collapseId = `${sectionId}:${node.key}`;
        const collapsed = state.collapsed.has(collapseId);
        const childHtml = collapsed ? "" : renderTreeChildren(node.children, sectionId, depth + 1);
        return `<button class="tree-group" type="button" style="padding-left:${8 + indent}px" data-collapse-id="${escapeHtml(collapseId)}">
          <span class="tree-caret">${collapsed ? "›" : "⌄"}</span>
          <span class="tree-label">${escapeHtml(displayNodeLabel(node))}</span>
          <span class="count">${node.count}</span>
        </button>${childHtml}`;
      }
      const info = tagInfo(node.tag);
      const active = hasFilter("tag", node.tag) ? " is-active" : "";
      return `<button class="facet-button${active}" type="button" style="padding-left:${8 + indent}px" data-filter-kind="tag" data-filter-value="${escapeHtml(node.tag)}" data-filter-label="${escapeHtml(info.zh)}">
        <span class="facet-main"><span class="facet-label">${escapeHtml(info.zh)}</span><span class="facet-key">${escapeHtml(info.id)}</span></span>
        <span class="count">${node.count}</span>
      </button>`;
    }

    function renderList(records) {
      const list = document.getElementById("assetList");
      if (!records.length) {
        list.innerHTML = `<li class="empty-state">没有匹配的文件 / No matching files</li>`;
        return;
      }
      list.innerHTML = records.map((record) => {
        const selected = record.path === state.selectedPath ? " is-selected" : "";
        const reviewClass = record.needs_human_review ? "review" : "ok";
        const reviewText = record.needs_human_review ? "需要复核 / Review" : "已分析 / Done";
        const statusClass = assetStatusClass(record.asset_status, record.review_requires_confirmation);
        const statusText = assetStatusLabel(record.asset_status);
        const tags = (record.tags || []).slice(0, 5).map(tagBadge).join("");
        return `<li>
          <button class="row${selected}" type="button" data-path="${escapeHtml(record.path)}">
            <div class="row-head">
              <h3 class="row-title">${escapeHtml(record.title || record.path)}</h3>
              <span class="row-badges">
                <span class="badge ${statusClass}">${escapeHtml(statusText)}</span>
                <span class="badge ${reviewClass}">${reviewText}</span>
              </span>
            </div>
            <div class="row-path">${escapeHtml(record.path)}</div>
            <p class="row-summary">${escapeHtml(record.summary || "暂无摘要 / No summary yet")}</p>
            <div class="tag-strip">${tags}</div>
          </button>
        </li>`;
      }).join("");
      list.querySelectorAll("button[data-path]").forEach((button) => {
        button.addEventListener("click", () => {
          state.selectedPath = button.dataset.path;
          render();
        });
      });
    }

    function renderDetail(record) {
      const panel = document.getElementById("detailPanel");
      if (!record) {
        panel.innerHTML = `<div class="detail-empty">请选择一个文件 / Select a file</div>`;
        return;
      }
      const tags = (record.tags || []).map(tagBadge).join("");
      const ruleTags = (record.rule_tags || []).map(tagBadge).join("");
      const manualTags = (record.manual_tags || []).map(tagBadge).join("");
      const acceptedTags = (record.accepted_tags || []).map(tagBadge).join("");
      const statusText = assetStatusLabel(record.asset_status);
      const statusClass = assetStatusClass(record.asset_status, record.review_requires_confirmation);
      const keyPoints = (record.key_points || []).length
        ? `<ul class="points">${record.key_points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>`
        : `<p class="summary">暂无理解要点 / No key points yet</p>`;
      panel.innerHTML = `<div class="detail-body">
        <h2 class="detail-title">${escapeHtml(record.title || record.path)}</h2>
        <div class="detail-path">${escapeHtml(record.path)}</div>
        <div class="detail-actions">
          <button class="ghost-button" type="button" id="copyPath">复制路径 / Copy path</button>
        </div>

        <section class="detail-section">
          <h3>摘要 / Summary</h3>
          <p class="summary">${escapeHtml(record.summary || "暂无摘要 / No summary yet")}</p>
        </section>

        <section class="detail-section">
          <h3>标签 / Tags</h3>
          <div class="tag-strip">${tags || "<span class=\"badge\">暂无标签 / No tags</span>"}</div>
        </section>

        <section class="detail-section">
          <h3>人工批复 / Human decision</h3>
          <dl class="kv">
            <dt>资产状态 / Asset</dt><dd><span class="badge ${statusClass}">${escapeHtml(statusText)}</span> <code>${escapeHtml(record.asset_status || "active")}</code></dd>
            <dt>批复选择 / Decision</dt><dd><code>${escapeHtml(record.review_decision || "none")}</code></dd>
            <dt>后续动作 / Action</dt><dd>${escapeHtml(record.review_action_title || record.review_action || "暂无 / None")} <code>${escapeHtml(record.review_action || "")}</code></dd>
            <dt>二次确认 / Confirm</dt><dd>${record.review_requires_confirmation ? "需要 / Required" : "不需要 / Not required"}</dd>
            <dt>人工标签 / Manual tags</dt><dd><div class="tag-strip">${manualTags || "<span class=\"badge\">暂无 / None</span>"}</div></dd>
            <dt>确认标签 / Accepted</dt><dd><div class="tag-strip">${acceptedTags || "<span class=\"badge\">暂无 / None</span>"}</div></dd>
            <dt>备注 / Note</dt><dd>${escapeHtml(record.review_note || "暂无 / None")}</dd>
            <dt>下一步 / Next step</dt><dd>${escapeHtml(record.review_next_step || "暂无 / None")}</dd>
            <dt>风险提示 / Warning</dt><dd>${escapeHtml(record.review_warning || "暂无 / None")}</dd>
          </dl>
        </section>

        <section class="detail-section">
          <h3>基本信息 / Basic info</h3>
          <dl class="kv">
            <dt>资产来源 / Asset source</dt><dd><code>${escapeHtml(record.asset_source || "analysis")}</code></dd>
            <dt>内容类型 / Type</dt><dd>${escapeHtml(contentTypeLabel(record.content_type))} <code>${escapeHtml(record.content_type)}</code></dd>
            <dt>分析方式 / Method</dt><dd>${escapeHtml(methodLabel(record.analysis_method))} <code>${escapeHtml(record.analysis_method)}</code></dd>
            <dt>置信度 / Confidence</dt><dd>${Number(record.confidence || 0).toFixed(2)}</dd>
            <dt>复核状态 / Review</dt><dd>${escapeHtml(record.needs_human_review ? "需要复核 / Review" : "暂不复核 / No review")} <code>${escapeHtml(record.review_reason || "")}</code></dd>
            <dt>向量许可 / Embedding</dt><dd>${record.embedding_allowed ? "允许 / Allowed" : "不允许 / Blocked"}</dd>
            <dt>解析器 / Parser</dt><dd><code>${escapeHtml(record.parser || "unknown")}</code></dd>
            <dt>扩展名 / Extension</dt><dd><code>${escapeHtml(record.extension || "")}</code></dd>
            <dt>字数估算 / Words</dt><dd>${Number(record.word_count || 0).toLocaleString("zh-CN")}</dd>
            <dt>字符数 / Characters</dt><dd>${Number(record.char_count || 0).toLocaleString("zh-CN")}</dd>
            <dt>行数 / Lines</dt><dd>${Number(record.line_count || 0).toLocaleString("zh-CN")}</dd>
          </dl>
        </section>

        <section class="detail-section">
          <h3>理解要点 / Key points</h3>
          ${keyPoints}
        </section>

        <section class="detail-section">
          <h3>规则版保留结果 / Rule fallback</h3>
          <dl class="kv">
            <dt>规则标题 / Rule title</dt><dd>${escapeHtml(record.rule_title || "暂无 / None")}</dd>
            <dt>规则摘要 / Rule summary</dt><dd>${escapeHtml(record.rule_summary || "暂无 / None")}</dd>
            <dt>规则标签 / Rule tags</dt><dd><div class="tag-strip">${ruleTags || "<span class=\"badge\">暂无 / None</span>"}</div></dd>
          </dl>
        </section>

        <section class="detail-section">
          <h3>模型说明 / Model notes</h3>
          <p class="summary">${escapeHtml(record.model_notes || "暂无模型说明 / No model notes")}</p>
        </section>
      </div>`;

      const copyPath = document.getElementById("copyPath");
      if (copyPath) {
        copyPath.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(record.path);
            copyPath.textContent = "已复制 / Copied";
            window.setTimeout(() => { copyPath.textContent = "复制路径 / Copy path"; }, 900);
          } catch (_error) {
            copyPath.textContent = "复制失败 / Copy failed";
            window.setTimeout(() => { copyPath.textContent = "复制路径 / Copy path"; }, 900);
          }
        });
      }
    }

    class CounterLike {
      constructor() {
        this.map = new Map();
      }
      add(key) {
        const value = String(key || "unknown");
        this.map.set(value, (this.map.get(value) || 0) + 1);
      }
      get(key) {
        return this.map.get(String(key)) || 0;
      }
      keys() {
        return this.map.keys();
      }
      entries() {
        return [...this.map.entries()];
      }
    }

    document.getElementById("searchInput").addEventListener("input", (event) => {
      state.query = event.target.value;
      state.page = 1;
      render();
    });
    document.getElementById("sortSelect").addEventListener("change", (event) => {
      state.sort = event.target.value;
      state.page = 1;
      render();
    });
    document.getElementById("pageSizeSelect").addEventListener("change", (event) => {
      state.pageSize = Number(event.target.value) || 10;
      state.page = 1;
      render();
    });
    document.getElementById("prevPage").addEventListener("click", () => {
      state.page = Math.max(1, state.page - 1);
      render();
    });
    document.getElementById("nextPage").addEventListener("click", () => {
      state.page += 1;
      render();
    });
    document.getElementById("clearFilters").addEventListener("click", clearFilters);

    render();
  </script>
</body>
</html>
"""
