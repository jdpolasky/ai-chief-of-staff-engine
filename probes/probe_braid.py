"""probe_braid -- the BRAID write-contract validator accepts/rejects correctly.

Run from the repo root:

    python probes/probe_braid.py

Asserts validate_braid:
  - Accepts well-formed fact and episode payloads.
  - Rejects: missing required fields, an invalid category enum, a tx_from in the
    wrong format (T-separator, second precision, garbage suffix), an unknown key
    (additionalProperties: false), and confidence out of range.
  - Raises BraidRejection carrying structured attributes (kind, payload, error).
  - Appends a JSON line per rejection to the rejections log.
  - Keeps raising the rejection even when the rejection-log write itself fails
    (log-failure non-suppression), emitting a warning to the given warn_stream.

Redirects the rejections log to a tempfile so the real log is untouched.
Exits 0 on pass; nonzero with a printed FAIL reason. No pytest dependency.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cos.braid as braid_pkg  # noqa: E402
import cos.braid.validate as braid_validate  # noqa: E402
from cos.braid import CONTRACTS_DIR  # noqa: E402
from cos.braid.validate import BraidRejection, validate_braid  # noqa: E402


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def expect_reject(record, kind, validator, label):
    """Assert validate_braid rejects `record` with the named validator."""
    try:
        validate_braid(record, kind)
        raise ProbeFail(f"{label}: should have rejected, did not")
    except BraidRejection as e:
        if validator is not None and e.error.validator != validator:
            raise ProbeFail(
                f"{label}: expected validator {validator!r}, got {e.error.validator!r}")
        return e


def main() -> int:
    for contract in ("fact_write.json", "episode_write.json"):
        if not (CONTRACTS_DIR / contract).exists():
            print(f"FAIL: contract missing: {CONTRACTS_DIR / contract}")
            return 1

    sandbox = Path(tempfile.mkdtemp(prefix="probe_braid_"))
    try:
        tmp_log = sandbox / "braid_rejections.log"
        braid_pkg.REJECTIONS_LOG = tmp_log
        braid_validate.REJECTIONS_LOG = tmp_log

        good_fact = {
            "content": "Vendor invoice cadence is net-30",
            "category": "decision",
            "source": "manual",
            "source_session": 12,
            "valid_from": "2026-05-04",
            "tx_from": "2026-05-04 18:32:11.456",
        }
        validate_braid(good_fact, "fact")  # raises on failure

        expect_reject({"content": "xxxxx", "category": "decision"}, "fact",
                      "required", "missing required fields")
        bad_category = dict(good_fact, category="banana")
        expect_reject(bad_category, "fact", "enum", "invalid category")
        expect_reject(dict(good_fact, tx_from="2026-05-04T18:32:11+00:00"),
                      "fact", "pattern", "tx_from T-format")
        expect_reject(dict(good_fact, tx_from="2026-05-04 18:32:11"),
                      "fact", "pattern", "tx_from second precision")
        expect_reject(dict(good_fact, tx_from="2026-05-04 18:32:11.456GARBAGE"),
                      "fact", "pattern", "tx_from garbage suffix (anchor check)")
        expect_reject(dict(good_fact, sorce="typo"), "fact",
                      "additionalProperties", "unknown key")
        conf_err = expect_reject(dict(good_fact, confidence=1.5), "fact",
                                 None, "confidence out of range")
        check(conf_err.error.validator in ("maximum", "exclusiveMaximum"),
              f"confidence: expected maximum validator, got {conf_err.error.validator}")

        # structured attributes
        e = expect_reject(bad_category, "fact", "enum", "attrs")
        check(e.kind == "fact", f"BraidRejection.kind != 'fact': {e.kind!r}")
        check(e.payload == bad_category, "BraidRejection.payload mismatch")
        check(e.error is not None, "BraidRejection.error is None")

        good_ep = {
            "title": "Quarter close",
            "content": "Closed the books for the quarter; invoices reconciled.",
            "occurred_at": "2026-05-25",
            "session": 12,
            "valence": "positive",
        }
        validate_braid(good_ep, "episode")
        expect_reject({"title": "xxxx"}, "episode", "required", "episode missing required")
        expect_reject(dict(good_ep, title="hi"), "episode", "minLength",
                      "episode title too short")

        # log-failure non-suppression: point the log at the temp DIRECTORY so the
        # open(...,"a") raises; the rejection must still propagate and a warning
        # must reach the supplied warn_stream.
        saved_pkg, saved_val = braid_pkg.REJECTIONS_LOG, braid_validate.REJECTIONS_LOG
        braid_pkg.REJECTIONS_LOG = sandbox
        braid_validate.REJECTIONS_LOG = sandbox
        warn = io.StringIO()
        raised = False
        try:
            validate_braid(bad_category, "fact", warn_stream=warn)
        except BraidRejection:
            raised = True
        check(raised, "log-failure: BraidRejection should still raise")
        check("failed to write rejection log" in warn.getvalue(),
              f"log-failure: warn_stream missing expected warning; got {warn.getvalue()!r}")
        braid_pkg.REJECTIONS_LOG = saved_pkg
        braid_validate.REJECTIONS_LOG = saved_val

        # rejections were logged as JSON lines with the expected keys.
        check(tmp_log.exists(), f"rejections log not created at {tmp_log}")
        lines = [ln for ln in tmp_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        parsed = [json.loads(ln) for ln in lines]
        check(len(parsed) >= 9, f"expected >=9 rejection log entries, got {len(parsed)}")
        for key in ("ts", "kind", "error_path", "error_message", "validator", "payload"):
            check(key in parsed[0], f"rejection log entry missing key: {key}")
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

    print("PASS: probe_braid  accept+reject paths, structured attrs, log-failure")
    return 0


if __name__ == "__main__":
    sys.exit(main())
