# AnyFile Wiki Agent Skill

MVP4 把 AnyFile Wiki 封装成 agent 可直接使用的本地文件知识能力。用户不需要记住长命令；agent 通过 Skill 读取配置、继续扫描、查询索引、引导人工复核，并把使用反馈写回 sidecar 事件账本。

## 一行安装

在仓库根目录运行：

```powershell
python scripts/install_agent_skill.py --editable --extras parse,ocr
```

这个脚本会安装当前包，并把 `skills/anyfile-wiki` 复制到 `$CODEX_HOME/skills/anyfile-wiki`。如果只想安装 Skill：

```powershell
python scripts/install_agent_skill.py --skill-only
```

先看计划、不写入任何文件：

```powershell
python scripts/install_agent_skill.py --dry-run
```

## Agent 初始化

```powershell
anyfile-wiki agent-init --profile configs/agent-profile.yaml --out data/daily-run
```

如果用户已经明确选择宿主 agent 语义理解，也可以初始化时写入：

```powershell
anyfile-wiki agent-init --profile configs/agent-profile.yaml --out data/daily-run --analysis-mode agent-llm --semantic-scope all_extractable
```

初始化会生成或补齐：

- `configs/agent-profile.yaml`：agent 读取入口，记录运行目录、索引、复核页和安全边界。
- `configs/privacy.yaml`：隐私策略，决定哪些路径禁止读取、metadata-only、no-embedding 或 allow。
- `configs/roots.yaml`：推荐扫描目录，供 agent 和用户选择。
- `configs/schedule.yaml`：空闲扫描建议配置，不会自动注册系统计划任务。

已有文件不会被覆盖。agent 应先解释现有配置，再建议用户确认或修改。

## 首次配置向导

安装 Skill 后不要立即扫描。宿主 agent 应按这个顺序带用户完成首次配置：

> 强制约定：首次配置不是“问一个扫描目录就结束”。如果用户只给了目录，agent 必须把它当作 setup_questions 的一个答案，然后继续确认敏感目录、metadata-only/no-embedding 目录、索引理解模式和 dry-run 报告。

1. 运行 `agent-init` 生成或补齐 `agent-profile.yaml`、`privacy.yaml`、`roots.yaml`、`schedule.yaml`。
2. 读取 `privacy.yaml`、`roots.yaml` 和 `agent-profile.yaml` 里 `analysis.setup_questions`。
3. 询问用户敏感目录、第一批扫描目录、metadata-only 目录、是否允许 no-embedding。
4. 询问“索引理解模式”：`rules`、`agent-llm`、`local-llm`、`cloud-llm`。
5. 如果用户选择 `agent-llm`，说明不需要配置 API key，AnyFile Wiki 只生成隐私门控后的任务清单，宿主 agent 只读取 `extracted_text_path` 并写回摘要。
6. 如果用户选择 `cloud-llm`，必须继续配置 `configs/llm.yaml`，包括 `allowed_paths` 和 `risk_acknowledged`。
7. 根据用户回答修改配置；已有用户配置只能在明确说明后更新。
8. 先运行 dry-run 扫描并展示 scan-plan、access-log 和策略命中统计。
9. 用户确认后再继续日常 `run` 流程。

这一步的目标是让配置成为“人类可理解、agent 可读取、日后可调整”的长期协议，而不是一次性命令参数。

## 索引读取顺序

agent 回答文件相关问题时，应按顺序读取：

```text
agent-profile.yaml
run-state.json
asset-index.jsonl
collection-index.jsonl
asset-score.jsonl
原始文件（只有在隐私策略允许且确实需要时）
```

查询入口：

```powershell
anyfile-wiki query "预算测算" --profile configs/agent-profile.yaml --limit 10 --json
```

查询不会重新扫描，也不会打开原始文件。

## 人工复核页面入口

日常人工复核必须优先启动服务模式：

```powershell
anyfile-wiki review-server --review-dir data/daily-run/review --once
```

服务只监听本机地址并打印带 token 的 `review_url`。agent 应打开这个 URL，让用户直接提交批复并写回 `review-decisions.jsonl`、`next-actions.jsonl` 和后续资产索引。静态 `human-review.html` 只是服务无法启动时的备选，不应作为默认入口。

## 安全清理候选计划

当用户想查看疑似重复、归档候选或删除复核候选时，agent 应优先基于 sidecar 索引生成计划：

```powershell
anyfile-wiki archive-plan --asset-index data/daily-run/assets/asset-index.jsonl --out data/daily-run/cleanup
```

这个命令只读取 `asset-index.jsonl`、`collection-index.jsonl` 和 `asset-score.jsonl`，输出 `archive-plan.jsonl`、`archive-plan.md` 和 `archive-plan-summary.json`。所有候选都是 proposed-only：不会移动、删除、重命名源文件，也不会自动执行清理。真正的文件动作必须另行让人确认，并先生成可回滚 manifest。

如果用户已经逐条批复清理候选，agent 可以把批复保存为 `cleanup-decisions.jsonl`，再生成草案动作和回滚 manifest 草案：

```powershell
anyfile-wiki cleanup-decisions --plan data/daily-run/cleanup/archive-plan.jsonl --decisions data/daily-run/cleanup/cleanup-decisions.jsonl --out data/daily-run/cleanup
```

支持的批复动作是 `approve_recommendation`、`reject`、`defer` 和 `keep`。即使选择 `approve_recommendation`，输出的 `cleanup-actions.jsonl` 和 `rollback-manifest-draft.jsonl` 也必须保持 `execution_allowed: false`，并要求最终人工确认；它们不是可执行脚本。

## 使用事件

agent 使用某个资产后，应记录事件：

```powershell
anyfile-wiki usage-event --asset-id "<asset_id>" --event cited --query "预算测算"
```

支持事件类型：

- `selected`
- `opened`
- `cited`
- `search_hit`

事件会追加到 `asset-usage-events.jsonl`。后续运行 `sidecars` 会把这些事件转成 `usage_score`、引用次数和搜索命中次数。

## Agent 语义索引与复核

在 Codex / OpenClaw / Hermes 这类宿主 agent 中，优先使用 `agent-llm` 工作流，而不是让 AnyFile Wiki 自己配置云端 API。

这里分成两条入口：

- `semantic-index`：对所有已成功提取、隐私允许的文本做语义增强，适合把规则摘要升级成真正的内容理解。
- `semantic-review`：只处理人工复核页里已经排队的 `queue_agent_semantic_review` 项目；旧版 `queue_local_llm_review` / `propose_cloud_llm_authorization` 仅作为兼容输入，也按宿主 agent 本地提取文本复核处理。

全量语义索引任务：

```powershell
anyfile-wiki agent-task --kind semantic-index --scope all-extractable --out data/daily-run/agent-review
```

人工复核队列任务：

```powershell
anyfile-wiki agent-task --kind semantic-review --in data/daily-run/review/next-actions.jsonl --out data/daily-run/agent-review
```

任务文件会写入：

- `semantic-index-tasks.jsonl` 或 `semantic-review-tasks.jsonl`：每条任务包含 `asset_id`、`path`、`extracted_text_path`、当前规则摘要/标签、允许标签、隐私上下文和期望输出 schema。
- `semantic-index-skipped.jsonl` 或 `semantic-review-skipped.jsonl`：被隐私策略、metadata-only、缺少提取文本、云端未授权等原因挡住的条目。
- `expected-output-schema.json`：宿主 agent 写回结果必须满足的字段。

宿主 agent 只读取 `extracted_text_path`，不读取原始 `path`。完成分析后写 `results.jsonl`，再交回 CLI：

```powershell
anyfile-wiki agent-review-apply --in data/daily-run/agent-review/results.jsonl
```

写回时 AnyFile Wiki 会校验 schema，并刷新：

- `data/daily-run/analyze/analysis-manifest.jsonl`
- `data/daily-run/analyze/knowledge-index.jsonl`
- `data/daily-run/assets/asset-index.jsonl`
- `data/daily-run/html/knowledge-index.html`

写回后的当前 `title`、`summary`、`tags` 会替换为宿主 agent 的语义结果，`analysis_method` 标记为 `agent-llm`。原来的 `rule_title`、`rule_summary`、`rule_tags` 会继续保留，方便审计、回滚和对比。

复核页里的“Agent 大模型复核”不是云端授权动作，不要求 `configs/llm.yaml`，也不会上传源文件；宿主 agent 只读取任务中的 `extracted_text_path`。`cloud-llm` 仍保留给无人值守、独立 CLI 或后台定时任务使用；这种模式继续要求 `configs/llm.yaml`、API key、`allowed_paths` 和 `risk_acknowledged`。

## 隐私边界

- `deny` 永远优先。
- metadata-only 文件只登记路径、文件名、大小和时间，不读取正文。
- 宿主 agent 语义复核只能读取任务中的 `extracted_text_path`，不能绕过 `privacy.yaml`。
- 云端 LLM 必须显式配置允许路径和风险确认。
- AnyFile Wiki 只给归档、删除、移动建议，不执行真实文件操作。

## OpenClaw / Hermes 适配约定

其他 agent 不需要复刻 Codex Skill 格式，只要遵守同一套协议：

- 初始化时读取 `configs/agent-profile.yaml`。
- 查询时优先使用 `asset-index.jsonl`、`collection-index.jsonl` 和 `asset-score.jsonl`。
- 日常空闲时重复执行 `anyfile-wiki run --out <default_run_dir>`。
- 需要人工确认时优先启动 `review-server` 并打开打印出的 `review_url`，静态 `human-review.html` 只作为备选。
- 需要增强所有已提取文本摘要时使用 `agent-task --kind semantic-index` 和 `agent-review-apply`，不要求用户重复配置宿主模型 API key。
- 只处理人工复核队列时使用 `agent-task --kind semantic-review` 和 `agent-review-apply`。
- 任何源文件移动、删除、重命名都必须升级为显式人工确认。
