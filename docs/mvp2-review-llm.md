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
python -m pfkb llm --llm-config configs/llm.example.yaml
python -m pfkb llm --llm-config configs/llm.example.yaml --json
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

真实 API 模式已经接入 `pfkb analyze`：

```powershell
python -m pfkb analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-local --method local-llm --llm-config configs/llm.yaml
python -m pfkb analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-cloud --method cloud-llm --llm-config configs/llm.yaml
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

## 人工待整理清单

生成清单：

```powershell
python -m pfkb review --inventory data/first-scan/inventory.sqlite --analysis data/first-analyze/analysis-manifest.jsonl --out data/first-review
```

输出：

- `human-review.md`：给人看的待整理清单。
- `human-review.jsonl`：给 agent 或后续程序读取的结构化清单。

清单会包含这些类型：

- `policy_blocked`：隐私策略明确拒绝读取。
- `metadata_only`：只允许记录元数据。
- `unsupported_format`：暂时没有解析器。
- `not_extracted`：允许提取但尚未提取。
- `extraction_problem`：提取失败或跳过。
- `rules_only_or_low_confidence`：规则版标签或低置信度结果，需要用户或本地 LLM 复核。
- `cloud_not_authorized`：云端模式下路径未显式授权。
- `cloud_forbidden_by_policy`：策略禁止云端处理。

## HTML 交互版

当前阶段继续保留 Markdown 和 JSONL：Markdown 适合人直接打开审阅，JSONL 适合 agent 和脚本读取。

随着文件数量增加，只靠 Markdown 会越来越难翻阅。当前已经先实现只读资产浏览页：

```powershell
python -m pfkb html --analysis data/first-analyze/knowledge-index.jsonl --out data/first-html
```

- `knowledge-index.html`：给人按标签、内容类型、分析方式和复核状态逐层浏览知识库。
- `human-review.html`：仍在后续计划中，用来处理待整理文件，并把选择写回本地决策记录。

后续可回写的 HTML 审阅页优先支持这些交互：

- 允许本地 LLM 查看这个文件。
- 在云端策略已经显式授权的前提下，允许云端 LLM 查看这个文件。
- 稍后审核这个文件。
- 忽略这个文件。
- 标记为已人工整理。
- 保持本地-only，不允许云端读取。

这些交互不应该悄悄删除文件，也不应该直接绕过隐私策略。建议把用户选择写入独立的本地记录，例如 `review-decisions.jsonl`，再由后续命令显式应用到配置或分析流程。

## 设计原则

当前系统不会假装理解了一切。

如果只是规则版分析，结果会写入：

- `analysis_method: rules`
- `confidence`
- `needs_human_review`
- `review_reason`

这些字段会被 `pfkb review` 用来生成待整理清单。真实 LLM 模式会把 `analysis_method` 写成 `local-llm` 或 `cloud-llm`，并把置信度、复核原因和模型说明写入同一套输出文件。
