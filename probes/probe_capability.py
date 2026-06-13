"""probe_capability -- the capability registry lookup routes every path.

Run from the repo root:

    python probes/probe_capability.py

Drives `python -m cos capability` as a subprocess against throwaway registry
files (never the shipped one) and asserts every branch:

  - --list prints the known task classes (exit 0)
  - a known class prints best route, ladder, and dead ends (exit 0)
  - an unknown class exits 1 with a graceful message (not a crash)
  - an UNEXPIRED dead end is shown with an [avoid] flag, not RETEST
  - an EXPIRED dead end (retest_after in the past) is shown with a RETEST flag
    instead of being hidden
  - a malformed registry (bad JSON) FAILS LOUD: exit 2 with a reason on stderr
  - a missing registry FAILS LOUD: exit 2
  - the usage guards: no args and both args each exit 2

The fail-loud assertions are the deliberate contrast with the enforcement
hooks, which fail OPEN. A hook must never wedge a live session, so a broken hook
allows the action. This is a CLI the owner runs by hand, so a broken registry
should tell the owner loudly rather than silently pretend it routed. The probe
pins that contrast: malformed/missing here is exit 2, not a silent allow.

No pytest dependency. Exits 0 on pass, nonzero with a printed FAIL reason.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def run_cap(registry_path: Path | None, *cli_args: str) -> dict:
    """Run `python -m cos capability <cli_args>` with COS_CAPABILITY_REGISTRY
    pointed at registry_path (or unset if None). Returns exit/out/err."""
    env = dict(os.environ)
    if registry_path is not None:
        env["COS_CAPABILITY_REGISTRY"] = str(registry_path)
    proc = subprocess.run(
        [sys.executable, "-m", "cos", "capability", *cli_args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
    }


def write_registry(path: Path, today: date) -> None:
    """Write a small valid registry: one unexpired dead end, one expired."""
    past = (today - timedelta(days=10)).isoformat()
    future = (today + timedelta(days=365)).isoformat()
    doc = {
        "task_classes": [
            {
                "task_class": "vault-file-operations",
                "description": "Reading or writing files in the owner's vault.",
                "best_route": "The notes app's API integration.",
                "ladder": ["The app integration.", "A direct file edit when closed."],
                "dead_ends": [
                    {
                        "route": "Editing on disk while the app holds a lock.",
                        "reason": "The app overwrites the on-disk change on save.",
                        "retest_after": future,
                    }
                ],
                "notes": "Prefer the integration for anything open.",
            },
            {
                "task_class": "web-public-read",
                "description": "Fetching a public page with no login.",
                "best_route": "A plain HTTP fetch.",
                "ladder": ["A plain HTTP fetch.", "A headless browser."],
                "dead_ends": [
                    {
                        "route": "Retrying a plain fetch on a script-rendered page.",
                        "reason": "The body never arrives in the raw HTML.",
                        "retest_after": past,
                    }
                ],
                "notes": "Escalate to the renderer instead of retrying.",
            },
        ]
    }
    path.write_text(json.dumps(doc), encoding="utf-8")


def probe_list(registry: Path) -> None:
    res = run_cap(registry, "--list")
    check(res["exit_code"] == 0, f"--list: exit {res['exit_code']}")
    check("vault-file-operations" in res["stdout"], "--list: missing first class")
    check("web-public-read" in res["stdout"], "--list: missing second class")


def probe_known_class(registry: Path) -> None:
    res = run_cap(registry, "vault-file-operations")
    check(res["exit_code"] == 0, f"known class: exit {res['exit_code']}")
    out = res["stdout"]
    check("best route" in out, "known class: best route not printed")
    check("API integration" in out, "known class: best route text missing")
    check("fallback ladder" in out, "known class: ladder header missing")
    check("1. The app integration." in out, "known class: ladder rung missing")
    check("dead ends" in out, "known class: dead-ends header missing")
    # This class's dead end is UNEXPIRED -> [avoid], never RETEST.
    check("[avoid" in out, "known class: unexpired dead end should show [avoid]")
    check("RETEST" not in out, "known class: unexpired dead end must NOT show RETEST")


def probe_expired_vs_unexpired(registry: Path) -> None:
    # web-public-read's dead end is in the past -> RETEST flag, not hidden.
    res = run_cap(registry, "web-public-read")
    check(res["exit_code"] == 0, f"expired class: exit {res['exit_code']}")
    out = res["stdout"]
    check("RETEST" in out, "expired dead end: should surface a RETEST flag")
    check("Retrying a plain fetch" in out,
          "expired dead end: the route must still be shown, not hidden")


def probe_unknown_class(registry: Path) -> None:
    res = run_cap(registry, "no-such-task-class")
    check(res["exit_code"] == 1, f"unknown class: expected exit 1, got {res['exit_code']}")
    check("no task class" in res["stderr"].lower(),
          "unknown class: should print a graceful message on stderr")
    check("known classes" in res["stderr"].lower(),
          "unknown class: should list the known classes to help the owner")


def probe_malformed_fails_loud(tmp: Path) -> None:
    bad = tmp / "broken.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    res = run_cap(bad, "vault-file-operations")
    check(res["exit_code"] == 2,
          f"malformed registry: expected exit 2 (fail loud), got {res['exit_code']}")
    check(res["stderr"].strip() != "",
          "malformed registry: should print a reason on stderr, not fail silent")
    check("json" in res["stderr"].lower(),
          "malformed registry: reason should name the JSON problem")

    # --list against the same broken file also fails loud.
    res = run_cap(bad, "--list")
    check(res["exit_code"] == 2, "malformed registry: --list should also fail loud")


def probe_missing_fails_loud(tmp: Path) -> None:
    missing = tmp / "does-not-exist.json"
    res = run_cap(missing, "vault-file-operations")
    check(res["exit_code"] == 2,
          f"missing registry: expected exit 2 (fail loud), got {res['exit_code']}")
    check("not found" in res["stderr"].lower(),
          "missing registry: stderr should say the file was not found")


def probe_usage_guards(registry: Path) -> None:
    # No task class and no --list -> usage error, exit 2.
    res = run_cap(registry)
    check(res["exit_code"] == 2, f"no-args guard: expected exit 2, got {res['exit_code']}")
    # Both a task class AND --list -> usage error, exit 2.
    res = run_cap(registry, "vault-file-operations", "--list")
    check(res["exit_code"] == 2, f"both-args guard: expected exit 2, got {res['exit_code']}")


def probe_default_registry_loads() -> None:
    """With no env override, the shipped capability/registry.json must load and
    list cleanly. This proves the default path resolution and that the seeded
    file is well-formed."""
    res = run_cap(None, "--list")
    check(res["exit_code"] == 0,
          f"shipped registry --list: exit {res['exit_code']}: {res['stderr']!r}")
    check("vault-file-operations" in res["stdout"],
          "shipped registry: expected the seeded vault class in --list")


def main() -> int:
    today = date.today()
    tmp = Path(tempfile.mkdtemp(prefix="probe_capability_"))
    try:
        registry = tmp / "registry.json"
        write_registry(registry, today)

        probe_list(registry)
        probe_known_class(registry)
        probe_expired_vs_unexpired(registry)
        probe_unknown_class(registry)
        probe_malformed_fails_loud(tmp)
        probe_missing_fails_loud(tmp)
        probe_usage_guards(registry)
        probe_default_registry_loads()
    except ProbeFail as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"FAIL: unexpected error: {e!r}")
        traceback.print_exc()
        return 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("PASS: probe_capability  list/known/unknown/expired/malformed, fail-loud")
    return 0


if __name__ == "__main__":
    sys.exit(main())
