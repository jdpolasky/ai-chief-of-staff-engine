#!/usr/bin/env python3
"""effort_governor -- PreToolUse hook, the runaway brake.

Counts tool calls per session and trips at thresholds, so a session that has
quietly ballooned into hundreds of tool calls gets stopped and forced to surface
its scope and cost to the owner before it burns more.

What this hook CAN see (per the Claude Code PreToolUse contract): one tool call
at a time, with a stable session_id. So it can keep a running per-session count
in a small state file keyed by that id.

What it CANNOT see: turn boundaries (it cannot tell where one of the owner's
prompts ends and the next begins) and tool results (PreToolUse fires before the
tool runs, so consecutive failures are invisible to it). This is therefore a
blunt per-session total, not a smart loop detector. Honest about that in
docs/ENFORCEMENT.md.

Thresholds from hooks/config/governor.json:
  warn_at         -- emit a one-time non-blocking warning
  block_once_at   -- block ONCE (force a scope/cost check-in), then allow
  max_calls       -- block every call until the owner raises the limit

Contract: deny via stdout JSON (hookSpecificOutput.permissionDecision="deny"),
exit 0. A non-blocking warning is printed to stderr with a non-blocking exit
(the documented "other exit code" path shows stderr in the transcript without
blocking). See docs/ENFORCEMENT.md.

STDLIB ONLY and FAILS OPEN: any internal error (including a corrupt state file)
is caught, logged to stderr, and the call is allowed. The brake must never be
the thing that bricks a session.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "governor.json"

DEFAULTS = {
    "max_calls_per_session": 200,
    "warn_at": 120,
    "block_once_at": 150,
}

# Non-blocking exit code: stderr is shown in the transcript, execution continues.
WARN_EXIT = 1


def _state_path(session_id: str) -> Path:
    """Per-session counter file in the OS temp dir. Allow override for tests."""
    base = os.environ.get("COS_HOOK_STATE_DIR")
    root = Path(base) if base else Path(tempfile.gettempdir())
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "nosession"
    return root / f"cos_governor_{safe}.json"


def _load_state(path: Path) -> dict:
    """Read the counter file. A corrupt or missing file resets cleanly (fail open)."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001  corrupt state -> start fresh
        pass
    return {"calls": 0, "warned": False, "block_once_fired": False}


def _save_state(path: Path, state: dict) -> None:
    try:
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError as exc:
        print(f"effort_governor: could not persist state ({exc!r})", file=sys.stderr)


def _allow() -> None:
    sys.exit(0)


def _deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception as exc:  # noqa: BLE001  fail open
        print(f"effort_governor: bad stdin, allowing: {exc!r}", file=sys.stderr)
        _allow()
        return

    try:
        cfg = dict(DEFAULTS)
        if CONFIG_PATH.exists():
            try:
                cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
            except Exception as exc:  # noqa: BLE001  bad config -> defaults
                print(f"effort_governor: bad config, using defaults: {exc!r}",
                      file=sys.stderr)

        max_calls = int(cfg.get("max_calls_per_session", DEFAULTS["max_calls_per_session"]))
        warn_at = int(cfg.get("warn_at", DEFAULTS["warn_at"]))
        block_once_at = int(cfg.get("block_once_at", DEFAULTS["block_once_at"]))

        session_id = str(data.get("session_id", "")) or "nosession"
        path = _state_path(session_id)
        state = _load_state(path)
        state["calls"] = int(state.get("calls", 0)) + 1
        calls = state["calls"]

        # Hard ceiling: block every call until the owner raises the limit.
        if calls >= max_calls:
            _save_state(path, state)
            _deny(
                f"BLOCKED (hard cap): this session has made {calls} tool calls, at "
                f"or over the limit of {max_calls}. Stop and tell the owner the "
                f"session has hit its tool-call ceiling. To continue, the owner "
                f"raises max_calls_per_session in hooks/config/governor.json, or "
                f"starts a fresh session. Do not retry until then."
            )
            return

        # One-time scope/cost check-in.
        if calls >= block_once_at and not state.get("block_once_fired", False):
            state["block_once_fired"] = True
            _save_state(path, state)
            _deny(
                f"BLOCKED ONCE (scope check): this session has made {calls} tool "
                f"calls (threshold {block_once_at}). Before doing more, stop and "
                f"surface to the owner: what you are doing, how much further it is "
                f"likely to go, and whether it is still worth it. After you have "
                f"checked in, subsequent calls are allowed up to the hard cap of "
                f"{max_calls}. This is a blunt brake, not a sign anything is wrong."
            )
            return

        # One-time non-blocking warning.
        if calls >= warn_at and not state.get("warned", False):
            state["warned"] = True
            _save_state(path, state)
            print(
                f"effort_governor: heads up, this session has made {calls} tool "
                f"calls (warn threshold {warn_at}). A scope check-in will be "
                f"required at {block_once_at}.", file=sys.stderr)
            sys.exit(WARN_EXIT)
            return

        _save_state(path, state)
        _allow()
    except Exception as exc:  # noqa: BLE001  fail open
        print(f"effort_governor: internal error, allowing: {exc!r}", file=sys.stderr)
        _allow()


if __name__ == "__main__":
    main()
