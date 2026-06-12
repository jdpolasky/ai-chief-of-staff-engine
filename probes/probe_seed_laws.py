"""probe_seed_laws -- the `cos memory seed` CLI seeds laws_*.md per-section.

Run from the repo root:

    python probes/probe_seed_laws.py

Asserts, via the real CLI path (`python -m cos memory seed` as a subprocess):
  - A memory dir containing a laws_*.md seeds its sections (the whole-file
    walker skips law files; the seed orchestration must load them per-section).
  - The summary prints a "law sections: inserted N, ..." line reporting them.
  - A re-run inserts nothing new (idempotent both for whole-file and law facts).
  - A non-laws corpus still seeds exactly as before (N whole-file inserts, zero
    law sections).

Builds throwaway memory dirs + sqlite db in tempfile sandboxes (the CLI runs
apply_schema itself). Exits 0 on pass; nonzero with a printed FAIL reason.
No pytest dependency.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def run_seed(repo_root: Path, mem_dir: Path, db_path: Path, vault: Path):
    """Run `python -m cos memory seed` as a subprocess. Returns the proc."""
    env = dict(os.environ)
    env["COS_VAULT"] = str(vault)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "cos", "memory", "seed",
         "--memory-dir", str(mem_dir), "--db", str(db_path)],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )


def law_section_facts(db_path: Path) -> list[dict]:
    """Facts tagged with a law: tag (i.e. produced by the per-section loader)."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("SELECT * FROM facts WHERE retracted = 0")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()
    return [r for r in rows if "law:" in (r.get("tags") or "")]


def parse_law_inserted(stdout: str) -> int:
    """Pull N from the 'law sections: inserted N, ...' summary line."""
    m = re.search(r"law sections: inserted (\d+)", stdout)
    if not m:
        raise ProbeFail(f"no 'law sections: inserted N' line in:\n{stdout}")
    return int(m.group(1))


def parse_whole_file_inserted(stdout: str) -> int:
    """Pull N from the 'memory-file loader: ... inserted N, ...' line."""
    m = re.search(r"memory-file loader:.*?inserted (\d+)", stdout)
    if not m:
        raise ProbeFail(f"no whole-file 'inserted N' line in:\n{stdout}")
    return int(m.group(1))


LAW_FILE = (
    "---\n"
    "type: law\n"
    "description: Governing rules for the agent.\n"
    "---\n"
    "# Operating Law\n\n"
    "## 1. Diagnose first\n\n"
    "When a problem is flagged, diagnose the root cause before acting.\n\n"
    "## 2. Compound rule\n\n"
    "Intro text for the compound rule that precedes the first child.\n\n"
    "### 2a. First child\n\n"
    "First child body, a small leaf section.\n\n"
    "### 2b. Second child\n\n"
    "Second child body, another small leaf section.\n\n"
    "## Provenance\n\n"
    "This footer must be skipped by the splitter.\n"
)

USER_FILE = (
    "---\n"
    "type: user\n"
    "description: Owner directs the system at a high level.\n"
    "---\n"
    "The owner works across many domains and prefers concise prose.\n"
)

FEEDBACK_FILE = (
    "---\n"
    "type: feedback\n"
    "description: Keep responses concise and warm.\n"
    "---\n"
    "No corporate filler.\n"
)


def assert_laws_seeded(repo_root: Path) -> None:
    sandbox = Path(tempfile.mkdtemp(prefix="probe_seed_laws_"))
    try:
        mem_dir = sandbox / "memory"
        mem_dir.mkdir()
        vault = sandbox / "vault"
        vault.mkdir()
        db_path = sandbox / "seed.db"

        write(mem_dir / "user_owner.md", USER_FILE)
        write(mem_dir / "feedback_tone.md", FEEDBACK_FILE)
        write(mem_dir / "laws_operating.md", LAW_FILE)

        # ---- first run ----
        proc = run_seed(repo_root, mem_dir, db_path, vault)
        check(proc.returncode == 0,
              f"first seed rc={proc.returncode}\nout={proc.stdout}\nerr={proc.stderr}")

        wf = parse_whole_file_inserted(proc.stdout)
        check(wf == 2,
              f"expected 2 whole-file inserts (user + feedback), got {wf}\n{proc.stdout}")

        law_n = parse_law_inserted(proc.stdout)
        check(law_n >= 3,
              f"expected >=3 law sections (1, 2a, 2b) inserted, got {law_n}\n{proc.stdout}")

        # DB shape: law facts exist, carry law: + section: tags, under the cap.
        law_facts = law_section_facts(db_path)
        check(len(law_facts) == law_n,
              f"DB law-fact count {len(law_facts)} != summary {law_n}")
        anchors = set()
        for r in law_facts:
            tags = r.get("tags") or ""
            check("law:operating" in tags, f"law fact missing law:operating tag: {tags}")
            m = re.search(r"section:([0-9a-z.]+)", tags)
            check(m is not None, f"law fact missing section: tag: {tags}")
            anchors.add(m.group(1))
            check(len(r["content"]) <= 2000,
                  f"law fact exceeds BRAID cap: len={len(r['content'])}")
        check("1" in anchors, f"missing section anchor 1: {anchors}")
        check("2a" in anchors and "2b" in anchors,
              f"missing compound-rule children 2a/2b: {anchors}")
        check(all(not a.startswith("provenance") for a in anchors),
              f"Provenance footer leaked into law sections: {anchors}")

        # ---- re-run: nothing new ----
        proc2 = run_seed(repo_root, mem_dir, db_path, vault)
        check(proc2.returncode == 0,
              f"re-run rc={proc2.returncode}\nout={proc2.stdout}\nerr={proc2.stderr}")
        check(parse_whole_file_inserted(proc2.stdout) == 0,
              f"re-run inserted whole-files (not idempotent):\n{proc2.stdout}")
        check(parse_law_inserted(proc2.stdout) == 0,
              f"re-run inserted law sections (not idempotent):\n{proc2.stdout}")

        # DB count unchanged after re-run.
        check(len(law_section_facts(db_path)) == law_n,
              "law-fact count changed across idempotent re-run")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def assert_non_law_corpus_unchanged(repo_root: Path) -> None:
    """A corpus with NO law files seeds exactly as before: N whole-file inserts,
    zero law sections, and the law summary line still prints (inserted 0)."""
    sandbox = Path(tempfile.mkdtemp(prefix="probe_seed_nolaw_"))
    try:
        mem_dir = sandbox / "memory"
        mem_dir.mkdir()
        vault = sandbox / "vault"
        vault.mkdir()
        db_path = sandbox / "seed.db"

        write(mem_dir / "user_owner.md", USER_FILE)
        write(mem_dir / "feedback_tone.md", FEEDBACK_FILE)

        proc = run_seed(repo_root, mem_dir, db_path, vault)
        check(proc.returncode == 0,
              f"non-law seed rc={proc.returncode}\nout={proc.stdout}\nerr={proc.stderr}")
        check(parse_whole_file_inserted(proc.stdout) == 2,
              f"expected 2 whole-file inserts, got:\n{proc.stdout}")
        check(parse_law_inserted(proc.stdout) == 0,
              f"expected 0 law sections in a no-law corpus, got:\n{proc.stdout}")
        check(not law_section_facts(db_path),
              "law facts present in DB for a no-law corpus")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def main() -> int:
    try:
        assert_laws_seeded(REPO_ROOT)
        assert_non_law_corpus_unchanged(REPO_ROOT)
    except ProbeFail as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:  # noqa: BLE001 -- probe surfaces any failure
        import traceback
        print(f"FAIL: unexpected error: {e!r}")
        traceback.print_exc()
        return 1

    print("PASS: probe_seed_laws all assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
