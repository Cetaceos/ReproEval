"""Top-level command-line entry point for ReproEval."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hy3-reproeval",
        description="Generate and evaluate evidence-grounded research reports with Hy3.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve-mcp", help="Run the migrated ReproScope MCP server over stdio.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve-mcp":
        from hy3_reproscope_mcp.server import main as run_server

        run_server()
        return 0
    parser.print_help()
    return 0
