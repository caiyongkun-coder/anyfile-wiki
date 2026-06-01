# AnyFile Wiki：把散落的个人文件变成 agent 可用的本地知识资产

中文 | [English](README.en.md)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-Apache--2.0-green)
![Privacy](https://img.shields.io/badge/Privacy-local--first-brightgreen)
![Status](https://img.shields.io/badge/Status-MVP4--ready-orange)

AnyFile Wiki 是一个给 AI agent 用的本地优先个人文件知识治理层。它让 OpenClaw、Hermes、Codex 等 agent 在空闲时，先通过隐私策略判断哪些文件能读、哪些只能记录元数据、哪些完全禁止，再把长期沉淀的文档、表格、PDF、图片、代码和应用数据整理成可搜索、可浏览、可复用的知识资产。

它不是普通 RAG 聊天工具。AnyFile Wiki 更像一个“本地文件知识治理层”：先判断文件能不能碰，再提取、摘要、打标签、生成资产索引和虚拟资料体系，最后只给出可审计的归档/删除建议，不直接改动你的原始文件。

## 为什么先装 Agent Skill

AnyFile Wiki 的目标使用者首先是 agent。只安装 Python 包时，agent 只能把它当成一组临时 CLI 命令；安装 `skills/anyfile-wiki/SKILL.md` 后，agent 会得到一套固定工作协议：先解释隐私配置，再 dry-run，再分步生成索引，最后优先查索引而不是反复打开原始文件。

Agent Skill 不绕过安全规则。它的作用是约束 agent 以更稳定、更省上下文、更可审计的方式使用这些规则。

| 工作环节 | 没装 Skill 的 agent | 装了 Skill 的 agent |
| --- | --- | --- |
| 首次设置 | 容易只问“扫哪个目录”，忽略敏感路径、metadata-only 和 no-embedding | 必须引导 `agent-init`、隐私问题、扫描根、索引模式和 dry-run 确认 |
| 隐私边界 | 依赖临时提示词记忆，容易把“能看到路径”误解成“能读正文” | 先读 `privacy.yaml` / `agent-profile.yaml`，按 `deny > metadata_only > no_embedding > allow` 执行 |
| 扫描与续跑 | 每次任务都可能重新遍历目录，失败后难以续上 | 使用 `run-state.json`、分阶段 `run`、增量 extraction，适合空闲时慢慢跑 |
| 查询资料 | 常用 `rg`、shell 遍历或直接打开文件，单次快但不可复用 | 优先查 `asset-index.jsonl`、sidecars 和 HTML 索引，必要时才读原文件 |
| 上下文消耗 | 容易把大量原文、文件列表或命令输出塞进上下文 | 通常只返回 top N 个 asset 记录、摘要、标签、asset_id 和复核状态 |
| 人工复核 | 需要临时解释哪些文件不确定、哪些需要确认 | 通过 `human-review.html` / `review-server` / `next-actions.jsonl` 形成可写回流程 |
| 长期优化 | agent 很难记住哪些文件被搜过、引用过、应该保留 | `usage-event` 和 `asset-score` 记录使用热度，后续能改进排序和归档建议 |

## 最安全的首次试用

第一次不要扫全盘，也不要扫敏感目录。建议先创建一个只包含合成文件或非敏感文件的小目录，然后只做 dry-run：

```powershell
anyfile-wiki scan .\demo-files\input --privacy .\demo-files\demo_privacy.yaml --out .\demo-files\out --max-entries 50
```

`anyfile-wiki scan` 是 dry-run：只生成访问计划、审计日志和 inventory，不读取文件正文、不生成摘要、不写入向量库。

如果你愿意反馈问题，请不要上传个人文件、真实敏感路径、密钥、聊天记录或包含私人文件名的截图。最有帮助的是：操作系统、Python 版本、脱敏命令、脱敏输出、合成样例目录结构，以及你觉得隐私边界不清楚的地方。

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
human-review.html              给人复核和批复的静态备选页面；日常优先用 review-server 写回
```

这意味着 agent 可以回答：

- 我有哪些资料，它们大概是什么？
- 某个文件在哪里，应该读哪个版本？
- 哪些文件像历史版本、附件、批次文件或疑似重复？
- 哪些文件需要人工复核？
- 哪些可以考虑归档，哪些绝对不能删？

## 性能测试与规模上限

下面的数字用于给 agent 预估工作量，不是硬件无关承诺。测试数据是本地生成的合成 `.txt` / `.md` 文件，不包含个人信息；测试目录位于 `.tmp_pytest/readme_benchmark`。测试环境是 Windows 11、Python 3.12.7、本地 SSD，命令入口是 `python -m anyfile_wiki`。

| 文件数 | 合成语料 | raw `rg budget` | `scan` dry-run | `extract` + `analyze` + `review` + `assets/html` | 全链路冷启动 | 索引后 `query` 平均 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 1.35 MB | 0.22s | 0.36s | 6.31s | 6.68s | 0.29s |
| 5,000 | 6.77 MB | 3.60s | 0.78s | 41.79s | 42.57s | 0.49s |
| 10,000 | 13.54 MB | 7.03s | 1.34s | 90.78s | 92.12s | 0.87s |

怎么理解这组数据：

- 对 1,000 个纯文本文件的一次性关键词搜索，`rg` 仍然很快，没必要把 AnyFile Wiki 解释成所有场景的 raw 搜索加速器。
- 到 10,000 个文件时，raw 全文搜索 `budget` 用了 7.03s；索引完成后，agent 通过 `anyfile-wiki query` 查已有资产索引平均 0.87s，约 8.1 倍更快，而且不需要重新打开原始文件。
- 冷启动全链路的主要瓶颈是 `extract`：10,000 个小文本文件里，extract 用了 79.08s；`scan` 本身只有 1.34s，rules 分析是 6.36s，assets/html/sidecars 是 4.62s。
- 对 agent 来说，最大的优化不是“第一次处理完全免费”，而是把一次性的原文读取成本换成可复用索引。之后的查找、引用、复核、归档建议都从 `asset_id` 和 sidecar 继续。

本次 10,000 个小文件的输出体积：`inventory.sqlite` 13.25 MB、`extract/` 19.28 MB、`analyze/` 38.83 MB、`assets/` 48.95 MB、`html/` 15.70 MB。小文件是元数据开销较高的场景；大 PDF、表格、OCR 图片或 LLM 分析会把瓶颈转移到解析器、OCR 或模型吞吐。

基于这次本机结果的保守估算：

| 规模 | 预期表现 |
| --- | --- |
| 10k 文件 | 本地纯文本冷启动约 1-2 分钟；之后 agent 查询通常低于 1 秒 |
| 100k 文件 | dry-run 扫描大约几十秒；完整直接文本提取和规则分析约 15-25 分钟；建议用 `run` 分块 |
| 500k+ 文件 | 冷启动提取可能进入小时级；需要更严格的 roots、metadata-only、exclude 和分批策略 |
| 100 万文件级 | 适合先做 metadata/inventory 分层治理；完整正文提取、HTML 和 JSONL 索引会成为主要上限 |

当前上限和注意事项：

- `anyfile-wiki run` 支持 `--max-scan-entries`、`--extract-limit`、`--analyze-limit`，大目录应分块跑，避免一次性占用太久。
- 直接文本提取对单个源文件有 25 MB 保护上限；更大的文档应通过专门 parser、分批策略或后续优化处理。
- OCR、MarkItDown、local-LLM、cloud-LLM 的耗时不在上表内，它们通常比 scan 和 rules 分析慢很多。
- 10k-100k 级别适合当前 JSONL/SQLite 结构；再往上需要更关注 HTML 分页、索引文件体积、查询加载成本和未来的 SQLite FTS/批量提取优化。

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
- 提供 `anyfile-wiki agent-init`，生成 agent 可读的 profile、隐私策略、扫描目录、索引理解模式和空闲扫描配置。
- 提供 `anyfile-wiki query`，直接查询已有资产索引和 sidecar，不重新扫描原文件。
- 提供 `anyfile-wiki usage-event`，记录 agent 对资产的选择、打开、引用和搜索命中。
- 提供 `anyfile-wiki privacy`、`anyfile-wiki status`、`anyfile-wiki list`、`anyfile-wiki show`、`anyfile-wiki roots`、`anyfile-wiki tags`。
- 提供 `anyfile-wiki run`，用 `run-state.json` 分阶段推进扫描、提取、分析、复核页、最终资产索引和 HTML 资产页，支持断点续跑。
- 提供 `anyfile-wiki extract`，只对策略允许读取的文件执行提取。
- 提供 `anyfile-wiki extracts`，查看持久化的提取结果和状态统计。
- 支持增量提取：默认跳过源文件未变化的成功项，支持 `--force` 和 `--retry-failed`。
- 提供 `anyfile-wiki analyze`，基于已提取文本生成本地规则版摘要、标签和知识索引；支持 `--method codex-mock`、`--method local-llm` 和 `--method cloud-llm`。
- 真实 LLM/API 只读取隐私门控后的提取文本；云端模式还必须显式配置授权路径和风险确认。
- 面向 Codex / OpenClaw / Hermes 的宿主 agent 场景，提供 `agent-task --kind semantic-index` / `semantic-review` + `agent-review-apply`：不需要 AnyFile Wiki 配置 API key，由宿主 agent 读取已授权提取文本并写回语义结果。
- 提供 `anyfile-wiki review`，生成 Markdown、JSONL 和静态 fallback `human-review.html` 人工复核页；CLI 和 profile 会把 `review-server` 标为首选入口。
- 提供 `anyfile-wiki review-server`，启动本地 `127.0.0.1` 批复服务，页面可直接提交批复并写入本地文件；日常推荐优先使用服务模式。
- 复核页里的“Agent 大模型复核”只会排队给当前宿主 agent 读取本地已提取文本，不会生成云端 LLM 授权候选，也不要求 `configs/llm.yaml`。
- 提供 `anyfile-wiki decisions`，读取人类从 HTML 页面导出的 `review-decisions.jsonl`，并生成摘要、`next-actions.jsonl` 和 `decision-plan.md`。
- 提供 `anyfile-wiki assets`，把分析索引、人工批复和 `next-actions.jsonl` 合并为最终 `asset-index.jsonl`，并刷新资产浏览 HTML；默认同步生成资产 sidecar 索引。
- 提供 `anyfile-wiki sidecars`，可对已有 `asset-index.jsonl` 回填/刷新 `asset-signature.jsonl`、`collection-index.jsonl`、`asset-score.jsonl` 和统计报告。
- 提供 `anyfile-wiki archive-plan`，基于 sidecar 评分生成疑似重复、归档和删除复核候选 manifest；只输出计划，不执行文件操作。
- 提供 `anyfile-wiki html`，把 `knowledge-index.jsonl` 转成本地可打开的中英双语资产浏览页，支持标签树、分页、筛选、搜索和文件详情。
- 支持直接文本提取和 Excel 轻量摘要；MarkItDown 和 RapidOCR 是可选解析依赖。

## 快速开始

MVP4 开始推荐先安装 Agent Skill，让 Codex / OpenClaw / Hermes 这类 agent 负责读取配置、引导初始化、继续扫描和查询索引。

```powershell
python scripts/install_agent_skill.py --editable --extras parse,ocr
```

然后对 agent 说：

```text
请用 AnyFile Wiki 初始化我的扫描目录，并解释隐私配置。
继续 AnyFile Wiki 日常扫描。
帮我找一下预算测算相关资料在哪里。
```

### 首次配置向导

安装后不要立刻扫描。第一次应该让 agent 引导你完成配置：

> 给 agent 的强提醒：首次配置是一个引导流程，不是只问扫描目录。用户给出目录后，也要继续确认敏感目录、metadata-only/no-embedding 目录、索引理解模式，并先展示 dry-run 报告。

1. agent 运行 `anyfile-wiki agent-init --profile configs/agent-profile.yaml --out data/daily-run`，只生成或补齐配置，不扫描正文。
2. agent 读取 `configs/privacy.yaml`、`configs/roots.yaml` 和 `configs/agent-profile.yaml` 里的 `setup_questions`。
3. agent 询问你哪些目录敏感、第一批扫描哪些目录、哪些目录只登记元数据。
4. agent 询问索引理解模式：`rules` 快速规则、`agent-llm` 宿主 agent 语义理解、`local-llm` 本地模型、`cloud-llm` 云端 API。
5. 选择 `agent-llm` 时不需要额外 API key；AnyFile Wiki 只生成隐私门控后的任务清单，宿主 agent 读取已提取文本并写回摘要。
6. 选择 `cloud-llm` 时必须配置 `configs/llm.yaml` 的 `allowed_paths` 和 `risk_acknowledged`。
7. agent 根据你的回答修改 `privacy.yaml`、`roots.yaml` 和 `agent-profile.yaml`，已有配置不会被静默覆盖。
8. agent 先做 dry-run 扫描，给出 scan-plan 和访问统计；你确认后才继续提取和分析。

详细 CLI 只放在 [CLI 参考](docs/cli-reference.md)，避免 README 变成命令手册。`anyfile-wiki scan` 始终是安全的 dry-run：只生成访问计划和 inventory，不读取正文、不做摘要、不写入向量库。

## 项目结构

```text
configs/
  schedule.example.yaml      空闲扫描配置示例
  roots.example.yaml         推荐扫描目录示例
  tags.example.yaml          标签体系示例
  llm.example.yaml           LLM 和云端读取策略示例
  excludes.default.yaml      默认排除规则
  privacy.example.yaml       用户隐私策略示例
docs/
  agent-skill.md             Agent Skill 和跨 agent 适配说明
  cli-reference.md           开发和调试用 CLI 参考
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
skills/
  anyfile-wiki/SKILL.md      Codex Skill 入口
scripts/
  install_agent_skill.py     一行安装包和 Skill 的脚本
src/anyfile_wiki/
  agent.py                   Agent profile、查询和使用事件入口
  policy.py                  隐私策略引擎
  scan.py                    dry-run 扫描器
  inventory.py               SQLite inventory
  report.py                  scan-plan 和 access-log 输出
  run_state.py               日常运行状态和断点续跑
  roots.py                   推荐扫描目录发现
  tags.py                    标签体系解析
  parse.py                   隐私门控后的提取管线
  analyze.py                 本地规则版摘要、标签和知识索引
  agent_review.py            宿主 agent 语义索引/复核任务与写回协议
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
- MVP4：agent skill / MCP 集成；当前已实现 Codex Skill、agent 初始化、索引查询、使用事件入口，以及宿主 agent 语义索引/复核写回协议。
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
- Agent 初始化、索引查询、使用事件、Skill 安装入口和宿主 agent 语义索引写回。
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
- [Agent Skill 说明](docs/agent-skill.md)
- [CLI 参考](docs/cli-reference.md)
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
