from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.models import ExtractClaimsResult
from hy3_reproscope_mcp.workspace import RunManifestWriter, Workspace
from scripts import run_live_isac_validation, run_live_transfer_validation, run_live_validation


def test_live_transfer_and_isac_validators_are_explicitly_opt_in() -> None:
    assert run_live_transfer_validation.LIVE_OPT_IN == "REPROSCOPE_RUN_LIVE"
    assert run_live_isac_validation.LIVE_OPT_IN == "REPROSCOPE_RUN_LIVE"


def test_live_validator_artifact_summaries_keep_hash_fields() -> None:
    artifact = SimpleNamespace(
        artifact_type="json",
        relative_path="run/result.json",
        content_hash="content",
        payload_hash="payload",
        schema_version="1.21",
    )

    assert run_live_transfer_validation._artifact_summary([artifact]) == [
        {
            "artifact_type": "json",
            "relative_path": "run/result.json",
            "content_hash": "content",
            "payload_hash": "payload",
            "schema_version": "1.21",
        }
    ]
    assert run_live_isac_validation._artifact_summary([artifact])[0]["payload_hash"] == "payload"


def test_isac_live_summary_uses_activation_source_and_manifest(tmp_path) -> None:
    settings = Settings(REPROSCOPE_WORKSPACE=tmp_path / "artifacts")
    workspace = Workspace(settings)
    result = ExtractClaimsResult(
        run_id="claims_isac_test",
        summary="Synthetic ISAC claim extraction.",
        domain_profile_activation={
            "requested_profile": "auto",
            "detected_profile": "isac_phy",
            "effective_profile": "isac_phy",
            "profile_version": "0.15.0",
            "confidence": 0.9,
            "activation_source": "auto_detection",
            "matched_signals": ["joint communication and sensing"],
        },
    )
    lifecycle = RunManifestWriter(
        workspace,
        run_id=result.run_id,
        tool_name="reproscope_extract_claims",
    )
    lifecycle.mark_running()
    result.artifacts.append(
        workspace.write_json_artifact(
            result.run_id,
            "extract_claims.json",
            result.model_dump(mode="json", exclude={"artifacts"}),
        )
    )
    lifecycle.mark_completed(result)

    summary = run_live_isac_validation._summary(workspace, result, case="auto_isac_positive")

    assert summary["activation_reason"] == "auto_detection; matched_signals=joint communication and sensing"
    assert summary["run_manifest"]["status"] == "completed"


def test_public_isac_candidate_manifest_is_not_expert_ground_truth() -> None:
    path = Path(__file__).resolve().parents[1] / "evals" / "isac_public_candidate_cases.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["annotation_status"] == "public_candidate_review_pending_expert_adjudication"
    assert payload["benchmark_status"] == "not_eligible_without_two_expert_adjudication"
    assert payload["review_protocol"]["split_frozen"] is False
    assert len(payload["cases"]) == 5
    assert all(case["requires_expert_review"] is True for case in payload["cases"])
    assert all(case["benchmark_eligible"] is False for case in payload["cases"])
    assert {case["expected_isac"] for case in payload["cases"]} == {True, False}


def test_sanitized_live_validation_index_is_current_and_credential_free() -> None:
    path = Path(__file__).resolve().parents[1] / "docs" / "LIVE_VALIDATION_0_15_INDEX.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["package_version"] == "0.15.0"
    assert payload["schema_version"] == "1.21"
    assert payload["latest_code_candidate_wheel_sha256"] == (
        "76A3F8C05D40031F81E97FB3538E8B595F7B6BD86CA9B1C3CC6657F3083A32F3"
    )
    assert payload["live_run_wheel_sha256"] == ("3C940B9CED5D95EACCABC563DCB459B462CE35B597AE8FDB20B2EC673976F950")
    assert payload["live_run_wheel_sha256"] != payload["latest_code_candidate_wheel_sha256"]
    assert payload["latest_candidate_online_revalidated"] is False
    assert payload["latest_candidate_online_attempted_on"] is None
    assert payload["latest_candidate_online_request_reached_service"] is False
    assert payload["latest_candidate_online_failure_stage"] == "not_run"
    assert payload["latest_candidate_online_completed_workflows"] == []
    assert payload["latest_candidate_online_unstarted_workflows"] == [
        "paper",
        "transfer",
        "isac",
    ]
    assert "pending" in payload["latest_candidate_online_blocker"].lower()
    assert payload["live_summary_sha256"] == ("0FE83471A9B613F807193E275EA3A6B85C0F4159C0198F1521AB0C8EE80E619A")
    assert payload["unique_run_count"] == 13
    assert payload["artifact_count"] == 28
    assert payload["artifact_hash_verification"]["all_run_manifests_completed"] is True
    assert payload["paper"]["runs"][0]["run_id"] == "claims_c6789d403a3c"
    assert payload["transfer"]["runs"][3]["run_id"] == "transfer_graph_0ee7b9cf3ac8"
    assert payload["historical_validation"]["retry_history"][0]["failed_run_status"] == ("failed")
    assert payload["transfer"]["deterministic_metrics"]["graph_validated"] is True
    assert payload["isac"]["assertions"]["all_manifests_completed"] is True
    assert payload["isac"]["assertions"]["auto_negative_effective_profile"] == "generic"
    assert payload["historical_validation"]["retry_history"][-1]["failed_run_id"] == "claims_05dfe2ec2b6c"
    serialized = path.read_text(encoding="utf-8").lower()
    assert "hy3_api_key" not in serialized
    assert "bearer " not in serialized


def test_tool_summary_reads_json_typed_run_manifest_by_path(tmp_path) -> None:
    settings = Settings(REPROSCOPE_WORKSPACE=tmp_path / "artifacts")
    workspace = Workspace(settings)
    result = ExtractClaimsResult(
        run_id="claims_test",
        summary="Synthetic claim extraction.",
    )
    lifecycle = RunManifestWriter(
        workspace,
        run_id=result.run_id,
        tool_name="reproscope_extract_claims",
    )
    lifecycle.mark_running()
    result.artifacts.append(
        workspace.write_json_artifact(
            result.run_id,
            "extract_claims.json",
            result.model_dump(mode="json", exclude={"artifacts"}),
        )
    )
    manifest_reference = lifecycle.mark_completed(result)
    assert manifest_reference.artifact_type == "json"

    summary = run_live_validation._tool_summary(workspace, result)

    assert summary["run_manifest"]["status"] == "completed"
    assert summary["run_manifest"]["status_history"] == ["created", "running", "completed"]
    assert summary["run_manifest"]["relative_path"].endswith("/run_manifest.json")
    assert len(summary["artifacts"]) == 2


@pytest.mark.asyncio
async def test_live_validation_rejects_version_mismatch_before_api_call(monkeypatch) -> None:
    monkeypatch.setenv(run_live_validation.LIVE_OPT_IN, "1")
    monkeypatch.setattr(run_live_validation, "version", lambda _: "0.4.0")

    with pytest.raises(RuntimeError, match="Source and installed distribution versions differ"):
        await run_live_validation._run()
