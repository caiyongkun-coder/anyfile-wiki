from __future__ import annotations

from argparse import ArgumentParser
import json
from pathlib import Path
import sys

from .inventory import Inventory
from .parse import build_parse_jobs_from_records, extract_jobs, write_manifest
from .policy import PolicyEngine
from .report import write_access_log, write_scan_plan
from .roots import discover_candidate_roots
from .scan import scan_paths


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="pfkb", description="Personal File Knowledge Base MVP0 CLI")
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
    roots.add_argument("--include-missing", action="store_true", help="Also show roots that do not exist")
    roots.add_argument("--json", action="store_true", help="Emit JSON")
    roots.set_defaults(func=cmd_roots)

    extract = subparsers.add_parser("extract", help="Extract content for inventory records allowed by policy")
    extract.add_argument("--inventory", default="data/inventory.sqlite", help="SQLite inventory path")
    extract.add_argument("--out", default="data/extract", help="Extraction output directory")
    extract.add_argument("--limit", type=int, default=100, help="Maximum inventory records to inspect")
    extract.add_argument("--manifest", default=None, help="Manifest JSONL path")
    extract.set_defaults(func=cmd_extract)

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
    roots = discover_candidate_roots(existing_only=not args.include_missing)
    payload = [
        {
            "name": root.name,
            "path": str(root.path),
            "exists": root.exists,
            "source": root.source,
        }
        for root in roots
    ]
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for root in roots:
        status = "exists" if root.exists else "missing"
        print(f"{root.name}\t{status}\t{root.path}")
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
    jobs = build_parse_jobs_from_records(records)
    results = extract_jobs(jobs, output_dir)
    write_manifest(results, manifest_path)
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    print(f"jobs: {len(jobs)}")
    print(f"manifest: {manifest_path}")
    for status, count in sorted(counts.items()):
        print(f"{status}: {count}")
    return 0 if not any(result.status == "error" for result in results) else 1


def _optional_path(value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value)
    return str(path) if path.exists() else None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
