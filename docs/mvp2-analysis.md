# MVP2 内容分析说明

MVP2 的目标是把已经提取出的正文转成第一版知识索引。

当前实现是全本地、规则版，不依赖大模型。它先提供稳定的基础能力：

- 从 `inventory.sqlite` 读取最新可分析的提取结果。
- 只分析 `ok` 或 `up_to_date` 且有文本产物的记录。
- 生成标题、基础摘要、标签、内容类型、字数、行数。
- 标记分析方式、规则置信度、是否需要人工复核、复核原因。
- 输出机器可读 JSONL 和人类可读 Markdown 索引。

## 使用顺序

先完成扫描和提取：

```powershell
python -m pfkb scan "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/first-scan --max-entries 500
python -m pfkb extract --inventory data/first-scan/inventory.sqlite --out data/first-extract
```

然后执行分析：

```powershell
python -m pfkb analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze
```

如果要模拟“API/LLM 已经接入”的语义理解结果，可以保留规则版输出，再跑一份 `codex-mock`：

```powershell
python -m pfkb analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-codex --method codex-mock --compare-to data/first-analyze/analysis-manifest.jsonl
```

`codex-mock` 不调用外部服务，也不代表真实模型能力。它的作用是先固定未来 API 接入后的数据结构和阅读形态：语义摘要、语义标签、理解要点、模型说明，以及保留下来的规则粗标签。

## 输出文件

`pfkb analyze` 会输出：

- `analysis-manifest.jsonl`：每个分析任务的完整结果，包括错误记录。
- `knowledge-index.jsonl`：成功分析的知识索引，适合 agent 和后续程序读取。
- `knowledge-index.md`：人类可读的知识索引，按内容类型分组。
- `tag-index.md`：人类可读的标签索引。
- `analysis-comparison.md`：当传入 `--compare-to` 时生成，用来对比规则粗标签和语义理解结果。

## 当前标签能力

当前标签来自路径、扩展名和正文关键词，属于保守的规则版：

- 内容类型：`code`、`docs`、`config`、`test`、`document`、`file`。
- 主题标签：`privacy`、`scan`、`extract`、`analysis`、`inventory`、`configuration`、`roots`、`cli`、`tests`、`docs`、`license`、`roadmap`。

后续可以在这一层之后接本地 LLM，提升摘要质量、抽取主题层级、识别项目/人物/时间线，并生成 wiki 页面。

## 模拟语义理解能力

`--method codex-mock` 会生成一份语义理解版索引：

- `analysis_method` 会变成 `codex-mock`。
- `tags` 会变成语义标签，例如 `privacy_policy`、`llm_policy`、`human_review`。
- `rule_tags` 会保留原来的规则粗标签。
- `rule_summary` 会保留原来的规则摘要。
- `key_points` 会记录模拟理解时抓到的代码符号、文档章节或配置字段。
- `model_notes` 会说明这是模拟 API 结果，没有调用外部服务。

这个模式用于开发和展示，不用于替代真实模型。后续接入本地 LLM 或云端 API 时，可以沿用这些字段。

## 复核字段

规则版分析不会假装自己已经真正理解文件。每条结果会包含：

- `analysis_method`：当前是 `rules`。
- `confidence`：规则置信度，最高也不会当作大模型理解。
- `needs_human_review`：是否建议人工或本地 LLM 复核。
- `review_reason`：复核原因，例如 `rules_only_needs_semantic_review`。

可以继续运行：

```powershell
python -m pfkb review --inventory data/first-scan/inventory.sqlite --analysis data/first-analyze/analysis-manifest.jsonl --out data/first-review
```

生成 `human-review.md`，把规则版低置信度、无法读取、无法提取、云端未授权的文件列出来。
