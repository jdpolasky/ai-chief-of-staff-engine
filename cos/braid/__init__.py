"""cos.braid -- input validation gate for cos.memory writes.

Write contracts do JSON Schema validation BEFORE any DB write, so malformed
records are rejected at the door rather than corrupting the store. The write
path calls validate_braid(record, kind) before touching memory.db or the jsonl
backup.

  - JSON Schema contracts ship with the package in cos/braid/contracts/*.json
  - validate_braid(record, kind) raises BraidRejection on failure
  - all rejections are logged to <state>/braid_rejections.log
"""

from pathlib import Path

from ..config import STATE_DIR

CONTRACTS_DIR = Path(__file__).parent / "contracts"
REJECTIONS_LOG = STATE_DIR / "braid_rejections.log"

__all__ = ["CONTRACTS_DIR", "REJECTIONS_LOG"]
