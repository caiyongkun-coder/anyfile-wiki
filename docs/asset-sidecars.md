# 资产 Sidecar 索引

`asset-index.jsonl` 仍然是主资产索引，用来保存文件路径、摘要、标签、分析方式和人工批复状态。Sidecar 索引用来补充 agent 长期使用时需要的稳定身份、虚拟目录、使用事件和文件管理建议。

这些文件只在索引层工作，不会移动、删除或重命名原始文件。

## 输出文件

默认运行 `anyfile-wiki assets` 或 `anyfile-wiki run` 的 assets 阶段时，会在资产目录中生成：

- `asset-index.jsonl`：主资产索引，保留原能力，并新增 `asset_id` 和 `asset_id_strategy`。
- `asset-signature.jsonl`：文件名归一化、文件元数据、抽取文本 hash 和抽取质量。
- `collection-index.jsonl`：虚拟资料族和虚拟目录，每行表示一个资产在虚拟资料体系中的位置和关系。
- `asset-usage-events.jsonl`：agent 或人类后续使用事件账本。生成 sidecar 时只创建空文件，不覆盖已有事件。
- `asset-score.jsonl`：使用热度、保留价值、归档建议和删除风险评分。
- `asset-sidecar-report.md`：简短统计报告。
- `archive-plan.jsonl` / `archive-plan.md`：由 `archive-plan` 命令生成的安全清理候选计划，不会自动执行。

## 命令

从分析结果和人工批复生成完整资产索引：

```powershell
anyfile-wiki assets --analysis data/analyze/knowledge-index.jsonl --actions data/review/next-actions.jsonl --review-items data/review/human-review.jsonl --out data/assets --html-out data/html
```

只回填已有 `asset-index.jsonl` 的 sidecar：

```powershell
anyfile-wiki sidecars --asset-index data/assets/asset-index.jsonl --out data/assets
```

只看计划和统计，不写文件：

```powershell
anyfile-wiki sidecars --asset-index data/assets/asset-index.jsonl --out data/assets --dry-run
```

只读主索引和文件元数据，不读取抽取文本：

```powershell
anyfile-wiki sidecars --asset-index data/assets/asset-index.jsonl --sidecar-level light
```

从 sidecar 评分生成可复核的清理候选计划：

```powershell
anyfile-wiki archive-plan --asset-index data/assets/asset-index.jsonl --out data/cleanup
```

`archive-plan` 会读取同目录下的 `collection-index.jsonl` 和 `asset-score.jsonl`，输出：

- `archive-plan.jsonl`：给 agent 或后续 UI 使用的候选 manifest。
- `archive-plan.md`：给人类复核的中文报告。
- `archive-plan-summary.json`：统计、来源路径和安全边界摘要。

人类批复清理候选后，可以把批复保存成 `cleanup-decisions.jsonl`，再生成下一步草案：

```powershell
anyfile-wiki cleanup-decisions --plan data/cleanup/archive-plan.jsonl --decisions data/cleanup/cleanup-decisions.jsonl --out data/cleanup
```

`cleanup-decisions` 输出：

- `cleanup-actions.jsonl`：批复后的草案动作，仍然 `execution_allowed: false`。
- `rollback-manifest-draft.jsonl`：仅对已批准建议生成的回滚 manifest 草案，记录 `original_path`、`target_path` 和 `intended_operation`，但 `rollback_ready: false`。
- `cleanup-decision-plan.md`：给人类和 agent 共同复核的草案说明。
- `cleanup-decisions-summary.json`：批复统计、输出路径和安全边界。

## Asset ID

第一版使用路径稳定主键：

```text
asset:path-sha256:<sha256(normalized_path)>
```

`normalized_path` 会把反斜杠转为 `/`，并做大小写折叠。它适合当前“不移动原文件”的阶段。抽取文本 hash 和未来的内容 hash 只作为辅助线索，不作为主键。

## 虚拟目录

`collection-index.jsonl` 会把文件放入虚拟目录，例如：

- `00_总览与待处理`
- `01_业务方案与需求`
- `02_FTP预算测算与取数`
- `03_财务数据与核对`
- `04_报表表样与模板`
- `05_定价规则与曲线`
- `06_技术设计与接口`
- `07_项目管理与交付`
- `08_培训汇报材料`
- `09_压缩包_不可解析_待复核`

分类优先使用低成本信息：文件名、扩展名、抽取状态、标签、摘要和规则标题。`review_only`、`error`、压缩包和不可解析文件会优先进入待复核目录，不会被强行并入资料族。

## 文件管理建议

`asset-score.jsonl` 拆分四类分数：

- `usage_score`：使用热度，来自 `asset-usage-events.jsonl`。
- `retention_score`：保留价值，来自摘要、标签、置信度、抽取质量和资料族关系。
- `archive_score`：归档建议强度。
- `delete_risk_score`：删除风险，越高越不能删。

`archive_policy` 只表示建议，不执行任何操作。低使用不代表可以删除；`review_required`、`master`、高保留价值或 `never_delete` 都会提高删除风险。

`archive-plan` 输出中的 `proposed_operation` 始终是 `none`，`execution_allowed` 始终是 `false`。`cleanup-decisions` 也只会生成草案动作和回滚 manifest 草案；即使人类批复了 `approve_recommendation`，输出仍不能直接执行。任何未来真实移动、删除、重命名都必须先由人最终确认，并生成包含 `original_path`、`target_path`、动作人和确认时间的独立回滚 manifest。
