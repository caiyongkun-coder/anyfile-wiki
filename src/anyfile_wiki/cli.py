from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .analyze import (
    AnalysisResult,
    analyze_extract_records,
    analysis_stats,
    write_analysis_comparison_md,
    write_analysis_outputs,
)
from .assets import build_asset_index, load_jsonl_records, write_asset_outputs
from .decisions import (
    actions_as_dicts,
    build_decision_actions,
    decisions_as_dicts,
    format_action_plan_summary,
    format_decisions_summary,
    load_review_decisions,
    write_decision_plan_md,
    write_decisions_summary_md,
    write_next_actions_jsonl,
)
from .html import load_browser_records, write_knowledge_browser_html
from .inventory import Inventory
from .llm_config import describe_llm_config, load_llm_config
from .parse import extract_job, extract_jobs, plan_parse_jobs_from_records, write_manifest
from .policy import PolicyEngine, describe_privacy_policy, load_policy
from .report import write_access_log, write_scan_plan
from .review import (
    ReviewItem,
    build_review_items,
    load_analysis_manifest,
    review_reason_stats,
    review_stats,
    write_review_outputs,
)
from .review_server import make_review_server
from .roots import describe_roots_config, discover_candidate_roots, load_roots_config
from .run_state import (
    STAGE_ORDER,
    format_run_state,
    load_run_state,
    mark_stage_result,
    mark_stage_started,
    new_run_state,
    next_stage,
    save_run_state,
)
from .scan import scan_paths
from .sidecars import SIDECAR_LEVELS, attach_asset_ids, write_jsonl_records, write_sidecar_outputs
from .tags import describe_tags_config, filter_tags, load_tags_config, tag_definitions


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="anyfile-wiki", description="AnyFile Wiki MVP0 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Create a privacy-first dry-run scan plan")
    scan.add_argument("roots", nargs="+", help="Root directories or files to scan")
    scan.add_argument("--privacy", default="configs/privacy.example.yaml", help="Privacy policy YAML")
    scan.add_argument("--excludes", default="configs/excludes.default.yaml", help="Default excludes YAML")
    scan.add_argument("--out", default="data", help="Output directory")
    scan.add_argument("--inventory", default=None, help="SQLite inventory path")
    scan.add_argument("--max-entries", type=int, default=None, help="Stop after N entries")
    scan.add_argument("--follow-symlinks", action="store_true", help="Follow symlinked directories")
    scan.add_argument("--no-inventory", action="store_true", help="Do not write inventory.sqlite")
    scan.set_defaults(func=cmd_scan)

    status = subparsers.add_parser("status", help="Show inventory status")
    status.add_argument("--inventory", default="data/inventory.sqlite", help="SQLite inventory path")
    status.add_argument("--sources", action="store_true", help="Show top policy sources")
    status.set_defaults(func=cmd_status)

    list_cmd = subparsers.add_parser("list", help="List inventory records")
    list_cmd.add_argument("--inventory", default="data/inventory.sqlite", help="SQLite inventory path")
    list_cmd.add_argument("--policy", default=None, help="Filter by access policy")
    list_cmd.add_argument("--limit", type=int, default=20, help="Maximum records to show")
    list_cmd.add_argument("--files-only", action="store_true", help="Hide directories")
    list_cmd.add_argument("--json", action="store_true", help="Emit JSON")
    list_cmd.set_defaults(func=cmd_list)

    show = subparsers.add_parser("show", help="Show one inventory record by path")
    show.add_argument("path", help="Path recorded in inventory")
    show.add_argument("--inventory", default="data/inventory.sqlite", help="SQLite inventory path")
    show.add_argument("--json", action="store_true", help="Emit JSON")
    show.set_defaults(func=cmd_show)

    roots = subparsers.add_parser("roots", help="Show suggested personal scan roots")
    roots.add_argument("--roots-config", default="configs/roots.example.yaml", help="Recommended roots YAML")
    roots.add_argument("--include-missing", action="store_true", help="Also show roots that do not exist")
    roots.add_argument("--include-disabled", action="store_true", help="Also show disabled configured roots")
    roots.add_argument("--explain", action="store_true", help="Explain the roots config instead of only listing resolved roots")
    roots.add_argument("--json", action="store_true", help="Emit JSON")
    roots.set_defaults(func=cmd_roots)

    privacy = subparsers.add_parser("privacy", help="Explain a privacy policy for humans or agents")
    privacy.add_argument("--privacy", default="configs/privacy.example.yaml", help="Privacy policy YAML")
    privacy.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    privacy.add_argument("--no-rules", action="store_true", help="Hide individual rule values in text output")
    privacy.set_defaults(func=cmd_privacy)

    tags = subparsers.add_parser("tags", help="Explain the tag taxonomy for humans or agents")
    tags.add_argument("--tags-config", default="configs/tags.example.yaml", help="Tag taxonomy YAML")
    tags.add_argument("--dimension", default=None, help="Filter tags by dimension")
    tags.add_argument("--search", default=None, help="Search tag ids, labels, aliases, and descriptions")
    tags.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    tags.set_defaults(func=cmd_tags)

    extract = subparsers.add_parser("extract", help="Extract content for inventory records allowed by policy")
    extract.add_argument("--inventory", default="data/inventory.sqlite", help="SQLite inventory path")
    extract.add_argument("--out", default="data/extract", help="Extraction output directory")
    extract.add_argument("--limit", type=int, default=100, help="Maximum inventory records to inspect")
    extract.add_argument(
        "--extensions",
        default="",
        help="Comma-separated extension filter such as .txt,.xlsx,.jpg; empty means all supported extensions",
    )
    extract.add_argument(
        "--max-source-mb",
        type=float,
        default=None,
        help="Only plan files at or below this source size in MB; useful for staged retries",
    )
    extract.add_argument("--manifest", default=None, help="Manifest JSONL path")
    extract.add_argument("--force", action="store_true", help="Re-extract even when source appears unchanged")
    extract.add_argument("--retry-failed", action="store_true", help="Only retry records whose latest extraction failed or skipped")
    extract.add_argument(
        "--timeout-seconds",
        type=int,
        default=0,
        help="Maximum seconds allowed for each external parser job; use 0 to disable",
    )
    extract.set_defaults(func=cmd_extract)

    extracts = subparsers.add_parser("extracts", help="List extraction results stored in inventory")
    extracts.add_argument("--inventory", default="data/inventory.sqlite", help="SQLite inventory path")
    extracts.add_argument("--status", default=None, help="Filter by extraction status")
    extracts.add_argument("--parser", default=None, help="Filter by parser")
    extracts.add_argument("--path", default=None, help="Filter by source path")
    extracts.add_argument("--limit", type=int, default=20, help="Maximum records to show")
    extracts.add_argument("--json", action="store_true", help="Emit JSON")
    extracts.add_argument("--stats", action="store_true", help="Show status counts (default)")
    extracts.add_argument("--no-stats", action="store_true", help="Hide status counts")
    extracts.set_defaults(func=cmd_extracts)

    analyze = subparsers.add_parser("analyze", help="Build a knowledge index from extracted text")
    analyze.add_argument("--inventory", default="data/inventory.sqlite", help="SQLite inventory path")
    analyze.add_argument("--out", default="data/analyze", help="Analysis output directory")
    analyze.add_argument("--limit", type=int, default=100, help="Maximum extracted records to analyze")
    analyze.add_argument("--max-text-chars", type=int, default=200_000, help="Maximum text chars to inspect per file")
    analyze.add_argument(
        "--method",
        choices=["rules", "codex-mock", "local-llm", "cloud-llm"],
        default="rules",
        help="Analysis method: rules, codex-mock, local-llm, or cloud-llm",
    )
    analyze.add_argument("--llm-config", default="configs/llm.example.yaml", help="LLM policy YAML")
    analyze.add_argument("--tags-config", default="configs/tags.example.yaml", help="Tag taxonomy YAML")
    analyze.add_argument(
        "--compare-to",
        default=None,
        help="Optional baseline analysis-manifest.jsonl to compare against",
    )
    analyze.add_argument("--json", action="store_true", help="Print analyzed records as JSON")
    analyze.set_defaults(func=cmd_analyze)

    llm = subparsers.add_parser("llm", help="Explain the LLM/privacy policy config")
    llm.add_argument("--llm-config", default="configs/llm.example.yaml", help="LLM policy YAML")
    llm.add_argument("--json", action="store_true", help="Emit JSON")
    llm.set_defaults(func=cmd_llm)

    review = subparsers.add_parser("review", help="Write a human review list for files needing manual attention")
    review.add_argument("--inventory", default="data/inventory.sqlite", help="SQLite inventory path")
    review.add_argument("--analysis", default=None, help="Optional analysis-manifest.jsonl path")
    review.add_argument("--llm-config", default="configs/llm.example.yaml", help="LLM policy YAML")
    review.add_argument("--out", default="data/review", help="Review output directory")
    review.add_argument("--limit", type=int, default=1000, help="Maximum inventory files to inspect")
    review.add_argument("--json", action="store_true", help="Print review items as JSON")
    review.set_defaults(func=cmd_review)

    review_server = subparsers.add_parser("review-server", help="Serve a local human review page that submits decisions")
    review_server.add_argument("--review-dir", default="data/review", help="Directory containing human-review.jsonl")
    review_server.add_argument("--host", default="127.0.0.1", help="Host to bind. Keep 127.0.0.1 for local-only use")
    review_server.add_argument("--port", type=int, default=8765, help="Port to bind. Use 0 to choose a free port")
    review_server.add_argument("--token", default=None, help="Optional access token. A random token is generated by default")
    review_server.add_argument("--once", action="store_true", help="Stop the server after a final submit")
    review_server.set_defaults(func=cmd_review_server)

    decisions = subparsers.add_parser("decisions", help="Read human review decisions exported from HTML")
    decisions.add_argument("--decisions", default="data/review/review-decisions.jsonl", help="review-decisions.jsonl path")
    decisions.add_argument("--out", default=None, help="Optional Markdown summary path")
    decisions.add_argument("--actions-out", default=None, help="Optional next-actions.jsonl path for agents")
    decisions.add_argument("--plan-out", default=None, help="Optional Markdown decision plan path")
    decisions.add_argument("--json", action="store_true", help="Emit JSON")
    decisions.set_defaults(func=cmd_decisions)

    assets = subparsers.add_parser("assets", help="Apply human review actions into the final asset index")
    assets.add_argument("--analysis", default="data/analyze/knowledge-index.jsonl", help="knowledge-index.jsonl path")
    assets.add_argument("--actions", default="data/review/next-actions.jsonl", help="next-actions.jsonl path")
    assets.add_argument("--review-items", default="data/review/human-review.jsonl", help="Optional human-review.jsonl path")
    assets.add_argument("--out", default="data/assets", help="Asset index output directory")
    assets.add_argument("--html-out", default="data/html", help="Also refresh the HTML asset browser in this directory")
    assets.add_argument("--no-html", action="store_true", help="Only write asset JSON/Markdown, do not refresh HTML")
    assets.add_argument("--no-sidecars", action="store_true", help="Only write asset JSON/Markdown, do not write sidecar indexes")
    assets.add_argument(
        "--sidecar-level",
        choices=sorted(SIDECAR_LEVELS),
        default="text",
        help="Sidecar scan level: light reads metadata only; text also hashes extracted output_path text",
    )
    assets.add_argument("--tags-config", default="configs/tags.example.yaml", help="Tag taxonomy YAML")
    assets.add_argument("--json", action="store_true", help="Emit JSON")
    assets.set_defaults(func=cmd_assets)

    sidecars = subparsers.add_parser("sidecars", help="Backfill or refresh sidecar indexes from an asset-index.jsonl")
    sidecars.add_argument("--asset-index", default="data/assets/asset-index.jsonl", help="Existing asset-index.jsonl path")
    sidecars.add_argument("--out", default=None, help="Sidecar output directory. Defaults to the asset-index directory")
    sidecars.add_argument(
        "--sidecar-level",
        choices=sorted(SIDECAR_LEVELS),
        default="text",
        help="Sidecar scan level: light reads metadata only; text also hashes extracted output_path text",
    )
    sidecars.add_argument("--dry-run", action="store_true", help="Print the sidecar plan without writing files")
    sidecars.add_argument("--json", action="store_true", help="Emit JSON")
    sidecars.set_defaults(func=cmd_sidecars)

    run = subparsers.add_parser("run", help="Run one resumable daily processing step with run-state.json")
    run.add_argument("roots", nargs="*", help="Root directories or files. Required when creating a new run state")
    run.add_argument("--state", default=None, help="run-state.json path. Defaults to <out>/run-state.json")
    run.add_argument("--out", default="data/run", help="Run output directory")
    run.add_argument("--privacy", default="configs/privacy.example.yaml", help="Privacy policy YAML")
    run.add_argument("--excludes", default="configs/excludes.default.yaml", help="Default excludes YAML")
    run.add_argument("--inventory", default=None, help="SQLite inventory path")
    run.add_argument("--max-scan-entries", type=int, default=500, help="Maximum scan entries for this run step")
    run.add_argument("--extract-limit", type=int, default=100, help="Maximum inventory records to inspect in this run step")
    run.add_argument(
        "--extract-timeout-seconds",
        type=int,
        default=0,
        help="Maximum seconds allowed for each external parser job during run extract stage; use 0 to disable",
    )
    run.add_argument("--analyze-limit", type=int, default=100, help="Maximum extracted records to analyze in this run step")
    run.add_argument("--review-limit", type=int, default=1000, help="Maximum inventory files to inspect when writing review outputs")
    run.add_argument(
        "--method",
        choices=["rules", "codex-mock", "local-llm", "cloud-llm"],
        default="rules",
        help="Analysis method for a new run state",
    )
    run.add_argument("--llm-config", default="configs/llm.example.yaml", help="LLM policy YAML")
    run.add_argument("--tags-config", default="configs/tags.example.yaml", help="Tag taxonomy YAML")
    run.add_argument("--follow-symlinks", action="store_true", help="Follow symlinked directories for a new run state")
    run.add_argument("--stage", choices=["auto", *STAGE_ORDER], default="auto", help="Stage to run. Defaults to the next incomplete stage")
    run.add_argument("--status", action="store_true", help="Only print current run-state.json")
    run.add_argument("--json", action="store_true", help="Emit JSON")
    run.set_defaults(func=cmd_run)

    html = subparsers.add_parser("html", help="Build a local HTML asset browser from a knowledge index")
    html.add_argument("--analysis", default="data/analyze/knowledge-index.jsonl", help="knowledge-index.jsonl or analysis-manifest.jsonl path")
    html.add_argument("--tags-config", default="configs/tags.example.yaml", help="Tag taxonomy YAML")
    html.add_argument("--out", default="data/html", help="HTML output directory")
    html.set_defaults(func=cmd_html)

    return parser


def cmd_scan(args) -> int:
    out_dir = Path(args.out)
    inventory_path = Path(args.inventory) if args.inventory else out_dir / "inventory.sqlite"
    policy = PolicyEngine.from_files(_optional_path(args.privacy), _optional_path(args.excludes))

    result = scan_paths(
        args.roots,
        policy,
        dry_run=True,
        follow_symlinks=args.follow_symlinks,
        max_entries=args.max_entries,
    )

    plan_path = out_dir / "scan-plan.md"
    log_path = out_dir / "access-log.jsonl"
    write_scan_plan(result, plan_path)
    write_access_log(result, log_path)

    inventory_count = 0
    if not args.no_inventory:
        with Inventory(inventory_path) as inventory:
            inventory_count = inventory.upsert_entries(result.entries)

    print(f"scan-plan: {plan_path}")
    print(f"access-log: {log_path}")
    if not args.no_inventory:
        print(f"inventory: {inventory_path} ({inventory_count} entries)")
    for key, value in result.stats.as_dict().items():
        print(f"{key}: {value}")
    if result.errors:
        print("errors:")
        for error in result.errors[:20]:
            print(f"- {error}")
    return 0 if not result.errors else 2


def cmd_status(args) -> int:
    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        print(f"inventory not found: {inventory_path}", file=sys.stderr)
        return 2
    with Inventory(inventory_path) as inventory:
        stats = inventory.stats()
        source_stats = inventory.source_stats() if args.sources else []
    if not stats:
        print("inventory is empty")
        return 0
    for policy, count in sorted(stats.items()):
        print(f"{policy}: {count}")
    if args.sources:
        print("policy_sources:")
        for source, count in source_stats:
            print(f"- {source}: {count}")
    return 0


def cmd_list(args) -> int:
    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        print(f"inventory not found: {inventory_path}", file=sys.stderr)
        return 2
    with Inventory(inventory_path) as inventory:
        records = inventory.list_files(
            limit=args.limit,
            access_policy=args.policy,
            include_dirs=not args.files_only,
        )
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return 0
    for record in records:
        kind = "dir" if record["is_dir"] else "file"
        print(f"{record['access_policy']}\t{kind}\t{record['path']}")
    return 0


def cmd_show(args) -> int:
    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        print(f"inventory not found: {inventory_path}", file=sys.stderr)
        return 2
    with Inventory(inventory_path) as inventory:
        record = inventory.get_file(args.path)
    if record is None:
        print(f"record not found: {args.path}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    for key, value in record.items():
        print(f"{key}: {value}")
    return 0


def cmd_roots(args) -> int:
    config = load_roots_config(_optional_path(args.roots_config))
    if args.explain:
        payload = describe_roots_config(config)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        print(_format_roots_summary(payload))
        return 0
    roots = discover_candidate_roots(
        existing_only=not args.include_missing,
        config=config,
        include_disabled=args.include_disabled,
    )
    payload = [root.as_dict() for root in roots]
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for root in roots:
        status = "exists" if root.exists else "missing"
        print(f"{root.name}\t{status}\t{root.risk}\t{root.path}")
    return 0


def cmd_privacy(args) -> int:
    privacy_path = Path(args.privacy)
    if not privacy_path.exists():
        print(f"privacy config not found: {privacy_path}", file=sys.stderr)
        return 2
    summary = describe_privacy_policy(load_policy(privacy_path))
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    print(_format_privacy_summary(summary, include_rules=not args.no_rules))
    return 0


def cmd_tags(args) -> int:
    tags_path = Path(args.tags_config)
    if not tags_path.exists():
        print(f"tags config not found: {tags_path}", file=sys.stderr)
        return 2
    config = load_tags_config(tags_path)
    summary = describe_tags_config(config)
    definitions = filter_tags(
        tag_definitions(config),
        dimension=args.dimension,
        query=args.search,
    )
    summary["tags"] = [definition.as_dict() for definition in definitions]
    summary["filtered_tag_count"] = len(definitions)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    print(_format_tags_summary(summary))
    return 0


def cmd_extract(args) -> int:
    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        print(f"inventory not found: {inventory_path}", file=sys.stderr)
        return 2
    output_dir = Path(args.out)
    manifest_path = Path(args.manifest) if args.manifest else output_dir / "extract-manifest.jsonl"
    with Inventory(inventory_path) as inventory:
        records = inventory.list_files(limit=args.limit, include_dirs=False)
        latest_success = inventory.latest_success_by_path()
        latest = inventory.latest_extracts_by_path()
    records = _filter_extract_records(records, extensions=args.extensions, max_source_mb=args.max_source_mb)
    plan = plan_parse_jobs_from_records(
        records,
        latest_success_by_path=latest_success,
        latest_by_path=latest,
        force=args.force,
        retry_failed=args.retry_failed,
    )
    timeout_seconds = args.timeout_seconds if args.timeout_seconds and args.timeout_seconds > 0 else None
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    stored_count = 0
    error_count = 0
    with Inventory(inventory_path) as inventory, manifest_path.open("w", encoding="utf-8") as manifest:
        for result in plan.skipped:
            _write_manifest_result(manifest, result)
            stored_count += inventory.add_extract_results([result])
            counts[result.status] = counts.get(result.status, 0) + 1
        for job in plan.jobs:
            result = extract_job(job, output_dir, timeout_seconds=timeout_seconds)
            _write_manifest_result(manifest, result)
            stored_count += inventory.add_extract_results([result])
            counts[result.status] = counts.get(result.status, 0) + 1
            if result.status == "error":
                error_count += 1
    print(f"jobs: {len(plan.jobs)}")
    print(f"planned: {len(plan.jobs)}")
    print(f"skipped: {len(plan.skipped)}")
    print(f"manifest: {manifest_path}")
    print(f"stored: {stored_count}")
    for status, count in sorted(counts.items()):
        print(f"{status}: {count}")
    return 0 if error_count == 0 else 1


def _write_manifest_result(handle, result) -> None:
    handle.write(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True) + "\n")
    handle.flush()


def _filter_extract_records(records: list[dict], *, extensions: str = "", max_source_mb: float | None = None) -> list[dict]:
    wanted_extensions = {
        item if item.startswith(".") else f".{item}"
        for item in (part.strip().lower() for part in str(extensions or "").split(","))
        if item and item != "."
    }
    max_bytes = int(max_source_mb * 1024 * 1024) if max_source_mb is not None else None
    filtered: list[dict] = []
    for record in records:
        extension = str(record.get("extension") or "").lower()
        if wanted_extensions and extension not in wanted_extensions:
            continue
        if max_bytes is not None:
            size = record.get("size_bytes")
            if size is not None and int(size) > max_bytes:
                continue
        filtered.append(record)
    return filtered


def cmd_extracts(args) -> int:
    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        print(f"inventory not found: {inventory_path}", file=sys.stderr)
        return 2
    with Inventory(inventory_path) as inventory:
        stats = {} if args.no_stats else inventory.extract_stats()
        records = inventory.list_extracts(
            limit=args.limit,
            status=args.status,
            parser=args.parser,
            path=args.path,
        )
    if args.json:
        payload = {"stats": stats, "records": records}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if not args.no_stats:
        print("extract_status:")
        if stats:
            for status, count in sorted(stats.items()):
                print(f"- {status}: {count}")
        else:
            print("- empty: 0")
    for record in records:
        print(
            f"{record['status']}\t{record['parser']}\t{record['path']}\t{record.get('output_path') or ''}"
        )
    return 0


def cmd_analyze(args) -> int:
    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        print(f"inventory not found: {inventory_path}", file=sys.stderr)
        return 2
    with Inventory(inventory_path) as inventory:
        latest = inventory.latest_analyzable_extracts_by_path()
    records = sorted(latest.values(), key=lambda record: str(record.get("path", "")))[: args.limit]
    llm_config = load_llm_config(_optional_path(args.llm_config)) if args.method in {"local-llm", "cloud-llm"} else None
    tag_config = load_tags_config(_optional_path(args.tags_config))
    allowed_tags = [definition.id for definition in tag_definitions(tag_config)]
    results = analyze_extract_records(
        records,
        max_text_chars=args.max_text_chars,
        analysis_method=args.method,
        llm_config=llm_config,
        allowed_tags=allowed_tags,
    )
    outputs = write_analysis_outputs(results, args.out)
    if args.compare_to:
        comparison_path = Path(args.out) / "analysis-comparison.md"
        write_analysis_comparison_md(_load_jsonl(args.compare_to), results, comparison_path)
        outputs["analysis_comparison_md"] = comparison_path
    stats = analysis_stats(results)
    if args.json:
        print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2))
        return 0
    print(f"inputs: {len(records)}")
    print(f"analyzed: {len(results)}")
    print(f"method: {args.method}")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    for status, count in sorted(stats.items()):
        print(f"{status}: {count}")
    return 0 if not any(result.status == "error" for result in results) else 1


def cmd_llm(args) -> int:
    llm_path = Path(args.llm_config)
    if not llm_path.exists():
        print(f"llm config not found: {llm_path}", file=sys.stderr)
        return 2
    summary = describe_llm_config(load_llm_config(llm_path))
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    print(_format_llm_summary(summary))
    return 0


def cmd_review(args) -> int:
    inventory_path = Path(args.inventory)
    if not inventory_path.exists():
        print(f"inventory not found: {inventory_path}", file=sys.stderr)
        return 2
    llm_config = load_llm_config(_optional_path(args.llm_config))
    analysis_records = load_analysis_manifest(args.analysis)
    with Inventory(inventory_path) as inventory:
        files = inventory.list_files(limit=args.limit, include_dirs=False)
        latest_extracts = inventory.latest_extracts_by_path()
    items = build_review_items(
        files,
        latest_extracts,
        analysis_records=analysis_records,
        llm_config=llm_config,
    )
    outputs = write_review_outputs(items, args.out)
    stats = review_stats(items)
    reason_stats = review_reason_stats(items)
    if args.json:
        print(json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2))
        return 0
    print(f"files_inspected: {len(files)}")
    print(f"review_items: {len(items)}")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    for category, count in sorted(stats.items()):
        print(f"{category}: {count}")
    if reason_stats:
        print("reason_codes:")
        for reason_code, count in sorted(reason_stats.items()):
            print(f"- {reason_code}: {count}")
    return 0


def cmd_review_server(args) -> int:
    review_dir = Path(args.review_dir)
    try:
        httpd, token = make_review_server(
            review_dir=review_dir,
            host=args.host,
            port=args.port,
            token=args.token,
            once=bool(args.once),
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    host, port = httpd.server_address[:2]
    url = f"http://{host}:{port}/review?token={token}"
    print(f"review_url: {url}")
    print(f"review_dir: {review_dir}")
    print(f"once: {str(bool(args.once)).lower()}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        httpd.server_close()
    return 0


def cmd_decisions(args) -> int:
    decisions_path = Path(args.decisions)
    if not decisions_path.exists():
        print(f"decisions file not found: {decisions_path}", file=sys.stderr)
        return 2
    try:
        decisions = load_review_decisions(decisions_path)
    except ValueError as exc:
        print(f"invalid decisions file: {exc}", file=sys.stderr)
        return 2
    actions = build_decision_actions(decisions)
    if args.out:
        write_decisions_summary_md(decisions, args.out)
    if args.actions_out:
        write_next_actions_jsonl(actions, args.actions_out)
    if args.plan_out:
        write_decision_plan_md(actions, args.plan_out)
    if args.json:
        print(
            json.dumps(
                {
                    "records": decisions_as_dicts(decisions),
                    "actions": actions_as_dicts(actions),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(format_decisions_summary(decisions))
    if args.actions_out or args.plan_out:
        print(format_action_plan_summary(actions))
    if args.out:
        print(f"decisions_summary_md: {Path(args.out)}")
    if args.actions_out:
        print(f"next_actions_jsonl: {Path(args.actions_out)}")
    if args.plan_out:
        print(f"decision_plan_md: {Path(args.plan_out)}")
    return 0


def cmd_assets(args) -> int:
    analysis_path = Path(args.analysis)
    actions_path = Path(args.actions)
    review_items_path = Path(args.review_items) if args.review_items else None
    if not analysis_path.exists():
        print(f"analysis file not found: {analysis_path}", file=sys.stderr)
        return 2
    if not actions_path.exists():
        print(f"actions file not found: {actions_path}", file=sys.stderr)
        return 2

    analysis_records = load_jsonl_records(analysis_path)
    action_records = load_jsonl_records(actions_path)
    review_items = load_jsonl_records(review_items_path) if review_items_path and review_items_path.exists() else []
    records = build_asset_index(analysis_records, action_records, review_items)
    tags_config = load_tags_config(_optional_path(args.tags_config))
    outputs = write_asset_outputs(
        records,
        args.out,
        html_dir=None if args.no_html else args.html_out,
        tags_config=tags_config,
        source_path=analysis_path,
        write_sidecars=not args.no_sidecars,
        sidecar_level=args.sidecar_level,
    )
    if args.json:
        print(
            json.dumps(
                {
                    "records": len(records),
                    "review_actions": len(action_records),
                    "review_items": len(review_items),
                    "outputs": {name: str(path) for name, path in outputs.items()},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(f"records: {len(records)}")
    print(f"review_actions: {len(action_records)}")
    print(f"review_items: {len(review_items)}")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


def cmd_sidecars(args) -> int:
    asset_index_path = Path(args.asset_index)
    if not asset_index_path.exists():
        print(f"asset index file not found: {asset_index_path}", file=sys.stderr)
        return 2
    out_dir = Path(args.out) if args.out else asset_index_path.parent
    records = attach_asset_ids(load_jsonl_records(asset_index_path))
    outputs, stats = write_sidecar_outputs(
        records,
        out_dir,
        sidecar_level=args.sidecar_level,
        dry_run=bool(args.dry_run),
        asset_index_path=asset_index_path,
    )
    if not args.dry_run:
        write_jsonl_records(records, asset_index_path)
    payload = {
        "dry_run": bool(args.dry_run),
        "records": len(records),
        "stats": stats,
        "outputs": {name: str(path) for name, path in outputs.items()},
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    action = "planned sidecars" if args.dry_run else "wrote sidecars"
    print(f"{action}: {len(records)} records")
    for key, value in stats.items():
        print(f"{key}: {value}")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


def cmd_run(args) -> int:
    state_path = Path(args.state) if args.state else Path(args.out) / "run-state.json"
    if args.status:
        if not state_path.exists():
            print(f"run state not found: {state_path}", file=sys.stderr)
            return 2
        state = load_run_state(state_path)
        _print_run_state(state, json_output=args.json)
        return 0

    if state_path.exists():
        state = load_run_state(state_path)
    else:
        if not args.roots:
            print("roots are required when creating a new run state", file=sys.stderr)
            return 2
        state = new_run_state(
            roots=[str(root) for root in args.roots],
            out_dir=args.out,
            privacy=args.privacy,
            excludes=args.excludes,
            inventory=args.inventory,
            follow_symlinks=bool(args.follow_symlinks),
            analysis_method=args.method,
            llm_config=args.llm_config,
            tags_config=args.tags_config,
        )

    stage = args.stage if args.stage != "auto" else next_stage(state)
    if stage is None:
        state["status"] = "complete"
        state["current_stage"] = "done"
        save_run_state(state, state_path)
        _print_run_state(state, json_output=args.json)
        return 0

    try:
        result = _run_one_stage(state, stage, args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    save_run_state(state, state_path)
    if args.json:
        print(json.dumps({"state": state, "result": result}, ensure_ascii=False, indent=2))
        return 0
    print(format_run_state(state))
    print("outputs:")
    print(f"- run_state: {state_path}")
    for name, path in (result.get("outputs") or {}).items():
        print(f"- {name}: {path}")
    return 0


def cmd_html(args) -> int:
    analysis_path = Path(args.analysis)
    if not analysis_path.exists():
        print(f"analysis file not found: {analysis_path}", file=sys.stderr)
        return 2
    tags_config = load_tags_config(_optional_path(args.tags_config))
    records = load_browser_records(analysis_path)
    outputs = write_knowledge_browser_html(
        records,
        args.out,
        tags_config=tags_config,
        source_path=analysis_path,
    )
    print(f"records: {len(records)}")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


def _run_one_stage(state: dict, stage: str, args) -> dict:
    mark_stage_started(state, stage)
    if stage == "scan":
        return _run_scan_stage(state, args)
    if stage == "extract":
        return _run_extract_stage(state, args)
    if stage == "analyze":
        return _run_analyze_stage(state, args)
    if stage == "review":
        return _run_review_stage(state, args)
    if stage == "assets":
        return _run_assets_stage(state)
    if stage == "html":
        return _run_html_stage(state)
    raise ValueError(f"unsupported run stage: {stage}")


def _run_scan_stage(state: dict, args) -> dict:
    paths = state["paths"]
    config = state["config"]
    stage_state = state["stages"]["scan"]
    chunk = int(stage_state.get("chunks") or 0) + 1
    scan_dir = Path(paths["scan_dir"])
    scan_dir.mkdir(parents=True, exist_ok=True)
    scan_plan = scan_dir / f"scan-plan-{chunk:04d}.md"
    access_log = scan_dir / f"access-log-{chunk:04d}.jsonl"
    limit = max(1, int(args.max_scan_entries))
    policy = PolicyEngine.from_files(_optional_path(config.get("privacy")), _optional_path(config.get("excludes")))
    result = scan_paths(
        state.get("roots") or [],
        policy,
        follow_symlinks=bool(config.get("follow_symlinks")),
        max_entries=limit,
        resume_after=stage_state.get("cursor_path"),
        sort_entries=True,
    )
    write_scan_plan(result, scan_plan)
    write_access_log(result, access_log)
    with Inventory(paths["inventory"]) as inventory:
        stored_count = inventory.upsert_entries(result.entries)
    cursor_path = result.entries[-1].path if result.entries else stage_state.get("cursor_path")
    status = "paused" if len(result.entries) >= limit else "complete"
    stats = result.stats.as_dict()
    stats["stored"] = stored_count
    stats["errors"] = len(result.errors)
    outputs = {
        "scan_plan": str(scan_plan),
        "access_log": str(access_log),
        "inventory": str(paths["inventory"]),
    }
    message = f"scanned {len(result.entries)} entries"
    mark_stage_result(
        state,
        "scan",
        status=status,
        message=message,
        stats=stats,
        outputs=outputs,
        cursor_path=cursor_path,
    )
    return {"stage": "scan", "status": status, "message": message, "stats": stats, "outputs": outputs}


def _run_extract_stage(state: dict, args) -> dict:
    paths = state["paths"]
    stage_state = state["stages"]["extract"]
    chunk = int(stage_state.get("chunks") or 0) + 1
    limit = max(1, int(args.extract_limit))
    extract_dir = Path(paths["extract_dir"])
    extract_dir.mkdir(parents=True, exist_ok=True)
    chunk_manifest = extract_dir / f"extract-manifest-{chunk:04d}.jsonl"
    aggregate_manifest = Path(paths["extract_manifest"])
    if chunk == 1 and aggregate_manifest.exists():
        aggregate_manifest.unlink()
    with Inventory(paths["inventory"]) as inventory:
        records = inventory.list_files_after(
            after_path=stage_state.get("cursor_path"),
            limit=limit,
            include_dirs=False,
        )
        latest_success = inventory.latest_success_by_path()
        latest = inventory.latest_extracts_by_path()
        plan = plan_parse_jobs_from_records(
            records,
            latest_success_by_path=latest_success,
            latest_by_path=latest,
        )
        timeout_seconds = (
            args.extract_timeout_seconds if args.extract_timeout_seconds and args.extract_timeout_seconds > 0 else None
        )
        extracted_count = 0
        stored_count = 0
        counts: Counter[str] = Counter()
        with chunk_manifest.open("w", encoding="utf-8") as chunk_handle, aggregate_manifest.open(
            "a", encoding="utf-8"
        ) as aggregate_handle:
            for result in plan.skipped:
                _write_manifest_result(chunk_handle, result)
                _write_manifest_result(aggregate_handle, result)
                stored_count += inventory.add_extract_results([result])
                counts[result.status] += 1
            for job in plan.jobs:
                result = extract_job(job, extract_dir, timeout_seconds=timeout_seconds)
                extracted_count += 1
                _write_manifest_result(chunk_handle, result)
                _write_manifest_result(aggregate_handle, result)
                stored_count += inventory.add_extract_results([result])
                counts[result.status] += 1
    cursor_path = str(records[-1]["path"]) if records else stage_state.get("cursor_path")
    status = "paused" if len(records) >= limit else "complete"
    stats = {
        "records_inspected": len(records),
        "jobs": len(plan.jobs),
        "skipped": len(plan.skipped),
        "stored": stored_count,
        "by_status": dict(counts),
    }
    outputs = {
        "chunk_manifest": str(chunk_manifest),
        "extract_manifest": str(aggregate_manifest),
    }
    message = f"inspected {len(records)} inventory records; extracted {extracted_count}"
    mark_stage_result(
        state,
        "extract",
        status=status,
        message=message,
        stats=stats,
        outputs=outputs,
        cursor_path=cursor_path,
    )
    return {"stage": "extract", "status": status, "message": message, "stats": stats, "outputs": outputs}


def _run_analyze_stage(state: dict, args) -> dict:
    paths = state["paths"]
    config = state["config"]
    stage_state = state["stages"]["analyze"]
    chunk = int(stage_state.get("chunks") or 0) + 1
    limit = max(1, int(args.analyze_limit))
    analyze_dir = Path(paths["analyze_dir"])
    analyze_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(paths["analysis_manifest"])
    index_path = Path(paths["knowledge_index"])
    if chunk == 1:
        for stale in (manifest_path, index_path):
            if stale.exists():
                stale.unlink()
    with Inventory(paths["inventory"]) as inventory:
        latest = inventory.latest_analyzable_extracts_by_path()
    cursor = str(stage_state.get("cursor_path") or "")
    cursor_key = _run_path_order_key(cursor) if cursor else ""
    records = [
        record
        for record in sorted(latest.values(), key=lambda item: _run_path_order_key(str(item.get("path", ""))))
        if not cursor_key or _run_path_order_key(str(record.get("path", ""))) > cursor_key
    ][:limit]
    method = str(config.get("analysis_method") or "rules")
    llm_config = load_llm_config(_optional_path(config.get("llm_config"))) if method in {"local-llm", "cloud-llm"} else None
    tag_config = load_tags_config(_optional_path(config.get("tags_config")))
    allowed_tags = [definition.id for definition in tag_definitions(tag_config)]
    results = analyze_extract_records(
        records,
        analysis_method=method,
        llm_config=llm_config,
        allowed_tags=allowed_tags,
    )
    result_dicts = [asdict(result) for result in results]
    _append_jsonl_records(result_dicts, manifest_path)
    _append_jsonl_records([record for record in result_dicts if record.get("status") == "ok"], index_path)
    cursor_path = str(records[-1]["path"]) if records else stage_state.get("cursor_path")
    status = "paused" if len(records) >= limit else "complete"
    outputs = {
        "analysis_manifest": str(manifest_path),
        "knowledge_index": str(index_path),
    }
    if status == "complete":
        all_results = _load_analysis_result_objects(manifest_path)
        final_outputs = write_analysis_outputs(all_results, analyze_dir)
        outputs.update({name: str(path) for name, path in final_outputs.items()})
    stats = {"records_analyzed": len(records), "by_status": analysis_stats(results)}
    message = f"analyzed {len(records)} extracted records"
    mark_stage_result(
        state,
        "analyze",
        status=status,
        message=message,
        stats=stats,
        outputs=outputs,
        cursor_path=cursor_path,
    )
    return {"stage": "analyze", "status": status, "message": message, "stats": stats, "outputs": outputs}


def _run_review_stage(state: dict, args) -> dict:
    paths = state["paths"]
    config = state["config"]
    stage_state = state["stages"]["review"]
    chunk = int(stage_state.get("chunks") or 0) + 1
    limit = max(1, int(args.review_limit))
    review_dir = Path(paths["review_dir"])
    chunks_dir = review_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    if chunk == 1:
        for stale in chunks_dir.glob("human-review-*.jsonl"):
            stale.unlink()
    analysis_records = load_analysis_manifest(paths["analysis_manifest"])
    llm_config = load_llm_config(_optional_path(config.get("llm_config")))
    with Inventory(paths["inventory"]) as inventory:
        files = inventory.list_files_after(
            after_path=stage_state.get("cursor_path"),
            limit=limit,
            include_dirs=False,
        )
        latest_extracts = inventory.latest_extracts_by_path()
    items = build_review_items(
        files,
        latest_extracts,
        analysis_records=analysis_records,
        llm_config=llm_config,
    )
    chunk_path = chunks_dir / f"human-review-{chunk:04d}.jsonl"
    _write_review_chunk(items, chunk_path)
    all_items = _load_review_chunks(chunks_dir)
    outputs = write_review_outputs(all_items, paths["review_dir"])
    status = "paused" if len(files) >= limit else "complete"
    cursor_path = str(files[-1]["path"]) if files else stage_state.get("cursor_path")
    stats = {
        "files_inspected": len(files),
        "review_items": len(items),
        "by_category": review_stats(items),
        "reason_codes": review_reason_stats(items),
    }
    output_strings = {name: str(path) for name, path in outputs.items()}
    output_strings["chunk_review_jsonl"] = str(chunk_path)
    message = f"reviewed {len(files)} files; wrote {len(all_items)} total review items"
    mark_stage_result(
        state,
        "review",
        status=status,
        message=message,
        stats=stats,
        outputs=output_strings,
        cursor_path=cursor_path,
    )
    return {"stage": "review", "status": status, "message": message, "stats": stats, "outputs": output_strings}


def _run_assets_stage(state: dict) -> dict:
    paths = state["paths"]
    config = state["config"]
    analysis_path = Path(paths["knowledge_index"])
    review_dir = Path(paths["review_dir"])
    actions_path = review_dir / "next-actions.jsonl"
    review_items_path = review_dir / "human-review.jsonl"
    tags_config = load_tags_config(_optional_path(config.get("tags_config")))
    analysis_records = load_jsonl_records(analysis_path)
    action_records = load_jsonl_records(actions_path)
    review_items = load_jsonl_records(review_items_path)
    records = build_asset_index(analysis_records, action_records, review_items)
    outputs = write_asset_outputs(
        records,
        paths["asset_dir"],
        tags_config=tags_config,
        source_path=analysis_path,
    )
    needs_review = sum(1 for record in records if bool(record.get("review_requires_confirmation")))
    stats = {
        "records": len(records),
        "review_actions": len(action_records),
        "review_items": len(review_items),
        "needs_confirmation": needs_review,
    }
    output_strings = {name: str(path) for name, path in outputs.items()}
    message = f"wrote asset index for {len(records)} records"
    mark_stage_result(
        state,
        "assets",
        status="complete",
        message=message,
        stats=stats,
        outputs=output_strings,
    )
    return {"stage": "assets", "status": "complete", "message": message, "stats": stats, "outputs": output_strings}


def _run_html_stage(state: dict) -> dict:
    paths = state["paths"]
    config = state["config"]
    tags_config = load_tags_config(_optional_path(config.get("tags_config")))
    asset_index = paths.get("asset_index") or str(Path(paths["out_dir"]) / "assets" / "asset-index.jsonl")
    source_path = Path(asset_index)
    if source_path is None or not source_path.is_file():
        source_path = Path(paths["knowledge_index"])
    records = load_browser_records(source_path)
    outputs = write_knowledge_browser_html(
        records,
        paths["html_dir"],
        tags_config=tags_config,
        source_path=source_path,
    )
    stats = {"records": len(records)}
    output_strings = {name: str(path) for name, path in outputs.items()}
    message = f"wrote HTML browser for {len(records)} records"
    mark_stage_result(
        state,
        "html",
        status="complete",
        message=message,
        stats=stats,
        outputs=output_strings,
    )
    return {"stage": "html", "status": "complete", "message": message, "stats": stats, "outputs": output_strings}


def _write_review_chunk(items: list[ReviewItem], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(asdict(item), ensure_ascii=False, sort_keys=True) + "\n")


def _load_review_chunks(chunks_dir: str | Path) -> list[ReviewItem]:
    items: list[ReviewItem] = []
    for path in sorted(Path(chunks_dir).glob("human-review-*.jsonl")):
        for record in load_jsonl_records(path):
            items.append(ReviewItem(**record))
    return items


def _run_path_order_key(path: str | Path) -> str:
    return str(Path(path).absolute()).replace("\\", "/").casefold()


def _append_jsonl_records(records: list[dict], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        output.touch(exist_ok=True)
        return
    with output.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _load_analysis_result_objects(path: str | Path) -> list[AnalysisResult]:
    records = _load_jsonl(path)
    return [AnalysisResult(**record) for record in records]


def _print_run_state(state: dict, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(format_run_state(state))


def _optional_path(value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value)
    return str(path) if path.exists() else None


def _load_jsonl(path: str | Path) -> list[dict]:
    records: list[dict] = []
    jsonl_path = Path(path)
    if not jsonl_path.exists():
        return records
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _format_privacy_summary(summary: dict, *, include_rules: bool) -> str:
    lines = [
        "privacy_policy:",
        f"- version: {summary.get('version')}",
        f"- purpose: {summary.get('purpose')}",
        f"- priority: {' > '.join(summary.get('priority', []))}",
        f"- require_allow: {str(summary.get('require_allow')).lower()}",
    ]
    setup_questions = summary.get("setup_questions") or []
    if setup_questions:
        lines.append("setup_questions:")
        lines.extend(f"- {question}" for question in setup_questions)
    lines.append("path_syntax:")
    lines.extend(f"- {item}" for item in summary.get("path_syntax", []))
    lines.append("policies:")
    for policy in summary.get("policies", []):
        lines.append(f"- {policy['policy']}: {policy['title']}")
        lines.append(f"  effect: {policy['effect']}")
        lines.append(f"  when_to_use: {policy['when_to_use']}")
        questions = policy.get("questions") or []
        if questions:
            lines.append("  questions:")
            lines.extend(f"  - {question}" for question in questions)
        examples = policy.get("examples") or []
        if examples:
            lines.append("  examples:")
            lines.extend(f"  - {example}" for example in examples)
        if include_rules:
            rules = policy.get("rules") or {}
            lines.append("  rules:")
            if not rules:
                lines.append("  - none")
            for rule_type, values in rules.items():
                for value in values:
                    lines.append(f"  - {rule_type}: {value}")
        else:
            counts = policy.get("rule_counts") or {}
            count_text = ", ".join(f"{key}={value}" for key, value in counts.items()) or "none"
            lines.append(f"  rule_counts: {count_text}")
    return "\n".join(lines)


def _format_roots_summary(summary: dict) -> str:
    lines = [
        "roots_config:",
        f"- version: {summary.get('version')}",
        f"- purpose: {summary.get('purpose')}",
    ]
    setup_questions = summary.get("setup_questions") or []
    if setup_questions:
        lines.append("setup_questions:")
        lines.extend(f"- {question}" for question in setup_questions)
    selection_notes = summary.get("selection_notes") or []
    if selection_notes:
        lines.append("selection_notes:")
        lines.extend(f"- {note}" for note in selection_notes)
    lines.append("roots:")
    for root in summary.get("roots", []):
        resolved = root.get("resolved") or {}
        path = resolved.get("path", "")
        exists = str(resolved.get("exists", False)).lower() if resolved else "unresolved"
        lines.append(
            f"- {root.get('name')}: enabled={str(root.get('enabled')).lower()} "
            f"risk={root.get('risk')} resolver={root.get('resolver')} exists={exists}"
        )
        if path:
            lines.append(f"  path: {path}")
        if root.get("description"):
            lines.append(f"  description: {root.get('description')}")
        if root.get("recommended_policy"):
            lines.append(f"  recommended_policy: {root.get('recommended_policy')}")
    return "\n".join(lines)


def _format_tags_summary(summary: dict) -> str:
    lines = [
        "tags_config:",
        f"- version: {summary.get('version')}",
        f"- purpose: {summary.get('purpose')}",
        f"- tag_count: {summary.get('tag_count')}",
        f"- filtered_tag_count: {summary.get('filtered_tag_count', summary.get('tag_count'))}",
    ]
    principles = summary.get("design_principles") or []
    if principles:
        lines.append("design_principles:")
        lines.extend(f"- {principle}" for principle in principles)
    inherited = summary.get("inherited_patterns") or []
    if inherited:
        lines.append("inherited_patterns:")
        for item in inherited:
            lines.append(f"- {item.get('system')}: {item.get('keep')}")
    dimensions = summary.get("dimensions") or []
    if dimensions:
        lines.append("dimensions:")
        for dimension in dimensions:
            lines.append(f"- {dimension.get('id')}: {dimension.get('zh')}")
            if dimension.get("purpose"):
                lines.append(f"  purpose: {dimension.get('purpose')}")
    output_fields = summary.get("output_fields") or {}
    if output_fields:
        lines.append("output_fields:")
        for name, description in output_fields.items():
            lines.append(f"- {name}: {description}")
    tags = summary.get("tags") or []
    if tags:
        lines.append("tags:")
        for tag in tags:
            lines.append(f"- {tag.get('id')}: {tag.get('zh')}")
            lines.append(f"  dimension: {tag.get('dimension')}")
            if tag.get("description"):
                lines.append(f"  description: {tag.get('description')}")
            if tag.get("aliases"):
                lines.append("  aliases: " + ", ".join(str(item) for item in tag.get("aliases")))
            if tag.get("recommended_policy"):
                lines.append(f"  recommended_policy: {tag.get('recommended_policy')}")
            if tag.get("default_sensitivity"):
                lines.append(f"  default_sensitivity: {tag.get('default_sensitivity')}")
    return "\n".join(lines)


def _format_llm_summary(summary: dict) -> str:
    lines = [
        "llm_config:",
        f"- version: {summary.get('version')}",
        f"- purpose: {summary.get('purpose')}",
        f"- mode: {summary.get('mode')}",
        f"- provider: {summary.get('provider')}",
        f"- model: {summary.get('model')}",
        f"- analysis_max_prompt_chars: {summary.get('analysis_max_prompt_chars')}",
        f"- analysis_timeout_seconds: {summary.get('analysis_timeout_seconds')}",
        f"- local_enabled: {str(summary.get('local_enabled')).lower()}",
        f"- local_ready: {str(summary.get('local_ready')).lower()}",
        f"- local_provider: {summary.get('local_provider')}",
        f"- local_model: {summary.get('local_model')}",
        f"- local_endpoint: {summary.get('local_endpoint')}",
        f"- local_loopback_only: {str(summary.get('local_loopback_only')).lower()}",
        f"- cloud_enabled: {str(summary.get('cloud_enabled')).lower()}",
        f"- cloud_provider: {summary.get('cloud_provider')}",
        f"- cloud_model: {summary.get('cloud_model')}",
        f"- cloud_api_key_env: {summary.get('cloud_api_key_env')}",
        f"- cloud_risk_acknowledged: {str(summary.get('cloud_risk_acknowledged')).lower()}",
        f"- cloud_allowed_paths: {len(summary.get('cloud_allowed_paths') or [])}",
    ]
    privacy_notes = summary.get("privacy_notes") or []
    if privacy_notes:
        lines.append("privacy_notes:")
        lines.extend(f"- {note}" for note in privacy_notes)
    setup_questions = summary.get("setup_questions") or []
    if setup_questions:
        lines.append("setup_questions:")
        lines.extend(f"- {question}" for question in setup_questions)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
