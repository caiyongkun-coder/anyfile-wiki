from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import ast
import re


@dataclass(frozen=True)
class SemanticUnderstanding:
    title: str
    summary: str
    tags: list[str]
    confidence: float
    needs_human_review: bool
    review_reason: str
    key_points: list[str]
    model_notes: str


TOPICS = [
    (
        "privacy_policy",
        "隐私策略",
        ("privacy", "隐私", "deny", "metadata_only", "no_embedding", "access_policy"),
        "定义哪些文件可以读取、只能记录元数据、禁止向量化或完全跳过。",
    ),
    (
        "llm_policy",
        "LLM 策略",
        ("llm", "cloud", "local", "risk_acknowledged", "allowed_paths", "model"),
        "控制内容理解阶段是否使用规则、本地模型或云端模型，并约束云端授权范围。",
    ),
    (
        "human_review",
        "人工复核",
        ("review", "human-review", "needs_human_review", "待整理", "人工"),
        "把系统无法可靠理解、提取或发送云端的文件交给用户确认。",
    ),
    (
        "semantic_analysis",
        "内容理解",
        ("analyze", "analysis", "knowledge-index", "tag-index", "summary", "confidence", "摘要", "标签"),
        "把已提取正文整理成摘要、主题标签、置信度和知识索引。",
    ),
    (
        "content_extraction",
        "正文提取",
        ("extract", "extraction", "parse", "parser", "markitdown", "direct_text", "提取"),
        "在隐私策略允许的前提下把文件内容转成可分析文本。",
    ),
    (
        "scan_reporting",
        "扫描报告",
        ("report", "write_scan_plan", "write_access_log", "summarize_by_policy", "访问日志"),
        "把扫描结果、策略命中和访问决策整理成人类可读报告与机器日志。",
    ),
    (
        "inventory_db",
        "文件清单数据库",
        ("inventory", "sqlite", "list_files", "upsert", "extractions"),
        "持久化扫描结果、提取状态和后续查询所需的文件元数据。",
    ),
    (
        "scan_planning",
        "扫描计划",
        ("scan", "dry-run", "access-log", "scan-plan", "follow_symlinks"),
        "先生成不读取正文的扫描计划和访问日志，避免一上来触碰敏感内容。",
    ),
    (
        "scan_roots",
        "扫描目录",
        ("roots", "documents", "downloads", "desktop", "onedrive", "推荐扫描目录"),
        "描述个人文件优先扫描的目录来源、风险等级和启用状态。",
    ),
    (
        "cli_workflow",
        "命令行流程",
        ("argparse", "subparsers", "cmd_", "python -m pfkb", "command"),
        "把扫描、提取、分析、复核等步骤串成可执行命令。",
    ),
    (
        "test_coverage",
        "测试覆盖",
        ("pytest", "assert", "fixture", "tmp_path", "test_"),
        "验证扫描、提取、分析、配置和复核流程不会回退。",
    ),
    (
        "project_documentation",
        "项目文档",
        ("readme", "docs", "guide", "mvp", "使用说明", "项目启动"),
        "向用户和协作者说明项目目标、使用方法、阶段边界和后续路线。",
    ),
    (
        "open_source",
        "开源治理",
        ("license", "apache", "github", "contributing", "开源"),
        "处理许可证、公开协作和项目发布相关信息。",
    ),
    (
        "roadmap",
        "路线图",
        ("roadmap", "development_plan", "project_start", "milestone", "计划"),
        "记录阶段目标、难点拆分、后续能力和实现优先级。",
    ),
    (
        "html_review_ui",
        "HTML 交互审阅",
        ("html", "knowledge-index.html", "human-review.html", "review-decisions", "交互"),
        "为大量文件准备可点击、可筛选、可记录决策的本地审阅界面。",
    ),
    (
        "configuration",
        "配置模板",
        ("config", "configuration", "yaml", "example", "enabled", "rules"),
        "提供可被人和 agent 共同理解、后续可个性化调整的配置结构。",
    ),
]


def infer_semantic_understanding(
    path: str,
    text: str,
    *,
    content_type: str,
    rule_title: str,
    rule_summary: str,
    rule_tags: list[str],
) -> SemanticUnderstanding:
    """Simulate the shape of an LLM/API semantic pass without network calls."""

    topics = _infer_topics(path, text, content_type, rule_tags)
    code_symbols = _code_symbols(path, text)
    headings = _headings(text)
    config_keys = _config_keys(path, text)
    tags = _dedupe([_content_semantic_tag(content_type), *[topic[0] for topic in topics]])
    title = _semantic_title(path, rule_title, topics)
    key_points = _key_points(topics, code_symbols, headings, config_keys)
    summary = _semantic_summary(path, content_type, topics, key_points, rule_summary)
    confidence = _semantic_confidence(topics, code_symbols, headings, config_keys, rule_summary)
    return SemanticUnderstanding(
        title=title,
        summary=summary,
        tags=tags[:12],
        confidence=confidence,
        needs_human_review=confidence < 0.7,
        review_reason=(
            "codex_mock_low_signal" if confidence < 0.7 else "codex_mock_semantic_reviewed"
        ),
        key_points=key_points[:5],
        model_notes=(
            "codex-mock 是本地模拟的 API 结果，用来验证 LLM 语义理解输出形态；"
            "当前没有调用外部服务，粗标签保留在 rule_tags/rule_summary 中。"
        ),
    )


def _infer_topics(
    path: str,
    text: str,
    content_type: str,
    rule_tags: list[str],
) -> list[tuple[str, str, tuple[str, ...], str]]:
    lower_path = path.replace("\\", "/").lower()
    # 粗标签只保留用于对比，不直接进入语义判断，避免模拟模型被规则结果带偏。
    _ = rule_tags
    haystack = f"{lower_path}\n{text[:50000]}".lower()
    scored: list[tuple[int, int, tuple[str, str, tuple[str, ...], str]]] = []
    for index, topic in enumerate(TOPICS):
        topic_key, _label, keywords, _purpose = topic
        score = 0
        for keyword in keywords:
            normalized = keyword.lower()
            if normalized in lower_path:
                score += 3
            if normalized in haystack:
                score += 1
        if topic_key == "test_coverage" and content_type == "test":
            score += 3
        if topic_key == "configuration" and content_type == "config":
            score += 2
        if topic_key == "project_documentation" and content_type == "docs":
            score += 2
        if topic_key == "semantic_analysis" and "analyze" in lower_path:
            score += 3
        if topic_key == "human_review" and "review" in lower_path:
            score += 3
        if topic_key == "content_extraction" and "parse" in lower_path:
            score += 3
        if topic_key == "scan_reporting" and "report" in lower_path:
            score += 3
        if topic_key == "inventory_db" and "inventory" in lower_path:
            score += 3
        if topic_key == "cli_workflow" and "cli.py" in lower_path:
            score += 3
        if score:
            scored.append((score, -index, topic))
    return [topic for _score, _index, topic in sorted(scored, reverse=True)[:5]]


def _semantic_title(
    path: str,
    rule_title: str,
    topics: list[tuple[str, str, tuple[str, ...], str]],
) -> str:
    name = Path(path).name
    if topics:
        return f"{name}：{topics[0][1]}"
    return rule_title or name


def _semantic_summary(
    path: str,
    content_type: str,
    topics: list[tuple[str, str, tuple[str, ...], str]],
    key_points: list[str],
    rule_summary: str,
) -> str:
    role = _content_role(content_type)
    name = Path(path).name
    if topics:
        labels = "、".join(topic[1] for topic in topics[:4])
        purpose = topics[0][3]
        summary = f"`{name}` 是一个{role}，主要用于{purpose}它关联的主题包括：{labels}。"
    else:
        summary = f"`{name}` 是一个{role}，当前模拟语义层没有提取到足够明确的主题。"
    if key_points:
        summary += " 关键线索：" + "；".join(key_points[:3]) + "。"
    elif rule_summary:
        summary += f" 规则版预览显示：{_truncate(rule_summary, 120)}"
    return _truncate(summary, 520)


def _key_points(
    topics: list[tuple[str, str, tuple[str, ...], str]],
    code_symbols: list[str],
    headings: list[str],
    config_keys: list[str],
) -> list[str]:
    points: list[str] = []
    if code_symbols:
        points.append("关键代码符号：" + "、".join(code_symbols[:8]))
    if headings:
        points.append("主要章节：" + "、".join(headings[:5]))
    if config_keys:
        points.append("配置字段：" + "、".join(config_keys[:8]))
    if topics:
        points.append("主题判断：" + "、".join(topic[1] for topic in topics[:5]))
    return points


def _semantic_confidence(
    topics: list[tuple[str, str, tuple[str, ...], str]],
    code_symbols: list[str],
    headings: list[str],
    config_keys: list[str],
    rule_summary: str,
) -> float:
    score = 0.45
    score += min(len(topics), 4) * 0.08
    if code_symbols:
        score += 0.08
    if headings:
        score += 0.07
    if config_keys:
        score += 0.06
    if len(rule_summary) >= 80:
        score += 0.04
    return min(round(score, 2), 0.92)


def _code_symbols(path: str, text: str) -> list[str]:
    if Path(path).suffix.lower() != ".py":
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(node.name)
    return symbols[:12]


def _headings(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,4}\s+(.+?)\s*$", line)
        if match:
            headings.append(_clean(match.group(1)))
    return headings[:12]


def _config_keys(path: str, text: str) -> list[str]:
    if Path(path).suffix.lower() not in {".yaml", ".yml", ".toml", ".json", ".ini", ".cfg"}:
        return []
    keys: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,2}([A-Za-z0-9_-]+)\s*[:=]", line)
        if match:
            keys.append(match.group(1))
    return _dedupe(keys)[:12]


def _content_semantic_tag(content_type: str) -> str:
    tags = {
        "code": "source_code",
        "config": "configuration_file",
        "docs": "project_documentation",
        "document": "document",
        "test": "test_file",
        "file": "file",
    }
    return tags.get(content_type, content_type)


def _content_role(content_type: str) -> str:
    roles = {
        "code": "源码文件",
        "config": "配置文件",
        "docs": "项目文档",
        "document": "文档",
        "test": "测试文件",
        "file": "文件",
    }
    return roles.get(content_type, "文件")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" #`")


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1].rstrip() + "…"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
