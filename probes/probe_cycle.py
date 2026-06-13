"""probe_cycle -- the `cos cycle` reader renders every cycle state correctly.

Run from the repo root:

    python probes/probe_cycle.py

Builds throwaway cycle directories in a tempdir and drives cos.subcommands.cycle
through every path, asserting on captured stdout/stderr and the exit code:

  active:    week-of-12 and days-left math; lead-measure totals summed across
             weeks per goal column; last week's score and note rendered.
  planning:  pending line, no score table required; exit 0.
  paused:    pause line with no shame language; exit 0.
  missing:   empty (or absent) cycles dir -> calm one-liner, exit 0.
  malformed: no frontmatter, unterminated frontmatter, bad status, bad date,
             missing scores section, and a non-integer Week cell each exit 1
             loudly (this is an owner-run CLI, not a hook, so it does not fail
             open).
  selection: an `active` cycle is chosen over a `planning` one; a `complete`
             cycle is ignored.

Self-contained: writes its own .md fixtures, never touches cycles/cycle-1-example.md
or the shipped config. Exits 0 on pass; nonzero with a printed FAIL reason. No
pytest dependency.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cos.subcommands.cycle import run  # noqa: E402


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def run_cycle(cycles_dir: Path, today: str | None = None) -> tuple[int, str, str]:
    """Invoke the command with a synthetic argparse Namespace; capture I/O."""
    args = argparse.Namespace(cycles_dir=str(cycles_dir), today=today)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = run(args)
    return code, out.getvalue(), err.getvalue()


ACTIVE_CYCLE = """---
cycle: 1
start: 2026-04-06
end: 2026-06-28
status: active
---

# Cycle 1 — test

## The one sentence

Test the reader.

## Weekly scores

| Week | Goal 1 | Goal 2 | Score | Note |
|------|--------|--------|-------|------|
| 1 | conversations 5, case studies 1 | species 8, price checks 2 | 4/4 | Clean week. |
| 2 | conversations 6, case studies 1 | species 9, price checks 1 | 3/4 | One short. |

## Review log

- 2026-04-06: opened.
"""

PLANNING_CYCLE = """---
cycle: 2
start: 2026-09-01
end: 2026-11-23
status: planning
---

# Cycle 2 — test

## The one sentence

Not started yet.

## Weekly scores

| Week | Goal 1 | Score | Note |
|------|--------|-------|------|
|      |        |       |      |
"""

PAUSED_CYCLE = """---
cycle: 3
start: 2026-04-06
end: 2026-06-28
status: paused
---

# Cycle 3 — test

## The one sentence

Paused by choice.

## Weekly scores

| Week | Goal 1 | Score | Note |
|------|--------|-------|------|
| 1 | conversations 3 | 0/1 | Then paused. |
"""

COMPLETE_CYCLE = """---
cycle: 0
start: 2026-01-06
end: 2026-03-29
status: complete
---

# Cycle 0 — done

## The one sentence

Already finished.

## Weekly scores

| Week | Goal 1 | Score | Note |
|------|--------|-------|------|
| 12 | conversations 5 | 1/1 | Closed. |
"""


def make_dir(root: Path, name: str, files: dict[str, str]) -> Path:
    d = root / name
    d.mkdir()
    for fname, content in files.items():
        (d / fname).write_text(content, encoding="utf-8")
    return d


def probe_active(root: Path) -> None:
    d = make_dir(root, "active", {"cycle-1.md": ACTIVE_CYCLE})
    # week 2: (2026-04-13 - 2026-04-06) = 7 days -> week 2.
    code, out, err = run_cycle(d, today="2026-04-13")
    check(code == 0, f"active: exit {code}, stderr={err!r}")
    check("week 2 of 12" in out, f"active: expected 'week 2 of 12', got {out!r}")
    # days left from 2026-04-13 to 2026-06-28 = 76.
    check("76 days left" in out, f"active: expected '76 days left', got {out!r}")
    # totals summed across both weeks: conversations 5+6=11, case studies 2.
    check("conversations 11" in out, f"active: conversations total wrong: {out!r}")
    check("case studies 2" in out, f"active: case studies total wrong: {out!r}")
    check("species 17" in out, f"active: species total wrong: {out!r}")
    # last scored week is week 2, score 3/4, note rendered.
    check("week 2): 3/4" in out, f"active: last-week score wrong: {out!r}")
    check("One short." in out, f"active: last-week note missing: {out!r}")


def probe_active_week_clamp(root: Path) -> None:
    # A date past the end clamps the week to 12 and floors days-left at 0.
    d = make_dir(root, "active-late", {"cycle-1.md": ACTIVE_CYCLE})
    code, out, err = run_cycle(d, today="2026-08-01")
    check(code == 0, f"active-late: exit {code}, stderr={err!r}")
    check("week 12 of 12" in out, f"active-late: week should clamp to 12: {out!r}")
    check("0 days left" in out, f"active-late: days-left should floor at 0: {out!r}")


def probe_planning(root: Path) -> None:
    d = make_dir(root, "planning", {"cycle-2.md": PLANNING_CYCLE})
    code, out, err = run_cycle(d, today="2026-08-01")
    check(code == 0, f"planning: exit {code}, stderr={err!r}")
    check("planning" in out.lower(), f"planning: should name the planning state: {out!r}")
    check("starts in" in out, f"planning: should say when it starts: {out!r}")
    check("week 12" not in out, "planning: should not render an active scoreboard")


def probe_paused(root: Path) -> None:
    d = make_dir(root, "paused", {"cycle-3.md": PAUSED_CYCLE})
    code, out, err = run_cycle(d, today="2026-05-01")
    check(code == 0, f"paused: exit {code}, stderr={err!r}")
    check("paused" in out.lower(), f"paused: should name the paused state: {out!r}")
    # No shame language: the pause line is neutral.
    for banned in ("fail", "behind", "should have", "overdue"):
        check(banned not in out.lower(),
              f"paused: line carries shame word {banned!r}: {out!r}")


def probe_missing(root: Path) -> None:
    # Empty directory.
    d = make_dir(root, "empty", {})
    code, out, err = run_cycle(d, today="2026-05-01")
    check(code == 0, f"missing(empty): exit {code}, stderr={err!r}")
    check("No active cycle" in out, f"missing(empty): expected calm line, got {out!r}")
    # Absent directory entirely.
    code, out, err = run_cycle(root / "does-not-exist", today="2026-05-01")
    check(code == 0, f"missing(absent): exit {code}, stderr={err!r}")
    check("No active cycle" in out, f"missing(absent): expected calm line, got {out!r}")


def probe_selection(root: Path) -> None:
    # active beats planning; complete is ignored.
    d = make_dir(root, "select", {
        "cycle-1.md": ACTIVE_CYCLE,
        "cycle-2.md": PLANNING_CYCLE,
        "cycle-0.md": COMPLETE_CYCLE,
    })
    code, out, err = run_cycle(d, today="2026-04-13")
    check(code == 0, f"selection: exit {code}, stderr={err!r}")
    check("Cycle 1" in out and "week" in out,
          f"selection: active cycle 1 should win, got {out!r}")
    # The template file is always skipped, even if present.
    (d / "CYCLE-TEMPLATE.md").write_text(ACTIVE_CYCLE.replace("cycle: 1", "cycle: 99"),
                                         encoding="utf-8")
    code, out, err = run_cycle(d, today="2026-04-13")
    check("Cycle 99" not in out, "selection: CYCLE-TEMPLATE.md must be skipped")


def probe_malformed(root: Path) -> None:
    cases = {
        "no-fm": "no frontmatter at all\n",
        "unterminated-fm": "---\ncycle: 1\nstatus: active\n(no closing dashes)\n",
        "bad-status":
            "---\ncycle: 1\nstart: 2026-04-06\nend: 2026-06-28\nstatus: bogus\n---\nbody\n",
        "bad-date":
            "---\ncycle: 1\nstart: not-a-date\nend: 2026-06-28\nstatus: active\n---\n"
            "## Weekly scores\n| Week | Score |\n|---|---|\n",
        "no-scores":
            "---\ncycle: 1\nstart: 2026-04-06\nend: 2026-06-28\nstatus: active\n---\n"
            "# Cycle 1\n\nbody with no scores section\n",
        "bad-week-cell":
            "---\ncycle: 1\nstart: 2026-04-06\nend: 2026-06-28\nstatus: active\n---\n"
            "## Weekly scores\n| Week | Score |\n|---|---|\n| one | 1/1 |\n",
    }
    for name, content in cases.items():
        d = make_dir(root, f"bad-{name}", {"cycle-x.md": content})
        code, out, err = run_cycle(d, today="2026-04-13")
        check(code == 1, f"malformed({name}): expected exit 1, got {code}; out={out!r}")
        check("malformed" in err.lower(),
              f"malformed({name}): expected loud stderr, got {err!r}")


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="probe_cycle_"))
    try:
        probe_active(root)
        probe_active_week_clamp(root)
        probe_planning(root)
        probe_paused(root)
        probe_missing(root)
        probe_selection(root)
        probe_malformed(root)
    except ProbeFail as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"FAIL: unexpected error: {e!r}")
        traceback.print_exc()
        return 1
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("PASS: probe_cycle  active/planning/paused/missing/selection/malformed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
