"""probe_regress -- `cos regress` keeps probes out of the user's real state.

Run from the repo root:

    python probes/probe_regress.py

Builds a fake "user" vault and state folder, points COS_VAULT, COS_STATE_DIR,
and COS_DB at them, then runs `python -m cos regress --probes-dir <tmp>` over a
one-probe suite. That inner probe writes through the default paths: it appends
to facts.jsonl with the stock jsonl writer and triggers a write-contract
rejection, which appends to braid_rejections.log. It also reports the paths it
saw.

Asserts:
  - the inner probe ran and passed;
  - it saw COS_VAULT, COS_STATE_DIR, and COS_DB pointed somewhere other than
    the user's folders;
  - the user's state folder is still empty afterward (no facts.jsonl, no
    braid_rejections.log, no memory.db);
  - the sandbox the inner probe wrote to is gone after the run.

Exits 0 on pass; nonzero with a printed FAIL reason.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

INNER_PROBE = r'''
import json, os, sys
from pathlib import Path
sys.path.insert(0, REPO_ROOT)
from cos.config import VAULT, STATE_DIR, DEFAULT_DB_PATH
from cos.braid.validate import validate_braid, BraidRejection
from cos.memory.jsonl import jsonl_append
jsonl_append({"content": "fixture fact from the probe"}, "fact", 1)
try:
    validate_braid({"content": "x"}, "fact")
except BraidRejection:
    pass
Path(REPORT).write_text(json.dumps({
    "vault": str(VAULT), "state": str(STATE_DIR), "db": str(DEFAULT_DB_PATH),
}), encoding="utf-8")
print("PASS: inner")
'''


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="probe_regress_"))
    try:
        user_vault = work / "user-vault"
        user_state = work / "user-state"
        user_vault.mkdir()
        user_state.mkdir()
        probes_dir = work / "inner-probes"
        probes_dir.mkdir()
        report = work / "report.json"
        (probes_dir / "probe_inner.py").write_text(
            f"REPO_ROOT = {str(REPO_ROOT)!r}\nREPORT = {str(report)!r}\n" + INNER_PROBE,
            encoding="utf-8",
        )

        env = dict(os.environ)
        env["COS_VAULT"] = str(user_vault)
        env["COS_STATE_DIR"] = str(user_state)
        env["COS_DB"] = str(user_state / "memory.db")
        proc = subprocess.run(
            [sys.executable, "-m", "cos", "regress", "--probes-dir", str(probes_dir)],
            cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=120,
        )
        check(proc.returncode == 0,
              f"inner regress failed: rc={proc.returncode} out={proc.stdout!r} "
              f"err={proc.stderr!r}")
        check("1 passed, 0 failed" in proc.stdout,
              f"inner regress summary missing: {proc.stdout!r}")
        check(report.exists(), "inner probe did not write its report")

        seen = json.loads(report.read_text(encoding="utf-8"))
        for key in ("vault", "state", "db"):
            p = Path(seen[key])
            check(user_vault not in p.parents and p != user_vault
                  and user_state not in p.parents and p != user_state,
                  f"inner probe saw {key}={p}, inside the user's folders")

        leftovers = sorted(x.name for x in user_state.iterdir())
        check(not leftovers, f"user state folder was written to: {leftovers}")
        check(not any(user_vault.iterdir()), "user vault folder was written to")

        sandbox_state = Path(seen["state"])
        check(not sandbox_state.exists(),
              f"regress sandbox not cleaned up: {sandbox_state}")
    except ProbeFail as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"FAIL: unexpected error: {e!r}")
        traceback.print_exc()
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("PASS: probe_regress  probes run in a sandbox; user state untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
