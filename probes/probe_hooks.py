"""probe_hooks -- the three enforcement hooks block/allow/fail-open correctly.

Run from the repo root:

    python probes/probe_hooks.py

Invokes each hook script as a subprocess with synthetic stdin JSON (exactly how
Claude Code drives them) and asserts every branch:

  protect_surfaces (PreToolUse):
    - non-protected path allows
    - non-write tool (Read) allows
    - protected path blocks (permissionDecision deny)
    - consent file allows once, and the file is consumed (deleted)
    - malformed stdin fails open (allow)

  effort_governor (PreToolUse):
    - under threshold allows
    - warn_at fires a non-blocking warning (once)
    - block_once_at blocks once, then the next call clears
    - max_calls blocks every call
    - corrupt state file fails open (allow)

  output_lint (Stop):
    - disabled rule is ignored (allow)
    - enabled rule blocks (decision block)
    - no-match allows
    - stop_hook_active short-circuits to allow
    - malformed config fails open (allow)

Each hook is copied into a sandbox with its own config so the probe never
touches the shipped config files. Exits 0 on pass; nonzero with a printed FAIL
reason. No pytest dependency.
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
HOOKS_DIR = REPO_ROOT / "hooks"


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def run_hook(script: Path, stdin_obj, env_extra: dict | None = None) -> dict:
    """Run a hook script with the given stdin (dict -> JSON, or raw str for
    malformed cases). Returns {exit_code, stdout, stderr, json (parsed or None)}."""
    if isinstance(stdin_obj, str):
        stdin_text = stdin_obj
    else:
        stdin_text = json.dumps(stdin_obj)
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    parsed = None
    out = (proc.stdout or "").strip()
    if out:
        try:
            parsed = json.loads(out)
        except json.JSONDecodeError:
            parsed = None
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout or "",
        "stderr": proc.stderr or "",
        "json": parsed,
    }


def pre_decision(res: dict):
    """Return the PreToolUse permissionDecision from a result, or None."""
    j = res["json"]
    if not isinstance(j, dict):
        return None
    return j.get("hookSpecificOutput", {}).get("permissionDecision")


def stop_decision(res: dict):
    """Return "block" if the Stop hook blocked (exit 2 + stderr reason), else None."""
    if res["exit_code"] == 2 and res["stderr"].strip():
        return "block"
    return None


# --------------------------------------------------------------------------
# protect_surfaces
# --------------------------------------------------------------------------

def probe_protect(sandbox: Path) -> None:
    script = sandbox / "protect_surfaces.py"
    cfg_dir = sandbox / "config"
    cfg = {
        "surfaces": [
            {"pattern": "vault/state/**", "label": "session-state", "note": "handoff"},
            {"pattern": "vault/Invoicing.md", "label": "invoicing", "note": "money"},
        ]
    }
    (cfg_dir / "protected_surfaces.json").write_text(json.dumps(cfg), encoding="utf-8")
    cwd = str(sandbox)

    # non-protected path allows
    res = run_hook(script, {
        "tool_name": "Write", "cwd": cwd,
        "tool_input": {"file_path": "vault/notes/scratch.md"},
    })
    check(res["exit_code"] == 0, f"protect non-protected: exit {res['exit_code']}")
    check(pre_decision(res) != "deny",
          f"protect non-protected: should not deny, got {pre_decision(res)}")

    # non-write tool allows (Read is not a write tool)
    res = run_hook(script, {
        "tool_name": "Read", "cwd": cwd,
        "tool_input": {"file_path": "vault/Invoicing.md"},
    })
    check(pre_decision(res) != "deny",
          "protect non-write tool: Read on protected path should not deny")

    # protected path blocks
    res = run_hook(script, {
        "tool_name": "Edit", "cwd": cwd,
        "tool_input": {"file_path": "vault/Invoicing.md"},
    })
    check(res["exit_code"] == 0, f"protect blocked: exit {res['exit_code']}")
    check(pre_decision(res) == "deny",
          f"protect blocked: expected deny, got {pre_decision(res)}")
    reason = res["json"]["hookSpecificOutput"]["permissionDecisionReason"]
    check(".consent-invoicing" in reason,
          "protect blocked: deny reason should name the consent file")

    # protected path via glob (state dir) blocks too
    res = run_hook(script, {
        "tool_name": "Write", "cwd": cwd,
        "tool_input": {"file_path": "vault/state/last_session.md"},
    })
    check(pre_decision(res) == "deny",
          "protect glob: vault/state/** should deny")

    # consent file allows once and is consumed
    consent = cfg_dir / ".consent-invoicing"
    consent.write_text("", encoding="utf-8")
    res = run_hook(script, {
        "tool_name": "Edit", "cwd": cwd,
        "tool_input": {"file_path": "vault/Invoicing.md"},
    })
    check(pre_decision(res) == "allow",
          f"protect consent: expected allow, got {pre_decision(res)}")
    check(not consent.exists(),
          "protect consent: consent file should be deleted after use")
    # next edit blocks again (consent was one-time)
    res = run_hook(script, {
        "tool_name": "Edit", "cwd": cwd,
        "tool_input": {"file_path": "vault/Invoicing.md"},
    })
    check(pre_decision(res) == "deny",
          "protect consent: protection should be back in force after consumption")

    # malformed stdin fails open
    res = run_hook(script, "{ this is not json")
    check(res["exit_code"] == 0, f"protect malformed: exit {res['exit_code']}")
    check(pre_decision(res) != "deny",
          "protect malformed: bad stdin should fail open (allow)")


# --------------------------------------------------------------------------
# effort_governor
# --------------------------------------------------------------------------

def probe_governor(sandbox: Path) -> None:
    script = sandbox / "effort_governor.py"
    cfg_dir = sandbox / "config"
    # Small thresholds so the probe is fast: warn 3, block-once 4, max 6.
    cfg = {"max_calls_per_session": 6, "warn_at": 3, "block_once_at": 4}
    (cfg_dir / "governor.json").write_text(json.dumps(cfg), encoding="utf-8")

    state_dir = sandbox / "gov-state"
    state_dir.mkdir()
    env = {"COS_HOOK_STATE_DIR": str(state_dir)}
    sid = "sess-A"

    def call():
        return run_hook(script, {
            "tool_name": "Bash", "session_id": sid,
            "tool_input": {"command": "echo hi"},
        }, env_extra=env)

    # calls 1,2 under threshold -> allow, exit 0, no warning
    for n in (1, 2):
        res = call()
        check(res["exit_code"] == 0, f"governor under({n}): exit {res['exit_code']}")
        check(pre_decision(res) != "deny", f"governor under({n}): should allow")

    # call 3 == warn_at -> non-blocking warning (nonzero exit, stderr), not a deny
    res = call()
    check(pre_decision(res) != "deny", "governor warn: should not deny")
    check(res["exit_code"] != 0, "governor warn: should use non-blocking warn exit")
    check("warn" in res["stderr"].lower() or "heads up" in res["stderr"].lower(),
          f"governor warn: expected a warning on stderr, got {res['stderr']!r}")

    # call 4 == block_once_at -> deny ONCE
    res = call()
    check(pre_decision(res) == "deny",
          f"governor block-once: expected deny, got {pre_decision(res)}")
    check("scope" in res["json"]["hookSpecificOutput"]["permissionDecisionReason"].lower(),
          "governor block-once: reason should mention scope check")

    # call 5 -> block-once already fired, under max -> allow (clears)
    res = call()
    check(pre_decision(res) != "deny",
          f"governor after block-once: should clear and allow, got {pre_decision(res)}")

    # call 6 == max -> deny (hard cap), and stays denied on the next call
    res = call()
    check(pre_decision(res) == "deny", "governor max: call 6 should hit hard cap deny")
    check("cap" in res["json"]["hookSpecificOutput"]["permissionDecisionReason"].lower(),
          "governor max: reason should mention the cap")
    res = call()
    check(pre_decision(res) == "deny", "governor max: stays denied past the cap")

    # corrupt state file fails open (fresh session, garbage state)
    sid2 = "sess-B"
    bad_state = state_dir / "cos_governor_sess-B.json"
    bad_state.write_text("{ not valid json", encoding="utf-8")
    res = run_hook(script, {
        "tool_name": "Bash", "session_id": sid2,
        "tool_input": {"command": "echo hi"},
    }, env_extra=env)
    check(res["exit_code"] == 0, f"governor corrupt: exit {res['exit_code']}")
    check(pre_decision(res) != "deny",
          "governor corrupt state: should fail open (reset + allow)")

    # malformed stdin fails open
    res = run_hook(script, "not json at all", env_extra=env)
    check(res["exit_code"] == 0, "governor malformed stdin: should fail open")
    check(pre_decision(res) != "deny", "governor malformed stdin: should allow")


# --------------------------------------------------------------------------
# output_lint
# --------------------------------------------------------------------------

def write_transcript(path: Path, final_text: str) -> None:
    """Write a minimal JSONL transcript ending in an assistant message."""
    lines = [
        {"type": "user", "message": {"role": "user",
                                     "content": [{"type": "text", "text": "hello"}]}},
        {"type": "assistant", "message": {"role": "assistant",
                                          "content": [{"type": "text", "text": final_text}]}},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")


def probe_lint(sandbox: Path) -> None:
    script = sandbox / "output_lint.py"
    cfg_dir = sandbox / "config"
    cfg_path = cfg_dir / "lint_rules.json"

    # Config: em_dash enabled, a second rule disabled.
    cfg = {
        "rules": [
            {"name": "em_dash", "pattern": "—",
             "message": "Em-dash found; rewrite.", "enabled": True},
            {"name": "banned_word", "pattern": "(?i)synergy",
             "message": "Banned word.", "enabled": False},
        ]
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    tx = sandbox / "transcript.jsonl"

    # disabled rule ignored: text trips only the disabled rule -> allow
    write_transcript(tx, "Let us find synergy across the teams today.")
    res = run_hook(script, {"transcript_path": str(tx), "stop_hook_active": False})
    check(res["exit_code"] == 0, f"lint disabled: exit {res['exit_code']}")
    check(stop_decision(res) != "block",
          "lint disabled rule: should not block on a disabled rule's pattern")

    # enabled rule blocks: text contains an em-dash
    write_transcript(tx, "The plan is clear — we ship today.")
    res = run_hook(script, {"transcript_path": str(tx), "stop_hook_active": False})
    check(stop_decision(res) == "block",
          f"lint enabled: expected block, got {stop_decision(res)}")
    check("rewrite" in res["stderr"].lower(),
          "lint enabled: block reason on stderr should be the rule's message")

    # no-match allows
    write_transcript(tx, "The plan is clear, we ship today.")
    res = run_hook(script, {"transcript_path": str(tx), "stop_hook_active": False})
    check(stop_decision(res) != "block", "lint no-match: clean text should allow")

    # stop_hook_active short-circuits to allow (loop guard) even with a matching msg
    write_transcript(tx, "The plan is clear — we ship today.")
    res = run_hook(script, {"transcript_path": str(tx), "stop_hook_active": True})
    check(stop_decision(res) != "block",
          "lint stop_hook_active: should not block again (loop guard)")

    # malformed config fails open (allow), even with a matching message
    cfg_path.write_text("{ broken json", encoding="utf-8")
    write_transcript(tx, "The plan is clear — we ship today.")
    res = run_hook(script, {"transcript_path": str(tx), "stop_hook_active": False})
    check(res["exit_code"] == 0, f"lint bad config: exit {res['exit_code']}")
    check(stop_decision(res) != "block",
          "lint malformed config: should fail open (allow)")


def main() -> int:
    for name in ("protect_surfaces.py", "effort_governor.py", "output_lint.py"):
        if not (HOOKS_DIR / name).exists():
            print(f"FAIL: hook script missing: {HOOKS_DIR / name}")
            return 1

    sandbox = Path(tempfile.mkdtemp(prefix="probe_hooks_"))
    try:
        # Copy each hook plus a config/ dir into the sandbox so the probe drives
        # the real scripts against throwaway configs, never the shipped ones.
        (sandbox / "config").mkdir()
        for name in ("protect_surfaces.py", "effort_governor.py", "output_lint.py"):
            shutil.copy2(HOOKS_DIR / name, sandbox / name)

        probe_protect(sandbox)
        probe_governor(sandbox)
        probe_lint(sandbox)
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

    print("PASS: probe_hooks  protect+governor+lint, all branches, fail-open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
