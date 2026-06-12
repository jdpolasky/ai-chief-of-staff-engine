#!/usr/bin/env python3
"""protect_surfaces -- PreToolUse hook enforcing the propose/commit split.

The owner holds commit-rights over their own surfaces; the agent holds only
propose-rights. This hook makes that mechanical: on an Edit/Write/NotebookEdit
whose target path matches a protected glob, it blocks the call and tells the
agent to propose the change to the owner instead. The owner can grant a
one-time override by dropping a consent file (`.consent-<label>`) next to the
config; the hook consumes (deletes) it on use and lets that single edit through.

Contract (Claude Code PreToolUse hook):
  - Input arrives as JSON on stdin: tool_name, tool_input (with file_path),
    session_id, cwd, etc.
  - To deny, this hook prints a JSON object on stdout with
    hookSpecificOutput.permissionDecision = "deny" and exits 0.
  - To allow, it exits 0 with no decision (the default permission flow runs).
  See docs/ENFORCEMENT.md for the grounding docs link.

STDLIB ONLY. This runs on every matching tool call in the owner's session; a
broken pip install must never brick the session, so there are no third-party
imports. The hook also fails OPEN: any internal error is caught, logged to
stderr, and the call is allowed (exit 0). A bug here must never lock the owner
out of their own files.
"""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path

# Tools that write to disk and therefore touch a "surface".
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "protected_surfaces.json"


def _allow() -> None:
    """Exit 0 with no decision: the default permission flow proceeds."""
    sys.exit(0)


def _deny(reason: str) -> None:
    """Emit a PreToolUse deny decision and exit 0 (the documented JSON path)."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def _candidate_paths(file_path: str, cwd: str) -> list[str]:
    """Forms of the target path to match globs against.

    Matching is forgiving on purpose: a glob like 'sample-vault/state/**' should
    catch both an absolute and a repo-relative file_path. We test the raw path,
    its POSIX form, and (when the path is under cwd) the cwd-relative form.
    """
    raw = file_path.replace("\\", "/")
    forms = {raw}
    try:
        p = Path(file_path)
        if cwd:
            try:
                rel = p.resolve().relative_to(Path(cwd).resolve())
                forms.add(rel.as_posix())
            except (ValueError, OSError):
                pass
        forms.add(p.as_posix())
    except (OSError, ValueError):
        pass
    return [f for f in forms if f]


def _matches(path_forms: list[str], pattern: str) -> bool:
    """True if any path form matches the glob (anywhere, via a *-prefixed form too)."""
    pat = pattern.replace("\\", "/")
    for form in path_forms:
        if fnmatch.fnmatch(form, pat):
            return True
        # Let a repo-relative pattern catch an absolute path: also try matching
        # the pattern against the tail by gluing a leading **/.
        if not pat.startswith("*") and fnmatch.fnmatch(form, f"*/{pat}"):
            return True
    return False


def main() -> None:
    # --- read + parse stdin (fail open on any problem) ---
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception as exc:  # noqa: BLE001  fail open
        print(f"protect_surfaces: bad stdin, allowing: {exc!r}", file=sys.stderr)
        _allow()
        return

    try:
        tool_name = data.get("tool_name", "")
        if tool_name not in WRITE_TOOLS:
            _allow()
            return

        tool_input = data.get("tool_input") or {}
        file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if not file_path:
            _allow()
            return

        if not CONFIG_PATH.exists():
            # No config means nothing is protected. Allow.
            _allow()
            return
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        surfaces = config.get("surfaces", [])

        cwd = data.get("cwd", "")
        path_forms = _candidate_paths(file_path, cwd)

        for entry in surfaces:
            pattern = entry.get("pattern", "")
            if not pattern or not _matches(path_forms, pattern):
                continue

            label = entry.get("label", "surface")
            note = entry.get("note", "")
            consent = CONFIG_PATH.parent / f".consent-{label}"

            if consent.exists():
                # One-time override: consume it and allow this single edit.
                try:
                    consent.unlink()
                    consumed = True
                except OSError as exc:
                    # Could not delete the token. Fail safe by still allowing
                    # (the owner explicitly granted consent) but say so loudly.
                    print(f"protect_surfaces: consent for {label!r} present but "
                          f"could not be deleted ({exc!r}); allowing once but the "
                          f"token may persist", file=sys.stderr)
                    consumed = False
                msg = (f"Override consent for '{label}' was found and "
                       f"{'consumed' if consumed else 'used'}. Allowing this one "
                       f"edit to {file_path}. The protection is back in force for "
                       f"the next edit.")
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                        "permissionDecisionReason": msg,
                    }
                }))
                sys.exit(0)
                return

            # No consent: block and tell the agent how to proceed.
            reason = (
                f"BLOCKED: '{file_path}' is a protected surface "
                f"({label}). {note} The owner commits changes here, not you. "
                f"Do not retry. Instead: (1) show the owner the exact change you "
                f"propose, then (2) ask them to either make the edit themselves "
                f"or grant a one-time override by creating an empty file named "
                f"'.consent-{label}' in the hooks/config directory next to "
                f"protected_surfaces.json. The hook deletes that file the moment "
                f"it is used, so the override is good for exactly one edit."
            )
            _deny(reason)
            return

        # No protected surface matched.
        _allow()
    except Exception as exc:  # noqa: BLE001  fail open on any internal error
        print(f"protect_surfaces: internal error, allowing: {exc!r}", file=sys.stderr)
        _allow()


if __name__ == "__main__":
    main()
