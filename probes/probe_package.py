"""probe_package -- pyproject.toml matches the code it packages.

Run from the repo root:

    python probes/probe_package.py

Asserts:
  - the `cos` console script points at a callable that exists;
  - every package-data pattern matches at least one real file (the schema and
    the write contracts the engine loads at run time);
  - the version is read from cos.__version__, and `python -m cos --version`
    prints `cos <that version>`;
  - the dependency floors are jsonschema>=4 and pyyaml>=6, and
    requires-python is >=3.10.

Uses tomllib on Python 3.11+; on 3.10 it falls back to reading the few keys it
needs with regular expressions. Exits 0 on pass; nonzero with a printed FAIL
reason.
"""

from __future__ import annotations

import importlib
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cos  # noqa: E402


class ProbeFail(Exception):
    pass


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise ProbeFail(msg)


def load_pyproject() -> dict:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    try:
        import tomllib  # Python 3.11+
        return tomllib.loads(text)
    except ImportError:
        pass

    def one(pattern: str) -> str:
        m = re.search(pattern, text, re.MULTILINE)
        check(m is not None, f"pyproject.toml: no match for {pattern!r}")
        return m.group(1)

    m = re.search(r"^dependencies = \[(.*?)\]", text, re.MULTILINE | re.DOTALL)
    check(m is not None, "pyproject.toml: no dependencies list")
    deps_block = m.group(1)
    return {
        "project": {
            "requires-python": one(r'^requires-python = "([^"]+)"'),
            "dependencies": re.findall(r'"([^"]+)"', deps_block),
            "scripts": {"cos": one(r'^cos = "([^"]+)"')},
        },
        "tool": {"setuptools": {
            "dynamic": {"version": {"attr": one(r'^version = \{ attr = "([^"]+)" \}')}},
            "package-data": {
                k: re.findall(r'"([^"]+)"', v)
                for k, v in re.findall(r'^"([^"]+)" = \[(.*?)\]', text, re.MULTILINE)
            },
        }},
    }


def main() -> int:
    try:
        data = load_pyproject()
        project = data["project"]
        setuptools = data["tool"]["setuptools"]

        target = project["scripts"]["cos"]
        mod_name, _, func_name = target.partition(":")
        mod = importlib.import_module(mod_name)
        check(callable(getattr(mod, func_name, None)),
              f"console script target {target!r} is not a callable")

        pkg_data = setuptools["package-data"]
        check(pkg_data, "no package-data declared")
        for pkg, patterns in pkg_data.items():
            pkg_dir = REPO_ROOT.joinpath(*pkg.split("."))
            for pat in patterns:
                hits = list(pkg_dir.glob(pat))
                check(hits, f"package-data {pkg}:{pat} matches no file")
        declared = {(pkg, pat) for pkg, pats in pkg_data.items() for pat in pats}
        check(("cos.memory", "schema.sql") in declared, "schema.sql not packaged")
        check(("cos.braid", "contracts/*.json") in declared, "contracts not packaged")

        check(setuptools["dynamic"]["version"]["attr"] == "cos.__version__",
              f"version not read from cos.__version__: {setuptools['dynamic']}")
        proc = subprocess.run([sys.executable, "-m", "cos", "--version"],
                              cwd=str(REPO_ROOT), capture_output=True, text=True,
                              timeout=60)
        check(proc.returncode == 0, f"--version rc={proc.returncode} err={proc.stderr!r}")
        check(proc.stdout.strip() == f"cos {cos.__version__}",
              f"--version printed {proc.stdout.strip()!r}, expected 'cos {cos.__version__}'")

        deps = set(project["dependencies"])
        check({"jsonschema>=4", "pyyaml>=6"} <= deps, f"dependency floors missing: {deps}")
        check(project["requires-python"] == ">=3.10",
              f"requires-python is {project['requires-python']!r}")
    except ProbeFail as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        import traceback
        print(f"FAIL: unexpected error: {e!r}")
        traceback.print_exc()
        return 1

    print(f"PASS: probe_package  entry point, package data, version {cos.__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
