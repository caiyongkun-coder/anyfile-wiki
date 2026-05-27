# MVP0 使用说明

MVP0 只做隐私优先的 dry-run 扫描：遍历路径、应用访问策略、记录元数据和审计结果，不读取文件正文，不解析正文，也不写入全文索引或向量索引。

## 运行 CLI 前

推荐新贡献者先在仓库根目录执行 editable install。项目采用 `src/` 布局，安装后 `python -m pfkb ...` 才能稳定找到包：

```powershell
python -m pip install -e .[dev]
```

如果暂时不安装包，只从源码树运行命令，请先在当前 PowerShell 会话设置 `PYTHONPATH`：

```powershell
$env:PYTHONPATH = 'src'
python -m pfkb analyze --help
```

未安装 editable 包且未设置 `PYTHONPATH` 时，`python -m pfkb ...` 可能报 `No module named pfkb`。

## 准备隐私策略

先从示例策略复制一份本地配置：

```powershell
if (-not (Test-Path configs/privacy.yaml)) {
    Copy-Item configs/privacy.example.yaml configs/privacy.yaml
}
```

如果 `configs/privacy.yaml` 已经存在，不要直接覆盖。先打开现有文件确认本地规则，再决定是否手动合并 `configs/privacy.example.yaml` 中的新增项。

建议先把高敏感内容加入 `deny` 或 `metadata_only`，例如密钥、密码库、财务、医疗、证件、浏览器数据目录；再把低风险、希望纳入知识库的目录加入 `allow`。

## 先扫描一个小目录

第一次不要直接扫描整个 `Documents` 或用户目录。可以先准备一个很小的试扫目录：

```powershell
New-Item -ItemType Directory -Force "$env:TEMP\pfkb-mvp0-smoke" | Out-Null
"hello from pfkb" | Set-Content -Encoding UTF8 "$env:TEMP\pfkb-mvp0-smoke\note.txt"
python -m pfkb scan "$env:TEMP\pfkb-mvp0-smoke" --privacy configs/privacy.yaml --out data/smoke --max-entries 50
```

`python -m pfkb scan` 在 MVP0 中就是 dry-run 扫描。`--max-entries` 用来限制最多记录多少个条目，适合先验证策略命中、输出文件和 inventory 结构。

确认试扫结果符合预期后，再把扫描根目录换成更大的目标，例如：

```powershell
python -m pfkb scan "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/first-scan --max-entries 500
```

## 查看扫描产物

扫描完成后，输出目录中会有三个主要产物。

`scan-plan.md` 是给人看的 dry-run 计划，汇总各策略命中数量、来源和每个条目的处理原因：

```powershell
Get-Content -Encoding UTF8 data/smoke/scan-plan.md
```

`access-log.jsonl` 是逐行 JSON 审计日志，适合抽样检查或后续导入工具：

```powershell
Get-Content -Encoding UTF8 data/smoke/access-log.jsonl | Select-Object -First 5
Get-Content -Encoding UTF8 data/smoke/access-log.jsonl | Select-Object -First 3 | ConvertFrom-Json
```

`inventory.sqlite` 是 SQLite 盘点库。优先使用项目自带的状态命令查看策略计数：

```powershell
python -m pfkb status --inventory data/smoke/inventory.sqlite
```

如果本机安装了 `sqlite3` CLI，也可以直接查询：

```powershell
sqlite3 data/smoke/inventory.sqlite ".tables"
sqlite3 data/smoke/inventory.sqlite "select access_policy, count(*) from files group by access_policy;"
```

## 为什么 dry-run 不读取正文

dry-run 的目标是先回答“这个文件能不能碰”，而不是尽早提取内容。它只需要路径、文件名、扩展名、大小、修改时间等元数据，就能应用 `deny`、`metadata_only`、`no_embedding` 和 `allow` 策略。

不读取正文有几个原因：

- 避免在策略还没确认前触碰敏感内容。
- 避免为了摘要、OCR、全文 hash、预览或 embedding 而意外打开文件。
- 让用户先审查 `scan-plan.md` 和 `access-log.jsonl`，确认每个目录的处理动作和原因。
- 让真实扫描必须重新经过同一套策略，而不是因为 dry-run 通过就绕过隐私规则。

因此，MVP0 即使写入 `inventory.sqlite`，也只写入元数据和策略决策，不写入正文片段、摘要或向量。

## 下一阶段与 MarkItDown

下一阶段会接入 MarkItDown 作为文档正文解析能力，但解析入口必须放在隐私策略之后。也就是说，文件先经过默认排除规则和 `privacy.yaml` 判断：

- 命中 `deny`：不读取正文，不交给 MarkItDown。
- 命中 `metadata_only`：只保留元数据，不交给 MarkItDown。
- 命中 `no_embedding`：可以在后续阶段读取和解析正文，但不能写入 embedding/向量索引。
- 命中 `allow` 且未命中更高优先级规则：后续阶段才可以进入正文解析、摘要和索引流程。

MarkItDown 只负责“已经允许读取的文件怎么解析”，不能负责决定“哪些文件可以读取”。这个边界是 MVP0 隐私策略继续向后兼容的关键。
