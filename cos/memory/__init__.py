"""cos.memory -- SQLite-backed memory layer.

Core storage: facts, episodes, fact_history tables + FTS5 full-text search
indices. Higher layers (the `cos memory` subcommand, BRAID write contracts)
build on this.

Paths come from cos.config and are environment-configurable.
"""

from pathlib import Path

from ..config import DEFAULT_DB_PATH, STATE_DIR, VAULT

SCHEMA_SQL = Path(__file__).parent / "schema.sql"

__all__ = ["VAULT", "STATE_DIR", "DEFAULT_DB_PATH", "SCHEMA_SQL"]
