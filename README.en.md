# PFKB: Personal File Knowledge Base

[中文](README.md) | English

PFKB (Personal File Knowledge Base) is a local-first knowledge base for personal computer files. Its goal is to let local agents such as OpenClaw, Hermes, Codex, and similar tools safely inventory personal files during idle time, then gradually turn documents, notes, PDFs, spreadsheets, code, and app data into searchable, browsable, reusable knowledge assets.

The project is currently at MVP0: solve "what is safe to touch" before parsing, summarizing, tagging, indexing, or compiling knowledge.

## Why This Exists

Personal computers accumulate valuable files over time, but many of them become information islands because filenames are casual, folder structures drift, and old material is rarely revisited. Traditional search can find names or keywords, but it does not really answer:

- What knowledge do I actually have on this machine?
- Which files should be kept, archived, reused, or reviewed?
- Which old files can be cleaned up safely?
- Can an agent retrieve my local knowledge before working?
- Can a human browse their digital assets through tags, topics, projects, timelines, and wiki-like pages?

PFKB is meant to be a knowledge governance layer over the local filesystem, not just another RAG chat app.

## Current Capabilities

- Privacy-first `privacy.yaml` policy.
- `deny` always wins: no reading, extraction, indexing, or embedding.
- `metadata_only`: record metadata without opening file content.
- `no_embedding`: allow future reading/summarization but block vector indexing.
- Recommended scan roots via `roots.example.yaml`, with human-facing notes and agent-readable setup metadata.
- Default excludes for system folders, developer noise, dangerous extensions, installers, caches, and temporary files.
- Dry-run scanning that only traverses paths and metadata; it does not read file bodies.
- Outputs `scan-plan.md`, `access-log.jsonl`, and `inventory.sqlite`.
- CLI commands: `pfkb privacy`, `pfkb status`, `pfkb list`, `pfkb show`, `pfkb roots`.
- `pfkb extract` for files allowed by policy.
- `pfkb extracts` for persisted extraction results and status counts.
- Incremental extraction: unchanged successful sources are skipped by default, with `--force` and `--retry-failed` available.
- Direct text extraction is supported; MarkItDown is an optional parser dependency.

## Quick Start

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

In MVP0, `pfkb scan` is a dry-run: it creates an access plan and an inventory, but it does not read file content, summarize files, or write vectors.

## Common Commands

```powershell
# Show suggested personal scan roots
python -m pfkb roots --include-missing

# Explain recommended scan roots config
python -m pfkb roots --explain
python -m pfkb roots --explain --json

# Explain the privacy policy for a user or setup agent
python -m pfkb privacy --privacy configs/privacy.yaml
python -m pfkb privacy --privacy configs/privacy.yaml --json

# Scan a small target first
python -m pfkb scan "$env:USERPROFILE\Documents" --privacy configs/privacy.yaml --out data/first-scan --max-entries 500

# Show policy counts and policy sources
python -m pfkb status --inventory data/first-scan/inventory.sqlite --sources

# List inventory records
python -m pfkb list --inventory data/first-scan/inventory.sqlite --limit 20

# Show denied records only
python -m pfkb list --inventory data/first-scan/inventory.sqlite --policy deny

# Explain the policy decision for one path
python -m pfkb show "C:\path\to\file.md" --inventory data/first-scan/inventory.sqlite

# Extract content from files allowed by policy
python -m pfkb extract --inventory data/first-scan/inventory.sqlite --out data/first-extract

# Force re-extraction
python -m pfkb extract --inventory data/first-scan/inventory.sqlite --out data/first-extract --force

# Retry only records whose latest extraction failed or skipped
python -m pfkb extract --inventory data/first-scan/inventory.sqlite --out data/first-extract --retry-failed

# Show extraction status
python -m pfkb extracts --inventory data/first-scan/inventory.sqlite --stats
```

## Project Layout

```text
configs/
  roots.example.yaml         Example recommended scan roots
  excludes.default.yaml      Default exclude rules
  privacy.example.yaml       Example user privacy policy
docs/
  configuration.md           Configuration guide
  privacy-setup.md           Privacy setup and agent-readable policy guide
  roots-setup.md             Recommended scan roots setup guide
  mvp0-usage.md              MVP0 usage guide
src/pfkb/
  policy.py                  Privacy policy engine
  scan.py                    Dry-run scanner
  inventory.py               SQLite inventory
  report.py                  scan-plan and access-log output
  roots.py                   Suggested scan root discovery
  parse.py                   Privacy-gated extraction pipeline
  cli.py                     CLI entry point
tests/
  *.py                       pytest specs
```

## Roadmap

- MVP0: privacy policy, default excludes, dry-run scanning, inventory, reports.
- MVP1: integrate MarkItDown for common document parsing and write an extraction manifest.
- MVP2: local summaries, tags, topics, projects, and file-type classification.
- MVP3: human-browsable asset map: tag tree, topic pages, project pages, file details.
- MVP4: agent skill / MCP integration for OpenClaw, Hermes, Codex, and similar agents.
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
- Suggested scan root discovery.
- Recommended scan roots config explanation and JSON output.
- Parser-job policy gating.
- Direct text extraction and extraction manifests.
- SQLite persistence and querying for extraction results.
- Incremental extraction, forced reruns, and failed/skipped retry strategy.

## Docs

- [Project Start](PROJECT_START.md)
- [Development Plan](DEVELOPMENT_PLAN.md)
- [Configuration Guide](docs/configuration.md)
- [Privacy Setup Guide](docs/privacy-setup.md)
- [Recommended Scan Roots Setup Guide](docs/roots-setup.md)
- [MVP0 Usage Guide](docs/mvp0-usage.md)
- [MVP1 Extraction Guide](docs/mvp1-extraction.md)

## License

This project is licensed under the [Apache License 2.0](LICENSE).
