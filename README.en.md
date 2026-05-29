# AnyFile Wiki: turn scattered personal files into local knowledge assets for agents

[中文](README.md) | English

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-Apache--2.0-green)
![Privacy](https://img.shields.io/badge/Privacy-local--first-brightgreen)
![Status](https://img.shields.io/badge/Status-MVP4--ready-orange)

AnyFile Wiki is a local-first knowledge base for personal computer files. Its goal is to let local agents such as OpenClaw, Hermes, Codex, and similar tools safely inventory personal files during idle time, then gradually turn documents, notes, PDFs, spreadsheets, code, and app data into searchable, browsable, reusable knowledge assets.

It is not just another RAG chat app. AnyFile Wiki is a local file knowledge governance layer: it first decides what is safe to touch, then extracts, summarizes, tags, builds an asset index, creates virtual collections, and gives auditable archive/delete suggestions without moving, deleting, or renaming your original files.

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
- `anyfile-wiki agent-init` for creating agent-readable profile, privacy, roots, and idle-scan configs.
- `anyfile-wiki query` for searching existing asset indexes and sidecars without rescanning original files.
- `anyfile-wiki usage-event` for recording agent selections, opens, citations, and search hits.
- CLI commands: `anyfile-wiki privacy`, `anyfile-wiki status`, `anyfile-wiki list`, `anyfile-wiki show`, `anyfile-wiki roots`, `anyfile-wiki tags`.
- `anyfile-wiki run` for resumable daily runs with `run-state.json`, progressing scan, extraction, analysis, review outputs, and the HTML asset browser in small steps.
- `anyfile-wiki extract` for files allowed by policy.
- `anyfile-wiki extracts` for persisted extraction results and status counts.
- Incremental extraction: unchanged successful sources are skipped by default, with `--force` and `--retry-failed` available.
- `anyfile-wiki analyze` for local rule-based summaries, tags, and knowledge indexes from extracted text; `--method codex-mock`, `--method local-llm`, and `--method cloud-llm` are supported.
- Real LLM/API analysis only receives privacy-gated extracted text; cloud mode also requires explicit allowed paths and risk acknowledgement.
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
anyfile-wiki agent-init --profile configs/agent-profile.yaml --out data/daily-run
```

Then tell your agent:

```text
Use AnyFile Wiki to initialize my scan roots and explain the privacy config.
Continue the AnyFile Wiki daily scan.
Find where my budget measurement files are.
```

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
- MVP4: agent skill / MCP integration. The Codex Skill, agent init, index query, and usage-event entry points are now implemented.
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
- Agent init, index query, usage events, and Skill installation.
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
