"""cos.lint -- deterministic structural checks over the memory corpus.

The corpus rots quietly: the index drifts out of sync with the files, two rules
end up named the same thing, a note is marked superseded but never moved, a
wikilink points at a name that no longer exists. None of that is a bug in the
engine; it is entropy in the human-authored markdown. This module reads the
corpus and reports the entropy. It is the deterministic half of the self-tending
ritual (the judgment half, the dream run, lives in `commands/dream.md`).

Five checks, all stdlib + the loader's own parsing helpers, no new deps:

  index-orphans        files present but absent from MEMORY.md, and index lines
                       pointing at files that do not exist.
  frontmatter-malformed files whose frontmatter lacks name, description, or type.
  stale-superseded     files whose first three body lines carry SUPERSEDED or
                       RESOLVED yet still sit in the live corpus root.
  duplicate-names      two files sharing one frontmatter `name`.
  broken-wikilinks     [[name]] references to a name no corpus file declares.

The lint is **read-only by construction**: it opens files for reading, never for
writing, and touches no database. A ritual that is silent on success and loud on
findings: an empty finding list is "corpus clean," anything else is a list the
owner (or the dream run) triages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cos.memory.loader import parse_frontmatter

# One MEMORY.md index line: "- [Title](file.md) -- hook". We only need the
# link target (the filename in the parentheses).
_INDEX_LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")

# Inline wikilink: [[name]] or [[name|alias]]. We match the target before any
# pipe and ignore section anchors (#...) the way Obsidian resolves them.
_WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+)")

INDEX_FILENAME = "MEMORY.md"
REQUIRED_FRONTMATTER = ("name", "description", "type")
STALE_MARKERS = ("SUPERSEDED", "RESOLVED")
STALE_SCAN_LINES = 3  # how many leading body lines the stale check inspects


@dataclass(frozen=True)
class Finding:
    """One lint finding. `check` is the check id; `target` the file or name it
    concerns; `detail` a one-line human explanation."""
    check: str
    target: str
    detail: str

    def to_line(self) -> str:
        return f"{self.check}: {self.target} -- {self.detail}"

    def to_dict(self) -> dict[str, str]:
        return {"check": self.check, "target": self.target, "detail": self.detail}


def corpus_files(memory_dir: Path) -> list[Path]:
    """Sorted *.md memory files in the corpus root, excluding the index.

    Mirrors the loader's own walk: top-level *.md only, MEMORY.md skipped. The
    lint deliberately does not recurse, matching how the corpus is seeded.
    """
    return [
        p for p in sorted(memory_dir.glob("*.md"))
        if p.name != INDEX_FILENAME
    ]


def _safe_frontmatter(path: Path) -> tuple[dict[str, Any], str, str | None]:
    """Read a file and split frontmatter. Returns (front, body, error).

    `error` is None on success, else a short reason ("read_error" /
    "yaml_error"). Read-only: opens for reading only. Reuses the loader's
    parse_frontmatter so the lint validates exactly what the loader will parse.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return {}, "", f"read_error: {e!r}"
    try:
        front, body = parse_frontmatter(text)
    except yaml.YAMLError as e:
        msg = str(e).replace("\n", " ").strip()
        return {}, text, f"yaml_error: {msg}"
    return front, body, None


def _frontmatter_name(front: dict[str, Any]) -> str | None:
    """The declared `name`, honoring a nested metadata block the way the loader
    tolerates nested `type`. Returns None when absent or not a string."""
    name = front.get("name")
    if name is None and isinstance(front.get("metadata"), dict):
        name = front["metadata"].get("name")
    return name if isinstance(name, str) and name.strip() else None


def _has_field(front: dict[str, Any], field: str) -> bool:
    """True if `field` is present (top-level or nested under metadata) and
    non-empty. Matches the loader's top-level-or-nested fallback."""
    val = front.get(field)
    if val is None and isinstance(front.get("metadata"), dict):
        val = front["metadata"].get(field)
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    return True


# --- the five checks --------------------------------------------------------

def check_index_orphans(memory_dir: Path, files: list[Path]) -> list[Finding]:
    """Files present but missing from MEMORY.md, and index lines pointing at
    files that do not exist. Two directions of the same drift."""
    findings: list[Finding] = []
    index_path = memory_dir / INDEX_FILENAME
    present = {p.name for p in files}

    if not index_path.is_file():
        # No index at all: every file is an orphan in the sense that nothing
        # lists it. Report the missing index once rather than N times.
        findings.append(Finding(
            "index-orphans", INDEX_FILENAME,
            "index file is missing; no memory is listed",
        ))
        return findings

    try:
        index_text = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        findings.append(Finding(
            "index-orphans", INDEX_FILENAME, f"index unreadable: {e!r}",
        ))
        return findings

    listed = set(_INDEX_LINK_RE.findall(index_text))

    for name in sorted(present - listed):
        findings.append(Finding(
            "index-orphans", name, "file present but not listed in MEMORY.md",
        ))
    for name in sorted(listed - present):
        findings.append(Finding(
            "index-orphans", name,
            "MEMORY.md links this file but it does not exist",
        ))
    return findings


def check_frontmatter_malformed(files: list[Path]) -> list[Finding]:
    """Files whose frontmatter lacks name, description, or type (or whose
    frontmatter is unreadable / invalid YAML)."""
    findings: list[Finding] = []
    for path in files:
        front, _body, error = _safe_frontmatter(path)
        if error:
            findings.append(Finding(
                "frontmatter-malformed", path.name, error,
            ))
            continue
        missing = [f for f in REQUIRED_FRONTMATTER if not _has_field(front, f)]
        if missing:
            findings.append(Finding(
                "frontmatter-malformed", path.name,
                f"frontmatter missing: {', '.join(missing)}",
            ))
    return findings


def check_stale_superseded(files: list[Path]) -> list[Finding]:
    """Files whose first three body lines carry SUPERSEDED or RESOLVED yet still
    sit in the live corpus root. The marker means the note's job is done; a done
    note that stays in the live corpus keeps seeding into retrieval."""
    findings: list[Finding] = []
    for path in files:
        _front, body, error = _safe_frontmatter(path)
        if error:
            # frontmatter check already reports the unreadable file; skip here.
            continue
        head_lines = body.lstrip("\n").splitlines()[:STALE_SCAN_LINES]
        head = "\n".join(head_lines)
        for marker in STALE_MARKERS:
            if marker in head:
                findings.append(Finding(
                    "stale-superseded", path.name,
                    f"body marked {marker} in the first {STALE_SCAN_LINES} lines "
                    "but still in the live corpus",
                ))
                break
    return findings


def check_duplicate_names(files: list[Path]) -> list[Finding]:
    """Two or more files sharing one frontmatter `name`. The schema keys
    retrieval and wikilinks on the name, so a collision is ambiguous."""
    findings: list[Finding] = []
    by_name: dict[str, list[str]] = {}
    for path in files:
        front, _body, error = _safe_frontmatter(path)
        if error:
            continue
        name = _frontmatter_name(front)
        if name is None:
            continue  # missing name is the frontmatter check's job, not this one
        by_name.setdefault(name, []).append(path.name)

    for name in sorted(by_name):
        owners = sorted(by_name[name])
        if len(owners) > 1:
            findings.append(Finding(
                "duplicate-names", name,
                f"declared by {len(owners)} files: {', '.join(owners)}",
            ))
    return findings


def check_broken_wikilinks(files: list[Path]) -> list[Finding]:
    """[[name]] references to a name that no corpus file declares.

    Wikilinks resolve against frontmatter `name` values (kebab-case), not
    filenames, matching how the corpus authors cross-link. A link whose target
    is in no file's `name` is broken.
    """
    findings: list[Finding] = []
    known_names: set[str] = set()
    parsed: list[tuple[Path, str]] = []  # (path, body) for the second pass

    for path in files:
        front, body, error = _safe_frontmatter(path)
        if error:
            continue
        name = _frontmatter_name(front)
        if name is not None:
            known_names.add(name)
        parsed.append((path, body))

    for path, body in parsed:
        seen_in_file: set[str] = set()
        for raw in _WIKILINK_RE.findall(body):
            target = raw.strip()
            if not target or target in seen_in_file:
                continue
            seen_in_file.add(target)
            if target not in known_names:
                findings.append(Finding(
                    "broken-wikilinks", path.name,
                    f"[[{target}]] resolves to no memory name",
                ))
    return findings


# --- orchestration ----------------------------------------------------------

def run_lint(memory_dir: Path) -> list[Finding]:
    """Run all five checks over memory_dir and return a flat list of Findings.

    Read-only. Returns [] for a clean corpus. The ordering is check-by-check in
    a stable order so output is deterministic and diffable.
    """
    files = corpus_files(memory_dir)
    findings: list[Finding] = []
    findings += check_index_orphans(memory_dir, files)
    findings += check_frontmatter_malformed(files)
    findings += check_stale_superseded(files)
    findings += check_duplicate_names(files)
    findings += check_broken_wikilinks(files)
    return findings
