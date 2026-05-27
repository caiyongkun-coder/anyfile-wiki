# MVP3 HTML 资产浏览页说明

MVP3 的第一步是让人类能直接浏览知识库，而不是只能读很长的 Markdown。

当前已经实现 `pfkb html`：它读取 `knowledge-index.jsonl` 或 `analysis-manifest.jsonl` 中 `status: ok` 的分析结果，生成一个可离线打开的 `knowledge-index.html`。页面文案以中文为主，后端字段和标签 key 继续保留英文，方便 agent、脚本和后续工具稳定读取。

## 使用命令

先完成扫描、提取和分析：

```powershell
python -m pfkb scan "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/first-scan --max-entries 500
python -m pfkb extract --inventory data/first-scan/inventory.sqlite --out data/first-extract
python -m pfkb analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze
```

再生成 HTML 资产浏览页：

```powershell
python -m pfkb html --analysis data/first-analyze/knowledge-index.jsonl --out data/first-html
```

输出文件：

```text
data/first-html/knowledge-index.html
```

这个 HTML 是单文件静态页面，可以直接在浏览器打开，不需要启动本地服务。

## 当前功能

- 中文资产浏览界面。
- 顶部搜索：可搜文件名、路径、摘要、标签和复核原因。
- 左侧标签树：按内容类型、分析方式、复核状态和标签维度筛选。
- 中间文件列表：显示标题、路径、摘要、标签和复核状态。
- 右侧文件详情：显示摘要、标签、分析方式、置信度、向量许可、解析器、字数、理解要点、规则版保留结果和模型说明。
- 支持 `knowledge-index.jsonl` 和 `analysis-manifest.jsonl`；如果传入 manifest，会自动过滤掉 `skipped` 和 `error`。

## 设计取舍

- 只读浏览，不修改源文件。
- 不写回隐私配置，也不写回人工复核决定。
- 数据直接内嵌到 HTML，方便复制、分享和离线打开。
- UI 使用中文，结构化 JSON 字段继续使用英文，避免破坏 agent 读取约定。
- 目前的标签层级主要来自 `configs/tags.example.yaml`，后续可以扩展到项目、时间、来源应用和用户自定义集合。

## 后续计划

- 增加 `human-review.html`，用于处理待整理文件。
- 增加本地决策记录，例如 `review-decisions.jsonl`，记录“稍后复核、忽略、允许本地 LLM、允许云端 LLM、归档候选”等选择。
- 增加主题页、项目页、来源应用页和时间线。
- 增加可选的本地搜索索引，让大规模知识库仍然能快速筛选。
- 继续保留 Markdown 和 JSONL 输出，HTML 只是更适合人类浏览的一层。
