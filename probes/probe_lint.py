"""probe_lint -- self-contained behavioral probe for cos.lint and `cos lint`.

Run from the repo root:

    python probes/probe_lint.py

Builds throwaway memory corpora in a tempfile.mkdtemp() sandbox and asserts
each of the five checks fires on a corpus that triggers it, plus the clean path
and the read-only / exit-code contract. Per the repo's standing rule every check
ships with a probe assertion that takes its branch. Exits 0 on pass; nonzero
with a printed FAIL reason. No pytest dependency.

Checks covered:
  index-orphans         file present but unlisted; index line to a missing file;
                        missing index entirely.
  frontmatter-malformed file missing a required key; invalid YAML.
  stale-superseded      SUPERSEDED / RESOLVED in the first three body lines.
  duplicate-names       two files sharing one frontmatter name.
  broken-wikilinks      [[name]] resolving to no corpus name.
  clean                 a well-formed corpus reports nothing.
  cli                   `cos lint` exits 0 + "corpus clean" on clean,
                        1 + a finding line on dirty, and never writes a file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cos.lint import run_lint  # noqa: E402


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def mem_file(name: str, description: str, mem_type: str, body: str) -> str:
    """A well-formed memory file with the three required frontmatter keys."""
    return (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"type: {mem_type}\n"
        "---\n\n"
        f"{body}\n"
    )


def index(entries: list[tuple[str, str]]) -> str:
    """A MEMORY.md index. entries are (filename, title) pairs."""
    lines = ["# Memory Index", "", "The loader skips this file.", ""]
    for filename, title in entries:
        lines.append(f"- [{title}]({filename}) -- a hook line")
    return "\n".join(lines) + "\n"


def findings_by_check(memory_dir: Path) -> dict[str, list]:
    out: dict[str, list] = {}
    for f in run_lint(memory_dir):
        out.setdefault(f.check, []).append(f)
    return out


def fresh_dir(sandbox: Path, name: str) -> Path:
    d = sandbox / name
    d.mkdir()
    return d


# --- clean corpus -----------------------------------------------------------

def build_clean(d: Path) -> None:
    write(d / "user_owner.md", mem_file(
        "user-owner", "Who the owner is.", "user",
        "The owner directs the system. See [[project-flagship]] for the main job.",
    ))
    write(d / "project_flagship.md", mem_file(
        "project-flagship", "The flagship project.", "project",
        "Standing project state. Cross-links to [[user-owner]].",
    ))
    write(d / "feedback_concise.md", mem_file(
        "feedback-concise", "Keep it short.", "feedback",
        "Direct and warm. No filler.",
    ))
    write(d / "MEMORY.md", index([
        ("user_owner.md", "Owner"),
        ("project_flagship.md", "Flagship"),
        ("feedback_concise.md", "Concise"),
    ]))


def assert_clean(sandbox: Path) -> None:
    d = fresh_dir(sandbox, "clean")
    build_clean(d)
    findings = run_lint(d)
    check(not findings, f"clean corpus produced findings: {[f.to_line() for f in findings]}")


# --- index-orphans ----------------------------------------------------------

def assert_index_orphans(sandbox: Path) -> None:
    d = fresh_dir(sandbox, "orphans")
    build_clean(d)
    # Add a file the index does not list.
    write(d / "reference_unlisted.md", mem_file(
        "reference-unlisted", "A tool nobody indexed.", "reference",
        "Present on disk, absent from MEMORY.md.",
    ))
    # And an index that points at a file that does not exist, while still
    # listing the real ones (so only the two drifts show).
    write(d / "MEMORY.md", index([
        ("user_owner.md", "Owner"),
        ("project_flagship.md", "Flagship"),
        ("feedback_concise.md", "Concise"),
        ("reference_ghost.md", "Ghost"),  # no such file
    ]))
    by = findings_by_check(d)
    orphans = by.get("index-orphans", [])
    targets = {f.target for f in orphans}
    check("reference_unlisted.md" in targets,
          f"present-but-unlisted file not flagged: {[f.to_line() for f in orphans]}")
    check("reference_ghost.md" in targets,
          f"index line to missing file not flagged: {[f.to_line() for f in orphans]}")

    # Missing index entirely: reported once, not per file.
    d2 = fresh_dir(sandbox, "orphans_noindex")
    build_clean(d2)
    (d2 / "MEMORY.md").unlink()
    by2 = findings_by_check(d2)
    no_idx = by2.get("index-orphans", [])
    check(len(no_idx) == 1 and no_idx[0].target == "MEMORY.md",
          f"missing index should report once as MEMORY.md: {[f.to_line() for f in no_idx]}")


# --- frontmatter-malformed --------------------------------------------------

def assert_frontmatter_malformed(sandbox: Path) -> None:
    d = fresh_dir(sandbox, "malformed")
    build_clean(d)
    # Missing the `type` key.
    write(d / "feedback_notype.md", (
        "---\n"
        "name: feedback-notype\n"
        "description: This one forgot its type.\n"
        "---\n\n"
        "Body with no type in frontmatter.\n"
    ))
    # Invalid YAML in the frontmatter block.
    write(d / "feedback_badyaml.md", (
        "---\n"
        "name: feedback-badyaml\n"
        "description: [unterminated\n"
        "type: feedback\n"
        "---\n\n"
        "Body after broken yaml.\n"
    ))
    # Keep the index honest so index-orphans does not also fire on these.
    write(d / "MEMORY.md", index([
        ("user_owner.md", "Owner"),
        ("project_flagship.md", "Flagship"),
        ("feedback_concise.md", "Concise"),
        ("feedback_notype.md", "NoType"),
        ("feedback_badyaml.md", "BadYaml"),
    ]))
    by = findings_by_check(d)
    mal = by.get("frontmatter-malformed", [])
    targets = {f.target for f in mal}
    check("feedback_notype.md" in targets,
          f"missing-type file not flagged: {[f.to_line() for f in mal]}")
    check("feedback_badyaml.md" in targets,
          f"invalid-yaml file not flagged: {[f.to_line() for f in mal]}")


# --- stale-superseded -------------------------------------------------------

def assert_stale_superseded(sandbox: Path) -> None:
    d = fresh_dir(sandbox, "stale")
    build_clean(d)
    write(d / "project_done.md", mem_file(
        "project-done", "A finished project still in the live corpus.", "project",
        "SUPERSEDED by project-flagship. This note's job is done.",
    ))
    write(d / "feedback_resolved.md", mem_file(
        "feedback-resolved", "A correction that has been resolved.", "feedback",
        "RESOLVED: the owner changed the workflow, this no longer applies.",
    ))
    # A file with the marker DEEP in the body (line 5+) must NOT trip the check.
    write(d / "reference_mentions.md", mem_file(
        "reference-mentions", "A note that merely mentions the words.", "reference",
        "Line one.\nLine two.\nLine three.\nLine four mentions SUPERSEDED in prose.",
    ))
    write(d / "MEMORY.md", index([
        ("user_owner.md", "Owner"),
        ("project_flagship.md", "Flagship"),
        ("feedback_concise.md", "Concise"),
        ("project_done.md", "Done"),
        ("feedback_resolved.md", "Resolved"),
        ("reference_mentions.md", "Mentions"),
    ]))
    by = findings_by_check(d)
    stale = by.get("stale-superseded", [])
    targets = {f.target for f in stale}
    check("project_done.md" in targets,
          f"SUPERSEDED-in-head file not flagged: {[f.to_line() for f in stale]}")
    check("feedback_resolved.md" in targets,
          f"RESOLVED-in-head file not flagged: {[f.to_line() for f in stale]}")
    check("reference_mentions.md" not in targets,
          "marker deep in the body should not trip the stale check (false positive)")


# --- duplicate-names --------------------------------------------------------

def assert_duplicate_names(sandbox: Path) -> None:
    d = fresh_dir(sandbox, "dupes")
    build_clean(d)
    # A second file claiming a name already taken by project_flagship.md.
    write(d / "project_flagship_copy.md", mem_file(
        "project-flagship", "An accidental duplicate of the flagship name.",
        "project", "Same name, different file. Ambiguous to retrieval.",
    ))
    write(d / "MEMORY.md", index([
        ("user_owner.md", "Owner"),
        ("project_flagship.md", "Flagship"),
        ("feedback_concise.md", "Concise"),
        ("project_flagship_copy.md", "FlagshipCopy"),
    ]))
    by = findings_by_check(d)
    dupes = by.get("duplicate-names", [])
    check(any(f.target == "project-flagship" for f in dupes),
          f"shared frontmatter name not flagged: {[f.to_line() for f in dupes]}")
    # The detail should name both colliding files.
    dupe = next(f for f in dupes if f.target == "project-flagship")
    check("project_flagship.md" in dupe.detail and "project_flagship_copy.md" in dupe.detail,
          f"duplicate detail should name both files: {dupe.detail}")


# --- broken-wikilinks -------------------------------------------------------

def assert_broken_wikilinks(sandbox: Path) -> None:
    d = fresh_dir(sandbox, "wikilinks")
    build_clean(d)
    write(d / "project_links.md", mem_file(
        "project-links", "A note linking to a name that does not exist.", "project",
        "Points at [[user-owner]] (real) and [[reference-ghost]] (dangling). "
        "Also a piped link [[project-flagship|the flagship]] which is real.",
    ))
    write(d / "MEMORY.md", index([
        ("user_owner.md", "Owner"),
        ("project_flagship.md", "Flagship"),
        ("feedback_concise.md", "Concise"),
        ("project_links.md", "Links"),
    ]))
    by = findings_by_check(d)
    broken = by.get("broken-wikilinks", [])
    details = " ".join(f.detail for f in broken)
    check("reference-ghost" in details,
          f"dangling wikilink not flagged: {[f.to_line() for f in broken]}")
    check("user-owner" not in details,
          "real wikilink should not be flagged as broken")
    check("project-flagship" not in details,
          "piped wikilink to a real name should not be flagged as broken")


# --- CLI + read-only contract -----------------------------------------------

def run_cli(memory_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "cos", "lint", "--memory-dir", str(memory_dir)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def dir_snapshot(d: Path) -> dict[str, tuple[float, int]]:
    """mtime + size per file, to prove the lint never wrote anything."""
    snap: dict[str, tuple[float, int]] = {}
    for p in sorted(d.glob("*.md")):
        st = p.stat()
        snap[p.name] = (st.st_mtime, st.st_size)
    return snap


def assert_cli_and_readonly(sandbox: Path) -> None:
    # Clean corpus: exit 0, "corpus clean".
    clean = fresh_dir(sandbox, "cli_clean")
    build_clean(clean)
    before = dir_snapshot(clean)
    proc = run_cli(clean)
    check(proc.returncode == 0,
          f"clean CLI exit != 0: {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    check("corpus clean" in proc.stdout,
          f"clean CLI did not print 'corpus clean':\n{proc.stdout}")
    check(dir_snapshot(clean) == before,
          "lint modified a file on the clean corpus (must be read-only)")

    # Dirty corpus: exit 1, a finding line, and still no writes.
    dirty = fresh_dir(sandbox, "cli_dirty")
    build_clean(dirty)
    write(dirty / "reference_unlisted.md", mem_file(
        "reference-unlisted", "Not in the index.", "reference", "Orphan body.",
    ))
    before_d = dir_snapshot(dirty)
    proc = run_cli(dirty)
    check(proc.returncode == 1,
          f"dirty CLI exit != 1: {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    check("index-orphans" in proc.stdout,
          f"dirty CLI did not list the orphan finding:\n{proc.stdout}")
    check(dir_snapshot(dirty) == before_d,
          "lint modified a file on the dirty corpus (must be read-only)")

    # --json on the dirty corpus reports the finding and exits 1.
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, "-m", "cos", "lint", "--memory-dir", str(dirty), "--json"],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
    )
    check(proc.returncode == 1, f"--json dirty exit != 1: {proc.returncode}")
    import json as _json
    payload = _json.loads(proc.stdout)
    check(payload["clean"] is False and payload["count"] >= 1,
          f"--json payload wrong for dirty corpus: {payload}")


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="probe_lint_"))
    try:
        assert_clean(sandbox)
        assert_index_orphans(sandbox)
        assert_frontmatter_malformed(sandbox)
        assert_stale_superseded(sandbox)
        assert_duplicate_names(sandbox)
        assert_broken_wikilinks(sandbox)
        assert_cli_and_readonly(sandbox)
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

    print("PASS: probe_lint  five checks + clean + cli + read-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
