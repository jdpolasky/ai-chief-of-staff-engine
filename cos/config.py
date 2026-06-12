"""Path configuration for cos, driven entirely by environment variables.

Nothing here is tied to a specific machine or user. Set these to point cos at
your own notes vault:

    COS_VAULT       root folder of your Markdown vault   (default: ~/cos-vault)
    COS_STATE_DIR   where the database + backups live     (default: <vault>/_state)
    COS_DB          the SQLite database file              (default: <state>/memory.db)
    COS_MEMORY_DIR  folder of memory .md files to seed    (default: <vault>/memory)
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    val = os.environ.get(name)
    return Path(val).expanduser() if val else default


VAULT = _env_path("COS_VAULT", Path.home() / "cos-vault")
STATE_DIR = _env_path("COS_STATE_DIR", VAULT / "_state")
DEFAULT_DB_PATH = _env_path("COS_DB", STATE_DIR / "memory.db")
MEMORY_DIR = _env_path("COS_MEMORY_DIR", VAULT / "memory")

__all__ = ["VAULT", "STATE_DIR", "DEFAULT_DB_PATH", "MEMORY_DIR"]
