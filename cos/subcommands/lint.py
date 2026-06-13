"""`cos lint` -- deterministic structural checks over the memory corpus.

A self-tending ritual: silent on success, loud on findings. Runs the five
checks in `cos.lint` (index-orphans, frontmatter-malformed, stale-superseded,
duplicate-names, broken-wikilinks) over COS_MEMORY_DIR (or `--memory-dir`) and
prints a one-line-per-finding report. Exit 0 with "corpus clean" when nothing is
found; exit 1 when findings exist, so a scheduled run can gate on it.

Read-only by construction: it never writes a file or touches the database.

  python -m cos lint
  python -m cos lint --memory-dir path/to/memory
  python -m cos lint --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cos.lint import run_lint
from cos.memory.loader import DEFAULT_MEMORY_DIR


def run(args: argparse.Namespace) -> int:
    memory_dir = Path(args.memory_dir) if args.memory_dir else DEFAULT_MEMORY_DIR

    if not memory_dir.is_dir():
        print(f"cos lint: memory dir not found at {memory_dir}", file=sys.stderr)
        return 2

    findings = run_lint(memory_dir)

    if args.json:
        payload = {
            "memory_dir": str(memory_dir),
            "clean": not findings,
            "count": len(findings),
            "findings": [f.to_dict() for f in findings],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if not findings else 1

    if not findings:
        print("corpus clean")
        return 0

    for f in findings:
        print(f.to_line())
    n = len(findings)
    print(f"\n{n} finding{'s' if n != 1 else ''} in {memory_dir}")
    return 1


def register(subparsers):
    p = subparsers.add_parser(
        "lint",
        help="Structural checks over the memory corpus (read-only). "
             "Silent on success, lists findings on drift.",
    )
    p.add_argument(
        "--memory-dir", dest="memory_dir", default=None,
        help=f"path to memory .md files (default: {DEFAULT_MEMORY_DIR})",
    )
    p.add_argument(
        "--json", action="store_true",
        help="machine-readable JSON output (one object) instead of plain lines",
    )
    p.set_defaults(func=run)
