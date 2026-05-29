from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    source_skill = repo_root / "skills" / "anyfile-wiki"
    codex_home = Path(args.codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    target_skill = Path(args.target or codex_home / "skills" / "anyfile-wiki")
    if not source_skill.exists():
        print(f"source skill not found: {source_skill}", file=sys.stderr)
        return 2

    pip_command = _pip_command(args, repo_root)
    print("AnyFile Wiki agent skill installer")
    if pip_command:
        print(f"- package install: {_format_command(pip_command)}")
    else:
        print("- package install: skipped")
    print(f"- skill source: {source_skill}")
    print(f"- skill target: {target_skill}")
    print(f"- dry_run: {bool(args.dry_run)}")

    if args.dry_run:
        return 0

    if pip_command:
        subprocess.run(pip_command, cwd=repo_root, check=True)
    copy_skill(source_skill, target_skill)
    print(f"installed skill: {target_skill}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install the AnyFile Wiki package and Codex skill")
    parser.add_argument("--editable", action="store_true", help="Install the package with pip -e")
    parser.add_argument("--extras", default="parse,ocr", help="Comma-separated extras, e.g. parse,ocr")
    parser.add_argument("--no-deps", action="store_true", help="Pass --no-deps to pip install")
    parser.add_argument("--skill-only", action="store_true", help="Only copy the skill; skip pip install")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without writing files")
    parser.add_argument("--codex-home", default=None, help="Codex home directory; defaults to CODEX_HOME or ~/.codex")
    parser.add_argument("--target", default=None, help="Explicit target skill directory")
    return parser


def _pip_command(args: argparse.Namespace, repo_root: Path) -> list[str]:
    if args.skill_only:
        return []
    extras = [item.strip() for item in str(args.extras or "").split(",") if item.strip()]
    spec = "."
    if extras:
        spec += "[" + ",".join(extras) + "]"
    command = [sys.executable, "-m", "pip", "install"]
    if args.editable:
        command.append("-e")
    command.append(spec)
    if args.no_deps:
        command.append("--no-deps")
    return command


def copy_skill(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def _format_command(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


if __name__ == "__main__":
    raise SystemExit(main())
