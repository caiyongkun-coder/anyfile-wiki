# AnyFile Wiki 当前状态

更新日期：2026-05-29

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
- 新增 `anyfile-wiki review-server`，可启动本地批复服务，让页面直接提交并写入本地批复结果。
- 人工复核页支持确认当前结果、让宿主 agent 大模型复核、已人工整理、忽略、稍后处理、保持隐私。
- 人工复核页可导出 `review-decisions.jsonl`。
- `anyfile-wiki decisions` 可读取 `review-decisions.jsonl`，生成批复摘要、`next-actions.jsonl` 和 `decision-plan.md`。
- `next-actions.jsonl` 已能把人类批复转成 agent 后续动作：宿主 agent 语义复核队列、忽略候选、人工标签覆盖、稍后复核和保持隐私。
- 新增 `anyfile-wiki assets`，可把 `knowledge-index.jsonl`、`human-review.jsonl` 和 `next-actions.jsonl` 合并为最终 `asset-index.jsonl`、`asset-index.md`，并刷新 `knowledge-index.html`。
- 新增资产 sidecar 索引：`asset-signature.jsonl`、`collection-index.jsonl`、`asset-usage-events.jsonl`、`asset-score.jsonl` 和 `asset-sidecar-report.md`，让 agent 能通过 `asset_id` 串联主索引、虚拟资料族和文件管理建议。
- `review-server` 服务版提交后，如果处在标准 run 目录结构中，会自动生成/刷新 `assets/asset-index.jsonl` 和 `html/knowledge-index.html`。
- 资产页已能展示资产状态、人工批复、后续动作、二次确认、人工标签和隐私冲突提示。
- `review-decisions.jsonl` 读取已兼容 Windows PowerShell 常见的 UTF-8 BOM 文件。
- 新增 `anyfile-wiki run`，通过 `run-state.json` 分阶段推进 scan、extract、analyze、review、assets 和 html，支持重复调用后继续下一小步。
- `run-state.json` 当前记录 root、配置、输出路径、阶段状态、路径游标、分块次数、累计统计和最后一步结果。
- `file://` 静态打开时，批复按钮已能即时响应。
- 导出批复后，按钮会动画变成 `✓ 导出完成 / Exported`；后续再修改批复会恢复为待导出状态。
- 当浏览器拦截下载或剪贴板时，人工复核页可直接显示 JSONL 文本，方便手动复制保存。
- 服务版批复页面隐藏 JSONL 复制、显示和导出按钮，只保留保存草稿和提交批复。
- 新增 MVP4 Agent Skill 入口：`skills/anyfile-wiki/SKILL.md`。
- 新增一行安装脚本：`python scripts/install_agent_skill.py --editable --extras parse,ocr`。
- 新增 `anyfile-wiki agent-init`，可生成 agent 可读的 profile、隐私策略、扫描目录和空闲扫描配置。
- 新增 `anyfile-wiki query`，可直接查询 `asset-index.jsonl`、`collection-index.jsonl` 和 `asset-score.jsonl`，不重新扫描原文件。
- 新增 `anyfile-wiki usage-event`，可把 agent 的选择、打开、引用和搜索命中追加到 `asset-usage-events.jsonl`。
- 新增 `docs/agent-skill.md` 和 `configs/schedule.example.yaml`，说明 Codex Skill 与 OpenClaw/Hermes 通用适配约定。

## 最新验证

- `python -m pytest -q`：`119 passed`
- `anyfile-wiki --help` 已包含 `agent-init`、`query`、`usage-event`、`decisions` 和 `assets` 命令。
- `anyfile-wiki run --help` 已包含 `run-state.json` 日常运行入口。
- 演示页已生成：
  - `data/review-html-demo/human-review.html`
  - `data/review-html-demo/human-review.jsonl`
  - `data/review-html-demo/human-review.md`

## 当前设计结论

- `knowledge-index.html` 是静态资产浏览页；人工批复默认使用 `review-server` 服务页，`human-review.html` 只是服务不可用时的静态备选。
- 服务页直接写回 `review-decisions.jsonl`、`next-actions.jsonl` 和批复计划；静态页面只负责手动导出，不直接启动本地命令。
- 人类批复写回后，由 agent 或 CLI 继续读取；当前已经能把批复动作回写到最终资产索引。
- 当前“执行下一步”会更新资产状态和后续动作，不直接移动、删除、重命名源文件，也不直接修改隐私配置。
- 日常运行入口使用路径游标做第一版断点续跑，先解决 agent 空闲时间短时的持续推进问题。
- 云端 LLM 必须显式授权目录和确认风险；默认不允许云端读取本地文件。

## 下一步建议

下一步优先打磨宿主 agent 语义复核体验：从 `queue_agent_semantic_review` 生成任务、读取已提取文本、回写资产索引，并保证复核页不把这个动作误导成云端授权。

随后增强 `run-state.json`：增加时间预算、失败重试策略和更细的目录级扫描游标。
