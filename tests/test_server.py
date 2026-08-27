from __future__ import annotations

import json
from datetime import timedelta

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import AnyUrl

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.server import SERVER_NAME, create_server
from hy3_reproscope_mcp.workspace import RunManifestWriter, Workspace


def test_create_server_does_not_require_api_key() -> None:
    server = create_server(Settings(HY3_API_KEY=None))

    assert server.name == SERVER_NAME
    assert "insufficient" in server.instructions.lower()


@pytest.mark.asyncio
async def test_mcp_initializes_and_lists_business_tools() -> None:
    server = create_server(Settings(HY3_API_KEY=None))

    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    ) as session:
        result = await session.list_tools()

    tools = {tool.name: tool for tool in result.tools}
    assert set(tools) == {
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
    assert all(tool.description for tool in result.tools)
    assert "graph_validated=true" in tools["reproscope_build_evidence_graph"].description
    assert "graph_validated=true" in tools["reproscope_build_transfer_graph"].description
    assert all("ctx" not in tool.inputSchema["properties"] for tool in result.tools)
    assert set(tools["reproscope_build_evidence_graph"].inputSchema["required"]) == {
        "claims_artifact_path",
        "comparison_artifact_path",
        "score_artifact_path",
    }
    assert "evidence_graph_artifact_path" in tools["reproscope_render_report"].inputSchema["properties"]
    assert "claims_artifact_path" in tools["reproscope_compare_results"].inputSchema["properties"]
    assert "group_filters" in tools["reproscope_compare_results"].inputSchema["properties"]
    assert "group_by" in tools["reproscope_compare_results"].inputSchema["properties"]
    assert "group_filters" in tools["reproscope_score_paper"].inputSchema["properties"]
    assert "repository_audit_artifact_path" in tools["reproscope_score_paper"].inputSchema["properties"]
    assert tools["reproscope_extract_claims"].inputSchema["properties"]["domain_profile"]["default"] == "generic"
    assert "profile_request_source" in tools["reproscope_extract_claims"].inputSchema["properties"]
    assert set(tools["reproscope_assess_transfer"].inputSchema["required"]) == {
        "solution_paths",
        "target_context_paths",
        "solution_profile_artifact_path",
    }
    assert "repository_audit_artifact_path" in tools["reproscope_assess_transfer"].inputSchema["properties"]
    assert set(tools["reproscope_render_transfer_report"].inputSchema["required"]) == {
        "solution_profile_artifact_path",
        "transfer_assessment_artifact_path",
    }
    assert set(tools["reproscope_build_transfer_graph"].inputSchema["required"]) == {
        "solution_profile_artifact_path",
        "transfer_assessment_artifact_path",
    }
    assert "transfer_graph_artifact_path" in tools["reproscope_render_transfer_report"].inputSchema["properties"]
    assert set(tools["reproscope_audit_repository"].inputSchema["required"]) == {"repository_path"}
    assert tools["reproscope_audit_repository"].inputSchema["properties"]["max_python_files"]["default"] == 200


@pytest.mark.asyncio
async def test_mcp_exposes_read_only_metadata_registry_and_run_resources(tmp_path) -> None:
    settings = Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(tmp_path),
        REPROSCOPE_WORKSPACE=tmp_path / "artifacts",
        HY3_API_KEY=None,
    )
    workspace = Workspace(settings)
    lifecycle = RunManifestWriter(workspace, run_id="claims_resource_1", tool_name="reproscope_extract_claims")
    lifecycle.mark_running()
    server = create_server(settings)

    async with create_connected_server_and_client_session(
        server,
        read_timeout_seconds=timedelta(seconds=10),
        raise_exceptions=True,
    ) as session:
        resources = await session.list_resources()
        templates = await session.list_resource_templates()
        metadata = await session.read_resource(AnyUrl("reproscope://metadata"))
        registry = await session.read_resource(AnyUrl("reproscope://isac/registry"))
        summary = await session.read_resource(AnyUrl("reproscope://run/claims_resource_1/summary"))
        manifest = await session.read_resource(AnyUrl("reproscope://run/claims_resource_1/manifest"))

    resource_uris = {str(resource.uri) for resource in resources.resources}
    template_uris = {str(template.uriTemplate) for template in templates.resourceTemplates}
    assert "reproscope://metadata" in resource_uris
    assert "reproscope://isac/registry" in resource_uris
    assert "reproscope://run/{run_id}/summary" in template_uris
    assert "reproscope://run/{run_id}/manifest" in template_uris

    metadata_payload = json.loads(metadata.contents[0].text)
    assert metadata_payload["artifact_schema"] == "1.21"
    assert metadata_payload["artifact_writes"] is True
    assert metadata_payload["code_execution"] is False
    assert metadata_payload["execution_policy"] == "local_artifact_writes_and_read_only_repository_audit"
    assert metadata_payload["third_party_execution"] == "default_deny_preflight_only"
    registry_payload = json.loads(registry.contents[0].text)
    assert registry_payload["collection_counts"]["metrics"] == 24
    summary_payload = json.loads(summary.contents[0].text)
    assert summary_payload["run_id"] == "claims_resource_1"
    assert summary_payload["status"] == "running"
    assert summary_payload["recovery_action"] == "inspect_only"
    assert summary_payload["resume_from"] == "manual_inspection"
    assert summary_payload["reusable_artifacts"] == []
    manifest_payload = json.loads(manifest.contents[0].text)
    assert manifest_payload["run_id"] == "claims_resource_1"
    assert manifest_payload["status"] == "running"
