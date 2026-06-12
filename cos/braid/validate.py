"""Write-contract validator.

Public surface:

    validate_braid(record: dict, kind: Literal["fact","episode"]) -> None
    BraidRejection: Exception subclass raised on validation failure

Rejection policy:
  - Validation failure raises BraidRejection (caller sees a structured error).
  - The rejection is ALSO appended as a JSON line to REJECTIONS_LOG so the
    failure is auditable independent of caller behavior.
  - No silent drops. No soft-accept.

Contracts are loaded from disk on each call. Caching is deferred -- premature
optimization; revisit if profiling shows it matters.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Literal

import jsonschema

from . import CONTRACTS_DIR, REJECTIONS_LOG

Kind = Literal["fact", "episode"]


class BraidRejection(Exception):
    """A write rejected by validation.

    Attributes:
        kind: 'fact' or 'episode'
        payload: the rejected record
        error: the underlying jsonschema.ValidationError
    """

    def __init__(
        self,
        kind: str,
        payload: dict[str, Any],
        error: jsonschema.ValidationError,
    ):
        self.kind = kind
        self.payload = payload
        self.error = error
        loc = "/".join(str(p) for p in error.absolute_path) or "<root>"
        super().__init__(f"rejected {kind} write at {loc}: {error.message}")


def _ts() -> str:
    """Match the cos.memory writers timestamp format (ms-precision, space-sep)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _load_schema(kind: Kind) -> dict[str, Any]:
    path = CONTRACTS_DIR / f"{kind}_write.json"
    if not path.exists():
        raise FileNotFoundError(f"write contract missing: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _log_rejection(
    kind: str,
    payload: dict[str, Any],
    error: jsonschema.ValidationError,
) -> None:
    REJECTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": _ts(),
        "kind": kind,
        "error_path": [str(p) for p in error.absolute_path],
        "error_message": error.message,
        "validator": error.validator,
        "validator_value": error.validator_value,
        "payload": payload,
    }
    with REJECTIONS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def validate_braid(
    record: dict[str, Any],
    kind: Kind,
    *,
    warn_stream: Any = None,
) -> None:
    """Validate `record` against the write contract for `kind`.

    Args:
        record: the payload to validate.
        kind: 'fact' or 'episode'.
        warn_stream: optional writable stream that receives the log-failure
            warning if `_log_rejection` raises. Defaults to `sys.stderr`.
            Tests pass an `io.StringIO()` to capture the warning text.

    Returns None on success.

    Raises:
        BraidRejection: record failed JSON Schema validation. Also appends a
            JSON line to REJECTIONS_LOG for audit. If log writing itself fails,
            a warning is emitted to `warn_stream` and the BraidRejection is
            still raised -- a log-write failure must not suppress the rejection
            the caller needs to see.
        FileNotFoundError: contract file missing. Indicates a packaging
            problem, not a write rejection. Propagates uncaught.
        json.JSONDecodeError: contract present but not parseable as JSON.
        jsonschema.SchemaError: contract is not a valid JSON Schema.

    All but BraidRejection are infrastructure-level; BraidRejection is the only
    one a normal write flow should expect to handle.
    """
    if warn_stream is None:
        warn_stream = sys.stderr
    schema = _load_schema(kind)
    validator = jsonschema.Draft202012Validator(schema)
    try:
        validator.validate(record)
    except jsonschema.ValidationError as e:
        try:
            _log_rejection(kind, record, e)
        except Exception as log_err:
            warn_stream.write(
                f"write-contract: failed to write rejection log at "
                f"{REJECTIONS_LOG}: {log_err!r}; BraidRejection still raised\n"
            )
        raise BraidRejection(kind, record, e) from e
