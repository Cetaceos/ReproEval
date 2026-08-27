"""Verify the installed ReproScope entrypoints over a real MCP stdio session."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {
    "reproscope_assess_transfer",
    "reproscope_audit_repository",
    "reproscope_build_evidence_graph",
    "reproscope_build_transfer_graph",
    "reproscope_compare_results",
    "reproscope_extract_claims",
    "reproscope_extract_solution_profile",
    "reproscope_render_report",
    "reproscope_render_transfer_report",
    "reproscope_score_paper",
}


def _entrypoint(use_console_script: bool) -> tuple[str, list[str], str]:
    if not use_console_script:
        return sys.executable, ["-m", "hy3_reproscope_mcp"], "module"

    executable = Path(sys.executable).parent / ("hy3-reproeval-mcp.exe" if os.name == "nt" else "hy3-reproeval-mcp")
    if not executable.is_file():
        raise RuntimeError(f"Console script was not installed: {executable.name}")
    return str(executable), [], "console_script"


async def _run(use_console_script: bool) -> dict[str, object]:
    command, args, entrypoint = _entrypoint(use_console_script)
    environment = os.environ.copy()
    environment.pop("HY3_API_KEY", None)
    parameters = StdioServerParameters(command=command, args=args, env=environment)

    async with (
        stdio_client(parameters) as (read_stream, write_stream),
        ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=timedelta(seconds=15),
        ) as session,
    ):
        await session.initialize()
        result = await session.list_tools()

    tools = {tool.name for tool in result.tools}
    if tools != EXPECTED_TOOLS:
        raise RuntimeError(f"Unexpected tool surface: {sorted(tools)}")
    return {
        "status": "passed",
        "entrypoint": entrypoint,
        "tool_count": len(tools),
        "tools": sorted(tools),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--console-script",
        action="store_true",
        help="Start the installed console script instead of the Python module.",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args.console_script)), indent=2))


if __name__ == "__main__":
    main()
