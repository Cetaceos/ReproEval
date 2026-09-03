from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from mcp.shared.memory import create_connected_server_and_client_session

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.server import create_server


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[1] / "skills" / "reproeval-research-audit"


def test_skill_metadata_and_references_are_complete() -> None:
    skill_root = _skill_root()
    skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter_text, body = skill_text.split("---", maxsplit=2)
    frontmatter = yaml.safe_load(frontmatter_text)
    agent_metadata = yaml.safe_load((skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8"))

    assert frontmatter["name"] == "reproeval-research-audit"
    assert "reproducibility" in frontmatter["description"]
    assert "technology-transfer" in frontmatter["description"]
    assert "TODO" not in skill_text
    assert agent_metadata["interface"]["default_prompt"].startswith("Use $reproeval-research-audit")
    reference_links = set(re.findall(r"\((references/[^)]+)\)", body))
    assert reference_links == {
        "references/reproduction-review.md",
        "references/transfer-assessment.md",
    }
    assert all((skill_root / relative_path).is_file() for relative_path in reference_links)


@pytest.mark.asyncio
async def test_skill_tool_contract_matches_mcp_server() -> None:
    skill_root = _skill_root()
    documented_text = "\n".join(path.read_text(encoding="utf-8") for path in skill_root.rglob("*.md"))
    documented_tools = set(re.findall(r"`(reproscope_[a-z_]+)`", documented_text))
    server = create_server(Settings(HY3_API_KEY=None))

    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    ) as session:
        result = await session.list_tools()

    assert documented_tools == {tool.name for tool in result.tools}
