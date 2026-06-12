"""cos.memory.context -- three-tier retrieval.

Pure retrieval functions, dependency-injectable. CLI wrapper at
cos.subcommands.memory.cmd_context.

Three tiers:
  operational  -- recent + relevant (configurable window + confidence floor)
  structural   -- pinned categories (preference/capability/reference/commitment)
                  above a confidence floor; no time bound
  reflective   -- episodes weighted by half-life decay

Merge mode collapses tiers into a single ranked list using score-first sort
with tier-priority as a tiebreaker only. The ranking and dedup rules are
documented inline below.

Design contract:
  - Callers pass a sqlite3.Connection and a ContextOptions instance.
  - retrieve_context() returns dict[Tier -> list[Hit]] (deduped, per-tier limited).
  - merge_hits() takes that dict and returns a single ranked list (total limited).
  - No I/O of its own beyond what's on the connection.
"""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

Tier = Literal["operational", "structural", "reflective"]

TIER_ORDER: tuple[Tier, ...] = ("operational", "structural", "reflective")

# Lower number = higher priority. Used as a sort key in merge mode and as the
# dedup priority order in dedup_priority().
TIER_PRIORITY: dict[Tier, int] = {
    "structural": 0,
    "operational": 1,
    "reflective": 2,
}

PINNED_CATEGORIES: tuple[str, ...] = (
    "preference", "capability", "reference", "commitment",
)

# Characters FTS5's MATCH parser treats as syntax-significant. Replaced with
# spaces before binding to keep user-supplied query strings safe. FTS5's
# unicode61 tokenizer then re-splits on whitespace, preserving the
# implicit-AND semantic across multi-token queries (e.g. "Q3 5/05 launch notes"
# becomes "Q3 5 05 launch notes", AND across tokens).
_FTS5_SPECIAL_RE = re.compile(r'[()"*:/.\-+^&]+')


def _sanitize_fts_query(query: str | None) -> str | None:
    """Replace FTS5-parser-special chars with spaces. Pass None through.

    Examples:
      "Q3 5/05 launch notes" -> "Q3 5 05 launch notes"
      "issue-1"              -> "issue 1"
      "Apollo (Phase II)"    -> "Apollo  Phase II "
    """
    if query is None:
        return None
    return _FTS5_SPECIAL_RE.sub(" ", query)


# Category sort order within structural.
_STRUCTURAL_CATEGORY_RANK_SQL = (
    "CASE category "
    "WHEN 'preference' THEN 0 "
    "WHEN 'capability' THEN 1 "
    "WHEN 'reference' THEN 2 "
    "WHEN 'commitment' THEN 3 "
    "ELSE 99 END"
)


@dataclass
class ContextOptions:
    """All knobs for `cos memory context`."""
    subject: str | None = None
    subject_type: str | None = None
    query: str | None = None
    tiers: tuple[Tier, ...] = TIER_ORDER
    limit: int = 10
    merge: bool = False
    operational_days: int = 30
    operational_confidence: float = 0.5
    structural_confidence: float = 0.8
    reflective_half_life_days: int = 90
    as_of: str | None = None  # ISO timestamp; None = current beliefs only


@dataclass
class Hit:
    """One retrieval result. `record` is the full row dict."""
    tier: Tier
    kind: Literal["fact", "episode"]
    id: int
    score: float
    record: dict[str, Any]


# --- shared helpers ---------------------------------------------------------

def _row_to_dict(cur: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    """Convert a sqlite3 tuple row to a dict using cursor.description.
    Does not mutate the connection's row_factory."""
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _bm25_to_score(bm25: float | None) -> float:
    """Normalize FTS5 bm25 (lower = better, unbounded above) to a 0-1 score.

    Formula: 1 / (1 + bm25). bm25=0 -> 1.0; bm25 grows -> score -> 0. Treats
    None (no FTS5 match, e.g. the no-query path) as recency-flag 1.0.
    """
    if bm25 is None:
        return 1.0
    try:
        b = float(bm25)
    except (TypeError, ValueError):
        return 1.0
    if b < 0:
        # FTS5 can technically return negative bm25 with custom weights; clamp.
        b = 0.0
    return 1.0 / (1.0 + b)


def _age_days(occurred_at: str) -> int:
    """Return age in days for an ISO date string. Clamps negative ages to 0
    (future-dated rows score as 'today'). Bad input yields 0 (treated fresh)."""
    try:
        s = (occurred_at or "")[:10]
        d = datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return 0
    today = datetime.now(timezone.utc).date()
    return max(0, (today - d).days)


def _half_life_score(age_days: int, half_life_days: int) -> float:
    """exp(-ln(2) * age / half_life). Score is 1.0 at age 0, 0.5 at half-life."""
    if half_life_days <= 0:
        return 1.0 if age_days == 0 else 0.0
    return math.exp(-math.log(2) * age_days / half_life_days)


def _as_of_facts_clause(opts: ContextOptions) -> tuple[str, list[Any]]:
    """Return (where_fragment, params) for the bitemporal filter on facts.

    With opts.as_of: 'what the system believed at TIMESTAMP'.
    Without: 'current beliefs only' (tx_to IS NULL).
    """
    if opts.as_of:
        return ("tx_from <= ? AND (tx_to > ? OR tx_to IS NULL)",
                [opts.as_of, opts.as_of])
    return ("tx_to IS NULL", [])


def _subject_clauses(opts: ContextOptions) -> tuple[list[str], list[Any]]:
    """Return (where_fragments_list, params_list) for subject filters."""
    parts: list[str] = []
    params: list[Any] = []
    if opts.subject is not None:
        parts.append("subject_id = ?")
        params.append(opts.subject)
    if opts.subject_type is not None:
        parts.append("subject_type = ?")
        params.append(opts.subject_type)
    return parts, params


# --- per-tier retrieval -----------------------------------------------------

def retrieve_operational(conn: sqlite3.Connection,
                         opts: ContextOptions) -> list[Hit]:
    """Recent + relevant facts and episodes within opts.operational_days."""
    hits: list[Hit] = []

    # === Facts ===
    fact_where: list[str] = ["facts.retracted = 0",
                             "facts.confidence >= ?",
                             f"facts.tx_from >= datetime('now', '-{int(opts.operational_days)} days')"]
    fact_params: list[Any] = [opts.operational_confidence]

    as_of_clause, as_of_params = _as_of_facts_clause(opts)
    fact_where.append(as_of_clause.replace("tx_from", "facts.tx_from")
                                  .replace("tx_to", "facts.tx_to"))
    fact_params.extend(as_of_params)

    subj_parts, subj_params = _subject_clauses(opts)
    fact_where.extend("facts." + p for p in subj_parts)
    fact_params.extend(subj_params)

    if opts.query:
        sql = (
            "SELECT facts.*, bm25(facts_fts) AS _bm25_score "
            "FROM facts JOIN facts_fts ON facts.id = facts_fts.rowid "
            "WHERE facts_fts MATCH ? AND " + " AND ".join(fact_where) +
            " ORDER BY _bm25_score ASC, facts.id DESC LIMIT ?"
        )
        params = [_sanitize_fts_query(opts.query)] + fact_params + [opts.limit]
    else:
        sql = (
            "SELECT facts.*, NULL AS _bm25_score FROM facts "
            "WHERE " + " AND ".join(fact_where) +
            " ORDER BY facts.tx_from DESC, facts.id DESC LIMIT ?"
        )
        params = fact_params + [opts.limit]

    cur = conn.execute(sql, params)
    for row in cur.fetchall():
        rec = _row_to_dict(cur, row)
        bm25 = rec.pop("_bm25_score", None)
        score = _bm25_to_score(bm25)
        hits.append(Hit(tier="operational", kind="fact",
                        id=int(rec["id"]), score=score, record=rec))

    # === Episodes ===
    # Episodes have no retracted, confidence, subject_type/id, or bitemporal
    # columns. Only the window filter applies (and the FTS5 query if given).
    ep_where: list[str] = [
        f"episodes.occurred_at >= date('now', '-{int(opts.operational_days)} days')"
    ]
    ep_params: list[Any] = []

    if opts.query:
        sql = (
            "SELECT episodes.*, bm25(episodes_fts) AS _bm25_score "
            "FROM episodes JOIN episodes_fts "
            "ON episodes.id = episodes_fts.rowid "
            "WHERE episodes_fts MATCH ? AND " + " AND ".join(ep_where) +
            " ORDER BY _bm25_score ASC, episodes.id DESC LIMIT ?"
        )
        params = [_sanitize_fts_query(opts.query)] + ep_params + [opts.limit]
    else:
        sql = (
            "SELECT episodes.*, NULL AS _bm25_score FROM episodes "
            "WHERE " + " AND ".join(ep_where) +
            " ORDER BY episodes.occurred_at DESC, episodes.id DESC LIMIT ?"
        )
        params = ep_params + [opts.limit]

    cur = conn.execute(sql, params)
    for row in cur.fetchall():
        rec = _row_to_dict(cur, row)
        bm25 = rec.pop("_bm25_score", None)
        score = _bm25_to_score(bm25)
        hits.append(Hit(tier="operational", kind="episode",
                        id=int(rec["id"]), score=score, record=rec))

    # When query present: sort by score DESC across facts+episodes mix.
    # When no query: sort by canonical date DESC (tx_from for facts,
    # occurred_at for episodes), id DESC as tiebreaker. Score is uniformly 1.0
    # in the no-query case so it's not part of the sort key.
    if opts.query:
        hits.sort(key=lambda h: (-h.score, -h.id))
    else:
        hits.sort(key=lambda h: (_canonical_date_key(h), h.id), reverse=True)

    return hits[: opts.limit]


def _canonical_date_key(h: Hit) -> str:
    """For operational mixed-kind sort: tx_from for facts, occurred_at for episodes.

    NOTE on mixed-kind tie behavior at same calendar date: tx_from is
    'YYYY-MM-DD HH:MM:SS.fff' (23 chars) and occurred_at is 'YYYY-MM-DD'
    (10 chars). Python's string comparison treats the shorter prefix as
    less-than the longer one, so at the same calendar date facts always sort
    above episodes when `reverse=True` is applied. Deterministic and acceptable.
    """
    if h.kind == "fact":
        return str(h.record.get("tx_from", ""))[:23]
    return str(h.record.get("occurred_at", ""))[:23]


def retrieve_structural(conn: sqlite3.Connection,
                        opts: ContextOptions) -> list[Hit]:
    """Pinned facts (categorical + confidence-floored, no time bound)."""
    placeholders = ", ".join("?" for _ in PINNED_CATEGORIES)
    where: list[str] = [
        "facts.retracted = 0",
        f"facts.category IN ({placeholders})",
        "facts.confidence >= ?",
    ]
    params: list[Any] = list(PINNED_CATEGORIES) + [opts.structural_confidence]

    as_of_clause, as_of_params = _as_of_facts_clause(opts)
    where.append(as_of_clause.replace("tx_from", "facts.tx_from")
                              .replace("tx_to", "facts.tx_to"))
    params.extend(as_of_params)

    subj_parts, subj_params = _subject_clauses(opts)
    where.extend("facts." + p for p in subj_parts)
    params.extend(subj_params)

    if opts.query:
        # Relevance ranking: bm25 is the within-category tiebreak so the row
        # whose body actually carries the query terms outranks siblings. Category
        # stays primary; confidence and id remain further tiebreaks.
        sql = (
            "SELECT facts.*, bm25(facts_fts) AS _bm25_score "
            "FROM facts JOIN facts_fts "
            "ON facts.id = facts_fts.rowid "
            "WHERE facts_fts MATCH ? AND " + " AND ".join(where) +
            f" ORDER BY {_STRUCTURAL_CATEGORY_RANK_SQL}, "
            f"_bm25_score ASC, facts.confidence DESC, facts.id DESC LIMIT ?"
        )
        full_params = [_sanitize_fts_query(opts.query)] + params + [opts.limit]
    else:
        sql = (
            "SELECT * FROM facts WHERE " + " AND ".join(where) +
            f" ORDER BY {_STRUCTURAL_CATEGORY_RANK_SQL}, "
            f"confidence DESC, id DESC LIMIT ?"
        )
        full_params = params + [opts.limit]

    cur = conn.execute(sql, full_params)
    hits: list[Hit] = []
    for row in cur.fetchall():
        rec = _row_to_dict(cur, row)
        rec.pop("_bm25_score", None)  # ranking-only column; keep it out of the record
        score = float(rec.get("confidence", 0.0))
        hits.append(Hit(tier="structural", kind="fact",
                        id=int(rec["id"]), score=score, record=rec))
    return hits


def retrieve_reflective(conn: sqlite3.Connection,
                        opts: ContextOptions) -> list[Hit]:
    """Episodes weighted by half-life decay."""
    if opts.query:
        sql = (
            "SELECT episodes.* FROM episodes JOIN episodes_fts "
            "ON episodes.id = episodes_fts.rowid "
            "WHERE episodes_fts MATCH ?"
        )
        params = [_sanitize_fts_query(opts.query)]
    else:
        sql = "SELECT * FROM episodes"
        params = []

    cur = conn.execute(sql, params)
    rows = cur.fetchall()

    half_life = max(1, int(opts.reflective_half_life_days))
    hits: list[Hit] = []
    for row in rows:
        rec = _row_to_dict(cur, row)
        age = _age_days(rec.get("occurred_at"))
        score = _half_life_score(age, half_life)
        hits.append(Hit(tier="reflective", kind="episode",
                        id=int(rec["id"]), score=score, record=rec))

    # Sort: score DESC, occurred_at DESC, id DESC.
    hits.sort(key=lambda h: (-h.score,
                             _neg_date_ordinal(h.record.get("occurred_at")),
                             -h.id))
    return hits[: opts.limit]


def _neg_date_ordinal(occurred_at: Any) -> int:
    """Sort key fragment for occurred_at DESC. Bad input sorts as oldest."""
    try:
        s = str(occurred_at or "")[:10]
        d = datetime.strptime(s, "%Y-%m-%d").date()
        return -d.toordinal()
    except (TypeError, ValueError):
        return 0  # treats bad/missing dates as 'today-ish' but with low score


# --- dedup + merge ----------------------------------------------------------

def dedup_priority(hits_by_tier: dict[Tier, list[Hit]]) -> dict[Tier, list[Hit]]:
    """Assign each (kind, id) to its highest-priority tier.

    Priority order: structural > operational > reflective. A record qualifying
    for two tiers is kept in the higher-priority tier and dropped from the lower.

    Returns a fresh dict; input is not mutated.
    """
    seen: set[tuple[str, int]] = set()
    result: dict[Tier, list[Hit]] = {t: [] for t in TIER_ORDER}
    for tier in sorted(hits_by_tier.keys(), key=lambda t: TIER_PRIORITY[t]):
        for h in hits_by_tier[tier]:
            key = (h.kind, h.id)
            if key in seen:
                continue
            seen.add(key)
            result[tier].append(h)
    return result


def retrieve_context(conn: sqlite3.Connection,
                     opts: ContextOptions) -> dict[Tier, list[Hit]]:
    """Main retrieval entry. Returns dict tier -> hits, deduped + per-tier limited.

    Pulls every requested tier independently (each may exceed opts.limit before
    dedup), dedups across all three by tier priority, then truncates each tier
    to opts.limit.
    """
    raw: dict[Tier, list[Hit]] = {}
    if "operational" in opts.tiers:
        raw["operational"] = retrieve_operational(conn, opts)
    if "structural" in opts.tiers:
        raw["structural"] = retrieve_structural(conn, opts)
    if "reflective" in opts.tiers:
        raw["reflective"] = retrieve_reflective(conn, opts)

    deduped = dedup_priority(raw)
    return {t: deduped[t][: opts.limit] for t in TIER_ORDER if t in raw}


def merge_hits(by_tier: dict[Tier, list[Hit]], limit: int) -> list[Hit]:
    """Combine tiers into one ranked list.

    Rule:
      1. Primary sort: normalized score DESC.
      2. Tiebreaker 1: tier priority (structural > operational > reflective).
      3. Tiebreaker 2: id DESC.

    `by_tier` is expected to be already-deduped (use retrieve_context's output).
    """
    flat: list[Hit] = []
    for tier in TIER_ORDER:
        flat.extend(by_tier.get(tier, []))

    flat.sort(key=lambda h: (-h.score, TIER_PRIORITY[h.tier], -h.id))
    return flat[:limit]


# --- output formatting ------------------------------------------------------

def hit_to_record(h: Hit) -> dict[str, Any]:
    """Wrap a Hit for JSON emission."""
    return {
        "tier": h.tier,
        "kind": h.kind,
        "id": h.id,
        "score": round(h.score, 6),
        "record": h.record,
    }


def format_human_section(tier: Tier, hits: list[Hit], limit: int) -> str:
    """Render one tier section in human format."""
    label = tier.capitalize()
    header = f"## {label} ({len(hits)} / {limit})"
    if not hits:
        return header + "\n(none)"
    lines = [header]
    for i, h in enumerate(hits, start=1):
        lines.append(_format_hit_line(i, h))
    return "\n".join(lines)


def format_human_merged(hits: list[Hit], limit: int) -> str:
    """Render the merged list section."""
    header = f"## Merged ({len(hits)} / {limit})"
    if not hits:
        return header + "\n(none)"
    lines = [header]
    for i, h in enumerate(hits, start=1):
        lines.append(_format_hit_line(i, h, show_tier=True))
    return "\n".join(lines)


def _format_hit_line(rank: int, h: Hit, show_tier: bool = False) -> str:
    """One line per hit. Truncates content to keep the output readable."""
    rec = h.record
    if h.kind == "fact":
        date_part = str(rec.get("tx_from", ""))[:10]
        cat = rec.get("category", "?")
        conf = rec.get("confidence", "?")
        content = str(rec.get("content", ""))
        excerpt = content if len(content) <= 120 else content[:117] + "..."
        tier_str = f"[{h.tier}] " if show_tier else ""
        return (f"[{rank}] {tier_str}fact #{h.id} ({cat}, {date_part}, "
                f"conf {conf}): {excerpt}")
    # episode
    date_part = str(rec.get("occurred_at", ""))[:10]
    title = rec.get("title", "")
    score_str = f"score {h.score:.2f}"
    tier_str = f"[{h.tier}] " if show_tier else ""
    return f"[{rank}] {tier_str}episode #{h.id} ({score_str}, {date_part}): {title}"
