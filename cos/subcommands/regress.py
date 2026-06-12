"""`cos regress` -- run the behavioral probe suite.

Discovers `probes/*.py` in the repo root (or a `--probes-dir` override), runs
each as a subprocess with the current interpreter, and reports pass/fail by
exit code. Each probe is a standalone, self-contained script: it builds its own
tempdir fixtures + temp sqlite db, exercises one slice of the engine, and exits
0 on pass / nonzero on failure (printing a FAIL reason).

Per-probe output (stdout/stderr) is captured; on failure the last lines of the
probe's output are echoed so a red run is diagnosable without re-running. A
per-probe timeout guards against a hung probe wedging the suite.

Usage:
  python -m cos regress
  python -m cos regress --quiet
  python -m cos regress --probes-dir path/to/probes
  python -m cos regress --probe probe_loader   # run one by stem (or filename)

Exit code: 0 only if every discovered probe passes; 1 otherwise (failure,
timeout, or no probes found).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# repo root = two levels up from this file (cos/subcommands/regress.py).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROBES_DIR = REPO_ROOT / "probes"
PROBE_GLOB = "probe_*.py"
TIMEOUT_SEC = 120
OUTPUT_TAIL_LINES = 8  # lines of probe output echoed on failure


def discover_probes(probes_dir: Path, filter_name: str | None = None) -> list[Path]:
    """Return sorted probe_*.py paths in probes_dir. `filter_name` (a stem or
    filename, with or without the .py / probe_ affixes) selects a single probe."""
    if not probes_dir.is_dir():
        return []
    probes = sorted(probes_dir.glob(PROBE_GLOB))
    if filter_name:
        want = filter_name.removesuffix(".py")
        # Match on the bare stem, the full filename, or a probe_-prefixed stem
        # so 'loader', 'probe_loader', and 'probe_loader.py' all select it.
        candidates = {want, filter_name, want if want.startswith("probe_") else f"probe_{want}"}
        probes = [p for p in probes if p.stem in candidates or p.name in candidates]
    return probes


def run_probe(probe_path: Path) -> dict:
    """Run one probe as a subprocess. Returns a result dict with pass/fail."""
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(probe_path)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC,
        )
        return {
            "probe": probe_path.name,
            "duration_sec": round(time.monotonic() - t0, 3),
            "exit_code": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "passed": proc.returncode == 0,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (
            e.stdout.decode("utf-8", "replace") if e.stdout else "")
        err = e.stderr if isinstance(e.stderr, str) else (
            e.stderr.decode("utf-8", "replace") if e.stderr else "")
        return {
            "probe": probe_path.name,
            "duration_sec": round(time.monotonic() - t0, 3),
            "exit_code": None,
            "stdout": out,
            "stderr": err or f"timeout after {TIMEOUT_SEC}s",
            "passed": False,
            "timed_out": True,
        }


def run(args: argparse.Namespace) -> int:
    probes_dir = Path(args.probes_dir) if args.probes_dir else DEFAULT_PROBES_DIR
    probes = discover_probes(probes_dir, args.probe)
    if not probes:
        if args.probe:
            print(f"cos regress: no probe matched {args.probe!r} in {probes_dir}")
        else:
            print(f"cos regress: no probes found in {probes_dir}")
        return 1

    results = []
    for probe in probes:
        result = run_probe(probe)
        results.append(result)
        if not args.quiet:
            tag = "[ OK ]" if result["passed"] else "[FAIL]"
            extra = " (TIMEOUT)" if result["timed_out"] else ""
            print(f"{tag} {result['probe']}{extra}  "
                  f"exit={result['exit_code']}  {result['duration_sec']}s")
        if not result["passed"]:
            # Echo the tail of the probe's own output for diagnosability.
            combined = (result["stdout"].rstrip() + "\n" + result["stderr"].rstrip()).strip()
            for line in combined.splitlines()[-OUTPUT_TAIL_LINES:]:
                print(f"        {line}")

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    print()
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def register(subparsers):
    p = subparsers.add_parser(
        "regress",
        help="Run the probe suite (probes/*.py); exit 0 only if all pass.",
    )
    p.add_argument(
        "--probes-dir", dest="probes_dir", default=None,
        help=f"directory of probe_*.py files (default: {DEFAULT_PROBES_DIR})",
    )
    p.add_argument(
        "--probe", default=None,
        help="run a single probe by stem or filename, e.g. 'probe_loader'",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="suppress per-probe OK lines (failures + summary still print)",
    )
    p.set_defaults(func=run)
