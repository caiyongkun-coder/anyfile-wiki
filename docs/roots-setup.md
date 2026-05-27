# 推荐扫描目录配置说明

推荐扫描目录配置负责回答一个问题：初始化时应该先把哪些本机目录展示给用户选择。

它不等于读取授权。目录即使命中推荐列表，也必须继续通过 `configs/privacy.yaml` 和 `configs/excludes.default.yaml`，才能进入扫描、提取或索引流程。

## 当前文件

- `configs/roots.example.yaml`：推荐扫描入口模板，包含人类注释和 AI 可读说明。
- `configs/roots.yaml`：用户本机真实推荐目录配置，可由模板复制后修改。
- `src/pfkb/roots.py`：解析配置、解析本机路径、去重并输出候选目录。

## 给用户看的方式

列出当前机器上解析出来且存在的推荐目录：

```powershell
python -m pfkb roots
```

包含不存在或环境变量未设置的目录：

```powershell
python -m pfkb roots --include-missing
```

解释推荐目录配置本身：

```powershell
python -m pfkb roots --explain
```

## 给 agent / 初始化向导读取的方式

输出结构化 JSON：

```powershell
python -m pfkb roots --explain --json
```

这个 JSON 会包含：

- `purpose`：推荐扫描目录配置的目的。
- `setup_questions`：初始化时应该询问用户的问题。
- `selection_notes`：选择目录时的风险提醒。
- `roots`：每个候选目录的解析方式、风险等级、建议隐私策略、标签和解析后的本机路径。

## 配置模块

推荐目录使用独立模块 `configs/roots.example.yaml`，而不是塞进 `privacy.yaml`。原因是它们负责不同层级：

- `roots`：告诉用户“可以从哪里开始选”。
- `privacy`：决定“这个路径能不能读、能读到什么程度”。
- `excludes`：提供跨机器的保守默认排除规则。

后续 UI 或 agent 初始化流程可以先读 `roots`，让用户选择目录；再读 `privacy`，确认每个目录和敏感区域如何授权；最后执行 dry-run。
