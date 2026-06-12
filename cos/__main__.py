"""Entry point: `python -m cos <subcommand> [args]`.

Each subcommand is a module under cos/subcommands/ exposing register(subparsers)
and a callable. The dispatcher discovers them and routes.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys

from . import subcommands as _subcmd_pkg


def discover_subcommands():
    """Yield (name, module) for every module under cos.subcommands.

    Skips modules whose name starts with underscore.
    """
    for info in pkgutil.iter_modules(_subcmd_pkg.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"cos.subcommands.{info.name}")
        yield info.name, module


def build_parser():
    parser = argparse.ArgumentParser(
        prog="cos",
        description="A portable memory engine for an AI assistant. "
                    "Subcommands live in cos.subcommands.",
    )
    sub = parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    sub.required = True
    for name, module in discover_subcommands():
        if not hasattr(module, "register"):
            continue
        module.register(sub)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    return func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
