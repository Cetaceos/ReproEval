from __future__ import annotations

import json

import pytest

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.errors import ArtifactIntegrityError, ArtifactSchemaCompatibilityError
from hy3_reproscope_mcp.models import SCHEMA_VERSION, ExtractClaimsResult
from hy3_reproscope_mcp.tools import _read_result_artifact
from hy3_reproscope_mcp.workspace import Workspace, canonical_payload_hash


def _workspace(tmp_path) -> Workspace:
    return Workspace(
        Settings(
            REPROSCOPE_ALLOWED_ROOTS=str(tmp_path),
            REPROSCOPE_WORKSPACE=tmp_path / "artifacts",
        )
    )


def test_json_artifact_embeds_and_verifies_payload_hash(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    artifact = workspace.write_json_artifact(
        "claims_test",
        "extract_claims.json",
        {"run_id": "claims_test", "summary": "Original analysis."},
    )

    payload, verified_reference = workspace.read_json_artifact_with_reference(artifact.relative_path)

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["artifact_integrity"]["algorithm"] == "sha256"
    assert payload["artifact_integrity"]["payload_hash"] == canonical_payload_hash(payload)
    assert verified_reference == artifact


def test_json_artifact_rejects_modified_payload(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    artifact = workspace.write_json_artifact(
        "claims_test",
        "extract_claims.json",
        {"run_id": "claims_test", "summary": "Original analysis."},
    )
    artifact_path = workspace.resolve_artifact_path(artifact.relative_path)
    artifact_path.write_text(
        artifact_path.read_text(encoding="utf-8").replace(
            "Original analysis.",
            "Modified analysis.",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ArtifactIntegrityError, match="payload hash does not match"):
        workspace.read_json_artifact(artifact.relative_path)


def test_schema_1_6_artifact_rejects_removed_integrity_marker(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    artifact = workspace.write_json_artifact(
        "claims_test",
        "extract_claims.json",
        {"run_id": "claims_test", "summary": "Original analysis."},
    )
    artifact_path = workspace.resolve_artifact_path(artifact.relative_path)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload.pop("artifact_integrity")
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError, match="missing its integrity marker"):
        workspace.read_json_artifact(artifact.relative_path)


def test_explicit_schema_1_5_artifact_remains_readable(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    artifact_path = workspace.workspace_path / "claims_legacy" / "extract_claims.json"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text(
        json.dumps(
            {
                "run_id": "claims_legacy",
                "schema_version": "1.5",
                "summary": "Legacy analysis.",
            }
        ),
        encoding="utf-8",
    )

    payload = workspace.read_json_artifact("claims_legacy/extract_claims.json")

    assert payload["summary"] == "Legacy analysis."


@pytest.mark.parametrize("schema_version", ["1.20", None, "1.22"])
def test_business_artifact_reader_rejects_non_current_schema(tmp_path, schema_version) -> None:
    workspace = _workspace(tmp_path)
    artifact = workspace.write_json_artifact(
        "claims_compatibility",
        "extract_claims.json",
        {
            "run_id": "claims_compatibility",
            "summary": "Compatibility check.",
            "core_claims": [],
            "experiment_settings": [],
            "missing_details": [],
        },
    )
    artifact_path = workspace.resolve_artifact_path(artifact.relative_path)
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    if schema_version is None:
        payload.pop("schema_version", None)
    else:
        payload["schema_version"] = schema_version
    payload.pop("artifact_integrity", None)
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ArtifactSchemaCompatibilityError) as exc_info:
        _read_result_artifact(workspace, artifact.relative_path, ExtractClaimsResult, "claims")

    assert exc_info.value.code == "ARTIFACT_SCHEMA_INCOMPATIBLE"
    assert "Expected Schema 1.21" in exc_info.value.message


def test_business_artifact_reader_accepts_current_schema(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    artifact = workspace.write_json_artifact(
        "claims_current",
        "extract_claims.json",
        {
            "run_id": "claims_current",
            "summary": "Current schema.",
            "core_claims": [],
            "experiment_settings": [],
            "missing_details": [],
        },
    )

    result, parent = _read_result_artifact(workspace, artifact.relative_path, ExtractClaimsResult, "claims")

    assert result.schema_version == SCHEMA_VERSION
    assert parent.schema_version == SCHEMA_VERSION
