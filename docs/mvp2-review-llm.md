# MVP2.1 LLM 策略与人工待整理清单

本阶段解决两个问题：

1. 内容理解可以使用规则、本地 LLM 或云端 LLM，但云端必须显式授权。
2. 系统不能理解、不能读取、不能提取、低置信度的文件必须列出来，交给用户确认。

## LLM 策略

配置模板：

```text
configs/llm.example.yaml
```

查看当前策略：

```powershell
anyfile-wiki llm --llm-config configs/llm.example.yaml
anyfile-wiki llm --llm-config configs/llm.example.yaml --json
```

默认模式是：

```yaml
llm:
  mode: rules
```

这表示不调用任何模型，只使用本地规则。云端 API 默认关闭：

```yaml
cloud:
  enabled: false
  risk_acknowledged: false
  allowed_paths: []
```

云端模式必须同时满足：

- `llm.mode` 是 `cloud`。
- `cloud.enabled` 是 `true`。
- `cloud.risk_acknowledged` 是 `true`。
- 文件策略在 `allowed_policies` 内。
- 文件策略不在 `forbidden_policies` 内。
- 文件路径位于 `allowed_paths` 之下。

`deny`、`metadata_only`、`no_embedding` 默认都禁止云端处理。

## 真实 LLM/API 分析

真实 API 模式已经接入 `anyfile-wiki analyze`：

```powershell
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-local --method local-llm --llm-config configs/llm.yaml
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-cloud --method cloud-llm --llm-config configs/llm.yaml
```

它不会让 API 直接访问本地原始文件。流程是：

```text
隐私策略通过 -> 本地提取正文 -> LLM 授权门禁 -> 发送提取文本 -> 接收 JSON 结果
```

本地模式要求：

- `llm.mode: local`
- `local.enabled: true`
- 配置 `local.provider` 和 `local.model`
- 默认 `local.endpoint` 必须是 loopback，例如 `http://localhost:11434`

云端模式要求：

- `llm.mode: cloud`
- `cloud.enabled: true`
- `cloud.risk_acknowledged: true`
- 文件 `access_policy` 在 `cloud.allowed_policies` 内
- 文件路径位于 `cloud.allowed_paths` 下

如果云端文件缺少原始隐私策略上下文，或没有位于授权目录内，分析结果会写成 `status: skipped`，不会调用 API。

## 宿主 Agent 语义复核

在 Codex、OpenClaw、Hermes 这类宿主 agent 中，推荐优先使用 `agent-llm` / `agent-review` 流程，而不是让 AnyFile Wiki 再配置一套云端 API key。

分工是：

- AnyFile Wiki：执行隐私门控、扫描、提取文本、生成待复核任务、校验写回结果。
- 宿主 agent：读取已提取文本，理解内容，生成结构化标题、摘要、标签、置信度和复核状态。
- 用户：只需要确认隐私配置和人工复核决定，不需要重复配置宿主模型的 API key。

生成任务：

```powershell
anyfile-wiki agent-task --kind semantic-review --in data/daily-run/review/next-actions.jsonl --out data/daily-run/agent-review
```

任务只会指向已经存在的 `extracted_text_path`。`deny`、`metadata_only`、缺少提取文本、或被策略挡住的文件会写入 `semantic-review-skipped.jsonl`，不会进入 agent 可读任务。

宿主 agent 写回 `results.jsonl` 后：

```powershell
anyfile-wiki agent-review-apply --in data/daily-run/agent-review/results.jsonl
```

CLI 会校验 schema，并刷新 `analysis-manifest.jsonl`、`knowledge-index.jsonl`、`assets/asset-index.jsonl` 和 `html/knowledge-index.html`。写回后的记录使用：

```text
analysis_method: agent-llm
```

`cloud-llm` 继续保留给独立 CLI、无人值守后台或定时任务；这种模式仍然要求 `configs/llm.yaml`、API key、`allowed_paths` 和 `risk_acknowledged`。

## 人工待整理清单

生成清单：

```powershell
anyfile-wiki review --inventory data/first-scan/inventory.sqlite --analysis data/first-analyze/analysis-manifest.jsonl --out data/first-review
```

输出：

- `human-review.md`：给人看的待整理清单。
- `human-review.jsonl`：给 agent 或后续程序读取的结构化清单。
- `human-review.html`：给人逐项批复的页面；日常推荐用 `review-server` 服务模式打开，静态文件作为备选。

清单会包含这些类型：

- `policy_blocked`：隐私策略明确拒绝读取。
- `metadata_only`：只允许记录元数据。
- `unsupported_format`：暂时没有解析器。
- `not_extracted`：允许提取但尚未提取。
- `extraction_problem`：提取失败或跳过。
- `rules_only_or_low_confidence`：规则版标签或低置信度结果，需要用户或本地 LLM 复核。
- `cloud_not_authorized`：云端模式下路径未显式授权。
- `cloud_forbidden_by_policy`：策略禁止云端处理。

## HTML 批复版

当前阶段继续保留 Markdown 和 JSONL：Markdown 适合人直接打开审阅，JSONL 适合 agent 和脚本读取。

随着文件数量增加，只靠 Markdown 会越来越难翻阅。当前已经实现两类 HTML：

```powershell
anyfile-wiki html --analysis data/first-analyze/knowledge-index.jsonl --out data/first-html
```

- `knowledge-index.html`：给人按标签、内容类型、分析方式和复核状态逐层浏览知识库。
- `human-review.html`：给人处理待整理文件，并导出本地决策记录。

静态 `human-review.html` 不会直接执行本地命令，也不会绕过隐私策略；用户点击“导出批复”后，浏览器下载 `review-decisions.jsonl`，再由 agent 读取。

更顺手的主流程是由 agent 启动本地批复服务：

```powershell
anyfile-wiki review-server --review-dir data/first-review --once
```

服务只监听本机地址，启动时会打印带 token 的 `review_url`。服务版页面不显示 JSONL 下载/复制按钮，只保留“保存草稿”和“提交批复”；提交后由本地 server 直接写入 `review-decisions.jsonl`、`decisions-summary.md`、`next-actions.jsonl` 和 `decision-plan.md`。

服务模式会把完全相同的重复提交视为幂等成功，不会额外生成新文件；页面也会在提交完成后禁用重复提交按钮。

如果 `review` 目录位于标准 run 结构中，例如 `data/daily-run/review`，提交后还会自动刷新：

- `data/daily-run/assets/asset-index.jsonl`
- `data/daily-run/assets/asset-index.md`
- `data/daily-run/html/knowledge-index.html`

读取批复结果：

```powershell
anyfile-wiki decisions --decisions data/first-review/review-decisions.jsonl --out data/first-review/decisions-summary.md --actions-out data/first-review/next-actions.jsonl --plan-out data/first-review/decision-plan.md
```

生成文件：

- `decisions-summary.md`：给人看的批复统计和明细。
- `next-actions.jsonl`：给 agent 读取的后续动作清单。
- `decision-plan.md`：给人和 agent 共同审阅的后续执行计划。

把批复结果应用回资产层：

```powershell
anyfile-wiki assets --analysis data/first-analyze/knowledge-index.jsonl --actions data/first-review/next-actions.jsonl --review-items data/first-review/human-review.jsonl --out data/first-assets --html-out data/first-html
```

生成文件：

- `asset-index.jsonl`：最终资产索引，包含 `asset_status`、`review_action`、`manual_tags` 和隐私冲突提示。
- `asset-index.md`：给人看的资产状态摘要。
- `knowledge-index.html`：刷新后的资产浏览页。

当前 HTML 审阅页支持这些批复动作：

- 允许本地 LLM 查看这个文件。
- 在云端策略已经显式授权的前提下，允许云端 LLM 查看这个文件。
- 稍后审核这个文件。
- 忽略这个文件。
- 标记为已人工整理。
- 保持本地-only，不允许云端读取。

这些交互不会悄悄删除文件，也不会直接改隐私配置。当前会先把用户选择写入独立记录，再由 `anyfile-wiki decisions` 转成后续动作计划，例如本地 LLM 复核队列、忽略候选、人工标签覆盖记录和云端授权候选；随后 `anyfile-wiki assets` 会把动作写回最终资产索引，供 agent 和 HTML 资产页使用。

## 设计原则

当前系统不会假装理解了一切。

如果只是规则版分析，结果会写入：

- `analysis_method: rules`
- `confidence`
- `needs_human_review`
- `review_reason`

这些字段会被 `anyfile-wiki review` 用来生成待整理清单。真实 LLM 模式会把 `analysis_method` 写成 `local-llm` 或 `cloud-llm`；宿主 agent 写回模式会写成 `agent-llm`。三者都会把置信度、复核原因和模型说明写入同一套输出文件。
