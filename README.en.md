# AnyFile Wiki: turn scattered personal files into local knowledge assets for agents

[中文](README.md) | English

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-Apache--2.0-green)
![Privacy](https://img.shields.io/badge/Privacy-local--first-brightgreen)
![Status](https://img.shields.io/badge/Status-MVP4--ready-orange)

AnyFile Wiki is a local-first personal file knowledge governance layer for AI agents. Its goal is to let local agents such as OpenClaw, Hermes, Codex, and similar tools apply privacy rules first, then safely inventory personal files during idle time and gradually turn documents, notes, PDFs, spreadsheets, code, and app data into searchable, browsable, reusable knowledge assets.

It is not just another RAG chat app. AnyFile Wiki is a local file knowledge governance layer: it first decides what is safe to touch, then extracts, summarizes, tags, builds an asset index, creates virtual collections, and gives auditable archive/delete suggestions without moving, deleting, or renaming your original files.

## Why Install the Agent Skill First

AnyFile Wiki is designed primarily for agents. If you only install the Python package, an agent can call the CLI as a loose set of commands; after installing `skills/anyfile-wiki/SKILL.md`, the agent gets a stable operating protocol: explain privacy rules first, run a dry-run, build indexes in stages, then query indexes before reopening original files.

The Agent Skill does not bypass safety rules. It constrains how agents use them, so the workflow becomes more stable, more context-efficient, and more auditable.

| Workflow area | Agent without the Skill | Agent with the Skill |
| --- | --- | --- |
| First setup | May only ask “which directory should I scan?” and miss sensitive paths, metadata-only roots, or no-embedding rules | Must guide `agent-init`, privacy questions, scan roots, analysis mode, and dry-run confirmation |
| Privacy boundary | Depends on temporary prompt memory and may confuse “can see path” with “can read body” | Reads `privacy.yaml` / `agent-profile.yaml` first and follows `deny > metadata_only > no_embedding > allow` |
| Scan and resume | May rewalk directories for every task and has weak recovery after interruption | Uses `run-state.json`, staged `run`, and incremental extraction for idle-time progress |
| Retrieval | Often uses `rg`, shell traversal, or direct file opens; good for one-off search but not reusable | Queries `asset-index.jsonl`, sidecars, and HTML indexes first, then opens originals only when needed |
| Context cost | Can flood context with raw text, long file lists, or command output | Usually returns top-N asset records, summaries, tags, asset IDs, and review state |
| Human review | Needs ad hoc explanations for uncertain files | Uses `human-review.html`, `review-server`, and `next-actions.jsonl` as a writeback loop |
| Long-term optimization | Has little memory of which files were searched, opened, or cited | `usage-event` and `asset-score` record usage signals for better ranking and archive suggestions |

## Safest First Test

Do not start by scanning your whole machine or a sensitive directory. Create a small folder with synthetic or non-sensitive files first, then run a dry-run:

```powershell
anyfile-wiki scan .\demo-files\input --privacy .\demo-files\demo_privacy.yaml --out .\demo-files\out --max-entries 50
```

`anyfile-wiki scan` is a dry-run: it writes an access plan, audit log, and inventory, but it does not read file bodies, summarize files, or write vectors.

If you share feedback, please do not upload personal files, sensitive paths, secrets, chat exports, or screenshots containing private filenames. The most useful reports include OS, Python version, redacted commands, redacted output, a synthetic sample folder shape, and the exact point where the privacy boundary felt unclear.

## One-Minute Overview

```text
Your real files stay exactly where they are
        |
Privacy policy decides what can be read, metadata-only, or fully denied
        |
Local extraction and analysis produce asset-index.jsonl
        |
Sidecar indexes add virtual collections, signatures, usage feedback, and archive suggestions
        |
Agents find assets through stable asset_id values, while humans browse and review HTML pages
```

Core promises:

- Never move, delete, or rename original files.
- Local-first by default; cloud LLM access requires explicit allowed paths and risk acknowledgement.
- `deny` privacy rules always win: no reading, extraction, indexing, or embedding.
- Archive/delete actions are suggestions only, never automatic operations.

## What You Get

After a run, agents can read these structured files first:

```text
asset-index.jsonl              Main asset index: path, summary, tags, analysis result
asset-signature.jsonl          File-name normalization, mtime/size, extracted-text hash
collection-index.jsonl         Virtual collections and virtual directories
asset-usage-events.jsonl       Append-only event ledger for later search/open/citation usage
asset-score.jsonl              Usage, retention, archive, and delete-risk scores
knowledge-index.html           Local asset browser for humans
human-review.html              Human review and approval page
```

This lets an agent answer:

- What material do I have, and roughly what is it about?
- Where is a file, and which version looks canonical?
- Which files look like history, attachments, batches, or duplicate candidates?
- Which files need human review?
- Which files may be archived, and which should never be deleted?

## Performance and Scale Limits

These numbers are for agent workload planning, not a hardware-independent guarantee. The benchmark used locally generated synthetic `.txt` / `.md` files with no personal data under `.tmp_pytest/readme_benchmark`. Test environment: Windows 11, Python 3.12.7, local SSD, command entry point `python -m anyfile_wiki`.

| Files | Synthetic corpus | raw `rg budget` | `scan` dry-run | `extract` + `analyze` + `review` + `assets/html` | Cold full pipeline | Indexed `query` average |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 1.35 MB | 0.22s | 0.36s | 6.31s | 6.68s | 0.29s |
| 5,000 | 6.77 MB | 3.60s | 0.78s | 41.79s | 42.57s | 0.49s |
| 10,000 | 13.54 MB | 7.03s | 1.34s | 90.78s | 92.12s | 0.87s |

How to read this:

- For a one-off keyword search over 1,000 plain text files, `rg` is still very fast. AnyFile Wiki should not be described as a universal raw-search accelerator.
- At 10,000 files, raw full-text search for `budget` took 7.03s; after indexing, `anyfile-wiki query` averaged 0.87s against the asset index, about 8.1x faster, without reopening original files.
- The cold full pipeline is dominated by `extract`: on 10,000 small text files, extract took 79.08s; `scan` took 1.34s, rules analysis 6.36s, and assets/html/sidecars 4.62s.
- The main agent optimization is not that the first pass is free. It is that one privacy-gated read creates reusable indexes, so future search, citation, review, and archive suggestions continue from `asset_id` and sidecars.

For the 10,000-file run, generated output sizes were: `inventory.sqlite` 13.25 MB, `extract/` 19.28 MB, `analyze/` 38.83 MB, `assets/` 48.95 MB, and `html/` 15.70 MB. Tiny files are a metadata-heavy case; large PDFs, spreadsheets, OCR images, or LLM analysis shift the bottleneck to parsers, OCR, or model throughput.

Conservative estimates from this local run:

| Scale | Expected behavior |
| --- | --- |
| 10k files | Local plain-text cold start in roughly 1-2 minutes; later agent queries usually under 1 second |
| 100k files | Dry-run scan in tens of seconds; full direct-text extraction and rules analysis around 15-25 minutes; chunked `run` is recommended |
| 500k+ files | Cold extraction can move into hours; use stricter roots, metadata-only rules, excludes, and batches |
| 1M-file class | Best approached as layered metadata/inventory governance first; full body extraction, HTML, and JSONL indexes become the main limits |

Current limits and cautions:

- `anyfile-wiki run` supports `--max-scan-entries`, `--extract-limit`, and `--analyze-limit`; large roots should run in chunks.
- Direct text extraction has a 25 MB per-source guardrail. Larger documents need specialized parsers, batching, or later optimization.
- OCR, MarkItDown, local LLM, and cloud LLM time are not included above; they are usually much slower than scan and rules analysis.
- The current JSONL/SQLite structure is comfortable for 10k-100k files. Beyond that, watch HTML pagination, index file size, query load cost, and future SQLite FTS / batched extraction work.

## Why This Exists

Personal computers accumulate valuable files over time, but many of them become information islands because filenames are casual, folder structures drift, and old material is rarely revisited. Traditional search can find names or keywords, but it does not really answer:

- What knowledge do I actually have on this machine?
- Which files should be kept, archived, reused, or reviewed?
- Which old files can be cleaned up safely?
- Can an agent retrieve my local knowledge before working?
- Can a human browse their digital assets through tags, topics, projects, timelines, and wiki-like pages?

AnyFile Wiki is meant to be a knowledge governance layer over the local filesystem, not just another RAG chat app.

## Current Capabilities

- Privacy-first `privacy.yaml` policy.
- `deny` always wins: no reading, extraction, indexing, or embedding.
- `metadata_only`: record metadata without opening file content.
- `no_embedding`: allow future reading/summarization but block vector indexing.
- Recommended scan roots via `roots.example.yaml`, with human-facing notes and agent-readable setup metadata.
- Default excludes for system folders, developer noise, dangerous extensions, installers, caches, and temporary files.
- Dry-run scanning that only traverses paths and metadata; it does not read file bodies.
- Outputs `scan-plan.md`, `access-log.jsonl`, and `inventory.sqlite`.
- `anyfile-wiki agent-init` for creating agent-readable profile, privacy, roots, index-understanding mode, and idle-scan configs.
- `anyfile-wiki query` for searching existing asset indexes and sidecars without rescanning original files.
- `anyfile-wiki usage-event` for recording agent selections, opens, citations, and search hits.
- CLI commands: `anyfile-wiki privacy`, `anyfile-wiki status`, `anyfile-wiki list`, `anyfile-wiki show`, `anyfile-wiki roots`, `anyfile-wiki tags`.
- `anyfile-wiki run` for resumable daily runs with `run-state.json`, progressing scan, extraction, analysis, review outputs, and the HTML asset browser in small steps.
- `anyfile-wiki extract` for files allowed by policy.
- `anyfile-wiki extracts` for persisted extraction results and status counts.
- Incremental extraction: unchanged successful sources are skipped by default, with `--force` and `--retry-failed` available.
- `anyfile-wiki analyze` for local rule-based summaries, tags, and knowledge indexes from extracted text; `--method codex-mock`, `--method local-llm`, and `--method cloud-llm` are supported.
- Real LLM/API analysis only receives privacy-gated extracted text; cloud mode also requires explicit allowed paths and risk acknowledgement.
- Host-agent semantic indexing for Codex / OpenClaw / Hermes: `agent-task --kind semantic-index` or `semantic-review`, then `agent-review-apply`; AnyFile Wiki does not need a duplicate API key in this mode.
- `anyfile-wiki llm` for explaining local/cloud model policy and cloud-read boundaries.
- `anyfile-wiki review` for Markdown, JSONL, and `human-review.html` review outputs covering unreadable, unsupported, low-confidence, or cloud-unauthorized files.
- `anyfile-wiki review-server` for a local `127.0.0.1` review service where the page submits decisions directly to local files.
- `anyfile-wiki decisions` for reading `review-decisions.jsonl` exported from the HTML review page, then writing a summary, `next-actions.jsonl`, and `decision-plan.md`.
- `anyfile-wiki assets` for applying human review actions back into the final `asset-index.jsonl`, refreshing the human HTML browser, and writing asset sidecar indexes by default.
- `anyfile-wiki sidecars` for backfilling or refreshing `asset-signature.jsonl`, `collection-index.jsonl`, `asset-score.jsonl`, and the sidecar report from an existing `asset-index.jsonl`.
- `anyfile-wiki html` for turning `knowledge-index.jsonl` into a local Chinese/English asset browser with a tag tree, pagination, filters, search, and file details.
- Direct text extraction and lightweight Excel summaries are supported; MarkItDown and RapidOCR are optional parser dependencies.

## Quick Start

Since MVP4, the recommended path is to install the Agent Skill first, then let Codex / OpenClaw / Hermes guide setup, daily runs, review, and asset queries.

```powershell
python scripts/install_agent_skill.py --editable --extras parse,ocr
```

Then tell your agent:

```text
Use AnyFile Wiki to initialize my scan roots and explain the privacy config.
Continue the AnyFile Wiki daily scan.
Find where my budget measurement files are.
```

First setup should be guided by the agent: it runs `agent-init`, reads privacy/roots/analysis setup questions, asks about sensitive paths, first scan roots, metadata-only folders, and index understanding mode. Choose `rules` for fast local summaries, `agent-llm` for host-agent semantic understanding without an extra API key, `local-llm` for a local model service, or `cloud-llm` only after explicit allowed paths and risk acknowledgement. The agent should run a dry-run scan before extraction or analysis.

Detailed CLI examples live in the [CLI Reference](docs/cli-reference.md), so the README stays focused on the agent-first workflow. `anyfile-wiki scan` is always a safe dry-run: it creates an access plan and inventory, but does not read file bodies, summarize files, or write vectors.

## Project Layout

```text
configs/
  schedule.example.yaml      Example idle scan schedule
  roots.example.yaml         Example recommended scan roots
  tags.example.yaml          Example tag taxonomy
  llm.example.yaml           Example LLM and cloud-read policy
  excludes.default.yaml      Default exclude rules
  privacy.example.yaml       Example user privacy policy
docs/
  agent-skill.md             Agent Skill and cross-agent adapter guide
  cli-reference.md           CLI reference for development and debugging
  configuration.md           Configuration guide
  privacy-setup.md           Privacy setup and agent-readable policy guide
  roots-setup.md             Recommended scan roots setup guide
  tags-taxonomy.md           Tag taxonomy guide
  mvp0-usage.md              MVP0 usage guide
  mvp2-analysis.md           MVP2 content analysis guide
  mvp2-review-llm.md         MVP2.1 LLM policy and human review guide
  mvp3-html-browser.md       MVP3 HTML asset browser guide
  asset-sidecars.md          Asset sidecar index guide
  agent-lifecycle.md         Agent lifecycle and daily run guide
skills/
  anyfile-wiki/SKILL.md      Codex Skill entry point
scripts/
  install_agent_skill.py     One-command package and Skill installer
src/anyfile_wiki/
  agent.py                   Agent profile, query, and usage event entry points
  policy.py                  Privacy policy engine
  scan.py                    Dry-run scanner
  inventory.py               SQLite inventory
  report.py                  scan-plan and access-log output
  run_state.py               Daily run state and resume support
  roots.py                   Suggested scan root discovery
  tags.py                    Tag taxonomy parser
  parse.py                   Privacy-gated extraction pipeline
  analyze.py                 Local rule-based summaries, tags, and knowledge indexes
  agent_review.py            Host-agent semantic index/review task and writeback protocol
  llm_client.py              Local/cloud LLM API client
  review.py                  Human review list builder
  decisions.py               Human decisions and agent follow-up action plans
  assets.py                  Final asset index merger after human review
  sidecars.py                Asset signatures, virtual collections, and score sidecars
  llm_config.py              LLM policy config parser
  html.py                    Local HTML asset browser generator
  cli.py                     CLI entry point
tests/
  *.py                       pytest specs
```

## Roadmap

- MVP0: privacy policy, default excludes, dry-run scanning, inventory, reports.
- MVP1: integrate MarkItDown for common document parsing and write an extraction manifest.
- MVP2: local summaries, tags, topics, projects, and file-type classification.
- MVP2.1: LLM policy, cloud authorization boundaries, and human review lists.
- MVP3: human-browsable asset map. The HTML asset browser, human review page, local submit service, and review writeback to `asset-index.jsonl` are now implemented.
- MVP4: agent skill / MCP integration. The Codex Skill, agent init, index query, usage-event entry points, and host-agent semantic index/review writeback protocol are now implemented.
- MVP5: safe cleanup assistant: duplicates, archive candidates, delete candidates, reversible manifests.
- MVP6: app personal-data adapters: browser bookmarks, chat exports, email, note apps, and more.

## Open Collaboration Areas

This project is especially suitable for shared work on hard local-first knowledge problems:

- Safely distinguishing personal files from system files, software files, and app data.
- Designing conservative, explainable, auditable privacy policies.
- Producing useful local-only summaries, tags, and clusters.
- Serving both agent retrieval and human hierarchical browsing from the same knowledge structure.
- Making cleanup suggestions safe, reversible, and low-risk.
- Reusing and integrating projects such as GNO, MarkItDown, Docling, OpenKB, and Paperless-ngx.

Contributions around rule sets, parsers, tests, privacy policies, UI, agent skills, MCP integration, and real-world usage feedback are welcome.

## Tests

```powershell
python -m pytest -q
```

Current tests cover:

- `deny` priority.
- `metadata_only` and `no_embedding` behavior.
- Default exclude rules.
- Dry-run scanning without reading file bodies.
- Inventory queries.
- CLI `status/list/show`.
- Agent init, index query, usage events, Skill installation, and host-agent semantic index writeback.
- Suggested scan root discovery.
- Recommended scan roots config explanation and JSON output.
- Parser-job policy gating.
- Direct text extraction and extraction manifests.
- SQLite persistence and querying for extraction results.
- Incremental extraction, forced reruns, and failed/skipped retry strategy.
- Local rule-based content analysis, tags, and knowledge index outputs.
- LLM policy explanation, cloud authorization boundaries, and human review list outputs.
- Real LLM/API analysis entry points, cloud authorization gates, and JSON response parsing.
- Static HTML asset browser generation, Chinese UI text, and CLI output.
- Human review actions applied into `asset-index.jsonl`, plus review-server submit refreshing asset JSON/HTML.
- Asset sidecar output, stable `asset_id` generation, virtual collections, dry-run behavior, and event-ledger protection.

## Docs

- [Project Start](PROJECT_START.md)
- [Development Plan](DEVELOPMENT_PLAN.md)
- [Agent Skill Guide](docs/agent-skill.md)
- [CLI Reference](docs/cli-reference.md)
- [Configuration Guide](docs/configuration.md)
- [Privacy Setup Guide](docs/privacy-setup.md)
- [Recommended Scan Roots Setup Guide](docs/roots-setup.md)
- [Tag Taxonomy Guide](docs/tags-taxonomy.md)
- [MVP0 Usage Guide](docs/mvp0-usage.md)
- [MVP1 Extraction Guide](docs/mvp1-extraction.md)
- [MVP2 Content Analysis Guide](docs/mvp2-analysis.md)
- [MVP2.1 LLM Policy and Human Review Guide](docs/mvp2-review-llm.md)
- [MVP3 HTML Asset Browser Guide](docs/mvp3-html-browser.md)
- [Asset Sidecar Index Guide](docs/asset-sidecars.md)
- [Agent Lifecycle and Daily Run Guide](docs/agent-lifecycle.md)

## License

This project is licensed under the [Apache License 2.0](LICENSE).
