from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json


def write_human_review_html(
    items: Iterable[Any],
    output_dir: str | Path,
    *,
    source_path: str | Path | None = None,
    server_mode: bool = False,
    submit_url: str = "/api/decisions",
) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    html_path = root / "human-review.html"
    html_path.write_text(
        render_human_review_html(items, source_path=source_path, server_mode=server_mode, submit_url=submit_url),
        encoding="utf-8",
    )
    return html_path


def render_human_review_html(
    items: Iterable[Any],
    *,
    source_path: str | Path | None = None,
    server_mode: bool = False,
    submit_url: str = "/api/decisions",
) -> str:
    normalized = [_normalize_item(item) for item in items]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path or ""),
        "items": normalized,
        "server_mode": bool(server_mode),
        "submit_url": submit_url,
    }
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    mode_class = "mode-server" if server_mode else "mode-static"
    controls = _server_controls() if server_mode else _static_controls()
    manual_export = "" if server_mode else _manual_export_panel()
    return (
        _HTML_TEMPLATE.replace("__ANYFILE_WIKI_REVIEW_DATA__", data_json)
        .replace("__ANYFILE_WIKI_REVIEW_MODE__", mode_class)
        .replace("__ANYFILE_WIKI_REVIEW_CONTROLS__", controls)
        .replace("__ANYFILE_WIKI_MANUAL_EXPORT__", manual_export)
    )


def _normalize_item(item: Any) -> dict[str, Any]:
    if is_dataclass(item):
        record = asdict(item)
    elif isinstance(item, dict):
        record = dict(item)
    else:
        record = dict(getattr(item, "__dict__", {}))
    tags = record.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    path = _text(record.get("path"))
    category = _text(record.get("category"))
    reason_code = _text(record.get("reason_code"))
    return {
        "id": f"{path}::{category}::{reason_code}",
        "path": path,
        "name": Path(path).name or path,
        "category": category,
        "reason_code": reason_code,
        "reason": _text(record.get("reason")),
        "action": _text(record.get("action")),
        "severity": _text(record.get("severity") or "medium"),
        "access_policy": _text(record.get("access_policy")),
        "policy_source": _text(record.get("policy_source")),
        "policy_reason": _text(record.get("policy_reason")),
        "extraction_status": _text(record.get("extraction_status")),
        "analysis_method": _text(record.get("analysis_method")),
        "confidence": _optional_float(record.get("confidence")),
        "tags": [str(tag) for tag in tags if str(tag)],
    }


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _static_controls() -> str:
    return """
      <button class=\"button\" type=\"button\" id=\"copyJsonl\">复制 JSONL / Copy</button>
      <button class=\"button\" type=\"button\" id=\"showJsonl\">显示 JSONL / Show</button>
      <button class=\"button primary\" type=\"button\" id=\"exportJsonl\">导出批复 / Export</button>"""


def _server_controls() -> str:
    return """
      <button class=\"button\" type=\"button\" id=\"saveDraft\">保存草稿 / Save</button>
      <button class=\"button primary\" type=\"button\" id=\"submitReview\">提交批复 / Submit</button>
      <span class=\"server-status\" id=\"serverStatus\" role=\"status\" aria-live=\"polite\"></span>"""


def _manual_export_panel() -> str:
    return """
    <section class=\"manual-export\" id=\"manualExport\" hidden aria-label=\"手动导出 JSONL / Manual JSONL export\">
      <div class=\"manual-export-row\">
        <div>
          <p class=\"manual-export-title\" id=\"manualExportTitle\">手动保存 review-decisions.jsonl / Manual save</p>
          <p class=\"manual-export-help\" id=\"manualExportHelp\"></p>
        </div>
        <button class=\"button\" type=\"button\" id=\"selectJsonl\">选中文本 / Select all</button>
      </div>
      <textarea id=\"manualJsonl\" readonly spellcheck=\"false\" aria-label=\"review-decisions.jsonl 内容 / review-decisions.jsonl content\"></textarea>
    </section>"""


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AnyFile Wiki 人工复核</title>
  <style>
    :root {
      --bg: #f4f6f8;
      --panel: #ffffff;
      --panel-soft: #f9fafb;
      --text: #18202f;
      --muted: #667085;
      --border: #d7dee8;
      --accent: #0f766e;
      --accent-soft: #d9f4ef;
      --blue: #2563eb;
      --amber: #b45309;
      --red: #b42318;
      --green: #047857;
      --shadow: 0 10px 26px rgba(24, 32, 47, 0.07);
    }

    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", "Noto Sans CJK SC", Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      letter-spacing: 0;
    }

    button, input, select, textarea {
      font: inherit;
      letter-spacing: 0;
    }

    button { cursor: pointer; }
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

    .brand h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
    }

    .source {
      margin-top: 4px;
      max-width: 64vw;
      color: var(--muted);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .title-en {
      margin-left: 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
      white-space: nowrap;
    }

    .metrics {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .metric {
      min-width: 88px;
      padding: 7px 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel-soft);
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
      grid-template-columns: minmax(220px, 1fr) repeat(6, auto);
      gap: 10px;
      padding: 12px 20px;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      align-items: center;
    }

    .search,
    .select,
    .button {
      height: 38px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
    }

    .search {
      min-width: 0;
      width: 100%;
      padding: 0 12px;
    }

    .select {
      padding: 0 32px 0 10px;
    }

    .button {
      padding: 0 12px;
      white-space: nowrap;
    }

    .button:disabled {
      cursor: not-allowed;
      opacity: 0.62;
    }

    .button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }

    .button.primary.is-done {
      border-color: var(--green);
      background: var(--green);
      animation: exportDonePulse 560ms ease-out;
    }

    .button:hover,
    .item-row:hover {
      border-color: #aab7c7;
      background: #f8fbff;
    }

    .button.primary:hover,
    .button.primary.is-done:hover {
      color: #fff;
    }

    .button.primary:hover {
      border-color: var(--accent);
      background: var(--accent);
    }

    .button.primary.is-done:hover {
      border-color: var(--green);
      background: var(--green);
    }

    .manual-export {
      margin: 0;
      padding: 12px 20px;
      background: #fffaf0;
      border-bottom: 1px solid #f3d19e;
    }

    .manual-export[hidden] {
      display: none;
    }

    .manual-export-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }

    .manual-export-title {
      margin: 0;
      color: #7c2d12;
      font-weight: 700;
    }

    .manual-export-help {
      margin: 4px 0 0;
      color: #7c2d12;
      font-size: 12px;
    }

    .manual-export textarea {
      display: block;
      width: 100%;
      min-height: 150px;
      padding: 10px;
      border: 1px solid #f3d19e;
      border-radius: 8px;
      background: #fff;
      color: var(--text);
      font-family: "Cascadia Mono", "Consolas", monospace;
      font-size: 12px;
      resize: vertical;
      white-space: pre;
    }

    .server-status {
      min-height: 20px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }

    @keyframes exportDonePulse {
      0% {
        transform: scale(1);
        box-shadow: 0 0 0 0 rgba(4, 120, 87, 0.32);
      }
      45% {
        transform: scale(1.03);
        box-shadow: 0 0 0 8px rgba(4, 120, 87, 0.16);
      }
      100% {
        transform: scale(1);
        box-shadow: 0 0 0 0 rgba(4, 120, 87, 0);
      }
    }

    .main {
      min-height: 0;
      display: grid;
      grid-template-columns: 280px minmax(360px, 1fr) 420px;
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
      padding: 12px;
      border-bottom: 1px solid #edf1f6;
    }

    .facet-heading {
      margin: 0 0 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }

    .facet-button {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      min-height: 32px;
      margin-top: 4px;
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
      color: #115e59;
    }

    .facet-label {
      min-width: 0;
      flex: 1 1 auto;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 600;
    }

    .count {
      color: var(--muted);
      font-size: 12px;
    }

    .results {
      min-height: 0;
      overflow: auto;
      padding: 12px;
    }

    .result-meta {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 12px;
    }

    .pager {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }

    .pager button {
      min-height: 30px;
      padding: 2px 9px;
      border: 1px solid var(--border);
      border-radius: 7px;
      background: #fff;
    }

    .pager button:disabled {
      cursor: not-allowed;
      opacity: 0.45;
      background: #f2f4f7;
    }

    .item-list {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .item-row {
      width: 100%;
      min-width: 0;
      padding: 11px 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 2px 8px rgba(24, 32, 47, 0.03);
      text-align: left;
    }

    .item-row.is-selected {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.16);
    }

    .row-head {
      display: flex;
      gap: 8px;
      justify-content: space-between;
      align-items: start;
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

    .row-path,
    .row-reason {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      background: #eef2f7;
      color: #344054;
      font-size: 12px;
      white-space: nowrap;
    }

    .badge.high { background: #ffe7e5; color: var(--red); }
    .badge.medium { background: #fff4e5; color: var(--amber); }
    .badge.low { background: #e8f6ef; color: var(--green); }
    .badge.decided { background: #e7f0ff; color: var(--blue); }

    .detail-body {
      padding: 16px;
    }

    .detail-empty {
      padding: 42px 18px;
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
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .detail-section {
      margin-top: 18px;
      padding-top: 14px;
      border-top: 1px solid #edf1f6;
    }

    .decision-section {
      position: sticky;
      top: 54px;
      z-index: 1;
      margin: 12px -16px 0;
      padding: 12px 16px 14px;
      border-top: 0;
      border-bottom: 1px solid #edf1f6;
      background: rgba(255, 255, 255, 0.97);
      backdrop-filter: blur(8px);
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
      grid-template-columns: 110px minmax(0, 1fr);
      gap: 7px 10px;
      margin: 0;
    }

    .kv dt { color: var(--muted); }
    .kv dd {
      margin: 0;
      min-width: 0;
      overflow-wrap: anywhere;
    }

    .decision-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .decision-button {
      min-height: 38px;
      padding: 6px 8px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
      text-align: left;
    }

    .decision-button.is-active {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
      font-weight: 700;
      box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.16);
    }

    .decision-button.is-active::before {
      content: "✓ ";
    }

    .field {
      display: grid;
      gap: 6px;
      margin-top: 10px;
    }

    .field label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }

    .input,
    .textarea {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
    }

    .input {
      height: 36px;
      padding: 0 10px;
    }

    .textarea {
      min-height: 86px;
      padding: 8px 10px;
      resize: vertical;
    }

    .tag-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }

    .tag {
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

    .empty-state {
      padding: 48px 20px;
      color: var(--muted);
      text-align: center;
      border: 1px dashed var(--border);
      border-radius: 8px;
      background: var(--panel);
    }

    @media (max-width: 1140px) {
      .main {
        grid-template-columns: 250px minmax(320px, 1fr);
      }
      .detail {
        grid-column: 1 / -1;
        border-left: 0;
        border-top: 1px solid var(--border);
        max-height: 58vh;
      }
      .toolbar {
        grid-template-columns: minmax(220px, 1fr) auto auto auto;
      }
    }

    @media (max-width: 760px) {
      .topbar {
        align-items: flex-start;
        flex-direction: column;
      }
      .source { max-width: 100%; }
      .metrics { justify-content: flex-start; }
      .toolbar { grid-template-columns: 1fr; }
      .main { grid-template-columns: 1fr; }
      .sidebar,
      .detail {
        border-left: 0;
        border-right: 0;
        max-height: none;
      }
      .result-meta {
        align-items: flex-start;
        flex-direction: column;
      }
      .pager { justify-content: flex-start; }
      .decision-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body class="__ANYFILE_WIKI_REVIEW_MODE__">
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <h1>AnyFile Wiki 人工复核 <span class="title-en">Human review</span></h1>
        <div class="source" id="sourceLine"></div>
      </div>
      <div class="metrics" aria-label="批复统计 / Review statistics">
        <div class="metric"><strong id="totalCount">0</strong><span>待复核 / Items</span></div>
        <div class="metric"><strong id="decidedCount">0</strong><span>已批复 / Decided</span></div>
        <div class="metric"><strong id="highCount">0</strong><span>高优先级 / High</span></div>
      </div>
    </header>

    <section class="toolbar" aria-label="复核工具栏 / Review toolbar">
      <input class="search" id="searchInput" type="search" placeholder="搜索文件名、路径、原因或标签 / Search name, path, reason, tags" autocomplete="off">
      <select class="select" id="categorySelect" aria-label="类别 / Category"></select>
      <select class="select" id="severitySelect" aria-label="严重程度 / Severity"></select>
      <select class="select" id="decisionSelect" aria-label="批复状态 / Decision status">
        <option value="all">全部状态 / All</option>
        <option value="undecided">未批复 / Undecided</option>
        <option value="decided">已批复 / Decided</option>
      </select>
__ANYFILE_WIKI_REVIEW_CONTROLS__
    </section>

__ANYFILE_WIKI_MANUAL_EXPORT__

    <main class="main">
      <aside class="sidebar">
        <div class="pane-title">
          <h2>复核队列 <span class="title-en">Review queue</span></h2>
          <p>按类别和优先级查看 / Browse by category and priority</p>
        </div>
        <div id="facets"></div>
      </aside>

      <section class="results">
        <div class="result-meta">
          <div>
            <div id="resultLine">复核列表 / Review list：0</div>
            <div id="filterLine"></div>
          </div>
          <div class="pager">
            <button type="button" id="prevPage">上一页 / Prev</button>
            <span id="pageLine"></span>
            <button type="button" id="nextPage">下一页 / Next</button>
          </div>
        </div>
        <ul class="item-list" id="reviewList"></ul>
      </section>

      <aside class="detail">
        <div class="pane-title">
          <h2>批复详情 <span class="title-en">Decision details</span></h2>
          <p>摘要、原因和人工决策 / Reason and decision</p>
        </div>
        <div id="detailPanel"></div>
      </aside>
    </main>
  </div>

  <script>
    const REVIEW_DATA = __ANYFILE_WIKI_REVIEW_DATA__;
    const STORAGE_KEY = `anyfile-wiki-review:${REVIEW_DATA.source_path || "embedded"}:${(REVIEW_DATA.items || []).length}`;
    const DECISIONS = [
      ["confirm_current", "确认当前结果 / Confirm"],
      ["allow_local_llm", "允许本地 LLM / Local LLM"],
      ["allow_cloud_llm", "允许云端 LLM / Cloud LLM"],
      ["mark_manual", "已人工整理 / Manually done"],
      ["ignore", "忽略 / Ignore"],
      ["later", "稍后处理 / Later"],
      ["keep_private", "保持隐私 / Keep private"]
    ];
    const CATEGORY_LABELS = {
      policy_blocked: "隐私策略阻止读取 / Policy blocked",
      metadata_only: "只登记元数据 / Metadata only",
      cloud_forbidden_by_policy: "策略禁止云端处理 / Cloud forbidden",
      unsupported_format: "暂不支持格式 / Unsupported format",
      not_extracted: "尚未提取 / Not extracted",
      extraction_problem: "提取问题 / Extraction problem",
      rules_only_or_low_confidence: "规则版或低置信度 / Rules or low confidence",
      cloud_not_authorized: "云端未授权 / Cloud not authorized"
    };
    const SEVERITY_LABELS = {
      high: "高 / High",
      medium: "中 / Medium",
      low: "低 / Low"
    };

    const state = {
      query: "",
      category: "all",
      severity: "all",
      decisionStatus: "all",
      page: 1,
      pageSize: 6,
      selectedId: (REVIEW_DATA.items || [])[0]?.id || "",
      decisions: loadStoredDecisions(),
      lastExportSignature: "",
      lastServerSignature: "",
      serverSubmitting: false,
      serverMessage: "",
      manualExportVisible: false,
      manualExportMessage: ""
    };

    function escapeHtml(value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    function normalize(value) {
      return String(value || "").toLowerCase();
    }

    function loadStoredDecisions() {
      try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      } catch (_error) {
        return {};
      }
    }

    function saveStoredDecisions() {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state.decisions));
      } catch (_error) {
        // Some file:// browser contexts block localStorage writes. Keep the in-memory
        // decision state working so button feedback and JSONL export still respond.
      }
    }

    function decisionFor(item) {
      return state.decisions[item.id] || { decision: "", note: "", manual_tags: [] };
    }

    function setDecision(itemId, patch, shouldRender = true) {
      state.decisions[itemId] = { ...decisionFor({ id: itemId }), ...patch };
      state.lastExportSignature = "";
      state.serverMessage = "";
      saveStoredDecisions();
      renderExportButton();
      renderServerButtons();
      renderManualExport();
      if (shouldRender) render();
    }

    function categoryLabel(value) {
      return CATEGORY_LABELS[value] || value || "未分类 / Unknown";
    }

    function severityLabel(value) {
      return SEVERITY_LABELS[value] || value || "中 / Medium";
    }

    function decisionLabel(value) {
      return (DECISIONS.find(([id]) => id === value) || ["", "未批复 / Undecided"])[1];
    }

    function searchText(item) {
      return normalize([
        item.path,
        item.name,
        item.category,
        item.reason_code,
        item.reason,
        item.action,
        item.access_policy,
        item.analysis_method,
        ...(item.tags || [])
      ].join(" "));
    }

    function visibleItems() {
      const query = normalize(state.query).trim();
      return (REVIEW_DATA.items || []).filter((item) => {
        const decision = decisionFor(item).decision;
        if (query && !searchText(item).includes(query)) return false;
        if (state.category !== "all" && item.category !== state.category) return false;
        if (state.severity !== "all" && item.severity !== state.severity) return false;
        if (state.decisionStatus === "decided" && !decision) return false;
        if (state.decisionStatus === "undecided" && decision) return false;
        return true;
      }).sort((a, b) => {
        const priority = { high: 0, medium: 1, low: 2 };
        return (priority[a.severity] ?? 9) - (priority[b.severity] ?? 9)
          || categoryLabel(a.category).localeCompare(categoryLabel(b.category))
          || normalize(a.path).localeCompare(normalize(b.path));
      });
    }

    function countBy(items, keyFn) {
      const map = new Map();
      for (const item of items) {
        const key = keyFn(item);
        map.set(key, (map.get(key) || 0) + 1);
      }
      return [...map.entries()];
    }

    function populateSelects() {
      const items = REVIEW_DATA.items || [];
      const categories = countBy(items, (item) => item.category)
        .sort((a, b) => categoryLabel(a[0]).localeCompare(categoryLabel(b[0])));
      document.getElementById("categorySelect").innerHTML =
        `<option value="all">全部类别 / All categories</option>` +
        categories.map(([value, count]) => `<option value="${escapeHtml(value)}">${escapeHtml(categoryLabel(value))} (${count})</option>`).join("");
      const severities = countBy(items, (item) => item.severity)
        .sort((a, b) => (["high", "medium", "low"].indexOf(a[0]) + 10) - (["high", "medium", "low"].indexOf(b[0]) + 10));
      document.getElementById("severitySelect").innerHTML =
        `<option value="all">全部优先级 / All priorities</option>` +
        severities.map(([value, count]) => `<option value="${escapeHtml(value)}">${escapeHtml(severityLabel(value))} (${count})</option>`).join("");
    }

    function render() {
      const items = visibleItems();
      const pageCount = Math.max(1, Math.ceil(items.length / state.pageSize));
      state.page = Math.min(Math.max(state.page, 1), pageCount);
      const start = (state.page - 1) * state.pageSize;
      const pageItems = items.slice(start, start + state.pageSize);
      if (pageItems.length && !pageItems.some((item) => item.id === state.selectedId)) {
        state.selectedId = pageItems[0].id;
      }
      if (!items.length) {
        state.selectedId = "";
      }
      renderHeader(items, pageItems, pageCount);
      renderFacets();
      renderList(pageItems);
      renderDetail((REVIEW_DATA.items || []).find((item) => item.id === state.selectedId));
    }

    function renderHeader(items, pageItems, pageCount) {
      const allItems = REVIEW_DATA.items || [];
      const decided = allItems.filter((item) => decisionFor(item).decision).length;
      const high = allItems.filter((item) => item.severity === "high").length;
      const first = items.length ? (state.page - 1) * state.pageSize + 1 : 0;
      const last = items.length ? first + pageItems.length - 1 : 0;
      document.getElementById("totalCount").textContent = allItems.length;
      document.getElementById("decidedCount").textContent = decided;
      document.getElementById("highCount").textContent = high;
      const source = REVIEW_DATA.source_path ? `来源 / Source：${REVIEW_DATA.source_path}` : "来源 / Source：当前 HTML 内嵌复核清单";
      document.getElementById("sourceLine").textContent = `${source} · 生成时间 / Generated：${REVIEW_DATA.generated_at || ""}`;
      document.getElementById("resultLine").textContent = `复核列表 / Review list：${first}-${last} / ${items.length}`;
      document.getElementById("filterLine").textContent = `未批复 / Undecided：${Math.max(0, allItems.length - decided)}`;
      document.getElementById("pageLine").textContent = `第 ${state.page} / ${pageCount} 页 · Page ${state.page} of ${pageCount}`;
      document.getElementById("prevPage").disabled = state.page <= 1;
      document.getElementById("nextPage").disabled = state.page >= pageCount;
      renderExportButton();
      renderManualExport();
    }

    function renderFacets() {
      const allItems = REVIEW_DATA.items || [];
      const categoryButtons = countBy(allItems, (item) => item.category)
        .sort((a, b) => categoryLabel(a[0]).localeCompare(categoryLabel(b[0])))
        .map(([value, count]) => facetButton("category", value, categoryLabel(value), count))
        .join("");
      const severityButtons = countBy(allItems, (item) => item.severity)
        .sort((a, b) => (["high", "medium", "low"].indexOf(a[0]) + 10) - (["high", "medium", "low"].indexOf(b[0]) + 10))
        .map(([value, count]) => facetButton("severity", value, severityLabel(value), count))
        .join("");
      document.getElementById("facets").innerHTML = `
        <section class="facet-section">
          <h3 class="facet-heading">类别 / Category</h3>
          ${categoryButtons}
        </section>
        <section class="facet-section">
          <h3 class="facet-heading">优先级 / Priority</h3>
          ${severityButtons}
        </section>
      `;
      document.querySelectorAll("[data-facet-kind]").forEach((button) => {
        button.addEventListener("click", () => {
          const kind = button.dataset.facetKind;
          const value = button.dataset.facetValue;
          if (kind === "category") {
            state.category = state.category === value ? "all" : value;
            document.getElementById("categorySelect").value = state.category;
          }
          if (kind === "severity") {
            state.severity = state.severity === value ? "all" : value;
            document.getElementById("severitySelect").value = state.severity;
          }
          state.page = 1;
          render();
        });
      });
    }

    function facetButton(kind, value, label, count) {
      const active = state[kind] === value ? " is-active" : "";
      return `<button class="facet-button${active}" type="button" data-facet-kind="${escapeHtml(kind)}" data-facet-value="${escapeHtml(value)}">
        <span class="facet-label">${escapeHtml(label)}</span>
        <span class="count">${count}</span>
      </button>`;
    }

    function renderList(items) {
      const list = document.getElementById("reviewList");
      if (!items.length) {
        list.innerHTML = `<li class="empty-state">没有匹配的复核项 / No matching review items</li>`;
        return;
      }
      list.innerHTML = items.map((item) => {
        const decision = decisionFor(item).decision;
        const selected = item.id === state.selectedId ? " is-selected" : "";
        const decisionBadge = decision ? `<span class="badge decided">${escapeHtml(decisionLabel(decision))}</span>` : "";
        return `<li>
          <button class="item-row${selected}" type="button" data-item-id="${escapeHtml(item.id)}">
            <div class="row-head">
              <h3 class="row-title">${escapeHtml(item.name || item.path)}</h3>
              <span class="badge ${escapeHtml(item.severity)}">${escapeHtml(severityLabel(item.severity))}</span>
            </div>
            <div class="row-path">${escapeHtml(item.path)}</div>
            <div class="row-reason">${escapeHtml(categoryLabel(item.category))} <code>${escapeHtml(item.reason_code || "")}</code> ${decisionBadge}</div>
          </button>
        </li>`;
      }).join("");
      list.querySelectorAll("button[data-item-id]").forEach((button) => {
        button.addEventListener("click", () => {
          state.selectedId = button.dataset.itemId;
          render();
        });
      });
    }

    function renderDetail(item) {
      const panel = document.getElementById("detailPanel");
      if (!item) {
        panel.innerHTML = `<div class="detail-empty">请选择一个复核项 / Select a review item</div>`;
        return;
      }
      const decision = decisionFor(item);
      const tags = (item.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
      const buttons = DECISIONS.map(([id, label]) => {
        const active = decision.decision === id ? " is-active" : "";
        return `<button class="decision-button${active}" type="button" data-decision="${escapeHtml(id)}">${escapeHtml(label)}</button>`;
      }).join("");
      panel.innerHTML = `<div class="detail-body">
        <h2 class="detail-title">${escapeHtml(item.name || item.path)}</h2>
        <div class="detail-path">${escapeHtml(item.path)}</div>

        <section class="detail-section decision-section">
          <h3>批复动作 / Decision</h3>
          <div class="decision-grid">${buttons}</div>
          <div class="field">
            <label for="manualTags">人工标签 / Manual tags</label>
            <input class="input" id="manualTags" type="text" value="${escapeHtml((decision.manual_tags || []).join(', '))}" placeholder="tag/a, tag/b">
          </div>
          <div class="field">
            <label for="decisionNote">备注 / Note</label>
            <textarea class="textarea" id="decisionNote" placeholder="给后续 agent 的简短说明 / Brief note for the agent">${escapeHtml(decision.note || "")}</textarea>
          </div>
        </section>

        <section class="detail-section">
          <h3>原因 / Reason</h3>
          <p class="summary">${escapeHtml(item.reason || "暂无 / None")}</p>
        </section>

        <section class="detail-section">
          <h3>建议动作 / Suggested action</h3>
          <p class="summary">${escapeHtml(item.action || "暂无 / None")}</p>
        </section>

        <section class="detail-section">
          <h3>基础信息 / Basic info</h3>
          <dl class="kv">
            <dt>类别 / Category</dt><dd>${escapeHtml(categoryLabel(item.category))} <code>${escapeHtml(item.category)}</code></dd>
            <dt>原因代码 / Reason code</dt><dd><code>${escapeHtml(item.reason_code || "unknown")}</code></dd>
            <dt>优先级 / Priority</dt><dd>${escapeHtml(severityLabel(item.severity))} <code>${escapeHtml(item.severity)}</code></dd>
            <dt>隐私策略 / Policy</dt><dd><code>${escapeHtml(item.access_policy || "unknown")}</code></dd>
            <dt>提取状态 / Extract</dt><dd><code>${escapeHtml(item.extraction_status || "unknown")}</code></dd>
            <dt>分析方式 / Method</dt><dd><code>${escapeHtml(item.analysis_method || "unknown")}</code></dd>
            <dt>置信度 / Confidence</dt><dd>${item.confidence === null || item.confidence === undefined ? "暂无 / None" : Number(item.confidence).toFixed(2)}</dd>
          </dl>
        </section>

        <section class="detail-section">
          <h3>当前标签 / Current tags</h3>
          <div class="tag-strip">${tags || "<span class=\"badge\">暂无标签 / No tags</span>"}</div>
        </section>
      </div>`;

      panel.querySelectorAll("button[data-decision]").forEach((button) => {
        button.addEventListener("click", () => {
          setDecision(item.id, { decision: button.dataset.decision });
        });
      });
      const tagsInput = document.getElementById("manualTags");
      tagsInput.addEventListener("input", () => {
        const manualTags = tagsInput.value.split(/[,\n，]+/).map((part) => part.trim()).filter(Boolean);
        setDecision(item.id, { manual_tags: manualTags }, false);
      });
      const noteInput = document.getElementById("decisionNote");
      noteInput.addEventListener("input", () => {
        setDecision(item.id, { note: noteInput.value }, false);
      });
    }

    function decisionRecords() {
      return (REVIEW_DATA.items || [])
        .map((item) => {
          const decision = decisionFor(item);
          if (!decision.decision) return null;
          return {
            schema_version: 1,
            decided_at: new Date().toISOString(),
            path: item.path,
            category: item.category,
            reason_code: item.reason_code,
            severity: item.severity,
            decision: decision.decision,
            manual_tags: decision.manual_tags || [],
            note: decision.note || "",
            source_reason: item.reason,
            source_action: item.action
          };
        })
        .filter(Boolean);
    }

    function decisionsJsonl() {
      const records = decisionRecords();
      return records.map((record) => JSON.stringify(record)).join("\n") + (records.length ? "\n" : "");
    }

    function decisionSignature() {
      return JSON.stringify(decisionRecords().map((record) => ({
        path: record.path,
        category: record.category,
        decision: record.decision,
        manual_tags: record.manual_tags,
        note: record.note
      })));
    }

    function renderExportButton() {
      const button = document.getElementById("exportJsonl");
      if (!button) return;
      const signature = decisionSignature();
      const isDone = Boolean(signature && state.lastExportSignature === signature);
      button.classList.toggle("is-done", isDone);
      button.textContent = isDone ? "✓ 导出完成 / Exported" : "导出批复 / Export";
      button.setAttribute("aria-label", isDone ? "导出完成 / Exported" : "导出批复 / Export");
    }

    function renderServerButtons(message = "") {
      if (!REVIEW_DATA.server_mode) return;
      const draftButton = document.getElementById("saveDraft");
      const submitButton = document.getElementById("submitReview");
      const status = document.getElementById("serverStatus");
      const signature = decisionSignature();
      const alreadySubmitted = Boolean(signature && state.lastServerSignature === signature);
      const activeMessage = message || state.serverMessage || "";
      if (draftButton) {
        draftButton.disabled = state.serverSubmitting;
        draftButton.textContent = state.serverSubmitting ? "保存中 / Saving..." : "保存草稿 / Save";
      }
      if (submitButton) {
        submitButton.disabled = state.serverSubmitting || alreadySubmitted;
        submitButton.classList.toggle("is-done", alreadySubmitted);
        if (state.serverSubmitting) {
          submitButton.textContent = "提交中 / Submitting...";
        } else if (alreadySubmitted) {
          submitButton.textContent = "✓ 已提交 / Submitted";
        } else {
          submitButton.textContent = "提交批复 / Submit";
        }
      }
      if (status) status.textContent = activeMessage;
    }

    function renderManualExport() {
      const panel = document.getElementById("manualExport");
      const textarea = document.getElementById("manualJsonl");
      const help = document.getElementById("manualExportHelp");
      if (!panel || !textarea || !help) return;
      panel.hidden = !state.manualExportVisible;
      if (!state.manualExportVisible) return;
      textarea.value = decisionsJsonl();
      help.textContent = state.manualExportMessage || "如果浏览器拦截下载或剪贴板，请在这里全选复制，然后保存为 review-decisions.jsonl。 / If download or clipboard is blocked, select all here and save as review-decisions.jsonl.";
    }

    function showManualJsonl(message) {
      const jsonl = decisionsJsonl();
      if (!jsonl) {
        window.alert("还没有批复项 / No decisions yet");
        return;
      }
      state.manualExportVisible = true;
      state.manualExportMessage = message || "";
      renderManualExport();
      const textarea = document.getElementById("manualJsonl");
      if (textarea) {
        textarea.focus();
        textarea.select();
      }
    }

    function exportJsonl() {
      const jsonl = decisionsJsonl();
      if (!jsonl) {
        window.alert("还没有批复项 / No decisions yet");
        return;
      }
      const blob = new Blob([jsonl], { type: "application/x-ndjson;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "review-decisions.jsonl";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      state.lastExportSignature = decisionSignature();
      renderExportButton();
      showManualJsonl("已尝试触发下载。如果没有看到文件，请从下方文本框复制内容并保存为 review-decisions.jsonl。 / Download was requested. If no file appears, copy the text below and save it as review-decisions.jsonl.");
    }

    async function copyJsonl() {
      const jsonl = decisionsJsonl();
      if (!jsonl) {
        window.alert("还没有批复项 / No decisions yet");
        return;
      }
      try {
        await navigator.clipboard.writeText(jsonl);
        document.getElementById("copyJsonl").textContent = "已复制 / Copied";
      } catch (_error) {
        document.getElementById("copyJsonl").textContent = "复制失败 / Failed";
        showManualJsonl("剪贴板被浏览器拦截。请从下方文本框手动复制内容。 / Clipboard was blocked. Copy the text below manually.");
      }
      window.setTimeout(() => {
        document.getElementById("copyJsonl").textContent = "复制 JSONL / Copy";
      }, 1000);
    }

    async function submitToServer(finalize) {
      const records = decisionRecords();
      if (!records.length) {
        window.alert("还没有批复项 / No decisions yet");
        return;
      }
      const target = REVIEW_DATA.submit_url || "/api/decisions";
      const signature = decisionSignature();
      if (finalize && signature && state.lastServerSignature === signature) {
        state.serverMessage = "已提交，无需重复提交 / Already submitted";
        renderServerButtons();
        return;
      }
      const activeButton = document.getElementById(finalize ? "submitReview" : "saveDraft");
      state.serverSubmitting = true;
      state.serverMessage = finalize ? "正在提交 / Submitting..." : "正在保存 / Saving...";
      renderServerButtons();
      try {
        const response = await fetch(target, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ final: Boolean(finalize), records })
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || `HTTP ${response.status}`);
        }
        state.lastExportSignature = signature;
        state.lastServerSignature = signature;
        state.serverMessage = payload.duplicate
          ? "已提交，无需重复提交 / Already submitted"
          : (finalize ? "批复已提交，本地流程可以继续 / Submitted, workflow can continue" : "草稿已保存 / Draft saved");
        renderExportButton();
      } catch (error) {
        state.serverMessage = `提交失败 / Submit failed: ${error.message || error}`;
        if (activeButton) activeButton.textContent = finalize ? "提交失败 / Failed" : "保存失败 / Failed";
        window.alert(`提交失败 / Submit failed: ${error.message || error}`);
      } finally {
        state.serverSubmitting = false;
        renderServerButtons();
      }
    }

    document.getElementById("searchInput").addEventListener("input", (event) => {
      state.query = event.target.value;
      state.page = 1;
      render();
    });
    document.getElementById("categorySelect").addEventListener("change", (event) => {
      state.category = event.target.value;
      state.page = 1;
      render();
    });
    document.getElementById("severitySelect").addEventListener("change", (event) => {
      state.severity = event.target.value;
      state.page = 1;
      render();
    });
    document.getElementById("decisionSelect").addEventListener("change", (event) => {
      state.decisionStatus = event.target.value;
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
    document.getElementById("exportJsonl")?.addEventListener("click", exportJsonl);
    document.getElementById("copyJsonl")?.addEventListener("click", copyJsonl);
    document.getElementById("showJsonl")?.addEventListener("click", () => {
      showManualJsonl("请从下方文本框复制内容，并保存为 review-decisions.jsonl。 / Copy the text below and save it as review-decisions.jsonl.");
    });
    document.getElementById("selectJsonl")?.addEventListener("click", () => {
      const textarea = document.getElementById("manualJsonl");
      if (!textarea) return;
      textarea.focus();
      textarea.select();
    });
    document.getElementById("saveDraft")?.addEventListener("click", () => submitToServer(false));
    document.getElementById("submitReview")?.addEventListener("click", () => submitToServer(true));

    populateSelects();
    render();
  </script>
</body>
</html>
"""
