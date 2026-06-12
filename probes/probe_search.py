"""probe_search -- the read-side memory CLI: retrieve, search, stats.

Run from the repo root:

    python probes/probe_search.py

Exercises cmd_retrieve / cmd_search / cmd_stats end-to-end by constructing
argparse Namespaces, capturing stdout/stderr, and parsing the JSONL/text output:

  retrieve: by-id happy; by-id missing -> empty; by-subject returns all current
            facts for the subject; subject-type narrowing filters; without
            --subject-type returns every type for the subject (the else branch);
            neither --id nor --subject -> exit 1.
  search:   fact-only hit; episode-only hit; a shared term hits both kinds;
            --kind restricts; a no-hit term returns empty.
  stats:    counts facts/episodes/rejections; retracted facts drop out of
            retrieve, search, and the stats facts count; a present rejections
            log is line-counted.

Self-contained: tempdir + temp sqlite db via apply_schema; injectable jsonl
writer targets a tempfile. Exits 0 on pass; nonzero with a printed FAIL reason.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cos.memory.migrate import apply_schema  # noqa: E402
from cos.memory.writers import retract_fact  # noqa: E402
from cos.subcommands.memory import (  # noqa: E402
    cmd_retrieve, cmd_search, cmd_stats, memory_add,
)


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


def run_cmd(cmd_func, **ns_kwargs):
    args = argparse.Namespace(**ns_kwargs)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cmd_func(args) or 0
    return rc, out.getvalue(), err.getvalue()


def parse_jsonl(s: str):
    return [json.loads(line) for line in s.strip().split("\n") if line.strip()]


def main() -> int:
    sandbox = Path(tempfile.mkdtemp(prefix="probe_search_"))
    try:
        db_path = sandbox / "memory.db"
        apply_schema(db_path)
        facts_jsonl = sandbox / "facts.jsonl"
        eps_jsonl = sandbox / "episodes.jsonl"
        rejections_log = sandbox / "braid_rejections.log"

        conn = sqlite3.connect(db_path)
        try:
            fact_a = {
                "content": "Larkspur Phase II ad budget capped at $350/mo",
                "category": "decision", "source": "manual",
                "subject_type": "project", "subject_id": "larkspur-phase-ii",
                "valid_from": "2026-05-04", "tx_from": "2026-05-04 18:32:11.456",
            }
            fact_b = {
                "content": "Larkspur Phase II uses split billing",
                "category": "decision", "source": "manual",
                "subject_type": "project", "subject_id": "larkspur-phase-ii",
                "valid_from": "2026-05-04", "tx_from": "2026-05-04 19:00:00.000",
            }
            fact_c = {
                "content": "Meadowlark uses a hosted CMS for the catalog",
                "category": "reference", "source": "manual",
                "subject_type": "project", "subject_id": "meadowlark",
                "valid_from": "2026-05-22", "tx_from": "2026-05-22 17:24:00.000",
            }
            # same subject_id, different subject_type -> narrowing fixture.
            fact_d = {
                "content": "Meadowlark is also the name of the survey drone",
                "category": "reference", "source": "manual",
                "subject_type": "tool", "subject_id": "meadowlark",
                "valid_from": "2024-01-01", "tx_from": "2024-01-01 00:00:00.000",
            }
            ep = {
                "title": "Larkspur Phase II kickoff",
                "content": "Phase II started with a spring trial bundle and scope review.",
                "occurred_at": "2026-05-04", "session": 17,
            }

            ids = {}
            for name, rec, kind, jl in (
                ("a", fact_a, "fact", facts_jsonl),
                ("b", fact_b, "fact", facts_jsonl),
                ("c", fact_c, "fact", facts_jsonl),
                ("d", fact_d, "fact", facts_jsonl),
                ("ep", ep, "episode", eps_jsonl),
            ):
                with conn:
                    ids[name] = memory_add(conn, rec, kind,
                                           jsonl_writer=make_jsonl_writer(jl))

            # retrieve by-id happy
            rc, out, err = run_cmd(cmd_retrieve, id=ids["a"], subject=None,
                                   subject_type=None, db=str(db_path))
            check(rc == 0, f"retrieve by-id: rc={rc} err={err!r}")
            rows = parse_jsonl(out)
            check(len(rows) == 1 and rows[0]["id"] == ids["a"],
                  f"retrieve by-id: expected id {ids['a']}, got {rows}")

            # retrieve by-id missing -> empty
            rc, out, _ = run_cmd(cmd_retrieve, id=999999, subject=None,
                                 subject_type=None, db=str(db_path))
            check(not out.strip(), f"retrieve missing: expected empty, got {out!r}")

            # by-subject returns both larkspur facts
            rc, out, _ = run_cmd(cmd_retrieve, id=None, subject="larkspur-phase-ii",
                                 subject_type=None, db=str(db_path))
            got = sorted(r["id"] for r in parse_jsonl(out))
            check(got == sorted([ids["a"], ids["b"]]),
                  f"retrieve by-subject: expected {sorted([ids['a'], ids['b']])}, got {got}")

            # narrowing: project:meadowlark only
            rc, out, _ = run_cmd(cmd_retrieve, id=None, subject="meadowlark",
                                 subject_type="project", db=str(db_path))
            rows = parse_jsonl(out)
            check(len(rows) == 1 and rows[0]["id"] == ids["c"],
                  f"retrieve narrowing: expected only fact_c ({ids['c']}), got {rows}")

            # else branch: no subject-type -> both types
            rc, out, _ = run_cmd(cmd_retrieve, id=None, subject="meadowlark",
                                 subject_type=None, db=str(db_path))
            rows = parse_jsonl(out)
            check(sorted(r["id"] for r in rows) == sorted([ids["c"], ids["d"]]),
                  f"retrieve cross-type: expected both c+d, got {[r['id'] for r in rows]}")
            check({r["subject_type"] for r in rows} == {"project", "tool"},
                  "retrieve cross-type: expected both subject_types back")

            # bad usage
            rc, out, err = run_cmd(cmd_retrieve, id=None, subject=None,
                                   subject_type=None, db=str(db_path))
            check(rc == 1, f"retrieve bad usage: expected rc=1, got {rc}")
            check("exactly one of" in err, f"retrieve bad usage: stderr {err!r}")

            # search: fact-only ('budget' unique to fact_a)
            rc, out, _ = run_cmd(cmd_search, query="budget", kind=None, db=str(db_path))
            fact_hits = [r for r in parse_jsonl(out) if r.get("kind") == "fact"]
            check(len(fact_hits) == 1 and fact_hits[0]["id"] == ids["a"],
                  f"search fact hit: expected fact_a, got {out!r}")

            # search: episode-only ('kickoff' unique to ep title)
            rc, out, _ = run_cmd(cmd_search, query="kickoff", kind=None, db=str(db_path))
            ep_hits = [r for r in parse_jsonl(out) if r.get("kind") == "episode"]
            check(len(ep_hits) == 1 and ep_hits[0]["id"] == ids["ep"],
                  f"search episode hit: expected episode, got {out!r}")

            # search: shared term hits both kinds
            rc, out, _ = run_cmd(cmd_search, query="Phase", kind=None, db=str(db_path))
            kinds = {r.get("kind") for r in parse_jsonl(out)}
            check(kinds == {"fact", "episode"},
                  f"search both kinds: expected both, got {kinds}")

            # --kind restricts
            rc, out, _ = run_cmd(cmd_search, query="Phase", kind="fact", db=str(db_path))
            check(all(r.get("kind") == "fact" for r in parse_jsonl(out)),
                  "search --kind fact: returned a non-fact")

            # no hit
            rc, out, _ = run_cmd(cmd_search, query="zzznotaword", kind=None, db=str(db_path))
            check(not out.strip(), f"search no hit: expected empty, got {out!r}")

            # stats with data, no rejections file
            rc, out, _ = run_cmd(cmd_stats, db=str(db_path),
                                 rejections_log=str(rejections_log))
            check("facts: 4" in out, f"stats: expected 'facts: 4', got {out!r}")
            check("episodes: 1" in out, f"stats: expected 'episodes: 1', got {out!r}")
            check("rejections: 0" in out, f"stats: expected 'rejections: 0', got {out!r}")

            # retract fact_a; it drops from retrieve, search, and stats count.
            with conn:
                retract_fact(conn, ids["a"], session=17, reason="probe retract")

            rc, out, _ = run_cmd(cmd_retrieve, id=ids["a"], subject=None,
                                 subject_type=None, db=str(db_path))
            check(not out.strip(), f"retrieve retracted by-id: expected empty, got {out!r}")

            rc, out, _ = run_cmd(cmd_retrieve, id=None, subject="larkspur-phase-ii",
                                 subject_type=None, db=str(db_path))
            check([r["id"] for r in parse_jsonl(out)] == [ids["b"]],
                  f"retrieve after retract: expected only b, got {out!r}")

            rc, out, _ = run_cmd(cmd_search, query="budget", kind=None, db=str(db_path))
            check(not out.strip(), f"search retracted: expected empty, got {out!r}")

            rc, out, _ = run_cmd(cmd_stats, db=str(db_path),
                                 rejections_log=str(rejections_log))
            check("facts: 3" in out, f"stats after retract: expected 'facts: 3', got {out!r}")

            # stats with a rejections log present
            rejections_log.write_text(
                '{"ts":"x","kind":"fact"}\n{"ts":"y","kind":"fact"}\n', encoding="utf-8")
            rc, out, _ = run_cmd(cmd_stats, db=str(db_path),
                                 rejections_log=str(rejections_log))
            check("rejections: 2" in out, f"stats rejections: expected 2, got {out!r}")
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

    print("PASS: probe_search  retrieve+search+stats+retracted-filter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
