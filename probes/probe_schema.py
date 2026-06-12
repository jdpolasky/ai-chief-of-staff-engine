"""probe_schema -- the memory.db schema applies cleanly and enforces its shape.

Run from the repo root:

    python probes/probe_schema.py

Applies cos/memory/schema.sql (via the engine's apply_schema) to a fresh temp
sqlite db and asserts:
  - Base tables facts / episodes / fact_history exist.
  - FTS5 virtual tables facts_fts / episodes_fts exist.
  - All expected indices and triggers exist.
  - FTS5 round-trip: a base-table insert propagates to the FTS index.
  - CHECK constraints reject: confidence outside [0,1], retracted outside {0,1},
    a bad episode valence, a bad fact_history operation.

Exits 0 on pass; nonzero with a printed FAIL reason. No pytest dependency.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cos.memory.migrate import apply_schema  # noqa: E402

EXPECTED_TABLES = {"facts", "episodes", "fact_history"}
EXPECTED_FTS = {"facts_fts", "episodes_fts"}
EXPECTED_INDICES = {
    "idx_facts_subject", "idx_facts_category", "idx_facts_valid",
    "idx_facts_tx", "idx_facts_session",
    "idx_episodes_occurred", "idx_episodes_session",
    "idx_fact_history_fact_tx", "idx_fact_history_tx",
}
EXPECTED_TRIGGERS = {
    "facts_ai", "facts_ad", "facts_au",
    "episodes_ai", "episodes_ad", "episodes_au",
}


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="probe_schema_"))
    try:
        db_path = sandbox / "memory.db"
        apply_schema(db_path)
        conn = sqlite3.connect(db_path)
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for t in EXPECTED_TABLES:
                check(t in tables, f"missing base table: {t}")
            for t in EXPECTED_FTS:
                check(t in tables, f"missing FTS5 virtual table: {t}")

            indices = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name NOT LIKE 'sqlite_%'").fetchall()}
            for idx in EXPECTED_INDICES:
                check(idx in indices, f"missing index: {idx}")

            triggers = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()}
            for trg in EXPECTED_TRIGGERS:
                check(trg in triggers, f"missing trigger: {trg}")

            # FTS5 round-trip: facts
            conn.execute(
                "INSERT INTO facts (content, category, source, valid_from, tx_from) "
                "VALUES (?, ?, ?, ?, ?)",
                ("Nursery irrigation budget capped this season", "decision",
                 "manual", "2026-05-04", "2026-05-04 00:00:00.000"),
            )
            conn.commit()
            hit = conn.execute(
                "SELECT rowid FROM facts_fts WHERE facts_fts MATCH ?", ("irrigation",)
            ).fetchone()
            check(hit is not None,
                  "FTS5 facts round-trip: insert did not propagate to facts_fts")

            # FTS5 round-trip: episodes
            conn.execute(
                "INSERT INTO episodes (title, content, occurred_at) VALUES (?, ?, ?)",
                ("Season wrap", "Consolidated the nursery logs for the quarter.",
                 "2026-05-24"),
            )
            conn.commit()
            hit = conn.execute(
                "SELECT rowid FROM episodes_fts WHERE episodes_fts MATCH ?",
                ("consolidated",),
            ).fetchone()
            check(hit is not None,
                  "FTS5 episodes round-trip: insert did not propagate to episodes_fts")

            # CHECK: confidence outside [0,1]
            try:
                conn.execute(
                    "INSERT INTO facts (content, category, source, valid_from, "
                    "tx_from, confidence) VALUES (?, ?, ?, ?, ?, ?)",
                    ("bad confidence", "decision", "manual", "2026-05-25",
                     "2026-05-25 00:00:00.000", 1.5),
                )
                conn.commit()
                raise ProbeFail("CHECK confidence: 1.5 accepted (should reject)")
            except sqlite3.IntegrityError:
                conn.rollback()

            # CHECK: retracted outside {0,1}
            try:
                conn.execute(
                    "INSERT INTO facts (content, category, source, valid_from, "
                    "tx_from, retracted) VALUES (?, ?, ?, ?, ?, ?)",
                    ("bad retracted", "decision", "manual", "2026-05-25",
                     "2026-05-25 00:00:00.000", 2),
                )
                conn.commit()
                raise ProbeFail("CHECK retracted: 2 accepted (should reject)")
            except sqlite3.IntegrityError:
                conn.rollback()

            # CHECK: episode valence enum
            try:
                conn.execute(
                    "INSERT INTO episodes (title, content, occurred_at, valence) "
                    "VALUES (?, ?, ?, ?)",
                    ("bad valence", "body", "2026-05-25", "ecstatic"),
                )
                conn.commit()
                raise ProbeFail("CHECK valence: 'ecstatic' accepted (should reject)")
            except sqlite3.IntegrityError:
                conn.rollback()

            # CHECK: fact_history.operation enum (FK against a real fact)
            cur = conn.execute(
                "INSERT INTO facts (content, category, source, valid_from, tx_from) "
                "VALUES (?, ?, ?, ?, ?)",
                ("anchor fact", "decision", "manual", "2026-05-25",
                 "2026-05-25 00:00:00.000"),
            )
            anchor_id = cur.lastrowid
            conn.commit()
            try:
                conn.execute(
                    "INSERT INTO fact_history (fact_id, operation) VALUES (?, ?)",
                    (anchor_id, "bogus"),
                )
                conn.commit()
                raise ProbeFail("CHECK operation: 'bogus' accepted (should reject)")
            except sqlite3.IntegrityError:
                conn.rollback()
        finally:
            conn.close()
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

    print("PASS: probe_schema  tables+fts+indices+triggers+checks+round_trips")
    return 0


if __name__ == "__main__":
    sys.exit(main())
