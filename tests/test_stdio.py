from __future__ import annotations

import os
import sys
from datetime import timedelta

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_module_entrypoint_initializes_over_stdio_without_key() -> None:
    environment = os.environ.copy()
    environment.pop("HY3_API_KEY", None)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "hy3_reproscope_mcp"],
        env=environment,
    )

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

    assert {tool.name for tool in result.tools} == {
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
