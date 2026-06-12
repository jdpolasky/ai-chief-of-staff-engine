"""Apply cos/memory/schema.sql to a target SQLite database.

Idempotent: every DDL statement is CREATE ... IF NOT EXISTS, so re-running on
an already-migrated database is a no-op.

CLI:
    python -m cos.memory.migrate --db path/to/memory.db
"""

import argparse
import sqlite3
from pathlib import Path

from . import DEFAULT_DB_PATH, SCHEMA_SQL


def apply_schema(db_path: Path) -> None:
    """Create the schema in the SQLite DB at db_path.

    Creates the parent directory if missing. Safe to call repeatedly.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    # `with sqlite3.connect(...)` commits but does NOT close the connection,
    # leaking the handle (and on Windows holding a file lock). Close explicitly.
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Apply the cos memory.db schema")
    p.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"path to memory.db (default: {DEFAULT_DB_PATH})",
    )
    args = p.parse_args()
    apply_schema(args.db)
    print(f"applied schema to {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
