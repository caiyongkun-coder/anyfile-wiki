# AnyFile Wiki：把散落的个人文件变成 agent 可用的本地知识资产

中文 | [English](README.en.md)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-Apache--2.0-green)
![Privacy](https://img.shields.io/badge/Privacy-local--first-brightgreen)
![Status](https://img.shields.io/badge/Status-MVP-orange)

AnyFile Wiki 是一个本地优先的个人文件知识库项目。它让 OpenClaw、Hermes、Codex 等 agent 在空闲时，安全地盘点电脑里的文档、表格、PDF、图片、代码和应用数据，把长期沉淀的文件整理成可搜索、可浏览、可复用的知识资产。

它不是普通 RAG 聊天工具。AnyFile Wiki 更像一个“本地文件知识治理层”：先判断文件能不能碰，再提取、摘要、打标签、生成资产索引和虚拟资料体系，最后只给出可审计的归档/删除建议，不直接改动你的原始文件。

## 一分钟看懂

```text
你的真实文件保持原地不动
        ↓
隐私策略决定哪些能读、哪些只能记元数据、哪些完全禁止
        ↓
本地提取与分析生成 asset-index.jsonl
        ↓
sidecar 索引生成虚拟资料族、文件指纹、使用热度和归档建议
        ↓
agent 通过稳定 asset_id 找资料，人类通过 HTML 页面浏览和复核
```

核心承诺：

- 不移动、不删除、不重命名原始文件。
- 默认本地优先；云端 LLM 必须显式授权目录和风险确认。
- `deny` 隐私规则永远优先，命中后不读取、不解析、不索引。
- 删除/归档只给建议，不自动执行。

## 你会得到什么

运行完成后，agent 可以优先读取这些结构化文件：

```text
asset-index.jsonl              主资产索引：路径、摘要、标签、分析结果
asset-signature.jsonl          文件名归一化、mtime/size、抽取文本 hash
collection-index.jsonl         虚拟资料族和虚拟目录
asset-usage-events.jsonl       使用事件账本，后续记录搜索、引用、打开
asset-score.jsonl              使用热度、保留价值、归档建议、删除风险
knowledge-index.html           给人看的本地资产浏览页
human-review.html              给人复核和批复的页面
```

这意味着 agent 可以回答：

- 我有哪些资料，它们大概是什么？
- 某个文件在哪里，应该读哪个版本？
- 哪些文件像历史版本、附件、批次文件或疑似重复？
- 哪些文件需要人工复核？
- 哪些可以考虑归档，哪些绝对不能删？

## 为什么做这个项目

个人电脑里有大量有价值的文件，但它们常常因为文件名随意、目录混乱、长期不用而变成信息孤岛。传统文件搜索只能找到文件名或关键词，不能真正回答：

- 我到底保存过哪些资料？
- 哪些文件值得保留、归档、复用？
- 哪些旧文件可以安全清理？
- agent 在工作前能不能先读取我的本地知识上下文？
- 人类能不能像逛标签树、主题树、wiki 一样查看自己的数字资产？

AnyFile Wiki 想把这些问题变成可审计的本地索引，而不是把所有文件先丢给云端模型。

## 当前能力

- 隐私优先的 `privacy.yaml` 策略。
- `deny` 永远优先，命中后不读取、不解析、不索引。
- 支持 `metadata_only`：只记录元数据，不读取正文。
- 支持 `no_embedding`：允许后续读取/摘要，但禁止进入向量索引。
- 推荐扫描目录配置 `roots.example.yaml`，支持人类说明和 AI 可读初始化信息。
- 默认排除系统目录、开发噪声、危险扩展名、安装包、缓存和临时文件。
- dry-run 扫描只遍历路径和元数据，不读取文件正文。
- 输出 `scan-plan.md`、`access-log.jsonl` 和 `inventory.sqlite`。
- 提供 `anyfile-wiki privacy`、`anyfile-wiki status`、`anyfile-wiki list`、`anyfile-wiki show`、`anyfile-wiki roots`、`anyfile-wiki tags`。
- 提供 `anyfile-wiki run`，用 `run-state.json` 分阶段推进扫描、提取、分析、复核页、最终资产索引和 HTML 资产页，支持断点续跑。
- 提供 `anyfile-wiki extract`，只对策略允许读取的文件执行提取。
- 提供 `anyfile-wiki extracts`，查看持久化的提取结果和状态统计。
- 支持增量提取：默认跳过源文件未变化的成功项，支持 `--force` 和 `--retry-failed`。
- 提供 `anyfile-wiki analyze`，基于已提取文本生成本地规则版摘要、标签和知识索引；支持 `--method codex-mock`、`--method local-llm` 和 `--method cloud-llm`。
- 真实 LLM/API 只读取隐私门控后的提取文本；云端模式还必须显式配置授权路径和风险确认。
- 提供 `anyfile-wiki review`，生成 Markdown、JSONL 和 `human-review.html` 人工复核批复页。
- 提供 `anyfile-wiki review-server`，启动本地 `127.0.0.1` 批复服务，页面可直接提交批复并写入本地文件。
- 提供 `anyfile-wiki decisions`，读取人类从 HTML 页面导出的 `review-decisions.jsonl`，并生成摘要、`next-actions.jsonl` 和 `decision-plan.md`。
- 提供 `anyfile-wiki assets`，把分析索引、人工批复和 `next-actions.jsonl` 合并为最终 `asset-index.jsonl`，并刷新资产浏览 HTML；默认同步生成资产 sidecar 索引。
- 提供 `anyfile-wiki sidecars`，可对已有 `asset-index.jsonl` 回填/刷新 `asset-signature.jsonl`、`collection-index.jsonl`、`asset-score.jsonl` 和统计报告。
- 提供 `anyfile-wiki html`，把 `knowledge-index.jsonl` 转成本地可打开的中英双语资产浏览页，支持标签树、分页、筛选、搜索和文件详情。
- 支持直接文本提取和 Excel 轻量摘要；MarkItDown 和 RapidOCR 是可选解析依赖。

## 快速开始

推荐先以 editable 模式安装项目，这样 `anyfile-wiki ...` 命令可以从任何当前目录正常使用：

```powershell
python -m pip install -e .[dev]
python -m pip install -e .[parse]  # Office/PDF 等文档解析
python -m pip install -e .[ocr]    # 图片 OCR

if (-not (Test-Path configs/privacy.yaml)) {
    Copy-Item configs/privacy.example.yaml configs/privacy.yaml
}

New-Item -ItemType Directory -Force "$env:TEMP\anyfile-wiki-mvp0-smoke" | Out-Null
"hello from AnyFile Wiki" | Set-Content -Encoding UTF8 "$env:TEMP\anyfile-wiki-mvp0-smoke\note.txt"

anyfile-wiki scan "$env:TEMP\anyfile-wiki-mvp0-smoke" --privacy configs/privacy.yaml --out data/smoke --max-entries 50
anyfile-wiki status --inventory data/smoke/inventory.sqlite --sources
anyfile-wiki list --inventory data/smoke/inventory.sqlite
anyfile-wiki tags --tags-config configs/tags.example.yaml --dimension topic
anyfile-wiki extract --inventory data/smoke/inventory.sqlite --out data/smoke-extract
anyfile-wiki extracts --inventory data/smoke/inventory.sqlite --stats
anyfile-wiki analyze --inventory data/smoke/inventory.sqlite --out data/smoke-analyze
anyfile-wiki analyze --inventory data/smoke/inventory.sqlite --out data/smoke-analyze-codex --method codex-mock --compare-to data/smoke-analyze/analysis-manifest.jsonl
anyfile-wiki review --inventory data/smoke/inventory.sqlite --analysis data/smoke-analyze/analysis-manifest.jsonl --out data/smoke-review
anyfile-wiki html --analysis data/smoke-analyze/knowledge-index.jsonl --out data/smoke-html

# 日常空闲运行入口：重复执行同一条命令，会根据 run-state.json 继续下一小步
anyfile-wiki run "$env:TEMP\anyfile-wiki-mvp0-smoke" --out data/smoke-run --max-scan-entries 50 --extract-limit 20 --analyze-limit 20

# 打开 data/smoke-review/human-review.html 批复并导出 review-decisions.jsonl 后：
# anyfile-wiki decisions --decisions data/smoke-review/review-decisions.jsonl --out data/smoke-review/decisions-summary.md --actions-out data/smoke-review/next-actions.jsonl --plan-out data/smoke-review/decision-plan.md
# anyfile-wiki assets --analysis data/smoke-analyze/knowledge-index.jsonl --actions data/smoke-review/next-actions.jsonl --review-items data/smoke-review/human-review.jsonl --out data/smoke-assets --html-out data/smoke-html
```

如果不安装包、只是临时从源码树运行 CLI，请先在当前 PowerShell 会话中设置 `PYTHONPATH`，然后用 `python -m anyfile_wiki ...` 启动模块：

```powershell
$env:PYTHONPATH = 'src'
python -m anyfile_wiki analyze --help
```

`anyfile-wiki scan` 在 MVP0 中是 dry-run：它只生成访问计划和 inventory，不读取正文、不做摘要、不写入向量库。

## 常用命令

```powershell
# 查看推荐扫描目录
anyfile-wiki roots --include-missing

# 解释推荐扫描目录配置
anyfile-wiki roots --explain
anyfile-wiki roots --explain --json

# 给用户或初始化 agent 解释隐私配置
anyfile-wiki privacy --privacy configs/privacy.yaml
anyfile-wiki privacy --privacy configs/privacy.yaml --json

# 扫描一个小目录
anyfile-wiki scan "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/first-scan --max-entries 500

# 查看策略统计
anyfile-wiki status --inventory data/first-scan/inventory.sqlite --sources

# 列出 inventory 记录
anyfile-wiki list --inventory data/first-scan/inventory.sqlite --limit 20

# 只看 deny 记录
anyfile-wiki list --inventory data/first-scan/inventory.sqlite --policy deny

# 查看单个路径的策略命中原因
anyfile-wiki show "C:\path\to\file.md" --inventory data/first-scan/inventory.sqlite

# 对允许读取的文件执行提取
anyfile-wiki extract --inventory data/first-scan/inventory.sqlite --out data/first-extract

# 强制重跑
anyfile-wiki extract --inventory data/first-scan/inventory.sqlite --out data/first-extract --force

# 只重试最近一次失败或跳过的记录
anyfile-wiki extract --inventory data/first-scan/inventory.sqlite --out data/first-extract --retry-failed

# 查看提取状态
anyfile-wiki extracts --inventory data/first-scan/inventory.sqlite --stats

# 生成本地规则版知识索引
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze

# 模拟 API/LLM 语义理解，并和规则版结果对比
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-codex --method codex-mock --compare-to data/first-analyze/analysis-manifest.jsonl

# 查看 LLM/云端隐私策略
anyfile-wiki llm --llm-config configs/llm.example.yaml

# 使用本地 LLM，例如 Ollama。需要先复制并修改 configs/llm.yaml，把 llm.mode 设为 local，local.enabled 设为 true
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-local --method local-llm --llm-config configs/llm.yaml

# 使用云端 LLM。必须显式设置 cloud.enabled、risk_acknowledged 和 allowed_paths
anyfile-wiki analyze --inventory data/first-scan/inventory.sqlite --out data/first-analyze-cloud --method cloud-llm --llm-config configs/llm.yaml

# 生成人工待整理清单
anyfile-wiki review --inventory data/first-scan/inventory.sqlite --analysis data/first-analyze/analysis-manifest.jsonl --out data/first-review

# 启动本地批复服务。页面提交后会直接写 review-decisions.jsonl 和后续动作计划
anyfile-wiki review-server --review-dir data/first-review --once

# 日常断点运行：首次带扫描根目录，之后重复同一条命令可按 run-state.json 继续
anyfile-wiki run "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/daily-run --max-scan-entries 500 --extract-limit 100 --analyze-limit 100
anyfile-wiki run --out data/daily-run
anyfile-wiki run --out data/daily-run --status

# 读取 human-review.html 导出的人工批复
anyfile-wiki decisions --decisions data/first-review/review-decisions.jsonl --out data/first-review/decisions-summary.md --actions-out data/first-review/next-actions.jsonl --plan-out data/first-review/decision-plan.md

# 把批复结果应用回最终资产索引，并刷新给人看的 HTML
anyfile-wiki assets --analysis data/first-analyze/knowledge-index.jsonl --actions data/first-review/next-actions.jsonl --review-items data/first-review/human-review.jsonl --out data/first-assets --html-out data/first-html

# 回填或刷新已有资产索引的 sidecar 虚拟资料体系
anyfile-wiki sidecars --asset-index data/first-assets/asset-index.jsonl --out data/first-assets

# 只看 sidecar 计划和统计，不写文件
anyfile-wiki sidecars --asset-index data/first-assets/asset-index.jsonl --out data/first-assets --dry-run

# 生成中文 HTML 资产浏览页
anyfile-wiki html --analysis data/first-analyze/knowledge-index.jsonl --out data/first-html
```

## 项目结构

```text
configs/
  roots.example.yaml         推荐扫描目录示例
  tags.example.yaml          标签体系示例
  llm.example.yaml           LLM 和云端读取策略示例
  excludes.default.yaml      默认排除规则
  privacy.example.yaml       用户隐私策略示例
docs/
  configuration.md           配置说明
  privacy-setup.md           隐私配置初始化和 AI 可读说明
  roots-setup.md             推荐扫描目录初始化说明
  tags-taxonomy.md           标签体系说明
  mvp0-usage.md              MVP0 使用说明
  mvp2-analysis.md           MVP2 内容分析说明
  mvp2-review-llm.md         MVP2.1 LLM 策略与人工待整理清单
  mvp3-html-browser.md       MVP3 HTML 资产浏览页说明
  asset-sidecars.md          资产 sidecar 索引说明
  agent-lifecycle.md         Agent 生命周期与日常运行流程
src/anyfile_wiki/
  policy.py                  隐私策略引擎
  scan.py                    dry-run 扫描器
  inventory.py               SQLite inventory
  report.py                  scan-plan 和 access-log 输出
  run_state.py               日常运行状态和断点续跑
  roots.py                   推荐扫描目录发现
  tags.py                    标签体系解析
  parse.py                   隐私门控后的提取管线
  analyze.py                 本地规则版摘要、标签和知识索引
  llm_client.py              本地/云端 LLM API 客户端
  review.py                  人工待整理清单
  decisions.py               人工批复结果和 agent 后续动作计划
  assets.py                  批复后的最终资产索引合并器
  sidecars.py                资产指纹、虚拟资料族和评分 sidecar
  llm_config.py              LLM 策略配置解析
  html.py                    本地 HTML 资产浏览页生成器
  cli.py                     CLI 入口
tests/
  *.py                       pytest 规格测试
```

## 路线图

- MVP0：隐私策略、默认排除、dry-run、inventory、扫描报告。
- MVP1：接入 MarkItDown，解析常见文档格式，并输出 extraction manifest。
- MVP2：本地摘要、标签、主题、项目和文件类型分类。
- MVP3：人类可浏览资产地图；已经实现 HTML 资产浏览页、人工批复页、本地提交服务和批复结果回写到 `asset-index.jsonl` 的闭环。
- MVP4：agent skill / MCP 集成，支持 OpenClaw、Hermes、Codex 使用本地知识。
- MVP5：安全清理助手：重复文件、归档候选、删除候选和可回滚 manifest。
- MVP6：应用个人数据适配器：浏览器书签、聊天导出、邮件、笔记应用等。

## 开源协作方向

这个项目适合大家一起攻克下面这些难点：

- 如何安全地区分个人文件、系统文件、软件文件和应用个人数据。
- 如何设计足够保守、可解释、可审计的隐私策略。
- 如何在全本地条件下做高质量摘要、标签和聚类。
- 如何让知识库同时服务 agent 检索和人类逐级浏览。
- 如何给出安全、可回滚、低误判的归档/删除建议。
- 如何复用 GNO、MarkItDown、Docling、OpenKB、Paperless-ngx 等开源项目。

欢迎围绕规则库、解析器、测试样例、隐私策略、UI、agent skill、MCP 集成和真实使用反馈贡献成果。

## 测试

```powershell
python -m pytest -q
```

当前测试覆盖：

- `deny` 优先级。
- `metadata_only` 和 `no_embedding` 行为。
- 默认排除规则。
- dry-run 不读取正文。
- inventory 查询。
- CLI `status/list/show`。
- 推荐扫描目录发现。
- 推荐扫描目录配置说明和 JSON 输出。
- 解析任务策略门控。
- 直接文本提取和 extraction manifest。
- extraction result SQLite 持久化和查询。
- 增量提取、强制重跑和失败重试策略。
- 本地规则版内容分析、标签和知识索引输出。
- 真实 LLM/API 分析入口、云端授权门禁和 JSON 响应解析。
- 静态 HTML 资产浏览页生成、中文界面和 CLI 输出。
- 人工批复动作应用到 `asset-index.jsonl`，以及批复服务提交后自动刷新资产 JSON/HTML。
- 资产 sidecar 输出、`asset_id` 稳定性、虚拟资料族、dry-run 和事件账本保护。

## 文档

- [项目启动文档](PROJECT_START.md)
- [开发计划与自研范围](DEVELOPMENT_PLAN.md)
- [配置说明](docs/configuration.md)
- [隐私配置初始化说明](docs/privacy-setup.md)
- [推荐扫描目录配置说明](docs/roots-setup.md)
- [标签体系说明](docs/tags-taxonomy.md)
- [MVP0 使用说明](docs/mvp0-usage.md)
- [MVP1 提取说明](docs/mvp1-extraction.md)
- [MVP2 内容分析说明](docs/mvp2-analysis.md)
- [MVP2.1 LLM 策略与人工待整理清单](docs/mvp2-review-llm.md)
- [MVP3 HTML 资产浏览页说明](docs/mvp3-html-browser.md)
- [资产 Sidecar 索引](docs/asset-sidecars.md)
- [Agent 生命周期与日常运行流程](docs/agent-lifecycle.md)

## 许可证

本项目使用 [Apache License 2.0](LICENSE)。
