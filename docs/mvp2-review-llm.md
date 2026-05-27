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

## 设计原则

当前系统不会假装理解了一切。

如果只是规则版分析，结果会写入：

- `analysis_method: rules`
- `confidence`
- `needs_human_review`
- `review_reason`

这些字段会被 `pfkb review` 用来生成待整理清单。后续接入本地 LLM 时，可以把 `analysis_method` 改成 `local_llm`，并把置信度和复核原因更新得更准确。
