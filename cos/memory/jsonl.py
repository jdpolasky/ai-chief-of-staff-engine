"""Append-only jsonl backup for memory.db writes.

Every validated record persisted to memory.db is also appended as a single
JSON line to a per-kind jsonl file in the state directory. The jsonl is the
durable record if memory.db is corrupted or needs a destructive schema
migration: you can replay it line-by-line to rebuild the database.

The `add` write path calls this INSIDE the same `with conn:` block as the DB
insert, so a jsonl write failure rolls back the DB write (sqlite3
deferred-transaction semantics).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from ..config import STATE_DIR

Kind = Literal["fact", "episode"]

FACTS_JSONL = STATE_DIR / "facts.jsonl"
EPISODES_JSONL = STATE_DIR / "episodes.jsonl"


def jsonl_path(kind: Kind) -> Path:
    if kind == "fact":
        return FACTS_JSONL
    if kind == "episode":
        return EPISODES_JSONL
    raise ValueError(f"jsonl_path: unknown kind {kind!r}; expected 'fact' or 'episode'")


def jsonl_append(record: dict[str, Any], kind: Kind, row_id: int) -> None:
    """Append one JSON line for `record` tagged with `row_id`.

    The line schema is {"row_id", "kind", "record"} -- you can replay the log
    by reading line-by-line and reissuing `cos memory add` for each.

    Caller manages the transaction context; this helper writes synchronously
    to disk. Raises any I/O exception unchanged -- the caller's `with conn:`
    block sees the exception and rolls back the DB write.
    """
    path = jsonl_path(kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"row_id": row_id, "kind": kind, "record": record}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
