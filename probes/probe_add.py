"""probe_add -- `cos memory add` stamps missing fact timestamps.

Run from the repo root:

    python probes/probe_add.py

Drives cmd_add end to end against a temp database:

  - a fact with no tx_from and no valid_from is accepted; tx_from is stamped in
    the contract's ms format and valid_from is today's date (from tx_from);
  - a fact with valid_from but no tx_from keeps the given valid_from;
  - a fact with a malformed tx_from is still rejected (the stamp only fills a
    missing value);
  - the write contract no longer lists tx_from as required, and still lists
    valid_from.

Points COS_STATE_DIR at a temp folder before importing cos, so the jsonl
backup and the rejections log land there. Exits 0 on pass; nonzero with a
printed FAIL reason.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SANDBOX = Path(tempfile.mkdtemp(prefix="probe_add_"))
os.environ["COS_STATE_DIR"] = str(SANDBOX / "state")

from cos.braid import CONTRACTS_DIR  # noqa: E402
from cos.subcommands.memory import cmd_add  # noqa: E402

TX_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$")


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def add(db: Path, payload: dict) -> tuple[int, str, str]:
    args = argparse.Namespace(kind="fact", json=json.dumps(payload), db=str(db))
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cmd_add(args) or 0
    return rc, out.getvalue(), err.getvalue()


def row(db: Path, fact_id: int) -> dict:
    conn = sqlite3.connect(db)
    try:
        cur = conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,))
        r = cur.fetchone()
        return dict(zip([d[0] for d in cur.description], r))
    finally:
        conn.close()


def main() -> int:
    try:
        db = SANDBOX / "memory.db"
        today = datetime.now(timezone.utc).date().isoformat()

        rc, out, err = add(db, {"content": "Probe fact with no timestamps at all",
                                "category": "reference", "source": "manual"})
        check(rc == 0, f"no timestamps: rc={rc} err={err!r}")
        r = row(db, int(out.strip()))
        check(bool(TX_RE.match(r["tx_from"] or "")), f"tx_from not stamped: {r['tx_from']!r}")
        check(r["valid_from"] == r["tx_from"][:10] == today,
              f"valid_from not today: {r['valid_from']!r} tx_from={r['tx_from']!r}")

        rc, out, err = add(db, {"content": "Probe fact with a given valid date",
                                "category": "reference", "source": "manual",
                                "valid_from": "2026-01-15"})
        check(rc == 0, f"valid_from only: rc={rc} err={err!r}")
        r = row(db, int(out.strip()))
        check(r["valid_from"] == "2026-01-15", f"valid_from overwritten: {r['valid_from']!r}")
        check(bool(TX_RE.match(r["tx_from"] or "")), f"tx_from not stamped: {r['tx_from']!r}")

        rc, out, err = add(db, {"content": "Probe fact with a bad tx_from",
                                "category": "reference", "source": "manual",
                                "tx_from": "2026-01-15T10:00:00"})
        check(rc == 1 and "rejected" in err,
              f"bad tx_from: expected rc=1 rejected, got rc={rc} err={err!r}")

        contract = json.loads((CONTRACTS_DIR / "fact_write.json").read_text(encoding="utf-8"))
        check("tx_from" not in contract["required"],
              f"tx_from still required: {contract['required']}")
        check("valid_from" in contract["required"],
              f"valid_from dropped from required: {contract['required']}")
    except ProbeFail as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"FAIL: unexpected error: {e!r}")
        traceback.print_exc()
        return 1
    finally:
        shutil.rmtree(SANDBOX, ignore_errors=True)

    print("PASS: probe_add  missing fact timestamps are stamped before validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
