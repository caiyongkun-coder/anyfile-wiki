# MVP2 内容分析说明

MVP2 的目标是把已经提取出的正文转成第一版知识索引。

当前实现是全本地、规则版，不依赖大模型。它先提供稳定的基础能力：

- 从 `inventory.sqlite` 读取最新可分析的提取结果。
- 只分析 `ok` 或 `up_to_date` 且有文本产物的记录。
- 生成标题、基础摘要、标签、内容类型、字数、行数。
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
