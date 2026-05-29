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

初始化会生成或补齐：

- `configs/agent-profile.yaml`：agent 读取入口，记录运行目录、索引、复核页和安全边界。
- `configs/privacy.yaml`：隐私策略，决定哪些路径禁止读取、metadata-only、no-embedding 或 allow。
- `configs/roots.yaml`：推荐扫描目录，供 agent 和用户选择。
- `configs/schedule.yaml`：空闲扫描建议配置，不会自动注册系统计划任务。

已有文件不会被覆盖。agent 应先解释现有配置，再建议用户确认或修改。

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

## 隐私边界

- `deny` 永远优先。
- metadata-only 文件只登记路径、文件名、大小和时间，不读取正文。
- 云端 LLM 必须显式配置允许路径和风险确认。
- AnyFile Wiki 只给归档、删除、移动建议，不执行真实文件操作。

## OpenClaw / Hermes 适配约定

其他 agent 不需要复刻 Codex Skill 格式，只要遵守同一套协议：

- 初始化时读取 `configs/agent-profile.yaml`。
- 查询时优先使用 `asset-index.jsonl`、`collection-index.jsonl` 和 `asset-score.jsonl`。
- 日常空闲时重复执行 `anyfile-wiki run --out <default_run_dir>`。
- 需要人工确认时打开 `human-review.html` 或读取 `human-review.jsonl`。
- 任何源文件移动、删除、重命名都必须升级为显式人工确认。
