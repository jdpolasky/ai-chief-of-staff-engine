"""cos.memory.loader -- Markdown memory files -> facts.

Walks a directory of `*.md` memory files and writes each one as a fact through
the same validated write path used by `cos memory add` (write-contract
validation + writers + facts.jsonl backup). Idempotent via content-exact dedup;
re-runs against unchanged files are no-ops.

Maps a memory file's frontmatter `type` to a BRAID `category`:
    feedback -> preference   (operating rules for your agent)
    user     -> capability   (facts about the owner)
    self     -> reference    (the agent's running observations)
    project  -> reference    (standing project-state knowledge)
    reference-> reference    (standing reference knowledge)
    law      -> reference    (governing rules, loaded per section)

Source enum is `manual` (the write contract's closest match for file ingest).
Confidence is 0.95 across the board (committed, hand-authored rules).
valid_from defaults to file mtime; tx_from is now() at insert.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from cos.config import MEMORY_DIR

DEFAULT_MEMORY_DIR = MEMORY_DIR

# Memory `type` -> BRAID `category`. Lives as a constant for easy override.
TYPE_TO_CATEGORY: dict[str, str] = {
    "feedback": "preference",
    "user": "capability",
    "self": "reference",
    "project": "reference",
    "reference": "reference",
    "law": "reference",  # Law files map honestly to reference rather than as `feedback`
}

# subject_type rules: filename prefix -> subject_type
PREFIX_TO_SUBJECT_TYPE: dict[str, str | None] = {
    "user_": "person",
    "self_": "system",
    "project_": "system",
    "reference_": "tool",
    "laws_": "system",  # Law files get a structural anchor (subject_id = law name)
    "feedback_": None,  # rules don't have a natural subject_type
}

# Map well-known filenames to a canonical subject id. Empty by default; users
# can add entries (e.g. "user_role.md": "owner") when a file's subject is fixed.
SUBJECT_ID_OVERRIDES: dict[str, str] = {}

BRAID_CONTENT_CAP = 1950  # write-contract limit is 2000; leave a 50-char margin


# --- result type -----------------------------------------------------------

@dataclass
class SeedSummary:
    """Aggregate summary of one loader run."""
    inserted: list[tuple[str, int]] = field(default_factory=list)  # (filename, fact_id)
    skipped_idempotent: list[str] = field(default_factory=list)    # filename
    skipped_unknown_type: list[str] = field(default_factory=list)  # filename
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (filename, reason)

    def total_seen(self) -> int:
        return (
            len(self.inserted) + len(self.skipped_idempotent)
            + len(self.skipped_unknown_type) + len(self.rejected)
        )

    def to_human(self) -> str:
        return (
            f"memory-file loader: seen {self.total_seen()}, "
            f"inserted {len(self.inserted)}, "
            f"skipped (idempotent) {len(self.skipped_idempotent)}, "
            f"skipped (unknown type) {len(self.skipped_unknown_type)}, "
            f"rejected {len(self.rejected)}"
        )


# --- parsing helpers --------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from body. Returns ({}, text) if no frontmatter
    block is present.

    Raises yaml.YAMLError if a frontmatter block IS present but YAML parsing
    fails. The loud-fail surface is intentional: silently swallowing parse
    errors lets a malformed file vanish from a corpus ingest without warning.
    Callers should catch and surface this as a distinct skip reason.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    front = yaml.safe_load(m.group(1)) or {}
    if not isinstance(front, dict):
        front = {}
    body = text[m.end():]
    return front, body


def truncate_at_word_boundary(text: str, cap: int) -> str:
    """Truncate text to <= cap chars at the last whitespace boundary."""
    if len(text) <= cap:
        return text
    cut = text[:cap]
    # Find the last whitespace; if none in last 100 chars, just hard-cut.
    last_ws = cut.rfind(" ")
    if last_ws < cap - 100:
        return cut.rstrip()
    return cut[:last_ws].rstrip()


def _word_chunks(text: str, cap: int) -> list[str]:
    """Split a single over-cap run into <= cap pieces at word boundaries.

    Last resort when one paragraph alone exceeds the cap. A word longer than
    cap is hard-cut (pathological; preserves all characters across pieces).
    """
    chunks: list[str] = []
    cur = ""
    for w in text.split(" "):
        candidate = w if not cur else cur + " " + w
        if len(candidate) <= cap:
            cur = candidate
            continue
        if cur:
            chunks.append(cur)
            cur = ""
        while len(w) > cap:
            chunks.append(w[:cap])
            w = w[cap:]
        cur = w
    if cur:
        chunks.append(cur)
    return chunks


def chunk_text(text: str, cap: int) -> list[str]:
    """Split text into ordered chunks, each <= cap chars, without dropping content.

    Breaks at paragraph (blank-line) boundaries, accumulating whole paragraphs
    up to the cap. A paragraph that alone exceeds the cap is word-split via
    `_word_chunks`. Returns [] for empty text, [text] when already under cap.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= cap:
        return [text]
    chunks: list[str] = []
    cur = ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) > cap:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.extend(_word_chunks(para, cap))
            continue
        candidate = para if not cur else cur + "\n\n" + para
        if len(candidate) <= cap:
            cur = candidate
        else:
            chunks.append(cur)
            cur = para
    if cur:
        chunks.append(cur)
    return chunks


def build_content(front: dict[str, Any], body: str) -> str:
    """Combine description + body into the fact content field, capped at the BRAID limit.

    The description carries the rule's summary (often most search-relevant);
    body has the elaboration. Prepending description keeps the most-searchable
    text inside the cap even if body must truncate.
    """
    description = (front.get("description") or "").strip()
    body = body.strip()
    if description:
        combined = description + "\n\n" + body
    else:
        combined = body
    return truncate_at_word_boundary(combined, BRAID_CONTENT_CAP)


_HEADING_RE = re.compile(r"^(#{2,3})\s+(.*)$")


@dataclass
class LawSection:
    """One retrievable slice of a law file.

    anchor: finest-heading id, e.g. "5", "5b", or a part suffix "5b.1" when an
            over-cap leaf was split. breadcrumb: parent-heading trail prepended
            to fact content for retrieval context. content: the section body,
            already sized so breadcrumb + content fits under the cap.
    """
    anchor: str
    breadcrumb: str
    content: str


def _anchor_from_title(title: str) -> str:
    """Derive a short anchor from a heading title.

    "5. Surface routing ..." -> "5"; "5b. Career copy" -> "5b"; falls back to a
    slug for un-numbered headings.
    """
    m = re.match(r"^([0-9]+[a-z]?)\b", title.strip())
    if m:
        return m.group(1)
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug[:24] or "sec"


def split_law_sections(
    body: str, *, cap: int = BRAID_CONTENT_CAP,
) -> list[LawSection]:
    """Split a law file body into one retrievable section per finest heading.

    Emits one section per finest-heading leaf: an `###` where its `##` parent
    has `###` children, else the `##` itself. A `##` intro preceding its first
    `###` is folded into that `##`'s first child (never dropped). The
    `## Provenance` footer is skipped. Any leaf whose content (plus its
    breadcrumb) would exceed the cap is split into ordered parts (`5b.1`,
    `5b.2`) via `chunk_text`, so no fact truncates and no content is lost.
    """
    # Phase 1: flat heading segments.
    segs: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for ln in body.split("\n"):
        m = _HEADING_RE.match(ln)
        if m:
            title = m.group(2).strip()
            cur = {
                "level": len(m.group(1)),
                "title": title,
                "anchor": _anchor_from_title(title),
                "lines": [],
            }
            segs.append(cur)
        elif cur is not None:
            cur["lines"].append(ln)

    # Phase 2: build leaves (anchor, breadcrumb, text), folding H2 intros.
    leaves: list[tuple[str, str, str]] = []
    i, n = 0, len(segs)
    while i < n:
        seg = segs[i]
        if seg["level"] == 2:
            if seg["title"].lower().startswith("provenance"):
                i += 1
                continue
            children = []
            j = i + 1
            while j < n and segs[j]["level"] == 3:
                children.append(segs[j])
                j += 1
            intro = "\n".join(seg["lines"]).strip()
            if children:
                for k, ch in enumerate(children):
                    text = "\n".join(ch["lines"]).strip()
                    if k == 0 and intro:
                        text = (intro + "\n\n" + text).strip()
                    leaves.append((ch["anchor"], f"{seg['title']} > {ch['title']}", text))
                i = j
            else:
                leaves.append((seg["anchor"], seg["title"], intro))
                i += 1
        else:
            # Orphan H3 (malformed file): treat as its own leaf.
            leaves.append((seg["anchor"], seg["title"], "\n".join(seg["lines"]).strip()))
            i += 1

    # Phase 3: enforce the cap per leaf (breadcrumb prepended at fact time).
    out: list[LawSection] = []
    for anchor, breadcrumb, text in leaves:
        if not text:
            continue
        eff_cap = max(200, cap - len(breadcrumb) - 1)
        chunks = chunk_text(text, eff_cap)
        if len(chunks) == 1:
            out.append(LawSection(anchor, breadcrumb, chunks[0]))
        else:
            for idx, ch in enumerate(chunks, 1):
                out.append(LawSection(f"{anchor}.{idx}", breadcrumb, ch))
    return out


def derive_subject(filename: str, front: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (subject_type, subject_id) for a memory file.

    Honors SUBJECT_ID_OVERRIDES for known files; otherwise derives from filename
    prefix + slug. Returns (None, None) for files whose subject is ambient
    (most feedback_*).
    """
    if filename in SUBJECT_ID_OVERRIDES:
        subject_id = SUBJECT_ID_OVERRIDES[filename]
        for prefix, st in PREFIX_TO_SUBJECT_TYPE.items():
            if filename.startswith(prefix):
                return st, subject_id
        return None, subject_id

    for prefix, st in PREFIX_TO_SUBJECT_TYPE.items():
        if filename.startswith(prefix):
            if st is None:
                return None, None
            slug = filename[len(prefix):].removesuffix(".md")
            return st, slug
    return None, None


def derive_valid_from(file_path: Path) -> str:
    """ISO date (YYYY-MM-DD) from file mtime, UTC."""
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
    return mtime.strftime("%Y-%m-%d")


def now_tx_from() -> str:
    """ms-precision UTC timestamp matching cos.memory.writers._now() format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# --- file -> BRAID record ---------------------------------------------------

def file_to_record(
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build a BRAID fact_write payload from one memory file.

    Returns (payload, None) on success or (None, reason) on skip.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return None, f"read_error: {e!r}"

    try:
        front, body = parse_frontmatter(text)
    except yaml.YAMLError as e:
        msg = str(e).replace("\n", " ").strip()
        return None, f"yaml_error: {msg}"
    # Frontmatter may carry `type` (and `originSession`) at the top level or
    # nested under a `metadata:` block. Fall back to the nested location when
    # the top-level key is absent.
    nested = front.get("metadata") if isinstance(front.get("metadata"), dict) else {}
    mem_type = front.get("type") or nested.get("type")
    if mem_type not in TYPE_TO_CATEGORY:
        return None, f"unknown_type: {mem_type!r}"

    content = build_content(front, body)
    if len(content) < 5:
        return None, f"content_too_short: len={len(content)}"

    subject_type, subject_id = derive_subject(path.name, front)
    source_session = front.get("originSession") or nested.get("originSession")
    if isinstance(source_session, str):
        try:
            source_session = int(source_session)
        except ValueError:
            source_session = None
    if not isinstance(source_session, int):
        source_session = None

    tags = ["seed:memory_file", f"seed_file:{path.name}"]
    mem_tags = front.get("tags") or []
    if isinstance(mem_tags, list):
        for t in mem_tags:
            if isinstance(t, str) and len(tags) < 16:
                tags.append(t)

    payload: dict[str, Any] = {
        "content": content,
        "category": TYPE_TO_CATEGORY[mem_type],
        "subject_type": subject_type,
        "subject_id": subject_id,
        "source": "manual",
        "source_session": source_session,
        "confidence": 0.95,
        "valid_from": derive_valid_from(path),
        "tx_from": now_tx_from(),
        "tags": tags,
    }
    return payload, None


# --- idempotency ------------------------------------------------------------

def already_seeded(
    conn: sqlite3.Connection,
    *,
    content: str,
    source: str,
    subject_id: str | None,
) -> bool:
    """True if a non-retracted fact with the same content/source/subject_id exists."""
    if subject_id is None:
        row = conn.execute(
            "SELECT 1 FROM facts WHERE source = ? AND subject_id IS NULL "
            "AND content = ? AND retracted = 0 LIMIT 1",
            (source, content),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM facts WHERE source = ? AND subject_id = ? "
            "AND content = ? AND retracted = 0 LIMIT 1",
            (source, subject_id, content),
        ).fetchone()
    return row is not None


# --- top-level orchestration ------------------------------------------------

def load_memory_file(
    conn: sqlite3.Connection,
    path: Path,
    *,
    add_fn=None,
) -> tuple[int | None, str | None]:
    """Load one memory file as a single fact. Pure single-file shape.

    Returns (fact_id, None) on successful insert. Returns (None, skip_reason)
    when the file cannot be inserted; skip_reason is one of:
      - "unknown_type: <repr>"   -- frontmatter type missing or not in TYPE_TO_CATEGORY
      - "content_too_short: ..." -- body shorter than the loader threshold
      - "read_error: ..."        -- file unreadable
      - "idempotent"             -- content already seeded under same source + subject
      - "braid: <message>"       -- write-contract validation rejected the payload
      - "write: <repr>"          -- sqlite write or TypeError/ValueError from writers

    Also used as the inner-loop body of `load_memory_files`.

    `add_fn` is dependency-injectable for probes; defaults to memory_add from
    cos.subcommands.memory (validate + writers + jsonl backup).
    """
    if add_fn is None:
        from cos.subcommands.memory import memory_add
        add_fn = memory_add

    from cos.braid.validate import BraidRejection

    payload, skip_reason = file_to_record(path)
    if payload is None:
        return None, skip_reason or "unknown"

    if already_seeded(
        conn,
        content=payload["content"],
        source=payload["source"],
        subject_id=payload["subject_id"],
    ):
        return None, "idempotent"

    try:
        with conn:
            fact_id = add_fn(conn, payload, "fact")
    except BraidRejection as e:
        return None, f"braid: {e}"
    except (sqlite3.IntegrityError, sqlite3.OperationalError, TypeError, ValueError) as e:
        return None, f"write: {e!r}"

    return fact_id, None


_LAW_NAME_RE = re.compile(r"^laws_(.+)\.md$")


@dataclass
class SectionLoadResult:
    """Result of loading one law file as per-section facts."""
    inserted: list[tuple[str, int]] = field(default_factory=list)  # (anchor, fact_id)
    skipped: list[tuple[str, str]] = field(default_factory=list)   # (anchor, reason)

    def to_human(self) -> str:
        return (
            f"section loader: inserted {len(self.inserted)} "
            f"({', '.join(a for a, _ in self.inserted)}), "
            f"skipped {len(self.skipped)}"
        )


def load_memory_file_sections(
    conn: sqlite3.Connection,
    path: Path,
    *,
    add_fn=None,
) -> SectionLoadResult:
    """Load one law file as one fact per section.

    Splits the body with `split_law_sections`, then inserts one fact per
    section through the same validate + writers + jsonl path as
    `load_memory_file`. Each fact's content is `breadcrumb + "\\n" + section
    text`, guaranteed under BRAID_CONTENT_CAP by the splitter, so nothing
    truncates. Tags carry `law:<name>` and `section:<anchor>` so the owning
    section fact is identifiable.

    Per-section skip reasons mirror `load_memory_file` (idempotent / braid /
    write / content_too_short). File-level failures (read/yaml/type/no-sections)
    record a single skip under anchor "*". Does NOT mutate live state beyond the
    given connection; `add_fn` is injectable for probes.
    """
    if add_fn is None:
        from cos.subcommands.memory import memory_add
        add_fn = memory_add

    from cos.braid.validate import BraidRejection

    result = SectionLoadResult()

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        result.skipped.append(("*", f"read_error: {e!r}"))
        return result

    try:
        front, body = parse_frontmatter(text)
    except yaml.YAMLError as e:
        msg = str(e).replace("\n", " ").strip()
        result.skipped.append(("*", f"yaml_error: {msg}"))
        return result

    nested = front.get("metadata") if isinstance(front.get("metadata"), dict) else {}
    mem_type = front.get("type") or nested.get("type")
    if mem_type not in TYPE_TO_CATEGORY:
        result.skipped.append(("*", f"unknown_type: {mem_type!r}"))
        return result

    m = _LAW_NAME_RE.match(path.name)
    law_name = m.group(1) if m else path.stem
    category = TYPE_TO_CATEGORY[mem_type]
    subject_type, subject_id = derive_subject(path.name, front)

    source_session = front.get("originSession") or nested.get("originSession")
    if isinstance(source_session, str):
        try:
            source_session = int(source_session)
        except ValueError:
            source_session = None
    if not isinstance(source_session, int):
        source_session = None

    valid_from = derive_valid_from(path)
    base_tags = ["seed:memory_file", f"seed_file:{path.name}", f"law:{law_name}"]
    mem_tags = [t for t in (front.get("tags") or []) if isinstance(t, str)]
    # Carry the law's frontmatter description into each section fact's
    # searchable content, mirroring build_content (the whole-file loader).
    # Without it, vocabulary that lives only in the description is unreachable
    # after the per-section split. Cap-guarded per section below.
    description = (front.get("description") or "").strip()

    sections = split_law_sections(body)
    if not sections:
        result.skipped.append(("*", "no_sections"))
        return result

    for sec in sections:
        base = f"{sec.breadcrumb}\n{sec.content}".strip()
        # Prepend the law description when it fits under the BRAID content cap;
        # otherwise fall back to base (skip the description for this over-long
        # section rather than truncate rule text). split_law_sections already
        # guarantees base <= BRAID_CONTENT_CAP.
        if description and (len(description) + 2 + len(base)) <= BRAID_CONTENT_CAP:
            content = f"{description}\n\n{base}"
        else:
            content = base
        if len(content) < 5:
            result.skipped.append((sec.anchor, f"content_too_short: len={len(content)}"))
            continue

        tags = list(base_tags) + [f"section:{sec.anchor}"]
        for t in mem_tags:
            if len(tags) < 16:
                tags.append(t)

        if already_seeded(conn, content=content, source="manual", subject_id=subject_id):
            result.skipped.append((sec.anchor, "idempotent"))
            continue

        payload: dict[str, Any] = {
            "content": content,
            "category": category,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "source": "manual",
            "source_session": source_session,
            "confidence": 0.95,
            "valid_from": valid_from,
            "tx_from": now_tx_from(),
            "tags": tags,
        }

        try:
            with conn:
                fact_id = add_fn(conn, payload, "fact")
        except BraidRejection as e:
            result.skipped.append((sec.anchor, f"braid: {e}"))
            continue
        except (sqlite3.IntegrityError, sqlite3.OperationalError, TypeError, ValueError) as e:
            result.skipped.append((sec.anchor, f"write: {e!r}"))
            continue

        result.inserted.append((sec.anchor, fact_id))

    return result


def load_memory_files(
    conn: sqlite3.Connection,
    memory_dir: Path,
    *,
    add_fn=None,
) -> SeedSummary:
    """Walk memory_dir, write each .md as a fact. Returns a SeedSummary.

    Delegates per-file work to `load_memory_file`; this function aggregates
    results into a summary suitable for batch reporting. Law files (`laws_*.md`)
    are loaded per-section by `load_memory_file_sections` instead, and are
    skipped here so they are not double-loaded.

    `add_fn` is dependency-injectable for probes: defaults to memory_add from
    cos.subcommands.memory (validate + writers + jsonl backup).
    """
    summary = SeedSummary()
    if not memory_dir.is_dir():
        summary.rejected.append((str(memory_dir), "memory_dir_missing"))
        return summary

    for path in sorted(memory_dir.glob("*.md")):
        if path.name == "MEMORY.md":
            continue  # MEMORY.md is the index, not a memory entry
        if path.name.startswith("laws_"):
            # Law files are loaded per-section via load_memory_file_sections,
            # not whole-file. Whole-file loading truncates at the BRAID cap and
            # would duplicate the per-section law facts.
            continue

        fact_id, skip_reason = load_memory_file(conn, path, add_fn=add_fn)
        if fact_id is not None:
            summary.inserted.append((path.name, fact_id))
            continue

        if skip_reason == "idempotent":
            summary.skipped_idempotent.append(path.name)
        elif skip_reason and skip_reason.startswith("unknown_type"):
            summary.skipped_unknown_type.append(path.name)
        else:
            summary.rejected.append((path.name, skip_reason or "unknown"))

    return summary


# --- law-aggregation orchestration ------------------------------------------

@dataclass
class LawSeedSummary:
    """Aggregate of the per-section law pass across all laws_*.md in a dir."""
    files: int = 0                                       # law files processed
    inserted: list[tuple[str, str, int]] = field(default_factory=list)  # (file, anchor, id)
    skipped: list[tuple[str, str, str]] = field(default_factory=list)   # (file, anchor, reason)

    def n_inserted(self) -> int:
        return len(self.inserted)

    def n_skipped_idempotent(self) -> int:
        return sum(1 for _, _, r in self.skipped if r == "idempotent")

    def n_rejected(self) -> int:
        """Section skips that are NOT idempotent: genuine rejections (braid /
        write / content_too_short / file-level read/yaml/type/no-sections)."""
        return sum(1 for _, _, r in self.skipped if r != "idempotent")

    def to_human(self) -> str:
        return (
            f"law sections: inserted {self.n_inserted()}, "
            f"skipped {len(self.skipped)} "
            f"(idempotent {self.n_skipped_idempotent()}, "
            f"rejected {self.n_rejected()})"
        )


def load_law_files(
    conn: sqlite3.Connection,
    memory_dir: Path,
    *,
    add_fn=None,
) -> LawSeedSummary:
    """Glob laws_*.md in memory_dir and load each per-section.

    Companion to `load_memory_files` (the whole-file walker, which deliberately
    skips laws_*.md). Runs `load_memory_file_sections` on every law file and
    aggregates the per-file SectionLoadResults into one LawSeedSummary. Returns
    an empty summary (files=0) when the directory has no law files.
    """
    summary = LawSeedSummary()
    if not memory_dir.is_dir():
        return summary

    for path in sorted(memory_dir.glob("laws_*.md")):
        summary.files += 1
        result = load_memory_file_sections(conn, path, add_fn=add_fn)
        for anchor, fact_id in result.inserted:
            summary.inserted.append((path.name, anchor, fact_id))
        for anchor, reason in result.skipped:
            summary.skipped.append((path.name, anchor, reason))

    return summary


# --- CLI entry --------------------------------------------------------------

def cmd_seed_memory_files(args) -> int:
    """`cos memory seed` CLI entry.

    Runs two passes over the memory dir: the whole-file walker
    (`load_memory_files`, which skips laws_*.md) followed by the per-section law
    loader (`load_law_files`). Both summaries are printed.

    Stop-the-line policy: the >10% rejection gate counts whole-file rejections
    AND non-idempotent law-section rejections against the combined item count
    (whole-file items seen + law sections seen). Law-section idempotent skips are
    NOT rejections. Folding law rejections into the same gate keeps a schema
    mismatch in a law file from slipping past a gate that only watched the
    whole-file pass.

    Exit codes:
      0 - completed (may include skips and a few rejections)
      1 - combined rejection rate exceeded 10% (suggests a schema mismatch)
      2 - usage error (memory_dir missing, db error)
    """
    import sys as _sys

    from cos.memory import DEFAULT_DB_PATH
    from cos.memory.migrate import apply_schema

    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    memory_dir = Path(args.memory_dir) if args.memory_dir else DEFAULT_MEMORY_DIR

    if not memory_dir.is_dir():
        print(f"cos memory seed: memory dir not found at {memory_dir}",
              file=_sys.stderr)
        return 2

    apply_schema(db_path)
    conn = sqlite3.connect(db_path)
    try:
        summary = load_memory_files(conn, memory_dir)
        law_summary = load_law_files(conn, memory_dir)
    finally:
        conn.close()

    print(summary.to_human())
    print(law_summary.to_human())

    # Combined stop-the-line gate. Numerator: whole-file rejections + law-section
    # rejections (non-idempotent). Denominator: whole-file items seen + law
    # sections seen (inserted + all skips). Law idempotent skips inflate neither.
    law_seen = law_summary.n_inserted() + len(law_summary.skipped)
    seen = summary.total_seen() + law_seen
    rejected_n = len(summary.rejected) + law_summary.n_rejected()
    if seen > 0 and rejected_n / seen > 0.10:
        for filename, reason in summary.rejected[:10]:
            print(f"  rejected {filename}: {reason}", file=_sys.stderr)
        for filename, anchor, reason in law_summary.skipped[:10]:
            if reason != "idempotent":
                print(f"  rejected {filename}#{anchor}: {reason}", file=_sys.stderr)
        print(
            f"REJECTION RATE > 10% ({rejected_n}/{seen}); "
            "stopping: a rate this high usually means a schema mismatch.",
            file=_sys.stderr,
        )
        return 1
    return 0
