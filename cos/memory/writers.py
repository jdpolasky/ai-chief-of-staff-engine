"""Bitemporal write helpers for cos.memory.

Primitives:
  - insert_fact(conn, **fields)            -> int    (new fact id)
  - supersede_fact(conn, old_id, **fields) -> int    (new fact id)
  - retract_fact(conn, fact_id, ...)       -> None
  - undo_supersede_fact(conn, source_id)   -> None
  - insert_episode(conn, **fields)         -> int    (new episode id)
  - batch_supersede(conn, pairs)           -> int    (count)

Each fact helper issues two back-to-back execute() calls on the caller's
connection: one INSERT/UPDATE on `facts`, one INSERT on `fact_history`.
Snapshots (prev_state / new_state) are stored as JSON in fact_history so the
log is self-contained for replay.

Atomicity contract: Python's sqlite3 module begins a transaction on the first
DML statement and holds it open until the caller commits or rolls back.
Because each helper issues its facts + fact_history writes back-to-back on the
same connection without an intervening commit, the pair is atomic when the
caller commits. The helpers do NOT commit on the caller's behalf; the caller
decides transaction boundaries (e.g. the `add` write path groups fact + jsonl
+ history into one commit for the facts.jsonl double-write).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

_FACT_COLS = (
    "content", "category", "subject_type", "subject_id",
    "source", "source_session", "confidence",
    "valid_from", "valid_to", "tx_from", "tx_to",
    "supersedes_id", "retracted", "tags",
)

_EPISODE_COLS = (
    "title", "content", "occurred_at", "session",
    "valence", "fact_refs", "tags",
)


def _now() -> str:
    """Millisecond-precision UTC timestamp matching SQLite's
    `strftime('%Y-%m-%d %H:%M:%f', 'now')` format.

    Format: 'YYYY-MM-DD HH:MM:SS.mmm'. Lexicographically comparable with all
    schema-default timestamps (created_at, recorded_at, tx_at). Millisecond
    resolution avoids same-second collisions on back-to-back writes.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _snapshot(conn: sqlite3.Connection, fact_id: int) -> dict[str, Any] | None:
    """Return a dict snapshot of a facts row, or None if missing.

    Does not mutate conn.row_factory; uses cursor.description to map column
    names to tuple values.
    """
    cur = conn.execute("SELECT * FROM facts WHERE id = ?", (fact_id,))
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _required_defaults(fields: dict[str, Any], *, default_tx_from: str) -> dict[str, Any]:
    """Fill defaults for fields the caller may omit or pass as None. Mutates
    and returns. valid_from defaults to the date portion of tx_from.
    """
    if not fields.get("tx_from"):
        fields["tx_from"] = default_tx_from
    if not fields.get("valid_from"):
        fields["valid_from"] = fields["tx_from"][:10]
    return fields


def insert_fact(
    conn: sqlite3.Connection,
    *,
    content: str,
    category: str,
    source: str,
    valid_from: str | None = None,
    tx_from: str | None = None,
    session: int | None = None,
    reason: str | None = None,
    **extra: Any,
) -> int:
    """Insert a new fact and append an 'insert' row to fact_history.

    Returns the new fact id. Caller manages the transaction (see module
    docstring). Raises TypeError on unknown **extra keys.
    """
    unknown = set(extra) - set(_FACT_COLS)
    if unknown:
        raise TypeError(
            f"insert_fact: unknown field(s) {sorted(unknown)}; "
            f"allowed: {sorted(_FACT_COLS)}"
        )
    fields: dict[str, Any] = {
        "content": content,
        "category": category,
        "source": source,
        "tx_from": tx_from or _now(),
        "valid_from": valid_from,
    }
    fields.update(extra)
    fields = _required_defaults(fields, default_tx_from=fields["tx_from"])

    # tags is a TEXT column; serialize list/tuple to JSON for storage.
    if isinstance(fields.get("tags"), (list, tuple)):
        fields["tags"] = json.dumps(list(fields["tags"]))

    cols = [k for k in fields if fields[k] is not None]
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    values = [fields[k] for k in cols]

    cur = conn.execute(
        f"INSERT INTO facts ({col_list}) VALUES ({placeholders})",
        values,
    )
    fact_id = cur.lastrowid

    new_state = _snapshot(conn, fact_id)
    conn.execute(
        "INSERT INTO fact_history (fact_id, operation, prev_state, new_state, "
        "session, reason) VALUES (?, 'insert', NULL, ?, ?, ?)",
        (fact_id, json.dumps(new_state), session, reason),
    )
    return fact_id


def supersede_fact(
    conn: sqlite3.Connection,
    old_id: int,
    *,
    content: str,
    category: str,
    source: str,
    valid_from: str | None = None,
    tx_from: str | None = None,
    session: int | None = None,
    reason: str | None = None,
    **extra: Any,
) -> int:
    """Replace fact `old_id` with a new fact that points back at it.

    Closes out old by setting old.tx_to = now. Inserts new with supersedes_id =
    old_id. Logs a single 'supersede' row in fact_history keyed on the OLD
    fact_id (the transition point).

    Returns the new fact id. Raises TypeError on unknown **extra keys.
    """
    unknown = set(extra) - set(_FACT_COLS)
    if unknown:
        raise TypeError(
            f"supersede_fact: unknown field(s) {sorted(unknown)}; "
            f"allowed: {sorted(_FACT_COLS)}"
        )
    prev = _snapshot(conn, old_id)
    if prev is None:
        raise ValueError(f"supersede_fact: fact {old_id} not found")
    if prev.get("retracted"):
        raise ValueError(f"supersede_fact: fact {old_id} is retracted")
    if prev.get("tx_to") is not None:
        raise ValueError(f"supersede_fact: fact {old_id} already superseded")

    now = _now()

    conn.execute(
        "UPDATE facts SET tx_to = ?, updated_at = ? WHERE id = ?",
        (now, now, old_id),
    )

    fields: dict[str, Any] = {
        "content": content,
        "category": category,
        "source": source,
        "tx_from": tx_from or now,
        "valid_from": valid_from,
        "supersedes_id": old_id,
    }
    fields.update(extra)
    fields = _required_defaults(fields, default_tx_from=fields["tx_from"])

    if isinstance(fields.get("tags"), (list, tuple)):
        fields["tags"] = json.dumps(list(fields["tags"]))

    cols = [k for k in fields if fields[k] is not None]
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    values = [fields[k] for k in cols]

    cur = conn.execute(
        f"INSERT INTO facts ({col_list}) VALUES ({placeholders})",
        values,
    )
    new_id = cur.lastrowid

    new_state = _snapshot(conn, new_id)
    conn.execute(
        "INSERT INTO fact_history (fact_id, operation, prev_state, new_state, "
        "session, reason) VALUES (?, 'supersede', ?, ?, ?, ?)",
        (old_id, json.dumps(prev), json.dumps(new_state), session, reason),
    )
    return new_id


def insert_episode(
    conn: sqlite3.Connection,
    *,
    title: str,
    content: str,
    occurred_at: str,
    **extra: Any,
) -> int:
    """Insert an episode row. Episodes are append-only -- no bitemporal
    semantics, no fact_history log, no supersede/retract surface. Returns the
    new episode id.

    Raises TypeError on unknown **extra keys. Caller manages the transaction;
    the FTS5 trigger keeps episodes_fts in sync. `fact_refs` and `tags`, if
    passed as lists, are JSON-serialized for storage.
    """
    unknown = set(extra) - set(_EPISODE_COLS)
    if unknown:
        raise TypeError(
            f"insert_episode: unknown field(s) {sorted(unknown)}; "
            f"allowed: {sorted(_EPISODE_COLS)}"
        )

    fields: dict[str, Any] = {
        "title": title,
        "content": content,
        "occurred_at": occurred_at,
    }
    fields.update(extra)

    for k in ("fact_refs", "tags"):
        if isinstance(fields.get(k), (list, tuple)):
            fields[k] = json.dumps(list(fields[k]))

    cols = [k for k in fields if fields[k] is not None]
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    values = [fields[k] for k in cols]

    cur = conn.execute(
        f"INSERT INTO episodes ({col_list}) VALUES ({placeholders})",
        values,
    )
    return cur.lastrowid


def retract_fact(
    conn: sqlite3.Connection,
    fact_id: int,
    *,
    session: int | None = None,
    reason: str | None = None,
) -> None:
    """Mark a fact as retracted (no replacement).

    Sets facts.retracted = 1 and facts.tx_to = now. Logs a 'retract' row in
    fact_history with new_state = NULL. Default reads (`WHERE retracted = 0`)
    skip the fact, but as-of queries before the retract time still find it.
    """
    prev = _snapshot(conn, fact_id)
    if prev is None:
        raise ValueError(f"retract_fact: fact {fact_id} not found")
    if prev.get("retracted"):
        raise ValueError(f"retract_fact: fact {fact_id} already retracted")

    now = _now()
    conn.execute(
        "UPDATE facts SET retracted = 1, tx_to = ?, updated_at = ? WHERE id = ?",
        (now, now, fact_id),
    )
    conn.execute(
        "INSERT INTO fact_history (fact_id, operation, prev_state, new_state, "
        "session, reason) VALUES (?, 'retract', ?, NULL, ?, ?)",
        (fact_id, json.dumps(prev), session, reason),
    )


def undo_supersede_fact(
    conn: sqlite3.Connection,
    source_fact_id: int,
    *,
    session: int | None = None,
    reason: str | None = None,
) -> None:
    """Reverse a supersede on a source fact. Clears tx_to so the fact reads live again.

    Logs an 'update' fact_history row with `reason` prefixed by 'undo_supersede'
    so the operation is auditable without expanding the fact_history.operation
    CHECK constraint (which would require a schema migration). Downstream tooling
    filters with `WHERE operation = 'update' AND reason LIKE 'undo_supersede%'`.

    Raises ValueError if the fact is not found, is retracted, or was never
    superseded (`tx_to` is NULL).
    """
    prev = _snapshot(conn, source_fact_id)
    if prev is None:
        raise ValueError(f"undo_supersede_fact: fact {source_fact_id} not found")
    if prev.get("retracted"):
        raise ValueError(
            f"undo_supersede_fact: fact {source_fact_id} is retracted; "
            "retract is a terminal state and cannot be undone via this primitive"
        )
    if prev.get("tx_to") is None:
        raise ValueError(
            f"undo_supersede_fact: fact {source_fact_id} is not superseded "
            "(tx_to is NULL); nothing to undo"
        )

    now = _now()
    conn.execute(
        "UPDATE facts SET tx_to = NULL, updated_at = ? WHERE id = ?",
        (now, source_fact_id),
    )

    new_state = _snapshot(conn, source_fact_id)
    full_reason = "undo_supersede"
    if reason:
        full_reason = f"undo_supersede: {reason}"
    conn.execute(
        "INSERT INTO fact_history (fact_id, operation, prev_state, new_state, "
        "session, reason) VALUES (?, 'update', ?, ?, ?, ?)",
        (source_fact_id, json.dumps(prev), json.dumps(new_state), session, full_reason),
    )


def batch_supersede(
    conn: sqlite3.Connection,
    pairs: list[tuple[int, int]],
    *,
    session: int | None = None,
    reason: str | None = None,
) -> int:
    """Close `tx_to` on N source facts that collapse onto already-inserted
    derived facts. Returns the number of pairs processed.

    For each (source_id, derived_id) pair: validate both rows are live and not
    retracted, set source.tx_to = now, and log a 'supersede' fact_history row
    keyed on the source. Handles 1:1, N:1, and N:M cardinality. An empty list
    is a no-op returning 0.

    Atomicity: each pair's UPDATE + INSERT is back-to-back on the same
    connection without an intervening commit. The whole batch is atomic if the
    caller wraps it in `with conn:`.
    """
    if not pairs:
        return 0

    now = _now()
    processed = 0

    for source_id, derived_id in pairs:
        source_prev = _snapshot(conn, source_id)
        if source_prev is None:
            raise ValueError(f"batch_supersede: source fact {source_id} not found")
        if source_prev.get("retracted"):
            raise ValueError(f"batch_supersede: source fact {source_id} is retracted")
        if source_prev.get("tx_to") is not None:
            raise ValueError(f"batch_supersede: source fact {source_id} already superseded")

        derived_snapshot = _snapshot(conn, derived_id)
        if derived_snapshot is None:
            raise ValueError(f"batch_supersede: derived fact {derived_id} not found")
        if derived_snapshot.get("retracted"):
            raise ValueError(f"batch_supersede: derived fact {derived_id} is retracted")

        conn.execute(
            "UPDATE facts SET tx_to = ?, updated_at = ? WHERE id = ?",
            (now, now, source_id),
        )
        conn.execute(
            "INSERT INTO fact_history (fact_id, operation, prev_state, new_state, "
            "session, reason) VALUES (?, 'supersede', ?, ?, ?, ?)",
            (
                source_id,
                json.dumps(source_prev),
                json.dumps(derived_snapshot),
                session,
                reason,
            ),
        )
        processed += 1

    return processed
