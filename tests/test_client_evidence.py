from __future__ import annotations

import json
from pathlib import Path

import pytest

from hy3_reproscope_mcp.client_evidence import EXPECTED_CLIENT_TOOLS, validate_client_evidence

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _payload() -> dict[str, object]:
    run_id = "run-client-1"
    return {
        "client": "visual_studio_code",
        "client_version": "1.129.1",
        "operating_system": "Windows",
        "python_version": "3.13.5",
        "tool_names": list(EXPECTED_CLIENT_TOOLS),
        "calls": [
            {
                "tool_name": "reproscope_build_transfer_graph",
                "run_id": run_id,
                "status": "completed",
                "graph_validated": True,
                "artifacts": [
                    {
                        "run_id": run_id,
                        "artifact_type": "transfer_graph",
                        "relative_path": "run-client-1/transfer_graph.json",
                        "content_hash": "a" * 64,
                        "payload_hash": "b" * 64,
                    }
                ],
            }
        ],
        "screenshot_ref": "docs/assets/vscode-0.15.0-tool-discovery.png",
        "secrets_redacted": True,
    }


def test_client_evidence_requires_canonical_ten_tool_order() -> None:
    evidence = validate_client_evidence(_payload())
    assert evidence.schema_version == "1.21"
    assert evidence.server_version == "0.15.0"


def test_checked_in_vscode_evidence_is_current_and_machine_validated() -> None:
    path = PROJECT_ROOT / "docs" / "CLIENT_VALIDATION_0_15_INDEX.json"
    evidence = validate_client_evidence(json.loads(path.read_text(encoding="utf-8")))

    assert evidence.client == "visual_studio_code"
    assert evidence.client_version == "1.131.0"
    assert evidence.calls[0].run_id == "repository_8246ee4f34e0"
    assert evidence.calls[0].tool_name == "reproscope_audit_repository"


def test_client_evidence_rejects_missing_tool() -> None:
    payload = _payload()
    payload["tool_names"] = list(EXPECTED_CLIENT_TOOLS[:-1])
    with pytest.raises(ValueError, match=r"ten 0\.15\.0"):
        validate_client_evidence(payload)


def test_client_evidence_rejects_absolute_path_and_secret_marker() -> None:
    payload = _payload()
    payload["screenshot_ref"] = "C:/Users/private/capture.png"
    with pytest.raises(ValueError, match="relative paths"):
        validate_client_evidence(payload)
    payload = _payload()
    payload["recording_ref"] = "notes/.env.capture"
    with pytest.raises(ValueError, match="secret marker"):
        validate_client_evidence(payload)


@pytest.mark.parametrize("tool_name", ["reproscope_build_evidence_graph", "reproscope_build_transfer_graph"])
def test_client_evidence_requires_explicit_graph_validation_marker(tool_name: str) -> None:
    payload = _payload()
    call = payload["calls"][0]
    call["tool_name"] = tool_name
    call.pop("graph_validated")

    with pytest.raises(ValueError, match="graph_validated=true"):
        validate_client_evidence(payload)
