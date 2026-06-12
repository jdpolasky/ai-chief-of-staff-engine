"""probe_writers -- bitemporal write helpers + the memory_add orchestration.

Run from the repo root:

    python probes/probe_writers.py

Covers cos.memory.writers and the memory_add write path:
  - insert + retract: facts row stays (retracted=1, tx_to set); fact_history has
    insert then retract rows; default read skips it; an as-of read at insert time
    still finds it; double-retract and retract-missing raise; FTS5 stays synced.
  - supersede round-trip: supersede_fact closes the old row and links the new;
    undo_supersede_fact reopens the source; supersede of a retracted/already-
    superseded fact raises.
  - batch_supersede: N:1 collapse closes all sources; bad pair raises.
  - memory_add: happy fact + episode land in DB and call the jsonl writer; a
    BRAID-rejected payload writes nothing; a jsonl-writer failure rolls the DB
    insert back (atomicity).

Self-contained: tempdir + temp sqlite db via apply_schema; injectable jsonl
writer targets a tempfile. Exits 0 on pass; nonzero with a printed FAIL reason.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cos.braid.validate import BraidRejection  # noqa: E402
from cos.memory.migrate import apply_schema  # noqa: E402
from cos.memory.writers import (  # noqa: E402
    batch_supersede,
    insert_fact,
    retract_fact,
    supersede_fact,
    undo_supersede_fact,
)
from cos.subcommands.memory import memory_add  # noqa: E402


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def make_jsonl_writer(target: Path):
    def writer(record, kind, row_id):
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"row_id": row_id, "kind": kind, "record": record},
                               default=str) + "\n")
    return writer


def fresh_db(sandbox: Path, name: str) -> sqlite3.Connection:
    db_path = sandbox / name
    apply_schema(db_path)
    return sqlite3.connect(db_path)


def assert_retract(sandbox: Path) -> None:
    conn = fresh_db(sandbox, "retract.db")
    try:
        a_id = insert_fact(
            conn, content="The estate uses the north well for irrigation",
            category="reference", subject_type="project", subject_id="estate",
            source="manual", valid_from="2026-03-01", session=10,
        )
        conn.commit()
        time.sleep(0.05)
        retract_fact(conn, a_id, session=11, reason="well decommissioned")
        conn.commit()

        row = conn.execute(
            "SELECT retracted, tx_to FROM facts WHERE id = ?", (a_id,)).fetchone()
        check(row is not None, "retract: row deleted (should remain)")
        check(row[0] == 1, f"retract: retracted should be 1, got {row[0]}")
        check(row[1] is not None, "retract: tx_to is NULL after retract")

        hist = conn.execute(
            "SELECT operation, fact_id, prev_state IS NULL, new_state IS NULL "
            "FROM fact_history ORDER BY id").fetchall()
        check(len(hist) == 2, f"fact_history: expected 2 rows, got {len(hist)}")
        op0, fid0, pn0, nn0 = hist[0]
        op1, fid1, pn1, nn1 = hist[1]
        check(op0 == "insert" and fid0 == a_id and pn0 == 1 and nn0 == 0,
              f"history[0] not insert(A) prev=NULL new=set: {hist[0]}")
        check(op1 == "retract" and fid1 == a_id and pn1 == 0 and nn1 == 1,
              f"history[1] not retract(A) prev=set new=NULL: {hist[1]}")

        default = conn.execute("SELECT id FROM facts WHERE retracted = 0").fetchall()
        check(all(r[0] != a_id for r in default),
              "default read (retracted=0) returned the retracted fact")

        tx_from = conn.execute(
            "SELECT tx_from FROM facts WHERE id = ?", (a_id,)).fetchone()[0]
        as_of = conn.execute(
            "SELECT id FROM facts WHERE tx_from <= ? AND (tx_to > ? OR tx_to IS NULL)",
            (tx_from, tx_from)).fetchall()
        check(a_id in {r[0] for r in as_of},
              "as-of read at insert time did not find the (later) retracted fact")

        for bad in (lambda: retract_fact(conn, a_id),
                    lambda: retract_fact(conn, 99999)):
            try:
                bad()
                raise ProbeFail("retract: expected ValueError, none raised")
            except ValueError:
                pass

        hit = conn.execute(
            "SELECT rowid FROM facts_fts WHERE facts_fts MATCH ?", ("irrigation",)
        ).fetchone()
        check(hit is not None and hit[0] == a_id,
              "FTS5: retracted fact should remain searchable (caller filters)")
    finally:
        conn.close()


def assert_supersede(sandbox: Path) -> None:
    conn = fresh_db(sandbox, "supersede.db")
    try:
        old_id = insert_fact(
            conn, content="Soil pH target is 6.0", category="reference",
            source="manual", confidence=0.9, valid_from="2026-01-01")
        conn.commit()
        new_id = supersede_fact(
            conn, old_id, content="Soil pH target is 6.5", category="reference",
            source="manual", confidence=0.95, valid_from="2026-04-01",
            session=20, reason="revised after survey")
        conn.commit()

        old_row = conn.execute(
            "SELECT tx_to FROM facts WHERE id = ?", (old_id,)).fetchone()
        check(old_row[0] is not None, "supersede: old fact tx_to not closed")
        new_row = conn.execute(
            "SELECT supersedes_id, tx_to FROM facts WHERE id = ?", (new_id,)).fetchone()
        check(new_row[0] == old_id, f"supersede: new.supersedes_id != old ({new_row[0]})")
        check(new_row[1] is None, "supersede: new fact already closed")

        live = conn.execute(
            "SELECT id FROM facts WHERE retracted = 0 AND tx_to IS NULL").fetchall()
        check({r[0] for r in live} == {new_id},
              f"supersede: live set should be just new, got {[r[0] for r in live]}")

        sup = conn.execute(
            "SELECT operation FROM fact_history WHERE operation='supersede'").fetchall()
        check(len(sup) == 1, f"supersede: expected 1 supersede history row, got {len(sup)}")

        # undo reopens the source.
        undo_supersede_fact(conn, old_id, session=21, reason="revert")
        conn.commit()
        reopened = conn.execute(
            "SELECT tx_to FROM facts WHERE id = ?", (old_id,)).fetchone()
        check(reopened[0] is None, "undo_supersede: source tx_to not reopened")

        # supersede of an already-superseded / retracted fact raises.
        again = supersede_fact(
            conn, old_id, content="Soil pH target is 6.5 (again)",
            category="reference", source="manual", valid_from="2026-04-02")
        conn.commit()
        try:
            supersede_fact(conn, old_id, content="dup", category="reference",
                           source="manual", valid_from="2026-04-03")
            raise ProbeFail("supersede: re-superseding a closed fact should raise")
        except ValueError:
            pass
        retract_fact(conn, again)
        conn.commit()
        try:
            supersede_fact(conn, again, content="dup2", category="reference",
                           source="manual", valid_from="2026-04-04")
            raise ProbeFail("supersede: superseding a retracted fact should raise")
        except ValueError:
            pass
    finally:
        conn.close()


def assert_batch_supersede(sandbox: Path) -> None:
    conn = fresh_db(sandbox, "batch.db")
    try:
        sources = [
            insert_fact(conn, content=f"draft rule {i}", category="preference",
                        source="manual", confidence=0.9, valid_from="2026-01-01")
            for i in range(3)
        ]
        derived = insert_fact(
            conn, content="consolidated rule", category="preference",
            source="manual", confidence=0.95, valid_from="2026-02-01")
        conn.commit()

        with conn:
            n = batch_supersede(conn, [(s, derived) for s in sources],
                                session=30, reason="collapse N:1")
        check(n == 3, f"batch_supersede: expected 3 processed, got {n}")

        live = {r[0] for r in conn.execute(
            "SELECT id FROM facts WHERE retracted = 0 AND tx_to IS NULL").fetchall()}
        check(live == {derived},
              f"batch_supersede: live set should be just derived, got {live}")

        check(batch_supersede(conn, []) == 0, "batch_supersede([]) should be 0")
        try:
            with conn:
                batch_supersede(conn, [(99999, derived)])
            raise ProbeFail("batch_supersede: missing source should raise")
        except ValueError:
            pass
    finally:
        conn.close()


def assert_memory_add(sandbox: Path) -> None:
    db_path = sandbox / "add.db"
    apply_schema(db_path)
    facts_jsonl = sandbox / "facts.jsonl"
    eps_jsonl = sandbox / "episodes.jsonl"
    conn = sqlite3.connect(db_path)
    try:
        good_fact = {
            "content": "Larkspur planting window opens in late April",
            "category": "reference", "source": "manual",
            "valid_from": "2026-04-04", "tx_from": "2026-04-04 18:32:11.456",
        }
        with conn:
            fid = memory_add(conn, good_fact, "fact",
                             jsonl_writer=make_jsonl_writer(facts_jsonl))
        check(bool(fid), f"fact add: expected row id, got {fid!r}")
        row = conn.execute("SELECT content FROM facts WHERE id = ?", (fid,)).fetchone()
        check(row and row[0] == good_fact["content"], "fact add: content mismatch")
        check(facts_jsonl.exists(), "fact add: jsonl not written")
        entry = json.loads(facts_jsonl.read_text(encoding="utf-8").strip())
        check(entry["row_id"] == fid and entry["kind"] == "fact",
              f"fact add: jsonl row_id/kind mismatch: {entry}")

        good_ep = {
            "title": "Larkspur kickoff",
            "content": "Project Larkspur kickoff covered scope and the schedule.",
            "occurred_at": "2026-05-25", "session": 30, "valence": "neutral",
        }
        with conn:
            eid = memory_add(conn, good_ep, "episode",
                             jsonl_writer=make_jsonl_writer(eps_jsonl))
        check(bool(eid), "episode add: expected row id")
        check(eps_jsonl.exists(), "episode add: jsonl not written")

        # BRAID rejection -> no side effects.
        pre_n = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        pre_sz = facts_jsonl.stat().st_size
        bad = dict(good_fact, category="banana")
        try:
            with conn:
                memory_add(conn, bad, "fact",
                           jsonl_writer=make_jsonl_writer(facts_jsonl))
            raise ProbeFail("BRAID: invalid category should raise BraidRejection")
        except BraidRejection:
            pass
        check(conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == pre_n,
              "BRAID rejection: facts count changed")
        check(facts_jsonl.stat().st_size == pre_sz,
              "BRAID rejection: jsonl size changed")

        # jsonl failure -> DB rollback.
        def raise_on_call(record, kind, row_id):
            raise IOError("synthetic jsonl write failure")

        pre = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        try:
            with conn:
                memory_add(conn, good_fact, "fact", jsonl_writer=raise_on_call)
            raise ProbeFail("jsonl failure: IOError should propagate")
        except IOError:
            pass
        check(conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == pre,
              "jsonl failure: facts table not rolled back (atomicity broken)")
    finally:
        conn.close()


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="probe_writers_"))
    try:
        assert_retract(sandbox)
        assert_supersede(sandbox)
        assert_batch_supersede(sandbox)
        assert_memory_add(sandbox)
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

    print("PASS: probe_writers  retract+supersede+batch+memory_add")
    return 0


if __name__ == "__main__":
    sys.exit(main())
