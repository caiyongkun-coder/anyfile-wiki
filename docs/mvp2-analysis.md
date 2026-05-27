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

## 输出文件

`pfkb analyze` 会输出：

- `analysis-manifest.jsonl`：每个分析任务的完整结果，包括错误记录。
- `knowledge-index.jsonl`：成功分析的知识索引，适合 agent 和后续程序读取。
- `knowledge-index.md`：人类可读的知识索引，按内容类型分组。
- `tag-index.md`：人类可读的标签索引。

## 当前标签能力

当前标签来自路径、扩展名和正文关键词，属于保守的规则版：

- 内容类型：`code`、`docs`、`config`、`test`、`document`、`file`。
- 主题标签：`privacy`、`scan`、`extract`、`analysis`、`inventory`、`configuration`、`roots`、`cli`、`tests`、`docs`、`license`、`roadmap`。

后续可以在这一层之后接本地 LLM，提升摘要质量、抽取主题层级、识别项目/人物/时间线，并生成 wiki 页面。

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
