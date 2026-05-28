# AnyFile Wiki 当前状态

更新日期：2026-05-28

## 仓库状态

- GitHub 仓库：`https://github.com/caiyongkun-coder/anyfile-wiki`
- 主分支：`main`
- 当前已推送提交：
  - `0e122cd Animate review export completion state`
  - `91a0e15 Fix review page decision feedback on file URLs`
  - `a309f97 Add human review decisions flow`
  - `322af00 Rename project to AnyFile Wiki`

## 已完成能力

- 项目已正式改名为 AnyFile Wiki。
- CLI 已统一为 `anyfile-wiki`。
- 已有隐私策略、推荐扫描目录、标签体系和 LLM 策略配置。
- 已能扫描配置路径，生成 `inventory.sqlite`、`scan-plan.md` 和 `access-log.jsonl`。
- 已能对允许读取的文件做内容提取。
- 已能生成规则版、模拟语义版和真实 LLM API 版分析结果。
- 已能生成给 agent 使用的 `knowledge-index.jsonl`、`analysis-manifest.jsonl`。
- 已能生成给人看的 `knowledge-index.md`、`tag-index.md`。
- 已能生成 `knowledge-index.html` 资产浏览页，支持中英双语、标签树、搜索、筛选、分页和详情面板。
- 已能生成 `human-review.html` 人工复核批复页。
- 人工复核页支持确认当前结果、允许本地 LLM、允许云端 LLM、已人工整理、忽略、稍后处理、保持隐私。
- 人工复核页可导出 `review-decisions.jsonl`。
- `anyfile-wiki decisions` 可读取 `review-decisions.jsonl`，生成批复摘要、`next-actions.jsonl` 和 `decision-plan.md`。
- `next-actions.jsonl` 已能把人类批复转成 agent 后续动作：本地 LLM 复核队列、云端授权候选、忽略候选、人工标签覆盖、稍后复核和保持隐私。
- `review-decisions.jsonl` 读取已兼容 Windows PowerShell 常见的 UTF-8 BOM 文件。
- 新增 `anyfile-wiki run`，通过 `run-state.json` 分阶段推进 scan、extract、analyze、review 和 html，支持重复调用后继续下一小步。
- `run-state.json` 当前记录 root、配置、输出路径、阶段状态、路径游标、分块次数、累计统计和最后一步结果。
- `file://` 静态打开时，批复按钮已能即时响应。
- 导出批复后，按钮会动画变成 `✓ 导出完成 / Exported`；后续再修改批复会恢复为待导出状态。

## 最新验证

- `python -m pytest -q`：`74 passed`
- `anyfile-wiki --help` 已包含 `decisions` 命令。
- `anyfile-wiki run --help` 已包含 `run-state.json` 日常运行入口。
- 演示页已生成：
  - `data/review-html-demo/human-review.html`
  - `data/review-html-demo/human-review.jsonl`
  - `data/review-html-demo/human-review.md`

## 当前设计结论

- `knowledge-index.html` 和 `human-review.html` 都是静态页面，不需要后端服务。
- 静态页面只负责人类浏览和批复，不直接启动本地命令。
- 人类批复导出为 `review-decisions.jsonl` 后，由 agent 或 CLI 继续读取并执行下一步。
- 当前“执行下一步”先落成计划文件，不直接移动、删除、重命名源文件，也不直接修改隐私配置。
- 日常运行入口使用路径游标做第一版断点续跑，先解决 agent 空闲时间短时的持续推进问题。
- 云端 LLM 必须显式授权目录和确认风险；默认不允许云端读取本地文件。

## 下一步建议

优先让 agent 自动消费 `next-actions.jsonl`：先处理本地 LLM 复核、人工标签覆盖和忽略候选汇总；云端 LLM 候选仍只生成配置建议，必须等待人类确认。

随后增强 `run-state.json`：增加时间预算、失败重试策略和更细的目录级扫描游标。
