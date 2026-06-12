"""`cos memory` -- CLI surface for memory.db.

Operations:
  add        validate via the write contract, write to memory.db + jsonl atomically
  retrieve   fetch by id or by subject
  search     FTS5 round-trip query across facts + episodes
  stats      counts and health metrics
  context    three-tier retrieval (operational/structural/reflective)

The pure-orchestration function `memory_add` is dependency-injectable for
testing (jsonl_writer can be replaced with a raise-on-call stub to assert DB
rollback on a jsonl failure). `cmd_context` wraps the pure retrieval functions
in cos.memory.context.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Callable, Literal

from cos.braid import REJECTIONS_LOG
from cos.braid.validate import validate_braid, BraidRejection
from cos.memory import DEFAULT_DB_PATH
from cos.memory.context import (
    ContextOptions, TIER_ORDER, Tier,
    format_human_merged, format_human_section,
    hit_to_record, merge_hits, retrieve_context,
)
from cos.memory.jsonl import jsonl_append
from cos.memory.loader import DEFAULT_MEMORY_DIR, cmd_seed_memory_files
from cos.memory.migrate import apply_schema
from cos.memory.writers import insert_episode, insert_fact

Kind = Literal["fact", "episode"]


# --- pure orchestration (testable, no I/O of its own beyond what's passed in) ---

def memory_add(
    conn: sqlite3.Connection,
    record: dict[str, Any],
    kind: Kind,
    *,
    jsonl_writer: Callable[[dict, str, int], None] = jsonl_append,
) -> int:
    """Validate + insert + jsonl-append. Returns the new row id.

    Caller manages the transaction (wrap in `with conn:` for atomic rollback if
    jsonl_writer raises). This function does NOT commit or open a transaction --
    the connection's deferred-transaction semantics plus the caller's
    `with conn:` block provide atomicity.

    Order: validate -> DB insert -> jsonl append. If jsonl_writer raises after a
    successful DB insert, the caller's `with conn:` exits with the exception and
    the DB write rolls back.

    Raises:
        BraidRejection: payload failed validation. No DB or jsonl side effect.
        TypeError: writer rejected an unknown field.
        Any I/O exception from jsonl_writer.
    """
    validate_braid(record, kind)
    if kind == "fact":
        row_id = insert_fact(conn, **record)
    elif kind == "episode":
        row_id = insert_episode(conn, **record)
    else:
        raise ValueError(f"memory_add: unknown kind {kind!r}")
    jsonl_writer(record, kind, row_id)
    return row_id


# --- shared read helpers ---

def _ensure_utf8_stdout() -> None:
    """Force stdout to UTF-8 with replace error handling.

    Note content can contain emoji and smart punctuation that crash on the
    Windows console default cp1252. Idempotent; no-op on streams without
    reconfigure (e.g. StringIO in tests).
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _row_to_dict(cur, row) -> dict[str, Any]:
    """Convert a sqlite3 tuple row to a dict using cursor.description."""
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _print_jsonl(records) -> None:
    """Emit records as one JSON object per line on stdout."""
    for r in records:
        sys.stdout.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


# --- CLI wrappers ---

def cmd_add(args: argparse.Namespace) -> int:
    try:
        record = json.loads(args.json)
    except json.JSONDecodeError as e:
        print(f"cos memory add: --json is not valid JSON: {e}", file=sys.stderr)
        return 2
    if not isinstance(record, dict):
        print(f"cos memory add: --json must be a JSON object; got {type(record).__name__}",
              file=sys.stderr)
        return 2

    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    apply_schema(db_path)  # idempotent
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            row_id = memory_add(conn, record, args.kind)
    except BraidRejection as e:
        print(f"rejected: {e}", file=sys.stderr)
        return 1
    except (sqlite3.IntegrityError, sqlite3.OperationalError, TypeError, ValueError) as e:
        print(f"cos memory add: write failed: {e!r}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    print(row_id)
    return 0


def cmd_retrieve(args: argparse.Namespace) -> int:
    """Retrieve facts by id, or by subject_id (with optional subject_type narrowing).

    Output: JSONL on stdout, one fact per line. Default filter: retracted=0.
    Exit codes: 0 on success (including empty result), 1 on bad usage, 2 on DB error.
    """
    _ensure_utf8_stdout()
    if (args.id is None) == (args.subject is None):
        print("cos memory retrieve: exactly one of --id or --subject is required",
              file=sys.stderr)
        return 1

    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    if not db_path.exists():
        print(f"cos memory retrieve: memory.db not found at {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    try:
        if args.id is not None:
            cur = conn.execute(
                "SELECT * FROM facts WHERE id = ? AND retracted = 0",
                (args.id,),
            )
        else:
            if args.subject_type:
                cur = conn.execute(
                    "SELECT * FROM facts WHERE subject_id = ? "
                    "AND subject_type = ? AND retracted = 0 "
                    "ORDER BY tx_from DESC, id DESC",
                    (args.subject, args.subject_type),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM facts WHERE subject_id = ? AND retracted = 0 "
                    "ORDER BY tx_from DESC, id DESC",
                    (args.subject,),
                )
        rows = cur.fetchall()
        _print_jsonl(_row_to_dict(cur, r) for r in rows)
    finally:
        conn.close()
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """FTS5 search across facts_fts and (optionally) episodes_fts.

    Output: JSONL on stdout. Each record carries a `kind` field ('fact' or
    'episode') plus the underlying row. Default scope: both indices. Default
    filter: retracted=0 for facts.
    """
    _ensure_utf8_stdout()
    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    if not db_path.exists():
        print(f"cos memory search: memory.db not found at {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    try:
        records = []
        kinds = ("fact", "episode") if args.kind is None else (args.kind,)

        if "fact" in kinds:
            cur = conn.execute(
                "SELECT facts.* FROM facts JOIN facts_fts "
                "ON facts.id = facts_fts.rowid "
                "WHERE facts_fts MATCH ? AND facts.retracted = 0",
                (args.query,),
            )
            for row in cur.fetchall():
                rec = _row_to_dict(cur, row)
                rec["kind"] = "fact"
                records.append(rec)

        if "episode" in kinds:
            cur = conn.execute(
                "SELECT episodes.* FROM episodes JOIN episodes_fts "
                "ON episodes.id = episodes_fts.rowid "
                "WHERE episodes_fts MATCH ?",
                (args.query,),
            )
            for row in cur.fetchall():
                rec = _row_to_dict(cur, row)
                rec["kind"] = "episode"
                records.append(rec)

        _print_jsonl(records)
    finally:
        conn.close()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Three counts, one line each: facts, episodes, write-contract rejections."""
    _ensure_utf8_stdout()
    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    if not db_path.exists():
        print(f"cos memory stats: memory.db not found at {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    try:
        facts_n = conn.execute(
            "SELECT COUNT(*) FROM facts WHERE retracted = 0"
        ).fetchone()[0]
        episodes_n = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    finally:
        conn.close()

    rejections_log = Path(args.rejections_log) if args.rejections_log else REJECTIONS_LOG
    if rejections_log.exists():
        with rejections_log.open(encoding="utf-8") as f:
            rejections_n = sum(1 for line in f if line.strip())
    else:
        rejections_n = 0

    print(f"facts: {facts_n}")
    print(f"episodes: {episodes_n}")
    print(f"rejections: {rejections_n}")
    return 0


# --- three-tier retrieval ---

def _parse_tiers(s: str) -> tuple[Tier, ...]:
    """Parse --tiers value 'operational,structural,reflective' to a tuple.

    Raises ValueError on bad tier names.
    """
    if not s:
        return TIER_ORDER
    parts = [t.strip().lower() for t in s.split(",") if t.strip()]
    unknown = [t for t in parts if t not in TIER_ORDER]
    if unknown:
        raise ValueError(
            f"--tiers: unknown tier(s) {unknown}; allowed: {list(TIER_ORDER)}"
        )
    # Preserve canonical order so output doesn't depend on input ordering.
    return tuple(t for t in TIER_ORDER if t in parts)  # type: ignore[misc]


def cmd_context(args: argparse.Namespace) -> int:
    """Three-tier retrieval over memory.db.

    Output:
      - Default human format: one '## <Tier> (n / limit)' section per requested
        tier, with '[rank] kind #id (...): content' lines.
      - --json: one JSON object per line.
      - --merge: collapse to one ranked list.

    Exit codes: 0 success (including empty), 1 bad usage, 2 DB or input error.
    """
    _ensure_utf8_stdout()

    if args.limit is None or args.limit <= 0:
        print(f"cos memory context: --limit must be positive (got {args.limit})",
              file=sys.stderr)
        return 2
    try:
        tiers = _parse_tiers(args.tiers) if args.tiers else TIER_ORDER
    except ValueError as e:
        print(f"cos memory context: {e}", file=sys.stderr)
        return 1

    try:
        op_conf = float(args.operational_confidence)
        st_conf = float(args.structural_confidence)
        half_life = int(args.reflective_half_life_days)
        op_days = int(args.operational_days)
    except (TypeError, ValueError) as e:
        print(f"cos memory context: numeric flag parse error: {e}", file=sys.stderr)
        return 2

    opts = ContextOptions(
        subject=args.subject,
        subject_type=args.subject_type,
        query=args.query,
        tiers=tiers,
        limit=int(args.limit),
        merge=bool(args.merge),
        operational_days=op_days,
        operational_confidence=op_conf,
        structural_confidence=st_conf,
        reflective_half_life_days=half_life,
        as_of=args.as_of,
    )

    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    if not db_path.exists():
        print(f"cos memory context: memory.db not found at {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    try:
        by_tier = retrieve_context(conn, opts)
    except sqlite3.OperationalError as e:
        print(f"cos memory context: DB error: {e!r}", file=sys.stderr)
        return 2
    finally:
        conn.close()

    if opts.merge:
        merged = merge_hits(by_tier, opts.limit)
        if args.json:
            recs = []
            for i, h in enumerate(merged, start=1):
                r = hit_to_record(h)
                r["tier"] = "merged"
                r["rank"] = i
                recs.append(r)
            _print_jsonl(recs)
        else:
            print(format_human_merged(merged, opts.limit))
        return 0

    if args.json:
        recs = []
        for tier in TIER_ORDER:
            if tier not in opts.tiers:
                continue
            hits = by_tier.get(tier, [])
            for i, h in enumerate(hits, start=1):
                r = hit_to_record(h)
                r["rank"] = i
                recs.append(r)
        _print_jsonl(recs)
    else:
        sections = []
        for tier in TIER_ORDER:
            if tier not in opts.tiers:
                continue
            hits = by_tier.get(tier, [])
            sections.append(format_human_section(tier, hits, opts.limit))
        print("\n\n".join(sections))
    return 0


# --- argparse registration ---

def register(subparsers):
    p = subparsers.add_parser(
        "memory",
        help="memory.db operations (add/retrieve/search/stats/context)",
    )
    sub = p.add_subparsers(dest="memory_op", required=True)

    p_add = sub.add_parser(
        "add",
        help="Validate a payload against the write contract and write atomically "
             "to memory.db + jsonl.",
    )
    p_add.add_argument("kind", choices=["fact", "episode"],
                       help="record kind (fact|episode)")
    p_add.add_argument("--json", required=True,
                       help="JSON object matching the write contract for `kind`")
    p_add.add_argument("--db", default=None,
                       help=f"path to memory.db (default: {DEFAULT_DB_PATH})")
    p_add.set_defaults(func=cmd_add)

    p_ret = sub.add_parser(
        "retrieve",
        help="Retrieve fact(s) by id or by subject. JSONL on stdout.",
    )
    p_ret.add_argument("--id", type=int, default=None, help="fact id (exact match)")
    p_ret.add_argument("--subject", default=None,
                       help="subject_id filter; returns all current facts for this subject")
    p_ret.add_argument("--subject-type", dest="subject_type", default=None,
                       help="optional narrower filter; only meaningful with --subject")
    p_ret.add_argument("--db", default=None,
                       help=f"path to memory.db (default: {DEFAULT_DB_PATH})")
    p_ret.set_defaults(func=cmd_retrieve)

    p_search = sub.add_parser(
        "search",
        help="FTS5 search across facts and episodes. JSONL on stdout.",
    )
    p_search.add_argument("query", help="FTS5 MATCH query string")
    p_search.add_argument("--kind", choices=["fact", "episode"], default=None,
                          help="restrict to one kind (default: both)")
    p_search.add_argument("--db", default=None,
                          help=f"path to memory.db (default: {DEFAULT_DB_PATH})")
    p_search.set_defaults(func=cmd_search)

    p_stats = sub.add_parser(
        "stats",
        help="Three counts: facts (non-retracted), episodes, write-contract rejections.",
    )
    p_stats.add_argument("--db", default=None,
                         help=f"path to memory.db (default: {DEFAULT_DB_PATH})")
    p_stats.add_argument("--rejections-log", dest="rejections_log", default=None,
                         help=f"path to rejections log (default: {REJECTIONS_LOG})")
    p_stats.set_defaults(func=cmd_stats)

    p_ctx = sub.add_parser(
        "context",
        help="Three-tier retrieval: operational + structural + reflective.",
    )
    p_ctx.add_argument("subject", nargs="?", default=None,
                       help="optional subject_id filter on facts")
    p_ctx.add_argument("--subject-type", dest="subject_type", default=None,
                       help="optional subject_type narrowing (with or without subject)")
    p_ctx.add_argument("--query", default=None,
                       help="optional FTS5 MATCH query applied to operational + reflective")
    p_ctx.add_argument("--tiers", default=None,
                       help="comma-separated tier selection (default: all three)")
    p_ctx.add_argument("--limit", type=int, default=10,
                       help="per-tier limit (default 10); total limit in --merge mode")
    p_ctx.add_argument("--merge", action="store_true",
                       help="collapse tiers into one score-weighted ranked list")
    p_ctx.add_argument("--json", action="store_true",
                       help="JSONL output (one object per line); default is human-readable")
    p_ctx.add_argument("--operational-days", dest="operational_days",
                       type=int, default=30, help="operational window in days (default 30)")
    p_ctx.add_argument("--operational-confidence", dest="operational_confidence",
                       type=float, default=0.5,
                       help="confidence floor for operational facts (default 0.5)")
    p_ctx.add_argument("--structural-confidence", dest="structural_confidence",
                       type=float, default=0.8,
                       help="confidence floor for structural facts (default 0.8)")
    p_ctx.add_argument("--reflective-half-life-days", dest="reflective_half_life_days",
                       type=int, default=90,
                       help="reflective half-life in days (default 90)")
    p_ctx.add_argument("--as-of", dest="as_of", default=None,
                       help="bitemporal as-of timestamp ('YYYY-MM-DD HH:MM:SS.fff')")
    p_ctx.add_argument("--db", default=None,
                       help=f"path to memory.db (default: {DEFAULT_DB_PATH})")
    p_ctx.set_defaults(func=cmd_context)

    p_seed = sub.add_parser(
        "seed",
        help="Seed facts from a directory of Markdown memory files (*.md).",
    )
    p_seed.add_argument("--memory-dir", dest="memory_dir", default=None,
                        help=f"path to memory .md files (default: {DEFAULT_MEMORY_DIR})")
    p_seed.add_argument("--db", default=None,
                        help=f"path to memory.db (default: {DEFAULT_DB_PATH})")
    p_seed.set_defaults(func=cmd_seed_memory_files)
