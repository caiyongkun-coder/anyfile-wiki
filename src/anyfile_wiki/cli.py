from __future__ import annotations

from argparse import ArgumentParser
import json
from pathlib import Path
import sys

from .analyze import (
    analyze_extract_records,
    analysis_stats,
    write_analysis_comparison_md,
    write_analysis_outputs,
)
from .decisions import (
    decisions_as_dicts,
    format_decisions_summary,
    load_review_decisions,
    write_decisions_summary_md,
)
from .html import load_browser_records, write_knowledge_browser_html
from .inventory import Inventory
from .llm_config import describe_llm_config, load_llm_config
from .parse import extract_jobs, plan_parse_jobs_from_records, write_manifest
from .policy import PolicyEngine, describe_privacy_policy, load_policy
from .report import write_access_log, write_scan_plan
from .review import build_review_items, load_analysis_manifest, review_stats, write_review_outputs
from .roots import describe_roots_config, discover_candidate_roots, load_roots_config
from .scan import scan_paths
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
    extract.add_argument("--manifest", default=None, help="Manifest JSONL path")
    extract.add_argument("--force", action="store_true", help="Re-extract even when source appears unchanged")
    extract.add_argument("--retry-failed", action="store_true", help="Only retry records whose latest extraction failed or skipped")
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

    decisions = subparsers.add_parser("decisions", help="Read human review decisions exported from HTML")
    decisions.add_argument("--decisions", default="data/review/review-decisions.jsonl", help="review-decisions.jsonl path")
    decisions.add_argument("--out", default=None, help="Optional Markdown summary path")
    decisions.add_argument("--json", action="store_true", help="Emit JSON")
    decisions.set_defaults(func=cmd_decisions)

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
    plan = plan_parse_jobs_from_records(
        records,
        latest_success_by_path=latest_success,
        latest_by_path=latest,
        force=args.force,
        retry_failed=args.retry_failed,
    )
    extracted = extract_jobs(plan.jobs, output_dir)
    results = [*plan.skipped, *extracted]
    write_manifest(results, manifest_path)
    with Inventory(inventory_path) as inventory:
        stored_count = inventory.add_extract_results(results)
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    print(f"jobs: {len(plan.jobs)}")
    print(f"planned: {len(plan.jobs)}")
    print(f"skipped: {len(plan.skipped)}")
    print(f"manifest: {manifest_path}")
    print(f"stored: {stored_count}")
    for status, count in sorted(counts.items()):
        print(f"{status}: {count}")
    return 0 if not any(result.status == "error" for result in results) else 1


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
    if args.json:
        print(json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2))
        return 0
    print(f"files_inspected: {len(files)}")
    print(f"review_items: {len(items)}")
    for name, path in outputs.items():
        print(f"{name}: {path}")
    for category, count in sorted(stats.items()):
        print(f"{category}: {count}")
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
    if args.out:
        write_decisions_summary_md(decisions, args.out)
    if args.json:
        print(json.dumps({"records": decisions_as_dicts(decisions)}, ensure_ascii=False, indent=2))
        return 0
    print(format_decisions_summary(decisions))
    if args.out:
        print(f"decisions_summary_md: {Path(args.out)}")
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
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
