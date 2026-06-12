#!/usr/bin/env python3
"""output_lint -- Stop hook that checks the agent's final message against rules.

When the agent is about to stop, this hook reads the last assistant message from
the transcript and tests it against a list of regex rules. If an enabled rule
matches, it blocks the stop with that rule's message, so the agent rewrites
before it hands the turn back. This is where an owner's hard output bans (no
em-dashes, no unsourced long quotes, no hedge-stacking) get enforced mechanically
instead of living in prose the model is asked to remember.

Contract (Claude Code Stop hook):
  - Input on stdin includes transcript_path and stop_hook_active.
  - The transcript is a JSONL file, one JSON object per line. Assistant turns
    carry the message content; this hook walks the file backward to the last
    assistant text and lints that.
  - To block the stop, print the reason to stderr and exit 2. The hooks
    reference documents exit code 2 as the blocking signal for Stop hooks
    (the agent continues and receives the stderr text as feedback).
  - stop_hook_active guards against an infinite block loop: if it is already
    true, this hook does not block again.
  See docs/ENFORCEMENT.md for the grounding docs link.

STDLIB ONLY and FAILS OPEN: any internal error is caught, logged to stderr, and
the stop is allowed (exit 0). A bug here must never trap the owner in a session
that cannot end.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "lint_rules.json"


def _allow() -> None:
    """Exit 0 with no decision: the agent is allowed to stop."""
    sys.exit(0)


def _block(reason: str) -> None:
    """Block the stop: reason on stderr, exit 2 (the documented Stop signal)."""
    print(reason, file=sys.stderr)
    sys.exit(2)


def _extract_text(message: object) -> str:
    """Pull plain text out of a transcript message's content.

    Content is either a plain string or a list of blocks; we keep the text of
    'text' blocks (and any bare strings) and ignore tool_use/tool_result blocks.
    """
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = None
    if isinstance(content, str):
        return content
    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "\n".join(parts)


def _last_assistant_text(transcript_path: str) -> str:
    """Return the text of the final assistant message in the transcript, or ''.

    Walks the JSONL backward and returns the first assistant entry that yields
    non-empty text. Tolerant of both the {'type','message':{...}} envelope and a
    flat {'role','content'} shape; ignores unparseable lines.
    """
    p = Path(transcript_path)
    if not transcript_path or not p.exists():
        return ""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Envelope form: {"type": "assistant", "message": {...}}
        role = entry.get("type")
        message = entry.get("message", entry)
        if role != "assistant" and message.get("role") != "assistant":
            continue
        text = _extract_text(message).strip()
        if text:
            return text
    return ""


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception as exc:  # noqa: BLE001  fail open
        print(f"output_lint: bad stdin, allowing stop: {exc!r}", file=sys.stderr)
        _allow()
        return

    try:
        # Guard against an endless block loop: if we already blocked once and the
        # agent is re-stopping, do not block again.
        if data.get("stop_hook_active"):
            _allow()
            return

        if not CONFIG_PATH.exists():
            _allow()
            return
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        rules = config.get("rules", [])

        text = _last_assistant_text(data.get("transcript_path", ""))
        if not text:
            # Nothing to lint (no readable final message). Allow.
            _allow()
            return

        for rule in rules:
            if not rule.get("enabled", False):
                continue
            pattern = rule.get("pattern", "")
            if not pattern:
                continue
            try:
                if re.search(pattern, text):
                    _block(rule.get("message", f"Output lint rule "
                                               f"'{rule.get('name', '?')}' matched."))
                    return
            except re.error as exc:
                # A broken regex must not break the session: skip the rule, log it.
                print(f"output_lint: bad regex in rule "
                      f"{rule.get('name', '?')!r}: {exc!r}", file=sys.stderr)
                continue

        _allow()
    except Exception as exc:  # noqa: BLE001  fail open
        print(f"output_lint: internal error, allowing stop: {exc!r}", file=sys.stderr)
        _allow()


if __name__ == "__main__":
    main()
