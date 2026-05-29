# CLI 参考

README 只保留 agent 优先的快速开始。本页保留开发、调试和手动运行时常用的 CLI 命令。

## 安装与 Skill

```powershell
# 一行安装包和 Codex Skill
python scripts/install_agent_skill.py --editable --extras parse,ocr

# 只看安装计划，不写文件
python scripts/install_agent_skill.py --dry-run

# 只安装包，不复制 Skill
python -m pip install -e .[dev]
python -m pip install -e .[parse]
python -m pip install -e .[ocr]
```

## Agent 入口

```powershell
# 初始化 agent 可读配置
anyfile-wiki agent-init --profile configs/agent-profile.yaml --out data/daily-run

# 继续日常断点运行
anyfile-wiki run --out data/daily-run

# 查看进度
anyfile-wiki run --out data/daily-run --status

# 查询已有资产索引，不重新扫描原文件
anyfile-wiki query "预算测算" --profile configs/agent-profile.yaml --json

# 生成宿主 agent 语义复核任务，不要求 AnyFile Wiki 配置 API key
anyfile-wiki agent-task --kind semantic-review --in data/daily-run/review/next-actions.jsonl --out data/daily-run/agent-review
anyfile-wiki agent-review-apply --in data/daily-run/agent-review/results.jsonl

# 记录 agent 使用事件
anyfile-wiki usage-event --asset-id "<asset_id>" --event cited --query "预算测算"
```

## 配置解释

```powershell
anyfile-wiki roots --include-missing
anyfile-wiki roots --explain
anyfile-wiki roots --explain --json

anyfile-wiki privacy --privacy configs/privacy.yaml
anyfile-wiki privacy --privacy configs/privacy.yaml --json

anyfile-wiki tags --tags-config configs/tags.example.yaml --dimension topic
anyfile-wiki llm --llm-config configs/llm.example.yaml
```

## 手动流水线

```powershell
# scan 是 dry-run，只生成访问计划和 inventory，不读取正文
anyfile-wiki scan "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/first-scan --max-entries 500
anyfile-wiki status --inventory data/first-scan/inventory.sqlite --sources
anyfile-wiki list --inventory data/first-scan/inventory.sqlite --limit 20
anyfile-wiki show "C:\path\to\file.md" --inventory data/first-scan/inventory.sqlite

anyfile-wiki extract --inventory data/first-scan/inventory.sqlite --out data/first-extract
anyfile-wiki extract --inventory data/first-scan/inventory.sqlite --out data/first-extract --force
anyfile-wiki extract --inventory data/first-scan/inventory.sqlite --out data/first-extract --retry-failed
anyfile-wiki extracts --inventory data/first-scan/inventory.sqlite --stats

anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-codex --method codex-mock --compare-to data/first-analyze/analysis-manifest.jsonl

anyfile-wiki review --inventory data/first-scan/inventory.sqlite --analysis data/first-analyze/analysis-manifest.jsonl --out data/first-review
anyfile-wiki review-server --review-dir data/first-review --once
anyfile-wiki decisions --decisions data/first-review/review-decisions.jsonl --out data/first-review/decisions-summary.md --actions-out data/first-review/next-actions.jsonl --plan-out data/first-review/decision-plan.md

anyfile-wiki assets --analysis data/first-analyze/knowledge-index.jsonl --actions data/first-review/next-actions.jsonl --review-items data/first-review/human-review.jsonl --out data/first-assets --html-out data/first-html
anyfile-wiki sidecars --asset-index data/first-assets/asset-index.jsonl --out data/first-assets
anyfile-wiki sidecars --asset-index data/first-assets/asset-index.jsonl --out data/first-assets --dry-run
anyfile-wiki html --analysis data/first-analyze/knowledge-index.jsonl --out data/first-html
```

## LLM 模式

```powershell
# Codex/OpenClaw/Hermes 宿主 agent 场景优先使用 agent-task / agent-review-apply。
# 下面两个模式适合独立 CLI 或后台无人值守自动化。

# 本地 LLM，例如 Ollama。先复制并修改 configs/llm.yaml
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-local --method local-llm --llm-config configs/llm.yaml

# 云端 LLM 必须显式配置 cloud.enabled、risk_acknowledged 和 allowed_paths
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-cloud --method cloud-llm --llm-config configs/llm.yaml
```
