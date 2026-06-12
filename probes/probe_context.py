"""probe_context -- three-tier retrieval CLI + FTS5 query sanitization.

Run from the repo root:

    python probes/probe_context.py

CLI surface (cmd_context, default human format):
  - `context <subject>` emits three labeled tier sections, headers of the form
    '## <Tier> (n / limit)', exit 0.

FTS query sanitization (cos.memory.context):
  - _sanitize_fts_query maps FTS5-special chars (/, -, parens, colon) to spaces
    and passes None through.
  - retrieve_context does not crash on FTS-hostile queries (slash / hyphen /
    paren) and still surfaces the relevant fact for the sanitized tokens.

Self-contained: tempdir + temp sqlite db via apply_schema. Exits 0 on pass;
nonzero with a printed FAIL reason. No pytest dependency.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cos.memory.context import (  # noqa: E402
    ContextOptions, _sanitize_fts_query, merge_hits, retrieve_context,
)
from cos.memory.migrate import apply_schema  # noqa: E402
from cos.memory.writers import insert_episode, insert_fact  # noqa: E402
from cos.subcommands.memory import cmd_context  # noqa: E402


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime(
        "%Y-%m-%d %H:%M:%S.000")


def date_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).date().isoformat()


def ctx_ns(**kwargs) -> argparse.Namespace:
    defaults = dict(
        subject=None, subject_type=None, query=None, tiers=None,
        limit=10, merge=False, json=False,
        operational_days=30, operational_confidence=0.5,
        structural_confidence=0.8, reflective_half_life_days=90,
        as_of=None, db=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def run_ctx(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cmd_context(args) or 0
    return rc, out.getvalue(), err.getvalue()


def assert_unit_sanitizer() -> None:
    cases = [
        ("Q3 5/05 launch notes", "Q3 5 05 launch notes"),
        ("issue-1", "issue 1"),
        ("Apollo (Phase II)", "Apollo  Phase II "),
        ("urn:li:activity:74575", "urn li activity 74575"),
        ("Plain query", "Plain query"),
        (None, None),
    ]
    for inp, expected in cases:
        got = _sanitize_fts_query(inp)
        check(got == expected,
              f"_sanitize_fts_query({inp!r}) = {got!r}, expected {expected!r}")


def assert_cli_default(sandbox: Path) -> None:
    db_path = sandbox / "ctx.db"
    apply_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            insert_fact(conn, content="Meadowlark uses a hosted CMS",
                        category="reference", source="manual",
                        subject_type="project", subject_id="meadowlark",
                        confidence=0.9, valid_from=date_ago(2), tx_from=days_ago(2))
            insert_fact(conn, content="Meadowlark branding direction locked",
                        category="preference", source="manual",
                        subject_type="project", subject_id="meadowlark",
                        confidence=0.95, valid_from=date_ago(5), tx_from=days_ago(5))
            insert_episode(conn, title="Meadowlark kickoff",
                           content="Project Meadowlark kickoff meeting covered scope.",
                           occurred_at=date_ago(10))
    finally:
        conn.close()

    rc, out, err = run_ctx(ctx_ns(subject="meadowlark", db=str(db_path)))
    check(rc == 0, f"context default: rc={rc} err={err!r}")
    for label in ("## Operational", "## Structural", "## Reflective"):
        check(label in out, f"context default: missing header {label!r}:\n{out}")
    check("/ 10)" in out, f"context default: missing '/ 10)' limit marker:\n{out}")


def assert_fts_hostile_queries(sandbox: Path) -> None:
    db_path = sandbox / "fts.db"
    apply_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            insert_fact(conn,
                        content="Survey 5/05 plot metrics: 590 stems and 308 in bloom.",
                        category="reference", source="manual", confidence=0.9,
                        valid_from=date_ago(7), tx_from=days_ago(7))
            insert_fact(conn,
                        content="Bed-1 verification confirmed the drainage fix held.",
                        category="reference", source="manual", confidence=0.9,
                        valid_from=date_ago(7), tx_from=days_ago(7))
    finally:
        conn.close()

    conn = sqlite3.connect(db_path)
    try:
        # slash query
        opts = ContextOptions(query="Survey 5/05 plot metrics",
                              tiers=("operational", "structural", "reflective"), limit=5)
        try:
            by_tier = retrieve_context(conn, opts)
        except sqlite3.OperationalError as e:
            raise ProbeFail(f"slash query raised: {e}")
        merged = merge_hits(by_tier, 5)
        check(any("Survey" in (h.record.get("content") or "") for h in merged),
              "slash query: expected a Survey-content hit in merged")

        # hyphen query
        opts2 = ContextOptions(query="Bed-1",
                               tiers=("operational", "structural", "reflective"), limit=5)
        try:
            by_tier2 = retrieve_context(conn, opts2)
        except sqlite3.OperationalError as e:
            raise ProbeFail(f"hyphen query raised: {e}")
        merged2 = merge_hits(by_tier2, 5)
        check(any("Bed-1" in (h.record.get("content") or "") for h in merged2),
              "hyphen query: expected a Bed-1-content hit in merged")

        # paren query (must not crash)
        opts3 = ContextOptions(query="Larkspur (Phase II)",
                               tiers=("operational", "structural", "reflective"), limit=5)
        try:
            retrieve_context(conn, opts3)
        except sqlite3.OperationalError as e:
            raise ProbeFail(f"paren query raised: {e}")
    finally:
        conn.close()


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="probe_context_"))
    try:
        assert_unit_sanitizer()
        assert_cli_default(sandbox)
        assert_fts_hostile_queries(sandbox)
    except ProbeFail as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"FAIL: unexpected error: {e!r}")
        traceback.print_exc()
        return 1
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    print("PASS: probe_context  three-tier CLI headers + FTS sanitization")
    return 0


if __name__ == "__main__":
    sys.exit(main())
