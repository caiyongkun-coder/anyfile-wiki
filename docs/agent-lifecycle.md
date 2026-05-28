# Agent 生命周期与日常运行流程

本项目的主要使用者不是单独的人类用户，也不是单独的网页应用，而是 OpenClaw、Hermes、Codex 等本地 agent。

因此整体流程应该设计成：人类负责授权、确认和批复；agent 负责部署、扫描、整理、生成知识资产，并在得到人类批复后继续执行后续流程。

## 总体目标

AnyFile Wiki 要形成一个本地优先的数据资产管理闭环：

```text
初始化配置 -> 日常扫描 -> 内容提取与理解 -> 人类浏览和批复 -> agent 读取知识资产 -> 后续整理、检索、归档建议
```

其中 HTML 页面不是独立产品，而是人类和 agent 之间的协作界面：

- `knowledge-index.html`：让人类浏览已经整理出的数据资产。
- `human-review.html`：让人类批复系统不确定或不能自动处理的文件。
- `review-decisions.jsonl`：让 agent 读取人类批复结果，并继续后续流程。
- `asset-index.jsonl`：让 agent 读取已经合并人工批复后的最终资产状态。

## 初始化阶段

初始化阶段由 agent 主导，但必须让人类确认关键配置。

### 1. Agent 安装和部署

Agent 读取项目文档、依赖和命令说明，完成本地部署。

典型动作：

- 检查 Python 版本。
- 安装项目依赖。
- 检查可选解析依赖，例如 MarkItDown 或后续 Docling。
- 确认当前系统平台和路径格式。
- 准备本地输出目录，例如 `data/`。

当前命令示例：

```powershell
python -m pip install -e .[dev]
python -m pytest -q
```

### 2. Agent 协助配置

Agent 读取默认配置，并把配置翻译成人类能理解的问题。

关键配置包括：

- `configs/privacy.yaml`：哪些路径可以读取、哪些只能登记元数据、哪些永远禁止读取。
- `configs/excludes.default.yaml`：系统目录、缓存、安装包、开发噪声等默认排除规则。
- `configs/roots.example.yaml`：推荐扫描目录。
- `configs/tags.example.yaml`：标签体系。
- `configs/llm.yaml`：本地或云端 LLM 策略。

配置不是一次性的。用户以后可以随时让 agent 重新解释配置、调整配置，然后重新执行 dry-run 或扫描。

建议初始化时先由 agent 执行：

```powershell
anyfile-wiki roots --explain
anyfile-wiki privacy --privacy configs/privacy.yaml
anyfile-wiki tags --tags-config configs/tags.example.yaml
anyfile-wiki llm --llm-config configs/llm.example.yaml
```

## 初始化后和日常运行阶段

日常阶段由 agent 在空闲时运行。重点不是一次性扫完全盘，而是可暂停、可恢复、可增量地持续整理。

### 1. 按配置扫描路径

Agent 根据隐私配置和推荐扫描目录，扫描允许处理的路径。

当前基础命令：

```powershell
anyfile-wiki scan "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/first-scan --max-entries 500
```

当前已经增加 `anyfile-wiki run` 作为日常空闲运行入口。它会在运行目录保存：

```text
data/runs/<run-id>/run-state.json
```

用于记录：

- 本次扫描的 root 列表。
- 已完成目录或游标。
- 本次最大文件数、最大耗时、最大读取字节数。
- 当前阶段：scan、extract、analyze、review、done。
- 上次中断原因。
- 下次继续的位置。

当前命令示例：

```powershell
anyfile-wiki run "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/daily-run --max-scan-entries 500 --extract-limit 100 --analyze-limit 100
anyfile-wiki run --out data/daily-run
anyfile-wiki run --out data/daily-run --status
```

首次运行需要给出 root。之后重复执行 `anyfile-wiki run --out data/daily-run`，系统会读取 `run-state.json`，继续下一个未完成阶段或下一个路径游标。

这样 agent 在空闲窗口很短时也能安全推进：

```text
本次处理 500 个文件 -> 保存 run-state.json -> 下次空闲继续
```

第一版使用稳定排序后的路径游标推进扫描、提取和分析。它先解决“不要每次从零开始”的问题；后续还可以继续增强为更细的目录级游标、时间预算和异常恢复策略。

### 2. 提取、分析和生成人类页面

Agent 对允许读取的文件执行提取和分析，然后生成两类页面。

当前流程：

```powershell
anyfile-wiki extract --inventory data/first-scan/inventory.sqlite --out data/first-extract
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze
anyfile-wiki review --inventory data/first-scan/inventory.sqlite --analysis data/first-analyze/analysis-manifest.jsonl --out data/first-review
anyfile-wiki html --analysis data/first-analyze/knowledge-index.jsonl --out data/first-html
```

当前已经实现：

- `knowledge-index.html`：资产浏览页。
- `human-review.md` 和 `human-review.jsonl`：需要人类复核的清单。
- `human-review.html`：人类批复页面，可导出 `review-decisions.jsonl`。
- `asset-index.jsonl`：批复动作应用后的最终资产索引，适合 agent 优先读取。

### 3. 人类批复，Agent 继续

这里的关键设计是：静态页面可以负责人类批复，agent 负责继续流程。

推荐流程：

```text
agent 生成 human-review.html
-> 人类打开页面批复
-> 页面生成 review-decisions.jsonl
-> agent 读取 review-decisions.jsonl
-> agent 根据批复继续执行
```

静态 HTML 页面不需要自己启动本地命令。它只需要把人的批复保存成 agent 可读的结构化文件。

当前读取命令：

```powershell
anyfile-wiki decisions --decisions data/first-review/review-decisions.jsonl --out data/first-review/decisions-summary.md --actions-out data/first-review/next-actions.jsonl --plan-out data/first-review/decision-plan.md
```

当前会生成：

- `decisions-summary.md`：批复摘要。
- `next-actions.jsonl`：agent 可读取的后续动作清单。
- `decision-plan.md`：人类和 agent 可共同审阅的执行计划。

把批复动作应用回资产层：

```powershell
anyfile-wiki assets --analysis data/first-analyze/knowledge-index.jsonl --actions data/first-review/next-actions.jsonl --review-items data/first-review/human-review.jsonl --out data/first-assets --html-out data/first-html
```

当前会生成：

- `asset-index.jsonl`：agent 优先读取的最终资产索引。
- `asset-index.md`：给人和 agent 都能快速理解的资产状态摘要。
- `knowledge-index.html`：刷新后的资产浏览页，包含资产状态、人工批复和后续动作。

建议批复文件：

```text
data/first-review/review-decisions.jsonl
```

示例记录：

```json
{
  "path": "C:/Users/me/Documents/example.docx",
  "category": "rules_only_or_low_confidence",
  "decision": "use_local_llm",
  "status": "approved",
  "note": "可以让本地模型复核，不允许云端读取。",
  "manual_tags": ["topic/project_plan"],
  "allow_local_llm": true,
  "allow_cloud_llm": false,
  "created_at": "2026-05-27T00:00:00+00:00"
}
```

后续 agent 可以根据这些决策执行：

- 使用本地 LLM 复核。
- 继续保持 metadata-only。
- 忽略某个文件。
- 生成隐私配置调整建议。
- 重新提取或重新分析。
- 记录人工修正标签。

当前实现已经能把这些动作落成计划文件，并应用到资产索引里的 `asset_status`、`review_action`、`manual_tags` 等字段，不会直接修改源文件或隐私配置。尤其是云端 LLM 相关决策，只会成为“云端授权候选”；如果来源是隐私策略阻止读取的文件，会标记为云端授权冲突，必须等配置显式授权路径和风险确认后才能执行。

### 4. 生成 Agent 可用知识资产

已经处理的数据应该生成 agent 可以快速读取的知识资产。

当前候选输出包括：

- `asset-index.jsonl`：合并人工批复后的最终结构化索引，适合 agent 优先读取。
- `knowledge-index.jsonl`：分析阶段结构化索引，适合作为资产索引的输入和回退。
- `analysis-manifest.jsonl`：完整分析记录，包括 skipped/error。
- `knowledge-index.md`：人类和 agent 都能直接阅读的知识索引。
- `tag-index.md`：按标签组织的 Markdown 索引。
- 后续 wiki/主题页：更适合长期知识沉淀和跨 agent 阅读。

这里需求还需要继续确认：最终 agent 优先消费哪种形态。

建议当前阶段两者都保留：

- JSONL 作为稳定机器接口。
- Markdown/wiki 作为通用兜底上下文。

### 5. Agent 管理本地数据资产

当扫描、分析、批复和知识资产输出形成闭环后，agent 才真正具备管理本地数据资产的能力。

可逐步支持：

- 根据用户问题检索本地知识。
- 解释某个文件是什么。
- 找出需要复核的文件。
- 找出可能重复或可归档的文件。
- 根据人类批复更新标签和备注。
- 生成下一次扫描计划。
- 生成隐私配置调整建议。

任何会影响源文件的动作，例如移动、删除、重命名，都必须进入更严格的显式确认流程。

## 当前流程是否有问题

整体流程没有方向性问题，但有几个需要补充或确认的点。

### 1. 需要进度和断点续跑机制

个人电脑文件很多，agent 空闲时间不稳定。必须设计运行状态文件，否则很容易出现每次从头扫、单次扫不完、无法知道上次做到哪里的问题。

### 2. 静态批复页可以成立，但要明确保存方式

静态 `human-review.html` 可以完成批复，但它不会自己启动后续命令。

合理职责是：

```text
静态页面生成 review-decisions.jsonl
agent 读取 review-decisions.jsonl 并继续
```

这符合本项目“主要给 agent 使用”的定位。

### 3. Agent 消费格式还需要确认

目前可同时输出 JSONL 和 Markdown。后续需要根据真实 agent 使用体验决定：

- 是否只读 JSONL。
- 是否生成 wiki。
- 是否接入 GNO/MCP。
- 是否保留 Markdown 作为所有 agent 都能读的通用格式。

### 4. 配置调整必须可追踪

初始化配置不是一次性动作。人类批复、扫描结果和实际误判都会反过来影响配置。

后续应该让 agent 生成配置变更建议，而不是静默修改隐私策略。

### 5. “管理数据资产”应分权限层级

推荐分层：

1. 只读浏览和索引。
2. 人工批复和标签修正。
3. 本地 LLM 复核。
4. 云端 LLM 复核，需要额外授权。
5. 归档/移动/删除建议。
6. 真正移动或删除文件，必须显式确认并可回滚。

## 当前建议的下一步

1. 让 agent 读取 `asset-index.jsonl` 中的 `local_llm_queue` 后自动触发本地 LLM 复核，并把结果再次回写资产索引。
2. 扩展 `run-state.json`：加入时间预算、失败重试策略和更细的目录级扫描游标。
3. 扩展 `human-review.html` 的批量批复和标签编辑能力。
4. 再确认 agent 最终消费的知识库形态：JSONL、Markdown/wiki、MCP/GNO，或组合。
