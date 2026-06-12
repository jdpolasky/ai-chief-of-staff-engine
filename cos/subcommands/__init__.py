"""Subcommands for the cos CLI. One module per command.

Each module must expose:
  - register(subparsers): add an argparse subparser, set its `func` to a callable
  - the callable receives the parsed Namespace and returns an int exit code or None
"""
