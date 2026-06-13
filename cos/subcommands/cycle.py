"""`cos cycle` -- render the active 12-week cycle for the daily briefing.

Reads the cycle plan files in COS_CYCLES_DIR (default <vault>/cycles), finds the
one cycle that is current, and prints a short scoreboard: which cycle, which week
of twelve, days left, the per-goal lead-measure totals against their weekly
targets, and last week's score. The session-loop /start command runs this during
the morning briefing so the plan carries itself instead of living in the owner's
memory.

This is an owner-run CLI, not a hook. It is read-only (it never writes a cycle
file) and it is loud on a malformed file: a cycle plan you cannot parse is a
plan you cannot trust, so it exits 1 with the reason rather than guessing.

Selection: among the cycle files (CYCLE-TEMPLATE.md is always skipped), an
`active` cycle wins. If none is active, a `planning` cycle is shown as pending,
and a `paused` cycle is shown as paused. `complete` cycles are ignored for the
briefing. No cycle file at all is a calm one-liner and exit 0, not an error:
not running a cycle is a valid state.

Frontmatter and table format are documented in cycles/CYCLE-TEMPLATE.md.

Stdlib only. No third-party YAML; the frontmatter here is flat key/value.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from pathlib import Path

from cos.config import CYCLES_DIR

CYCLE_WEEKS = 12
TEMPLATE_NAME = "CYCLE-TEMPLATE.md"
VALID_STATUS = {"planning", "active", "complete", "paused"}
# Priority order when more than one non-complete cycle is present.
_SELECT_ORDER = {"active": 0, "planning": 1, "paused": 2}


class CycleError(Exception):
    """A cycle file exists but cannot be trusted. Loud, exit 1."""


def _ensure_utf8_stdout() -> None:
    """Cycle notes can carry smart punctuation; the Windows console default
    cp1252 would crash on it. Idempotent; no-op on streams without reconfigure."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# --- parsing -------------------------------------------------------------

def parse_frontmatter(text: str, source: str) -> dict[str, str]:
    """Pull the leading `--- ... ---` YAML block as a flat key->value dict.

    Only flat `key: value` lines are read; comments after a `#` on a value line
    are stripped. A missing or unterminated block is a malformed file (loud).
    """
    if not text.startswith("---"):
        raise CycleError(f"{source}: no frontmatter block (file must open with ---)")
    end = text.find("\n---", 3)
    if end == -1:
        raise CycleError(f"{source}: frontmatter block is not terminated by a closing ---")
    block = text[3:end]
    fm: dict[str, str] = {}
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        # Strip an inline comment from the value (e.g. "planning   # draft").
        val = val.split("#", 1)[0].strip()
        fm[key.strip()] = val
    return fm


def _parse_date(value: str, field: str, source: str) -> _dt.date:
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        raise CycleError(f"{source}: frontmatter {field} {value!r} is not a YYYY-MM-DD date")


def parse_score_rows(text: str, source: str) -> list[dict[str, str]]:
    """Parse the Weekly scores markdown table into a list of row dicts.

    Returns rows with keys: week (int), and the raw cell strings for the goal
    columns plus score and note, keyed by the table's own header names. The
    header and the `---|---` separator row are skipped, as is any blank
    placeholder row (every cell empty). A row whose Week cell is not an integer
    is malformed (loud), because the score table drives the rendered totals.
    """
    lines = text.splitlines()
    # Find the "## Weekly scores" heading, then the first table under it.
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("## weekly scores"):
            start = i + 1
            break
    if start is None:
        raise CycleError(f"{source}: no '## Weekly scores' section found")

    header: list[str] | None = None
    rows: list[dict[str, str]] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("##"):
            break  # next section; table is over
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if all(set(c) <= {"-", ":"} for c in cells):
            continue  # the |---|---| separator row
        if all(c == "" for c in cells):
            continue  # blank placeholder row from the template
        row = dict(zip(header, cells))
        wk = row.get("week", "").strip()
        try:
            row["week"] = int(wk)
        except ValueError:
            raise CycleError(
                f"{source}: weekly-scores row has a non-integer Week cell {wk!r}")
        rows.append(row)
    return rows


# --- lead-measure totals -------------------------------------------------

_COUNT_RE = re.compile(r"([A-Za-z][A-Za-z _/-]*?)\s+(\d+)")


def parse_counts(cell: str) -> list[tuple[str, int]]:
    """Pull (label, count) pairs out of a goal cell like
    'conversations 5, case studies 1'. Tolerant: anything that is not a
    'word(s) number' pair is ignored, so a stray note does not break the total."""
    out: list[tuple[str, int]] = []
    for part in cell.split(","):
        m = _COUNT_RE.search(part.strip())
        if m:
            out.append((m.group(1).strip(), int(m.group(2))))
    return out


def goal_columns(rows: list[dict[str, str]]) -> list[str]:
    """The goal columns are the table headers that are not week/score/note."""
    if not rows:
        return []
    return [h for h in rows[0].keys()
            if h not in ("week", "score", "note") and isinstance(h, str)]


def sum_goal_counts(rows: list[dict[str, str]], col: str) -> list[tuple[str, int]]:
    """Sum each lead-measure label across every scored week for one goal column."""
    totals: dict[str, int] = {}
    for row in rows:
        for label, n in parse_counts(row.get(col, "")):
            totals[label] = totals.get(label, 0) + n
    return list(totals.items())


# --- cycle math ----------------------------------------------------------

def week_of(start: _dt.date, today: _dt.date) -> int:
    """1-based cycle week for `today`, clamped to 1..CYCLE_WEEKS."""
    delta_days = (today - start).days
    wk = delta_days // 7 + 1
    return max(1, min(CYCLE_WEEKS, wk))


def days_left(end: _dt.date, today: _dt.date) -> int:
    return (end - today).days


# --- file selection ------------------------------------------------------

def _load(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text, path.name)
    status = fm.get("status", "").strip()
    if status not in VALID_STATUS:
        raise CycleError(
            f"{path.name}: status {status!r} is not one of "
            f"{', '.join(sorted(VALID_STATUS))}")
    return fm, text


def select_cycle(cycles_dir: Path) -> tuple[Path, dict[str, str], str] | None:
    """Return (path, frontmatter, text) for the cycle to render, or None if there
    is no cycle to show. A malformed file raises CycleError (loud)."""
    if not cycles_dir.is_dir():
        return None
    candidates: list[tuple[int, Path, dict[str, str], str]] = []
    for path in sorted(cycles_dir.glob("*.md")):
        if path.name == TEMPLATE_NAME:
            continue
        fm, text = _load(path)  # loud on malformed
        status = fm["status"].strip()
        if status == "complete":
            continue
        candidates.append((_SELECT_ORDER.get(status, 9), path, fm, text))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1].name))
    _, path, fm, text = candidates[0]
    return path, fm, text


# --- rendering -----------------------------------------------------------

def render(path: Path, fm: dict[str, str], text: str, today: _dt.date) -> str:
    source = path.name
    status = fm["status"].strip()
    cycle_no = fm.get("cycle", "?").strip()
    start = _parse_date(fm.get("start", ""), "start", source)
    end = _parse_date(fm.get("end", ""), "end", source)

    if status == "planning":
        left = days_left(start, today)
        when = (f"starts in {left} days" if left > 0
                else "starts today" if left == 0
                else f"start date was {-left} days ago; mark it active when it begins")
        return (f"Cycle {cycle_no} (planning): {when}.\n"
                f"  Plan is drafted and waiting; scoring begins week 1.")

    if status == "paused":
        return (f"Cycle {cycle_no} (paused): scoring is on hold by choice.\n"
                f"  Resume it whenever you decide to.")

    # active
    wk = week_of(start, today)
    left = max(0, days_left(end, today))
    rows = parse_score_rows(text, source)
    cols = goal_columns(rows)

    lines = [f"Cycle {cycle_no}: week {wk} of {CYCLE_WEEKS}, {left} days left."]
    if cols:
        lines.append("  Lead-measure totals so far:")
        for col in cols:
            totals = sum_goal_counts(rows, col)
            if totals:
                parts = ", ".join(f"{label} {n}" for label, n in totals)
                lines.append(f"    {col}: {parts}")
            else:
                lines.append(f"    {col}: no counts logged yet")
    else:
        lines.append("  No weekly scores logged yet.")

    if rows:
        last = rows[-1]
        score = last.get("score", "").strip() or "(unscored)"
        note = last.get("note", "").strip()
        line = f"  Last scored week (week {last['week']}): {score}"
        lines.append(line)
        if note:
            lines.append(f"    {note}")
    return "\n".join(lines)


# --- command -------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    _ensure_utf8_stdout()
    cycles_dir = Path(args.cycles_dir) if args.cycles_dir else CYCLES_DIR
    today = (_dt.date.fromisoformat(args.today) if args.today
             else _dt.date.today())
    try:
        selected = select_cycle(cycles_dir)
    except CycleError as e:
        print(f"cos cycle: malformed cycle file: {e}", file=sys.stderr)
        return 1
    if selected is None:
        print("No active cycle. Copy cycles/CYCLE-TEMPLATE.md to start one.")
        return 0
    path, fm, text = selected
    try:
        print(render(path, fm, text, today))
    except CycleError as e:
        print(f"cos cycle: malformed cycle file: {e}", file=sys.stderr)
        return 1
    return 0


def register(subparsers):
    p = subparsers.add_parser(
        "cycle",
        help="Render the active 12-week cycle as a briefing scoreboard.",
    )
    p.add_argument(
        "--cycles-dir", dest="cycles_dir", default=None,
        help=f"directory of cycle plan files (default: {CYCLES_DIR})",
    )
    p.add_argument(
        "--today", default=None,
        help="override today's date (YYYY-MM-DD) for testing week/days math",
    )
    p.set_defaults(func=run)
