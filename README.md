# PFKB：个人文件知识库

中文 | [English](README.en.md)

PFKB（Personal File Knowledge Base）是一个本地优先的个人文件知识库项目。它的目标是让 OpenClaw、Hermes、Codex 等本地 agent 在空闲时，安全地盘点个人电脑里的文件，把沉淀的文档、笔记、PDF、表格、代码和应用数据逐步整理成可搜索、可浏览、可复用的知识资产。

当前项目处于 MVP0：先解决“哪些文件可以碰、哪些绝对不能碰”的问题，再进入解析、摘要、标签、检索和知识编译。

## 为什么做这个项目

个人电脑里有大量有价值的文件，但它们常常因为文件名随意、目录混乱、长期不用而变成信息孤岛。传统文件搜索只能找到文件名或关键词，不能真正回答：

- 我到底保存过哪些资料？
- 哪些文件值得保留、归档、复用？
- 哪些旧文件可以安全清理？
- agent 在工作前能不能先读取我的本地知识上下文？
- 人类能不能像逛标签树、主题树、wiki 一样查看自己的数字资产？

PFKB 想做的是本地文件系统上的“知识治理层”，而不是又一个普通 RAG 聊天工具。

## 当前能力

- 隐私优先的 `privacy.yaml` 策略。
- `deny` 永远优先，命中后不读取、不解析、不索引。
- 支持 `metadata_only`：只记录元数据，不读取正文。
- 支持 `no_embedding`：允许后续读取/摘要，但禁止进入向量索引。
- 推荐扫描目录配置 `roots.example.yaml`，支持人类说明和 AI 可读初始化信息。
- 默认排除系统目录、开发噪声、危险扩展名、安装包、缓存和临时文件。
- dry-run 扫描只遍历路径和元数据，不读取文件正文。
- 输出 `scan-plan.md`、`access-log.jsonl` 和 `inventory.sqlite`。
- 提供 `pfkb privacy`、`pfkb status`、`pfkb list`、`pfkb show`、`pfkb roots`。
- 提供 `pfkb extract`，只对策略允许读取的文件执行提取。
- 提供 `pfkb extracts`，查看持久化的提取结果和状态统计。
- 支持增量提取：默认跳过源文件未变化的成功项，支持 `--force` 和 `--retry-failed`。
- 支持直接文本提取；MarkItDown 是可选解析依赖。

## 快速开始

```powershell
python -m pip install -e .[dev]

if (-not (Test-Path configs/privacy.yaml)) {
    Copy-Item configs/privacy.example.yaml configs/privacy.yaml
}

New-Item -ItemType Directory -Force "$env:TEMP\pfkb-mvp0-smoke" | Out-Null
"hello from pfkb" | Set-Content -Encoding UTF8 "$env:TEMP\pfkb-mvp0-smoke\note.txt"

python -m pfkb scan "$env:TEMP\pfkb-mvp0-smoke" --privacy configs/privacy.yaml --out data/smoke --max-entries 50
python -m pfkb status --inventory data/smoke/inventory.sqlite --sources
python -m pfkb list --inventory data/smoke/inventory.sqlite
python -m pfkb extract --inventory data/smoke/inventory.sqlite --out data/smoke-extract
python -m pfkb extracts --inventory data/smoke/inventory.sqlite --stats
```

`pfkb scan` 在 MVP0 中是 dry-run：它只生成访问计划和 inventory，不读取正文、不做摘要、不写入向量库。

## 常用命令

```powershell
# 查看推荐扫描目录
python -m pfkb roots --include-missing

# 解释推荐扫描目录配置
python -m pfkb roots --explain
python -m pfkb roots --explain --json

# 给用户或初始化 agent 解释隐私配置
python -m pfkb privacy --privacy configs/privacy.yaml
python -m pfkb privacy --privacy configs/privacy.yaml --json

# 扫描一个小目录
python -m pfkb scan "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/first-scan --max-entries 500

# 查看策略统计
python -m pfkb status --inventory data/first-scan/inventory.sqlite --sources

# 列出 inventory 记录
python -m pfkb list --inventory data/first-scan/inventory.sqlite --limit 20

# 只看 deny 记录
python -m pfkb list --inventory data/first-scan/inventory.sqlite --policy deny

# 查看单个路径的策略命中原因
python -m pfkb show "C:\path\to\file.md" --inventory data/first-scan/inventory.sqlite

# 对允许读取的文件执行提取
python -m pfkb extract --inventory data/first-scan/inventory.sqlite --out data/first-extract

# 强制重跑
python -m pfkb extract --inventory data/first-scan/inventory.sqlite --out data/first-extract --force

# 只重试最近一次失败或跳过的记录
python -m pfkb extract --inventory data/first-scan/inventory.sqlite --out data/first-extract --retry-failed

# 查看提取状态
python -m pfkb extracts --inventory data/first-scan/inventory.sqlite --stats
```

## 项目结构

```text
configs/
  roots.example.yaml         推荐扫描目录示例
  excludes.default.yaml      默认排除规则
  privacy.example.yaml       用户隐私策略示例
docs/
  configuration.md           配置说明
  privacy-setup.md           隐私配置初始化和 AI 可读说明
  roots-setup.md             推荐扫描目录初始化说明
  mvp0-usage.md              MVP0 使用说明
src/pfkb/
  policy.py                  隐私策略引擎
  scan.py                    dry-run 扫描器
  inventory.py               SQLite inventory
  report.py                  scan-plan 和 access-log 输出
  roots.py                   推荐扫描目录发现
  parse.py                   隐私门控后的提取管线
  cli.py                     CLI 入口
tests/
  *.py                       pytest 规格测试
```

## 路线图

- MVP0：隐私策略、默认排除、dry-run、inventory、扫描报告。
- MVP1：接入 MarkItDown，解析常见文档格式，并输出 extraction manifest。
- MVP2：本地摘要、标签、主题、项目和文件类型分类。
- MVP3：人类可浏览资产地图：标签树、主题页、项目页、文件详情页。
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

## 文档

- [项目启动文档](PROJECT_START.md)
- [开发计划与自研范围](DEVELOPMENT_PLAN.md)
- [配置说明](docs/configuration.md)
- [隐私配置初始化说明](docs/privacy-setup.md)
- [推荐扫描目录配置说明](docs/roots-setup.md)
- [MVP0 使用说明](docs/mvp0-usage.md)
- [MVP1 提取说明](docs/mvp1-extraction.md)

## 许可证

本项目使用 [Apache License 2.0](LICENSE)。
