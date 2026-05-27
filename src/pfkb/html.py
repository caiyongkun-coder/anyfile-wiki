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
    return _HTML_TEMPLATE.replace("__PFKB_DATA__", data_json)


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    tags = _string_list(record.get("tags"))
    rule_tags = _string_list(record.get("rule_tags"))
    key_points = _string_list(record.get("key_points"))
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
                "purpose": _text(item.get("purpose")),
            }
        )
    return payload


def _stats_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    tag_counts = Counter(tag for record in records for tag in record["tags"])
    type_counts = Counter(record["content_type"] for record in records)
    method_counts = Counter(record["analysis_method"] for record in records)
    return {
        "record_count": len(records),
        "needs_review_count": sum(1 for record in records if record["needs_human_review"]),
        "tag_counts": dict(tag_counts.most_common()),
        "content_type_counts": dict(type_counts.most_common()),
        "analysis_method_counts": dict(method_counts.most_common()),
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
  <title>PFKB 资产浏览</title>
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
      grid-template-columns: minmax(220px, 1fr) auto auto;
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
    }
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <h1>PFKB 资产浏览</h1>
        <div class="source" id="sourceLine"></div>
      </div>
      <div class="metrics" aria-label="知识库统计">
        <div class="metric"><strong id="totalCount">0</strong><span>全部文件</span></div>
        <div class="metric"><strong id="visibleCount">0</strong><span>当前可见</span></div>
        <div class="metric"><strong id="reviewCount">0</strong><span>需要复核</span></div>
      </div>
    </header>

    <section class="toolbar" aria-label="筛选工具栏">
      <input class="search" id="searchInput" type="search" placeholder="搜索文件名、路径、摘要或标签" autocomplete="off">
      <select class="select" id="sortSelect" aria-label="排序方式">
        <option value="title">按标题排序</option>
        <option value="path">按路径排序</option>
        <option value="confidence">按置信度排序</option>
        <option value="review">需要复核优先</option>
      </select>
      <button class="ghost-button" id="clearFilters" type="button">清空筛选</button>
    </section>
    <div class="active-filters" id="activeFilters" aria-label="当前筛选"></div>

    <main class="main">
      <aside class="sidebar">
        <div class="pane-title">
          <h2>标签树</h2>
          <p>按层级逐步展开</p>
        </div>
        <div id="facets"></div>
      </aside>

      <section class="results" aria-label="文件列表">
        <div class="result-meta">
          <span id="resultLine">文件列表</span>
          <span id="filterLine"></span>
        </div>
        <ul class="row-list" id="assetList"></ul>
      </section>

      <aside class="detail" aria-label="文件详情">
        <div class="pane-title">
          <h2>文件详情</h2>
          <p>摘要、标签和分析来源</p>
        </div>
        <div id="detailPanel"></div>
      </aside>
    </main>
  </div>

  <script>
    const PFKB_DATA = __PFKB_DATA__;

    const labels = {
      dimensions: {
        document: "文档形态",
        topic: "主题",
        workflow: "处理状态",
        sensitivity: "敏感度",
        collection: "集合",
        source: "来源",
        other: "其他标签"
      },
      contentTypes: {
        code: "代码",
        config: "配置",
        docs: "文档",
        document: "文档",
        test: "测试",
        file: "文件",
        unknown: "未知"
      },
      methods: {
        rules: "本地规则",
        "codex-mock": "模拟语义",
        "local-llm": "本地 LLM",
        "cloud-llm": "云端 LLM"
      },
      review: {
        true: "需要复核",
        false: "暂不复核"
      }
    };

    const tagById = new Map((PFKB_DATA.tags || []).map((tag) => [tag.id, tag]));
    const dimensionById = new Map((PFKB_DATA.dimensions || []).map((dimension) => [dimension.id, dimension]));
    const state = {
      query: "",
      sort: "title",
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
      const meta = tagById.get(tag) || {};
      const dimension = meta.dimension || (String(tag).includes("/") ? String(tag).split("/", 1)[0] : "other");
      return {
        id: tag,
        zh: meta.zh || localName(tag),
        en: meta.en || tag,
        dimension
      };
    }

    function localName(tag) {
      const parts = String(tag).split("/");
      return parts[parts.length - 1].replace(/_/g, " ");
    }

    function dimensionLabel(dimension) {
      const meta = dimensionById.get(dimension) || {};
      return meta.zh || labels.dimensions[dimension] || dimension;
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
      render();
    }

    function removeFilter(kind, value) {
      state.filters = state.filters.filter((filter) => !(filter.kind === kind && filter.value === String(value)));
      render();
    }

    function clearFilters() {
      state.query = "";
      state.filters = [];
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
        record.review_reason,
        ...(record.tags || []),
        ...(record.rule_tags || [])
      ].join(" "));
    }

    function matchesFilter(record, filter) {
      if (filter.kind === "tag") return (record.tags || []).includes(filter.value);
      if (filter.kind === "content_type") return record.content_type === filter.value;
      if (filter.kind === "analysis_method") return record.analysis_method === filter.value;
      if (filter.kind === "review") return String(Boolean(record.needs_human_review)) === filter.value;
      return true;
    }

    function visibleRecords() {
      const query = normalize(state.query).trim();
      const grouped = new Map();
      for (const filter of state.filters) {
        if (!grouped.has(filter.kind)) grouped.set(filter.kind, []);
        grouped.get(filter.kind).push(filter);
      }
      const records = (PFKB_DATA.records || []).filter((record) => {
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
        return Number(Boolean(b.needs_human_review)) - Number(Boolean(a.needs_human_review)) || normalize(a.title).localeCompare(normalize(b.title));
      }
      if (state.sort === "path") {
        return normalize(a.path).localeCompare(normalize(b.path));
      }
      return normalize(a.title).localeCompare(normalize(b.title));
    }

    function render() {
      const records = visibleRecords();
      if (records.length && !records.some((record) => record.path === state.selectedPath)) {
        state.selectedPath = records[0].path;
      }
      if (!records.length) {
        state.selectedPath = "";
      }
      renderHeader(records);
      renderFilters();
      renderFacets(records);
      renderList(records);
      renderDetail(records.find((record) => record.path === state.selectedPath));
    }

    function renderHeader(records) {
      const total = (PFKB_DATA.records || []).length;
      const reviewTotal = (PFKB_DATA.records || []).filter((record) => record.needs_human_review).length;
      document.getElementById("totalCount").textContent = total;
      document.getElementById("visibleCount").textContent = records.length;
      document.getElementById("reviewCount").textContent = reviewTotal;
      const source = PFKB_DATA.source_path ? `来源：${PFKB_DATA.source_path}` : "来源：当前 HTML 内嵌知识索引数据";
      document.getElementById("sourceLine").textContent = `${source} · 生成时间：${PFKB_DATA.generated_at || ""}`;
      document.getElementById("resultLine").textContent = `文件列表：${records.length} / ${total}`;
      document.getElementById("filterLine").textContent = state.filters.length ? `已选 ${state.filters.length} 个筛选` : "";
    }

    function renderFilters() {
      const root = document.getElementById("activeFilters");
      if (!state.filters.length && !state.query) {
        root.innerHTML = "";
        return;
      }
      const chips = [];
      if (state.query) {
        chips.push(`<span class="chip">搜索：${escapeHtml(state.query)} <button type="button" data-clear-query aria-label="清除搜索">×</button></span>`);
      }
      for (const filter of state.filters) {
        chips.push(`<span class="chip">${escapeHtml(filter.label)} <button type="button" data-kind="${escapeHtml(filter.kind)}" data-value="${escapeHtml(filter.value)}" aria-label="移除筛选">×</button></span>`);
      }
      root.innerHTML = chips.join("");
      root.querySelectorAll("button[data-kind]").forEach((button) => {
        button.addEventListener("click", () => removeFilter(button.dataset.kind, button.dataset.value));
      });
      const clearQuery = root.querySelector("button[data-clear-query]");
      if (clearQuery) {
        clearQuery.addEventListener("click", () => {
          state.query = "";
          document.getElementById("searchInput").value = "";
          render();
        });
      }
    }

    function renderFacets(filteredRecords) {
      const allRecords = PFKB_DATA.records || [];
      const tagCounts = new CounterLike();
      const typeCounts = new CounterLike();
      const methodCounts = new CounterLike();
      const reviewCounts = new CounterLike();
      for (const record of allRecords) {
        for (const tag of record.tags || []) tagCounts.add(tag);
        typeCounts.add(record.content_type || "unknown");
        methodCounts.add(record.analysis_method || "rules");
        reviewCounts.add(String(Boolean(record.needs_human_review)));
      }

      const dimensions = new Map();
      for (const tag of tagCounts.keys()) {
        const info = tagInfo(tag);
        if (!dimensions.has(info.dimension)) dimensions.set(info.dimension, []);
        dimensions.get(info.dimension).push(tag);
      }

      const sections = [];
      sections.push(renderSimpleFacet("内容类型", "content_type", typeCounts.entries(), contentTypeLabel));
      sections.push(renderSimpleFacet("分析方式", "analysis_method", methodCounts.entries(), methodLabel));
      sections.push(renderSimpleFacet("复核状态", "review", reviewCounts.entries(), reviewLabel));
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
        list.innerHTML = `<li class="empty-state">没有匹配的文件</li>`;
        return;
      }
      list.innerHTML = records.map((record) => {
        const selected = record.path === state.selectedPath ? " is-selected" : "";
        const reviewClass = record.needs_human_review ? "review" : "ok";
        const reviewText = record.needs_human_review ? "需要复核" : "已分析";
        const tags = (record.tags || []).slice(0, 5).map(tagBadge).join("");
        return `<li>
          <button class="row${selected}" type="button" data-path="${escapeHtml(record.path)}">
            <div class="row-head">
              <h3 class="row-title">${escapeHtml(record.title || record.path)}</h3>
              <span class="badge ${reviewClass}">${reviewText}</span>
            </div>
            <div class="row-path">${escapeHtml(record.path)}</div>
            <p class="row-summary">${escapeHtml(record.summary || "暂无摘要")}</p>
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
        panel.innerHTML = `<div class="detail-empty">请选择一个文件</div>`;
        return;
      }
      const tags = (record.tags || []).map(tagBadge).join("");
      const ruleTags = (record.rule_tags || []).map(tagBadge).join("");
      const keyPoints = (record.key_points || []).length
        ? `<ul class="points">${record.key_points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>`
        : `<p class="summary">暂无理解要点</p>`;
      panel.innerHTML = `<div class="detail-body">
        <h2 class="detail-title">${escapeHtml(record.title || record.path)}</h2>
        <div class="detail-path">${escapeHtml(record.path)}</div>
        <div class="detail-actions">
          <button class="ghost-button" type="button" id="copyPath">复制路径</button>
        </div>

        <section class="detail-section">
          <h3>摘要</h3>
          <p class="summary">${escapeHtml(record.summary || "暂无摘要")}</p>
        </section>

        <section class="detail-section">
          <h3>标签</h3>
          <div class="tag-strip">${tags || "<span class=\"badge\">暂无标签</span>"}</div>
        </section>

        <section class="detail-section">
          <h3>基本信息</h3>
          <dl class="kv">
            <dt>内容类型</dt><dd>${escapeHtml(contentTypeLabel(record.content_type))} <code>${escapeHtml(record.content_type)}</code></dd>
            <dt>分析方式</dt><dd>${escapeHtml(methodLabel(record.analysis_method))} <code>${escapeHtml(record.analysis_method)}</code></dd>
            <dt>置信度</dt><dd>${Number(record.confidence || 0).toFixed(2)}</dd>
            <dt>复核状态</dt><dd>${escapeHtml(record.needs_human_review ? "需要复核" : "暂不复核")} <code>${escapeHtml(record.review_reason || "")}</code></dd>
            <dt>向量许可</dt><dd>${record.embedding_allowed ? "允许" : "不允许"}</dd>
            <dt>解析器</dt><dd><code>${escapeHtml(record.parser || "unknown")}</code></dd>
            <dt>扩展名</dt><dd><code>${escapeHtml(record.extension || "")}</code></dd>
            <dt>字数估算</dt><dd>${Number(record.word_count || 0).toLocaleString("zh-CN")}</dd>
            <dt>字符数</dt><dd>${Number(record.char_count || 0).toLocaleString("zh-CN")}</dd>
            <dt>行数</dt><dd>${Number(record.line_count || 0).toLocaleString("zh-CN")}</dd>
          </dl>
        </section>

        <section class="detail-section">
          <h3>理解要点</h3>
          ${keyPoints}
        </section>

        <section class="detail-section">
          <h3>规则版保留结果</h3>
          <dl class="kv">
            <dt>规则标题</dt><dd>${escapeHtml(record.rule_title || "暂无")}</dd>
            <dt>规则摘要</dt><dd>${escapeHtml(record.rule_summary || "暂无")}</dd>
            <dt>规则标签</dt><dd><div class="tag-strip">${ruleTags || "<span class=\"badge\">暂无</span>"}</div></dd>
          </dl>
        </section>

        <section class="detail-section">
          <h3>模型说明</h3>
          <p class="summary">${escapeHtml(record.model_notes || "暂无模型说明")}</p>
        </section>
      </div>`;

      const copyPath = document.getElementById("copyPath");
      if (copyPath) {
        copyPath.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(record.path);
            copyPath.textContent = "已复制";
            window.setTimeout(() => { copyPath.textContent = "复制路径"; }, 900);
          } catch (_error) {
            copyPath.textContent = "复制失败";
            window.setTimeout(() => { copyPath.textContent = "复制路径"; }, 900);
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
      render();
    });
    document.getElementById("sortSelect").addEventListener("change", (event) => {
      state.sort = event.target.value;
      render();
    });
    document.getElementById("clearFilters").addEventListener("click", clearFilters);

    render();
  </script>
</body>
</html>
"""
