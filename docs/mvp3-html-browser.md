# MVP3 HTML 资产浏览页说明

MVP3 的第一步是让人类能直接浏览知识库，而不是只能读很长的 Markdown。

当前已经实现 `anyfile-wiki html`：它读取 `knowledge-index.jsonl`、`analysis-manifest.jsonl` 或批复后的 `asset-index.jsonl` 中 `status: ok` 的结果，生成一个可离线打开的 `knowledge-index.html`。页面固定文案尽量采用中英双语，后端字段和标签 key 继续保留英文，方便 agent、脚本和后续工具稳定读取。

## 使用命令

先完成扫描、提取和分析：

```powershell
anyfile-wiki scan "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/first-scan --max-entries 500
anyfile-wiki extract --inventory data/first-scan/inventory.sqlite --out data/first-extract
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze
```

再生成 HTML 资产浏览页：

```powershell
anyfile-wiki html --analysis data/first-analyze/knowledge-index.jsonl --out data/first-html
```

如果已经完成人工批复，推荐先生成最终资产索引，再刷新 HTML：

```powershell
anyfile-wiki assets --analysis data/first-analyze/knowledge-index.jsonl --actions data/first-review/next-actions.jsonl --review-items data/first-review/human-review.jsonl --out data/first-assets --html-out data/first-html
```

输出文件：

```text
data/first-html/knowledge-index.html
```

这个 HTML 是单文件静态页面，可以直接在浏览器打开，不需要启动本地服务。

## 当前功能

- 中英双语资产浏览界面。
- 顶部搜索：可搜文件名、路径、摘要、标签和复核原因。
- 左侧标签树：按内容类型、分析方式、复核状态和标签维度筛选。
- 中间文件列表：默认分页显示，可选择每页 10、15 或 30 条；每条显示标题、路径、摘要、标签和复核状态。
- 右侧文件详情：显示摘要、标签、分析方式、置信度、向量许可、解析器、字数、理解要点、规则版保留结果和模型说明。
- 支持 `knowledge-index.jsonl`、`analysis-manifest.jsonl` 和 `asset-index.jsonl`；如果传入 manifest，会自动过滤掉 `skipped` 和 `error`。
- 批复后的资产页会显示资产状态、人工批复、后续动作、二次确认、人工标签和隐私冲突提示。

## 设计取舍

- 只读浏览，不修改源文件。
- 不写回隐私配置，也不写回人工复核决定。
- 数据直接内嵌到 HTML，方便复制、分享和离线打开。
- UI 固定文案尽量使用中英双语，结构化 JSON 字段继续使用英文，避免破坏 agent 读取约定。
- 目前的标签层级主要来自 `configs/tags.example.yaml`，后续可以扩展到项目、时间、来源应用和用户自定义集合。

## 后续计划

- 扩展 `human-review.html` 的批量批复、标签编辑和决策复查能力。
- 让 agent 读取 `asset-index.jsonl` 中的 `local_llm_queue` 后自动触发本地 LLM 复核，并把复核结果继续回写资产索引。
- 增加主题页、项目页、来源应用页和时间线。
- 增加可选的本地搜索索引，让大规模知识库仍然能快速筛选。
- 继续保留 Markdown 和 JSONL 输出，HTML 只是更适合人类浏览的一层。
