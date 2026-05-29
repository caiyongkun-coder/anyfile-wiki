---
name: anyfile-wiki
description: Use when a user wants an agent to initialize, scan, index, browse, review, query, or manage local personal files through AnyFile Wiki. Covers privacy-first setup, resumable daily runs, HTML review pages, asset indexes, virtual collections, sidecar scores, and safe file-management suggestions without moving, deleting, or renaming original files.
---

# AnyFile Wiki Agent Skill

Use this skill when the user asks about local file knowledge, personal-file inventory, finding documents, organizing file types, continuing idle scans, opening review pages, or asking where a file or topic lives.

## Safety Rules

- Never move, delete, rename, or rewrite original user files.
- Read indexes before opening original files.
- Respect `configs/privacy.yaml` and `configs/excludes.default.yaml`; `deny` always wins.
- Cloud LLM reading is forbidden unless the config explicitly authorizes paths and acknowledges the risk.
- In Codex/OpenClaw/Hermes host-agent use, prefer `agent-task` + `agent-review-apply`; do not ask the user for a duplicate API key just to use the host agent's model ability.
- Treat archive/delete results as suggestions only.

## Setup Workflow

1. Check installation with `anyfile-wiki --help`.
2. If missing, suggest or run from the repo: `python scripts/install_agent_skill.py --editable --extras parse,ocr`.
3. Initialize agent-readable configs:
   ```powershell
   anyfile-wiki agent-init --profile configs/agent-profile.yaml --out data/daily-run
   ```
4. Read and explain, in this order:
   - `configs/agent-profile.yaml`
   - `configs/privacy.yaml`
   - `configs/roots.yaml`
   - `configs/schedule.yaml`
5. Read `setup_questions` from privacy/roots config and ask the user about sensitive paths, first scan roots, and metadata-only folders.
6. Update `privacy.yaml` / `roots.yaml` only after the user answers.
7. Run a dry-run scan and explain the report before the first extraction or analysis run.

## Daily Run Workflow

For the first run, pass an approved scan root:

```powershell
anyfile-wiki run "<approved-scan-root>" --privacy configs/privacy.yaml --out data/daily-run
```

For later idle work, continue with:

```powershell
anyfile-wiki run --out data/daily-run
```

Check progress with:

```powershell
anyfile-wiki run --out data/daily-run --status
```

If review items exist, prefer the service page:

```powershell
anyfile-wiki review-server --review-dir data/daily-run/review --once
```

Use static `human-review.html` only as a fallback. Pause for review before treating uncertain files as confirmed.

## Agent Semantic Review Workflow

When a user approves semantic review inside the host agent, do not configure `OPENAI_API_KEY` for AnyFile Wiki. Generate privacy-gated tasks:

```powershell
anyfile-wiki agent-task --kind semantic-review --in data/daily-run/review/next-actions.jsonl --out data/daily-run/agent-review
```

Then:

1. Read `data/daily-run/agent-review/semantic-review-tasks.jsonl`.
2. For each task, read only `extracted_text_path`.
3. Do not read the original `path` unless the user explicitly asks and privacy allows it.
4. Produce `data/daily-run/agent-review/results.jsonl` matching `expected-output-schema.json`.
5. Apply results:
   ```powershell
   anyfile-wiki agent-review-apply --in data/daily-run/agent-review/results.jsonl
   ```

Use `cloud-llm` only for unattended standalone CLI runs with explicit `configs/llm.yaml`, allowed paths, risk acknowledgement, and API key.

## Query Workflow

For user questions like "where is my budget file", "show project docs", "find duplicate candidates", or "what needs review", query the index first:

```powershell
anyfile-wiki query "<keyword or topic>" --profile configs/agent-profile.yaml --json
```

Read in this priority:

1. `configs/agent-profile.yaml`
2. `data/daily-run/run-state.json`
3. `data/daily-run/assets/asset-index.jsonl`
4. `data/daily-run/assets/collection-index.jsonl`
5. `data/daily-run/assets/asset-score.jsonl`
6. Original files only if privacy allows and the answer requires it.

After using an asset, record feedback:

```powershell
anyfile-wiki usage-event --asset-id "<asset_id>" --event cited --query "<user query>"
```

Use `selected`, `opened`, `cited`, or `search_hit` as the event type.

## Common Intents

- Initialize: run `agent-init`, then explain privacy and roots.
- Continue scan: run `anyfile-wiki run --out data/daily-run`.
- Show progress: run `anyfile-wiki run --out data/daily-run --status`.
- Open asset browser: point to `data/daily-run/html/knowledge-index.html`.
- Open review page: start `review-server`; point to `data/daily-run/review/human-review.html` only if service mode is not available.
- Run host-agent semantic review: run `agent-task`, analyze extracted text, then run `agent-review-apply`.
- Find a file/type/topic: run `query`, then cite paths and virtual paths.
- Find review items: query `waiting review`, `needs review`, or inspect `human-review.jsonl`.
- Find duplicates/archive candidates: query `duplicate_candidate`, `nas`, `cold`, or inspect `asset-score.jsonl`.

## Output Style

When answering the user, summarize the high-signal matches first: title, path, virtual path, review status, and delete risk. Keep command details hidden unless the user asks for them.
