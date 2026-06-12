"""cos -- a portable, plain-text-first memory engine for an AI assistant.

Your vault of Markdown notes stays the source of truth. This package adds a
rebuildable SQLite index and search layer on top, so an assistant can answer
"what do I know about X" in seconds instead of re-reading files. Delete the
database and it regenerates from the Markdown. Nothing lives only in the
database.

Paths are configured through environment variables (see cos.config); nothing
is tied to one machine or user.
"""

__version__ = "0.1.0"
