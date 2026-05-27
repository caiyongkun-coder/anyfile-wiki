# 个人文件知识库项目启动文档

版本：v0.1  
日期：2026-05-26

## 1. 项目背景

个人电脑里会长期沉淀大量有价值文件：文档、PDF、表格、PPT、笔记、代码、图片、下载资料、压缩包、聊天导出、网页资料，以及各类应用里的个人数据。

这些文件常见的问题是：

- 文件名随手起，后面很难再搜到。
- 文件夹结构随着时间漂移，旧资料变成信息孤岛。
- 很多文件只用过一次，之后就沉淀下来。
- 用户记得“好像写过/看过/保存过”，但不记得路径和文件名。
- 清理文件时很难判断哪些有价值、哪些可以归档、哪些可以删除。

现在的本地 agent，例如 OpenClaw、Hermes、Codex 等，已经具备读取文件、总结内容、打标签、生成索引、维护知识库的能力。如果这些 agent 在闲置时自动整理本地个人文件，就可以把沉淀文件变成可检索、可追问、可复用的个人知识库。

本项目的目标不是简单做一个“本地文件搜索工具”，而是做一个 **本地文件记忆层**：让电脑里的个人文件持续变成 agent 可读取、可理解、可行动的知识资产。

## 2. 项目愿景

构建一个本地优先的个人文件知识库系统，由 agent 在空闲时持续维护，并通过 skill、MCP、CLI、索引文件或 wiki 文件提供给 OpenClaw、Hermes、Codex 等 agent 快速使用。

系统应能做到：

- 扫描个人电脑中的文件。
- 排除系统文件、软件安装目录、缓存、临时文件等噪声。
- 允许用户配置哪些路径、文件类型、应用数据或敏感内容绝对不读取、不解析、不索引。
- 本地解析常见文件类型。
- 对文件内容进行摘要、标签、主题识别和价值判断。
- 支持自然语言找文件、问内容、了解文件、发现重复文件、归档建议和删除建议。
- 支持人类通过标签、层级、主题、项目、时间、文件类型逐级浏览知识库，清楚知道自己拥有哪些资料。
- 核心数据全部保存在本地。
- 以 agent 友好的方式暴露知识库能力。

### 2.1 当前落地流程

当前实现应围绕 agent 生命周期推进，而不是只围绕一次性 CLI 命令。

初始化时：

1. OpenClaw、Hermes、Codex 等 agent 读取项目文档和依赖，协助完成本地安装部署。
2. Agent 读取默认配置，并协助人类理解和调整个性化配置，包括扫描目录、隐私策略、标签体系和 LLM 策略。
3. 配置不是一次性动作，后续可以随时由人类和 agent 重新审阅、调整和 dry-run。

初始化后和日常运行期间：

1. Agent 在空闲时按配置扫描路径，并保存运行进度，避免单次任务扫不完时下次从头开始。
2. Agent 提取和分析允许处理的文件，生成数据资产浏览 HTML 和需要人类复核打标的批复 HTML。
3. 人类在批复 HTML 中做确认、忽略、稍后处理、允许本地 LLM、手工标签修正等决策。
4. 静态批复页把结果保存为 `review-decisions.jsonl`；agent 读取这个文件后继续后续流程。
5. 已处理的数据输出为 agent 可读的 JSONL、Markdown 或后续 wiki/MCP 知识接口。
6. 从这里开始，agent 才能持续管理本地数据资产，例如检索、解释、复核、归档建议和安全清理建议。

更完整的流程说明见：[Agent 生命周期与日常运行流程](docs/agent-lifecycle.md)。

## 3. 项目定位

本项目不是传统笔记软件，也不是普通 RAG 聊天工具。

更准确的定位是：

> 面向个人电脑文件系统的本地知识整理与 agent 记忆层。

它关注的是“已经在电脑里的文件”，而不是要求用户主动写笔记、上传文档、维护资料库。

## 4. 初始范围

### 4.1 平台范围

长期目标是跨平台兼容：

- Windows
- macOS
- Linux

早期优先 Windows，原因是当前主要使用环境是 Windows。

第一阶段建议：

- Windows x64 优先。
- 核心数据结构保持跨平台。
- 文件路径、权限、隐藏目录、应用数据目录等逻辑做 OS 抽象，避免后续重写。

### 4.2 文件范围

长期目标是覆盖全盘个人文件，但不能粗暴地把整个系统盘都当成知识库。

第一版建议优先扫描高价值个人目录：

- Desktop
- Documents
- Downloads
- OneDrive / Dropbox / Google Drive 等同步目录
- 用户指定的项目目录
- 用户创建的笔记、资料、媒体目录
- 具有个人数据价值的应用数据目录

默认排除：

- Windows 系统目录
- Program Files
- 软件安装目录
- 包管理缓存
- `node_modules`
- 虚拟环境
- 编译产物
- 浏览器缓存
- 安装包
- 临时文件
- 大型无文本二进制文件
- 备份和更新缓存

### 4.3 隐私访问范围

扫描和索引必须受用户配置控制。系统不能只依赖默认排除规则，而要提供明确的隐私访问策略。

用户应能配置：

- 永久禁止读取的路径，例如私密目录、密码库、财务目录、医疗资料、证件资料。
- 只记录元数据但不读取内容的路径。
- 允许扫描但不进入摘要/embedding 的路径。
- 禁止读取的文件类型，例如 `.key`、`.pem`、`.env`、密码库、浏览器 cookie、钱包文件等。
- 应用数据的读取范围，例如只读取导出的聊天记录，不直接读取应用内部数据库。
- 临时会话级排除规则，例如“这次扫描先不要读 Downloads”。

访问策略应支持 dry-run：在真正读取文件内容前，先生成“将会读取什么、跳过什么、为什么”的报告。

策略优先级建议：

1. `deny` 永远优先，命中后不读取、不解析、不索引。
2. `metadata_only` 只记录路径、大小、时间、类型等元数据，不读取正文。
3. `no_embedding` 可以读取摘要，但不进入向量索引。
4. `allow` 只对明确允许的路径或类型生效，不能覆盖 `deny`。

示例配置：

```yaml
deny:
  paths:
    - "C:/Users/<user>/Documents/Private"
    - "C:/Users/<user>/.ssh"
  extensions:
    - ".pem"
    - ".key"
    - ".env"

metadata_only:
  paths:
    - "C:/Users/<user>/Documents/Finance"

no_embedding:
  paths:
    - "C:/Users/<user>/Documents/Contracts"

allow:
  paths:
    - "C:/Users/<user>/Desktop"
    - "C:/Users/<user>/Documents"
```

### 4.4 文件类型

第一版优先支持：

- 文本：`.txt`、`.md`、`.rst`、`.log`
- Office：`.docx`、`.pptx`、`.xlsx`
- PDF：优先支持有文本层的 PDF，扫描版 PDF 后续通过 OCR 支持
- Web / 数据：`.html`、`.csv`、`.json`、`.xml`、`.yaml`
- 代码文件

后续扩展：

- 图片 OCR
- 音频转录
- 视频字幕/转录
- 邮件
- 聊天记录
- 浏览器书签/历史
- 应用内个人数据

系统需要允许用户自定义扩展名和解析器。

## 5. 核心使用场景

### 5.1 找文件

用户记得文件的大概内容、项目、人物、时间、主题或一句话，但不记得文件名和路径。

例子：

> 找一下我以前写过的关于“本地知识库”和“agent 空闲时间整理文件”的资料。

### 5.2 问内容

用户直接跨本地文件提问。

例子：

> 我以前关于删除旧文件有什么原则？

### 5.3 快速了解文件

用户不想打开文件，只想知道它是什么、值不值得保留。

例子：

> 总结这个旧 PDF，判断它还有没有价值。

### 5.4 自动打标签和分类

系统为文件生成主题、项目、人物、类型、价值、敏感性和建议动作。

示例标签：

- `project:personal-kb`
- `type:contract`
- `topic:local-ai`
- `action:archive-candidate`
- `sensitivity:private`

### 5.5 人类浏览和盘点

用户不一定每次都想搜索或提问，也可能想像逛目录、逛标签库、逛 wiki 一样，逐层查看自己有什么资料。

系统需要提供人类可读的浏览视图：

- 按标签逐级展开。
- 按主题、项目、人物、时间、文件类型浏览。
- 每个分类下显示文件数量、摘要和代表性文件。
- 支持从总览进入分类，再进入文件详情。
- 支持看到“未分类”“需要复核”“高价值”“可归档”等状态。

例子：

> 我想点开“本地 AI / 知识库 / 文件管理”这条标签路径，看看有哪些文档、笔记、PDF 和项目文件。

### 5.6 文件归档和删除建议

系统不自动删除文件，只给出建议。

建议状态包括：

- 保留
- 归档
- 需要复核
- 疑似重复
- 低价值
- 安装包/缓存
- 删除候选

删除动作必须经过用户明确确认。更安全的方式是先移动到隔离区或回收站，并生成 manifest 记录。

### 5.7 Agent 检索个人知识

OpenClaw、Hermes、Codex 等 agent 在执行任务前，可以从个人文件知识库中检索相关上下文。

例子：

> 在修改这个项目之前，先检索我的个人知识库，看看以前有没有关于类似设计的笔记。

## 6. 调研结论

目前已经有不少开源项目覆盖了局部能力。建议不要从零做完整 RAG 底座，而是做一个“个人文件知识库 skill / 编排层”，复用成熟组件。

### 6.1 GNO

GNO 是目前最接近本项目需求的底座。它是本地知识引擎，支持本地搜索、混合检索、引用回答、Web UI、REST API、MCP、SDK、后台 daemon 和 agent skills。它明确支持 Codex 和 OpenClaw 的 skill / MCP 集成。

适合作为：

- 检索和索引底座
- agent-facing skill
- MCP server
- 本地搜索和问答入口

参考：

- [GNO GitHub](https://github.com/gmickel/gno)
- [GNO MCP 文档](https://gno.sh/docs/mcp)
- [GNO Agent Skills 文档](https://gno.sh/docs/skills)

### 6.2 OpenKB

OpenKB 的思路是把原始文档编译成结构化、互相链接的 wiki。这个方向很适合本项目的长期目标，因为个人知识库不应该只在每次查询时临时 RAG，而应该把重要内容沉淀成摘要、概念页、标签和交叉引用。

适合作为：

- wiki 生成思路参考
- “编译型知识库”设计参考
- 高价值文件知识沉淀模块参考

参考：

- [OpenKB GitHub](https://github.com/VectifyAI/OpenKB)

### 6.3 Docling

Docling 是强文档解析层，支持 PDF、DOCX、PPTX、XLSX、HTML、图片、音频、OCR、Markdown 导出、本地执行和 MCP server。

适合作为：

- 高质量文档解析器
- PDF 版面、表格、OCR 管线
- 复杂文件的后备解析方案

参考：

- [Docling GitHub](https://github.com/docling-project/docling)

### 6.4 MarkItDown

MarkItDown 可以把多种格式转换成 Markdown，适合 LLM 和文本分析流程。它支持 PDF、PowerPoint、Word、Excel、图片 OCR、音频元数据/转录、HTML、CSV、JSON、XML、ZIP、EPub 等。

适合作为：

- 第一版轻量解析器
- Markdown 标准化层
- 本地提取内容的简单路径

参考：

- [MarkItDown GitHub / MCP Registry](https://github.com/mcp/microsoft/markitdown)

### 6.5 其他参考项目

- [Khoj](https://docs.khoj.dev/)：成熟的开源 personal AI / second brain。
- [AnythingLLM](https://github.com/mintplex-labs/anything-llm)：隐私优先的文档问答和 agent 应用。
- [PrivateGPT](https://github.com/zylon-ai/private-gpt)：本地私有文档摄取和 RAG API 参考。
- [Open Semantic Search](https://github.com/opensemanticsearch/open-semantic-search)：搜索、OCR、元数据、NER、知识图谱能力很完整，但 GPL-3.0 许可证会影响复用策略。

## 7. 推荐架构

### 7.1 Scanner：文件发现层

负责发现候选个人文件。

职责：

- 枚举磁盘和用户目录。
- 应用 OS 感知的 include / exclude 规则。
- 在读取文件内容前应用用户隐私访问策略。
- 识别文件类型和 MIME。
- 记录文件大小、时间戳、路径、hash、来源。
- 跳过已知噪声目录。
- 增量检测新增、移动、删除和修改。
- 支持 dry-run 扫描报告，展示允许读取、仅记录元数据、完全跳过的文件范围。

输出：

- `inventory.sqlite`
- 扫描报告
- 候选文件列表

### 7.2 Extractor：文件解析层

负责把文件转换为文本、Markdown 或结构化 chunk。

建议顺序：

1. 对文本、代码、Markdown 直接读取。
2. 常见 Office、PDF、Web、数据文件优先用 MarkItDown。
3. 复杂 PDF、扫描版 PDF、表格、图片、OCR、版面敏感文件再用 Docling。
4. 对应用数据使用自定义解析器。

输出：

- 提取后的 Markdown / 文本
- 元数据
- 解析错误
- parser 来源和版本

### 7.3 Knowledge Store：知识存储层

负责保存机器可读和人类可读的知识资产。

建议产物：

- `inventory.sqlite`：文件元数据和生命周期状态
- `chunks.sqlite` 或向量后端：检索 chunk
- `summaries/`：每个文件的 Markdown 摘要
- `wiki/`：生成的概念页和交叉链接
- `tags.jsonl`：标签记录
- `actions.jsonl`：归档、删除、复核建议

### 7.4 Retrieval：检索层

第一版建议尽量复用 GNO。

能力：

- 精确搜索
- 语义搜索
- 混合搜索
- 带引用的检索结果
- 根据 URI / 路径读取上下文
- 后续支持 graph / backlink / related file

### 7.5 Human Browse Interface：人类浏览层

向用户提供可视化、可点击、可逐级展开的知识库视图。这个界面不只是搜索框，而是帮助用户盘点自己的数字资产。

核心视图：

- 标签树：按主题、项目、人物、类型、动作状态逐级展开。
- 层级视图：保留原始文件夹层级，同时叠加系统生成的知识分类。
- 主题页：展示某个主题下的摘要、相关文件、时间分布和子主题。
- 文件详情页：展示文件摘要、标签、来源路径、相关文件、建议动作和解析状态。
- 盘点视图：展示未分类文件、高价值文件、长期未用文件、归档候选、删除候选、重复候选。

输出形式可以先从静态 Markdown / HTML 开始，后续再做本地 Web UI 或桌面 UI。

### 7.6 Agent Interface：Agent 接口层

向 OpenClaw、Hermes、Codex 等 agent 暴露能力。

接口形式：

- Skill instructions
- MCP server
- CLI commands
- Markdown / wiki 文件，作为所有 agent 都能读取的兜底格式

建议命令：

- `pfkb status`
- `pfkb scan`
- `pfkb index`
- `pfkb search "<query>"`
- `pfkb ask "<question>"`
- `pfkb summarize <path-or-id>`
- `pfkb tags <path-or-id>`
- `pfkb review-deletes`
- `pfkb archive-plan`
- `pfkb explain-file <path-or-id>`

## 8. 数据模型草案

### 8.1 File Record

字段：

- `id`
- `path`
- `normalized_path`
- `drive`
- `size_bytes`
- `mtime`
- `ctime`
- `hash`
- `mime`
- `extension`
- `source_kind`
- `is_personal_candidate`
- `is_excluded`
- `exclude_reason`
- `access_policy`
- `policy_source`
- `is_read_allowed`
- `is_extract_allowed`
- `metadata_only`
- `last_seen_at`
- `last_indexed_at`
- `lifecycle_state`
- `sensitivity`

### 8.2 Extract Record

字段：

- `file_id`
- `parser`
- `parser_version`
- `status`
- `content_hash`
- `text_path`
- `markdown_path`
- `error`
- `created_at`

### 8.3 Summary Record

字段：

- `file_id`
- `short_summary`
- `long_summary`
- `topics`
- `entities`
- `tags`
- `suggested_actions`
- `confidence`
- `created_at`

### 8.4 Browse / Taxonomy Record

用于支持人类逐级浏览知识库。

字段：

- `id`
- `kind`
- `name`
- `parent_id`
- `path`
- `description`
- `file_count`
- `representative_file_ids`
- `related_tags`
- `created_at`
- `updated_at`

### 8.5 Action Record

字段：

- `file_id`
- `action`
- `reason`
- `risk`
- `requires_user_approval`
- `created_at`
- `resolved_at`

## 9. 隐私与安全原则

- 默认本地优先。
- 核心流程不把文件内容发送到云端模型。
- 任何云模型或远程服务都必须显式 opt-in。
- 用户必须能配置禁止读取、仅记录元数据、禁止索引、禁止摘要的路径和文件类型。
- 隐私访问策略必须在内容读取前生效，而不是解析后再过滤。
- 第一次全盘扫描前应先执行 dry-run，生成访问计划供用户确认。
- 不自动删除文件。
- 归档/删除动作需要可回滚 manifest。
- 敏感目录和应用数据要保守处理。
- Agent 写操作默认关闭。
- 文件访问、索引、解析、删除建议都要可审计。

建议配置文件：

- `privacy.yaml`：用户显式配置的隐私访问策略。
- `excludes.yaml`：默认系统噪声和危险文件排除规则。
- `scan-plan.md`：dry-run 生成的人类可读扫描计划。
- `access-log.jsonl`：实际访问、跳过、解析失败、策略命中的审计日志。

## 10. MVP 计划

### MVP 0：项目骨架和扫描验证

交付物：

- 项目目录结构
- Windows 扫描器原型
- 默认 include / exclude 规则
- 用户可配置的 `privacy.yaml`
- dry-run 扫描计划
- SQLite inventory
- 示例扫描报告

目标：

- 验证可以发现个人文件，同时避免被系统文件噪声淹没。
- 验证用户能清楚控制哪些文件不会被读取。

### MVP 1：本地索引和 Agent 搜索

交付物：

- 扫描结果接入 GNO collections 或等价索引
- 支持常见文档类型索引
- 支持 Codex / OpenClaw 风格 skill
- 支持显式搜索和上下文读取命令

目标：

- Agent 能搜索本地个人文件，并取回有用上下文。

### MVP 2：摘要和标签

交付物：

- 每个文件的摘要
- 主题、实体、标签提取
- 标签树和分类层级索引
- 文件生命周期分类
- 可搜索摘要库

目标：

- 旧文件不用打开，也能知道是什么、有没有价值。
- 用户可以按标签、主题、项目、文件类型逐级浏览资料。

### MVP 3：清理和归档助手

交付物：

- 重复文件候选检测
- 归档候选识别
- 安装包/缓存/低价值文件识别
- 人工复核报告
- 隔离区/回收站计划和 manifest

目标：

- 帮助用户安全减少文件混乱，不误删有价值资料。

### MVP 4：Wiki / 知识编译

交付物：

- 生成概念页
- 文件、主题、项目、人物之间的交叉链接
- 项目页、人物页、主题页
- 人类可点击浏览的 wiki / HTML / Markdown 导航页
- agent 可直接读取的 wiki 输出

目标：

- 把文件归档转化为会增长的个人知识体系。
- 用户不用提问，也能通过浏览界面清楚知道自己有什么。

## 11. 主要风险

### 11.1 文件噪声

全盘扫描会产生大量噪声。Scanner 必须保守，并能解释为什么排除某些目录或文件。

### 11.2 性能

全量索引可能很慢。需要增量扫描、按需 hash、文件大小限制、低优先级后台任务和空闲调度。

### 11.3 本地模型效果

全本地摘要和标签质量可能弱于云模型。第一版可以先保证检索有用，再逐步提升总结质量。

### 11.4 敏感数据

个人文件中可能包含证件、合同、财务、医疗、账号、聊天记录。系统必须把隐私边界放在核心设计里。

### 11.5 解析失败

Office、PDF、OCR、压缩包、损坏文件都会失败。失败不能静默吞掉，需要记录并展示。

### 11.6 删除风险

删除建议是高风险能力。第一版只做建议和复核报告，不做自动删除。

## 12. 待确认问题

- 哪些应用数据目录应被视为“个人文件”？
- 浏览器历史、书签、下载记录是否进入第一版？
- 聊天记录应该按文档、时间线还是记忆记录处理？
- 面向低配 Windows 机器，推荐哪套本地 embedding / LLM？
- 第一版是强依赖 GNO，还是把 GNO 作为可选 backend？
- 摘要文件应该集中存放，还是靠近源文件存放，还是两者都支持？
- 加密文件、密码保护文件如何处理？
- 最小可用 UI 是 CLI、Web UI，还是 agent-only？
- 隐私访问策略的默认模板应该有多保守？
- 是否需要提供“一键私密模式”，默认只扫描明确允许的目录？

## 13. 初始技术建议

第一阶段做 Windows-first、本地-only 原型，不试图替代现有知识库产品。

建议路径：

1. 自己实现 scanner 和 inventory database。
2. 轻量解析优先使用 MarkItDown。
3. 复杂文档在后续接入 Docling。
4. 第一版检索和 agent 集成尽量复用 GNO。
5. 摘要、标签、清理建议输出为 Markdown / JSONL / SQLite 等持久 artifact。
6. 编写 OpenClaw / Hermes / Codex skill，让 agent 知道何时调用知识库。

项目的独特价值不是“又一个 RAG 应用”，而是：

> 一个本地 agent 工作流，持续把用户真实文件系统转化为可搜索、可复核、可复用的个人知识资产。

## 14. 下一步建议

下一步可以进入 MVP 0：

1. 确定项目目录结构。
2. 编写 Windows 文件扫描器。
3. 建立默认排除规则和用户 `privacy.yaml`。
4. 先输出 dry-run 扫描计划，确认哪些文件会读取、哪些只记录元数据、哪些完全跳过。
5. 生成 `inventory.sqlite`。
6. 输出第一份扫描统计报告。
7. 用少量真实目录验证噪声比例、候选文件质量和隐私策略命中情况。

MVP 0 完成后，再决定是直接接入 GNO，还是先实现一个最小本地索引。
