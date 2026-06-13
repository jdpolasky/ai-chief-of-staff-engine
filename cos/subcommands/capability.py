"""`cos capability <task-class>` -- consult the routing registry before picking a tool.

The capability registry (capability/registry.json) is owner-curated routing
memory: for a class of task, it records the best route, an ordered fallback
ladder, and dead ends that carry a retest date. The agent reads it BEFORE
choosing a tool, so a routing lesson learned once is not re-discovered at the
cost of a failed attempt every session.

Operations:
  cos capability <task-class>   print best route, ladder, and live dead ends
  cos capability --list         list the known task classes

This is a read-only lookup the owner (or the agent on the owner's behalf) runs
from the command line. Unlike the enforcement hooks, which fail OPEN so a bug in
a hook can never wedge a live session, this command fails LOUD: a malformed or
missing registry exits nonzero with the reason on stderr, because a CLI the
owner runs should tell them their registry is broken rather than silently
pretending it routed. Standard library only.

The registry path resolves from COS_CAPABILITY_REGISTRY if set, else the
capability/registry.json shipped at the repo root (two levels up from this
module's package). This mirrors the kit's env-var seam in cos/config.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

# repo root = three levels up from this file (cos/subcommands/capability.py).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_REGISTRY_PATH = REPO_ROOT / "capability" / "registry.json"


class RegistryError(Exception):
    """The registry file is missing, unreadable, or malformed. Fail loud."""


def _ensure_utf8_stdout() -> None:
    """Force stdout to UTF-8 with replace error handling.

    Registry prose can carry smart punctuation that crashes on the Windows
    console default cp1252. Idempotent; no-op on streams without reconfigure.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _registry_path(args: argparse.Namespace) -> Path:
    """Resolve the registry path: --registry flag, then env, then the default."""
    if getattr(args, "registry", None):
        return Path(args.registry).expanduser()
    env = os.environ.get("COS_CAPABILITY_REGISTRY")
    if env:
        return Path(env).expanduser()
    return DEFAULT_REGISTRY_PATH


def load_registry(path: Path) -> list[dict]:
    """Read and validate the registry. Returns the list of task-class entries.

    Fails loud (raises RegistryError) on a missing file, invalid JSON, or a
    structurally wrong document. This is the deliberate contrast with the
    enforcement hooks' fail-open posture: an owner running this command should
    learn their registry is broken, not get silent wrong routing.
    """
    if not path.exists():
        raise RegistryError(f"registry not found at {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RegistryError(f"registry is not valid JSON ({path}): {e}")
    if not isinstance(raw, dict):
        raise RegistryError(
            f"registry root must be a JSON object, got {type(raw).__name__}"
        )
    classes = raw.get("task_classes")
    if not isinstance(classes, list):
        raise RegistryError("registry is missing a 'task_classes' list")
    for i, entry in enumerate(classes):
        if not isinstance(entry, dict):
            raise RegistryError(f"task_classes[{i}] must be an object")
        if not entry.get("task_class"):
            raise RegistryError(f"task_classes[{i}] is missing 'task_class'")
    return classes


def _find_class(classes: list[dict], name: str) -> dict | None:
    """Return the entry whose task_class matches name (exact, then case-fold)."""
    for entry in classes:
        if entry.get("task_class") == name:
            return entry
    lowered = name.lower()
    for entry in classes:
        if str(entry.get("task_class", "")).lower() == lowered:
            return entry
    return None


def _is_expired(retest_after: str, today: date) -> bool:
    """True if the retest date has arrived (dead end is due for a retry).

    An unparseable date is treated as NOT expired: a typo should not silently
    promote a dead end to a retest. The registry is owner-curated, so a bad date
    is the owner's to fix, and meanwhile the safe reading is "still a dead end".
    """
    try:
        return date.fromisoformat(str(retest_after)) <= today
    except (TypeError, ValueError):
        return False


def _print_entry(entry: dict, today: date) -> None:
    """Print one task class: best route, ladder, live and due-for-retest dead ends."""
    print(f"task class: {entry.get('task_class', '(unnamed)')}")
    desc = entry.get("description")
    if desc:
        print(f"  {desc}")
    print()
    print(f"  best route: {entry.get('best_route', '(none recorded)')}")

    ladder = entry.get("ladder") or []
    print()
    print("  fallback ladder:")
    if ladder:
        for i, rung in enumerate(ladder, start=1):
            print(f"    {i}. {rung}")
    else:
        print("    (none recorded)")

    dead_ends = entry.get("dead_ends") or []
    print()
    print("  dead ends:")
    if not dead_ends:
        print("    (none recorded)")
    else:
        for de in dead_ends:
            route = de.get("route", "(unspecified route)")
            reason = de.get("reason", "")
            retest = de.get("retest_after", "")
            if retest and _is_expired(retest, today):
                # A dead end past its retest date is NOT hidden: it is surfaced
                # with a RETEST flag so the agent re-tries the route once and
                # proposes an update based on the result.
                print(f"    [RETEST {retest}] {route}")
            else:
                when = f" (retest after {retest})" if retest else ""
                print(f"    [avoid{when}] {route}")
            if reason:
                print(f"        why: {reason}")

    notes = entry.get("notes")
    if notes:
        print()
        print(f"  notes: {notes}")


def cmd_capability(args: argparse.Namespace) -> int:
    """Look up a task class, or --list the known classes. Read-only.

    Exit codes: 0 on a found class or a successful --list, 1 on an unknown class
    (graceful message), 2 on a broken registry (fail loud).
    """
    _ensure_utf8_stdout()
    path = _registry_path(args)
    try:
        classes = load_registry(path)
    except RegistryError as e:
        print(f"cos capability: {e}", file=sys.stderr)
        return 2

    if args.list:
        if not classes:
            print("(no task classes in the registry)")
            return 0
        print("known task classes:")
        for entry in classes:
            name = entry.get("task_class", "(unnamed)")
            desc = entry.get("description", "")
            if desc:
                print(f"  {name}  --  {desc}")
            else:
                print(f"  {name}")
        return 0

    entry = _find_class(classes, args.task_class)
    if entry is None:
        known = ", ".join(str(e.get("task_class")) for e in classes) or "(none)"
        print(
            f"cos capability: no task class {args.task_class!r} in the registry.\n"
            f"  known classes: {known}\n"
            f"  run 'python -m cos capability --list' to see them, or propose a new "
            f"entry to the owner.",
            file=sys.stderr,
        )
        return 1

    _print_entry(entry, date.today())
    return 0


def register(subparsers):
    p = subparsers.add_parser(
        "capability",
        help="Consult the routing registry for a task class before picking a tool.",
    )
    p.add_argument(
        "task_class", nargs="?", default=None,
        help="the task class to look up (omit with --list)",
    )
    p.add_argument(
        "--list", action="store_true",
        help="list the known task classes instead of looking one up",
    )
    p.add_argument(
        "--registry", default=None,
        help=f"path to registry.json (default: COS_CAPABILITY_REGISTRY or "
             f"{DEFAULT_REGISTRY_PATH})",
    )
    p.set_defaults(func=_dispatch)


def _dispatch(args: argparse.Namespace) -> int:
    """Guard: exactly one of <task-class> or --list is required."""
    if args.list and args.task_class:
        print("cos capability: give a task class OR --list, not both",
              file=sys.stderr)
        return 2
    if not args.list and not args.task_class:
        print("cos capability: a task class is required (or --list to see them)",
              file=sys.stderr)
        return 2
    return cmd_capability(args)
