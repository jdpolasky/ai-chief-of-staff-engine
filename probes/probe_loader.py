"""probe_loader -- self-contained behavioral probe for cos.memory.loader.

Run from the repo root:

    python probes/probe_loader.py

Exits 0 on pass; nonzero with a printed FAIL reason on the first failed
assertion. Builds a throwaway memory dir and sqlite db in a tempfile.mkdtemp()
sandbox (via the engine's own apply_schema), exercises the loader, and cleans
up after itself. No pytest dependency.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

# Make the repo root importable when run as `python probes/probe_loader.py`.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cos.memory.loader import (  # noqa: E402
    load_memory_file_sections,
    load_memory_files,
)
from cos.memory.migrate import apply_schema  # noqa: E402


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def fact_rows(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute("SELECT * FROM facts WHERE retracted = 0")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def tags_of(row: dict) -> list[str]:
    raw = row.get("tags")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def build_fixtures(mem_dir: Path) -> None:
    # 1. valid user_*.md -> capability / person, slug "owner"
    write(mem_dir / "user_owner.md", (
        "---\n"
        "type: user\n"
        "description: Owner is a generalist who directs the system at a high level.\n"
        "---\n"
        "The owner prefers concise prose and works across many domains at once.\n"
    ))

    # 2. feedback_*.md -> preference / NULL subject
    write(mem_dir / "feedback_concise_output.md", (
        "---\n"
        "type: feedback\n"
        "description: Keep responses concise; prose over bullet lists.\n"
        "---\n"
        "Direct and warm, not corporate. No filler.\n"
    ))

    # 3. nested metadata.type honored when top-level type absent
    write(mem_dir / "project_nested.md", (
        "---\n"
        "metadata:\n"
        "  type: project\n"
        "  originSession: 42\n"
        "---\n"
        "A standing project whose type lives under the metadata block.\n"
    ))

    # 4. unknown type -> skipped_unknown_type, not rejected
    write(mem_dir / "mystery_unknown.md", (
        "---\n"
        "type: wat\n"
        "description: This type is not in the mapping.\n"
        "---\n"
        "Body that should never be inserted.\n"
    ))

    # 5. laws_*.md with two `##` sections; the second has `###` children.
    #    The first `##` section is numbered "5." with an over-cap body so it
    #    splits into parts 5.1, 5.2 via chunk_text.
    big_para_a = ("ALPHA " * 400).strip()   # ~2400 chars
    big_para_b = ("BETA " * 400).strip()    # ~2000 chars
    write(mem_dir / "laws_governance.md", (
        "---\n"
        "type: law\n"
        "description: Governing rules for the agent.\n"
        "---\n"
        "# Governance Law\n\n"
        "## 5. Oversized rule\n\n"
        f"{big_para_a}\n\n"
        f"{big_para_b}\n\n"
        "## 6. Compound rule\n\n"
        "Intro text for the compound rule that precedes the first child.\n\n"
        "### 6a. First child\n\n"
        "First child body, a small leaf section.\n\n"
        "### 6b. Second child\n\n"
        "Second child body, another small leaf section.\n\n"
        "## Provenance\n\n"
        "This footer must be skipped by the splitter.\n"
    ))


def assert_whole_file_loads(mem_dir: Path, db_path: Path) -> None:
    apply_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        summary = load_memory_files(conn, mem_dir)
    finally:
        conn.close()

    inserted_names = {n for n, _ in summary.inserted}
    check("user_owner.md" in inserted_names, "user_owner.md was not inserted")
    check("feedback_concise_output.md" in inserted_names,
          "feedback_concise_output.md was not inserted")
    check("project_nested.md" in inserted_names,
          "project_nested.md (nested metadata.type) was not inserted")

    # unknown type counted as skipped_unknown_type, not rejected
    check("mystery_unknown.md" in summary.skipped_unknown_type,
          f"unknown-type file not in skipped_unknown_type: {summary.skipped_unknown_type}")
    check(not summary.rejected,
          f"unexpected rejections: {summary.rejected}")

    # laws_*.md must be SKIPPED by the whole-file walker entirely.
    check("laws_governance.md" not in inserted_names,
          "laws_governance.md was loaded by the whole-file walker (double-load risk)")
    check(all(n != "laws_governance.md" for n in summary.skipped_idempotent),
          "laws file appeared in whole-file walker results")

    # Now assert DB-level shape of the seeded facts.
    conn = sqlite3.connect(db_path)
    try:
        rows = fact_rows(conn)
    finally:
        conn.close()
    by_file = {}
    for r in rows:
        for t in tags_of(r):
            if t.startswith("seed_file:"):
                by_file[t.split(":", 1)[1]] = r

    owner = by_file.get("user_owner.md")
    check(owner is not None, "user_owner.md fact missing from DB")
    check(owner["category"] == "capability",
          f"user_owner category != capability: {owner['category']}")
    check(owner["subject_type"] == "person",
          f"user_owner subject_type != person: {owner['subject_type']}")
    check(owner["subject_id"] == "owner",
          f"user_owner subject_id != owner: {owner['subject_id']}")

    feedback = by_file.get("feedback_concise_output.md")
    check(feedback is not None, "feedback fact missing from DB")
    check(feedback["category"] == "preference",
          f"feedback category != preference: {feedback['category']}")
    check(feedback["subject_id"] is None,
          f"feedback subject_id not NULL: {feedback['subject_id']!r}")


def assert_idempotent(mem_dir: Path, db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        summary = load_memory_files(conn, mem_dir)
    finally:
        conn.close()
    check(not summary.inserted,
          f"second run inserted facts (not idempotent): {summary.inserted}")
    # all three valid files should now be idempotent skips
    for name in ("user_owner.md", "feedback_concise_output.md", "project_nested.md"):
        check(name in summary.skipped_idempotent,
              f"{name} not counted as idempotent skip: {summary.skipped_idempotent}")


def assert_law_sections(mem_dir: Path, db_path: Path) -> None:
    law_path = mem_dir / "laws_governance.md"
    conn = sqlite3.connect(db_path)
    try:
        result = load_memory_file_sections(conn, law_path)
    finally:
        conn.close()

    anchors = [a for a, _ in result.inserted]
    check(result.inserted, f"no law sections inserted; skipped={result.skipped}")

    # Provenance footer must not produce a section.
    check(all(not a.startswith("provenance") for a in anchors),
          f"Provenance footer leaked into sections: {anchors}")

    # Leaf sections for the compound rule's children.
    check("6a" in anchors, f"missing leaf section 6a: {anchors}")
    check("6b" in anchors, f"missing leaf section 6b: {anchors}")

    # Over-cap section 5 split into ordered parts 5.1, 5.2 (chunked, no loss).
    check("5.1" in anchors and "5.2" in anchors,
          f"over-cap section did not chunk into 5.1/5.2: {anchors}")

    # Verify the chunked facts carry law:<name> + section:<anchor> tags and
    # that the chunked content together preserves the oversized body.
    conn = sqlite3.connect(db_path)
    try:
        rows = fact_rows(conn)
    finally:
        conn.close()

    law_rows = [r for r in rows if "law:governance" in tags_of(r)]
    check(law_rows, "no facts tagged law:governance")
    for r in law_rows:
        ts = tags_of(r)
        check(any(t.startswith("section:") for t in ts),
              f"law fact missing section: tag: {ts}")
        check(len(r["content"]) <= 2000,
              f"law fact content exceeds BRAID cap: len={len(r['content'])}")

    # Content preservation: ALPHA/BETA tokens span all 5.x parts without loss.
    part_contents = []
    for r in law_rows:
        for t in tags_of(r):
            if t.startswith("section:5."):
                part_contents.append(r["content"])
    joined = " ".join(part_contents)
    alpha_count = joined.count("ALPHA")
    beta_count = joined.count("BETA")
    check(alpha_count >= 390,
          f"ALPHA tokens lost in chunking: found {alpha_count}, expected ~400")
    check(beta_count >= 390,
          f"BETA tokens lost in chunking: found {beta_count}, expected ~400")


def assert_cli_end_to_end(repo_root: Path) -> None:
    sandbox = Path(tempfile.mkdtemp(prefix="probe_loader_cli_"))
    try:
        mem_dir = sandbox / "memory"
        mem_dir.mkdir()
        vault = sandbox / "vault"
        vault.mkdir()
        db_path = sandbox / "cli.db"

        # Two clean, valid files -> expect exactly 2 inserts.
        write(mem_dir / "user_owner.md", (
            "---\n"
            "type: user\n"
            "description: Owner directs the system.\n"
            "---\n"
            "The owner works across many domains.\n"
        ))
        write(mem_dir / "feedback_tone.md", (
            "---\n"
            "type: feedback\n"
            "description: Keep responses concise and warm.\n"
            "---\n"
            "No corporate filler.\n"
        ))

        env = dict(os.environ)
        env["COS_VAULT"] = str(vault)
        # PYTHONIOENCODING so the subprocess stdout is decodable cross-platform.
        env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.run(
            [sys.executable, "-m", "cos", "memory", "seed",
             "--memory-dir", str(mem_dir), "--db", str(db_path)],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
        )
        check(proc.returncode == 0,
              f"CLI exit code != 0: {proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}")
        check("inserted 2" in proc.stdout,
              f"CLI summary did not report 'inserted 2':\n{proc.stdout}")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="probe_loader_"))
    try:
        mem_dir = sandbox / "memory"
        mem_dir.mkdir()
        db_path = sandbox / "memory.db"

        build_fixtures(mem_dir)
        assert_whole_file_loads(mem_dir, db_path)
        assert_idempotent(mem_dir, db_path)
        assert_law_sections(mem_dir, db_path)
        assert_cli_end_to_end(REPO_ROOT)
    except ProbeFail as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:  # noqa: BLE001 -- probe surfaces any failure
        import traceback
        print(f"FAIL: unexpected error: {e!r}")
        traceback.print_exc()
        return 1
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)

    print("PASS: probe_loader all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
