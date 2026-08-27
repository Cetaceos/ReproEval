from __future__ import annotations

from hashlib import sha256

import pytest

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.errors import ArtifactLineageError, PathPolicyError
from hy3_reproscope_mcp.models import RenderReportResult, RunManifest, RunStatus
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import render_report
from hy3_reproscope_mcp.workspace import Workspace, parent_artifact_reference


def _settings(tmp_path) -> Settings:
    return Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(tmp_path),
        REPROSCOPE_WORKSPACE=tmp_path / "artifacts",
    )


def _citation(source_id: str, locator: str = "L1") -> dict[str, str]:
    return {
        "source_id": source_id,
        "support": "mentions",
        "locator": locator,
        "rationale": "Grounded in the supplied evidence.",
    }


def _source(source_id: str, content_hash: str) -> dict[str, str]:
    is_paper = source_id.startswith("paper_")
    return {
        "source_id": source_id,
        "source_path": "paper.md" if is_paper else "results.csv",
        "source_type": "markdown" if is_paper else "csv",
        "content_hash": content_hash,
    }


def test_render_report_reads_validated_artifacts_and_writes_markdown(tmp_path) -> None:
    settings = _settings(tmp_path)
    workspace = Workspace(settings)
    claims_artifact = workspace.write_json_artifact(
        "claims_test",
        "extract_claims.json",
        {
            "run_id": "claims_test",
            "sources": [_source("paper_1", "a" * 64)],
            "summary": "The paper reports one main result.",
            "core_claims": [
                {
                    "claim_id": "claim_1",
                    "claim_type": "main_result",
                    "statement": "Accuracy reaches 0.91 on Dataset-A.",
                    "reported_value": "0.91",
                    "citations": [_citation("paper_1")],
                    "reproducibility_impact": "Primary result.",
                }
            ],
            "experiment_settings": [
                {
                    "name": "training budget",
                    "value": "100 epochs",
                    "disclosed": True,
                    "citations": [_citation("paper_1")],
                }
            ],
            "evidence_quality_notes": ["Per-seed scores are not reported."],
            "missing_details": [
                {
                    "item": "package versions",
                    "impact": "The software environment cannot be reconstructed exactly.",
                    "severity": "material",
                    "citations": [_citation("paper_1")],
                }
            ],
        },
    )
    comparison_artifact = workspace.write_json_artifact(
        "compare_test",
        "compare_results.json",
        {
            "run_id": "compare_test",
            "claims_run_id": "claims_test",
            "parent_artifacts": [parent_artifact_reference("claims", claims_artifact).model_dump(mode="json")],
            "sources": [_source("paper_1", "a" * 64), _source("repro_1", "b" * 64)],
            "summary": "The reproduced mean is lower.",
            "metric_comparisons": [
                {
                    "metric": "accuracy",
                    "paper_value": 0.91,
                    "reproduced_value": 0.876,
                    "reproduced_stddev": 0.01,
                    "sample_count": 5,
                    "absolute_delta": -0.034,
                    "relative_delta_percent": -3.7363,
                    "computation_status": "computed",
                    "severity": "material",
                    "conclusion": "The central result is only partially reproduced.",
                    "citations": [_citation("paper_1"), _citation("repro_1", "L1-L20")],
                }
            ],
            "supported_claim_ids": ["claim_1"],
            "claim_relation_diagnostics": {
                "total_claim_count": 1,
                "assessed_claim_count": 1,
                "fully_supported_count": 1,
                "partially_supported_count": 0,
                "contradicted_count": 0,
                "unassessed_claim_count": 0,
                "claim_relation_coverage": 1.0,
                "unassessed_claim_ids": [],
            },
            "conclusion_stability": "The conclusion is weakened.",
            "unresolved_questions": ["Would the gap persist across all five seeds?"],
        },
    )
    score_artifact = workspace.write_json_artifact(
        "score_test",
        "reliability_score.json",
        {
            "run_id": "score_test",
            "parent_artifacts": [
                parent_artifact_reference("claims", claims_artifact).model_dump(mode="json"),
                parent_artifact_reference("comparison", comparison_artifact).model_dump(mode="json"),
            ],
            "sources": [_source("paper_1", "a" * 64), _source("repro_1", "b" * 64)],
            "overall_score": 68,
            "reliability_band": "moderate",
            "conclusion_confidence": 0.75,
            "assessment_scope": "paper_and_reproduction",
            "evidence_coverage": 0.8,
            "rubric_coverage": 1,
            "summary": "The paper is moderately reliable but incompletely reproducible.",
            "dimensions": [
                {
                    "name": "reproduction_result_agreement",
                    "score": 65,
                    "weight": 0.3,
                    "rationale": "The reproduced mean is lower than reported.",
                    "citations": [_citation("repro_1", "L1-L20")],
                }
            ],
            "reproduction_verdict": "Partially reproduced.",
            "experimental_rigor_verdict": "Important setup details are missing.",
            "major_strengths": ["Core metric is clearly stated."],
            "major_risks": ["Package versions are missing."],
            "recommended_checks": ["Repeat all reported seeds."],
        },
    )

    result = render_report(
        AppContext(settings=settings),
        claims_artifact_path=claims_artifact.relative_path,
        comparison_artifact_path=comparison_artifact.relative_path,
        score_artifact_path=score_artifact.relative_path,
        title="Dataset-A reliability audit",
    )

    report_path = settings.reproscope_workspace / result.report_path
    report = report_path.read_text(encoding="utf-8")
    manifest_payload, manifest_artifact = workspace.read_json_artifact_with_reference(result.manifest_path)
    manifest = RenderReportResult.model_validate(manifest_payload)
    run_manifest = RunManifest.model_validate(workspace.read_json_artifact(result.artifacts[-1].relative_path))
    assert result.run_id.startswith("report_")
    assert result.source_run_ids == ["claims_test", "compare_test", "score_test"]
    assert result.manifest_path == f"{result.run_id}/report_manifest.json"
    assert result.artifact_integrity is not None
    assert result.artifact_integrity.payload_hash == manifest_artifact.payload_hash
    assert [artifact.role for artifact in result.artifact_inventory] == ["claims", "comparison", "score"]
    assert len(result.artifacts) == 3
    assert result.artifacts[-1].relative_path == f"{result.run_id}/run_manifest.json"
    assert run_manifest.status is RunStatus.COMPLETED
    assert run_manifest.artifacts == result.artifacts[:-1]
    assert len(manifest.artifacts) == 1
    assert manifest.artifacts[0].relative_path == result.report_path
    assert manifest.artifacts[0].content_hash == sha256(report_path.read_bytes()).hexdigest()
    assert all(artifact.relative_path != result.manifest_path for artifact in manifest.artifacts)
    assert "# Dataset-A reliability audit" in report
    assert "-3.736%" in report
    assert "[paper_1@L1]" in report
    assert "100 epochs" in report
    assert "Would the gap persist across all five seeds?" in report
    assert "## Source inventory" in report
    assert "`" + "b" * 64 + "`" in report
    assert "Metric aggregates and the final weighted score are calculated deterministically" in report
    assert "### Upstream artifact inventory" in report
    assert claims_artifact.relative_path in report
    assert f"`{claims_artifact.content_hash}`" in report
    assert f"`{claims_artifact.payload_hash}`" in report
    assert "### Direct parent lineage" in report
    assert comparison_artifact.relative_path in report
    assert "### Claim relationship coverage" in report
    assert "| 1 | 1 | 0 | 0 | 0 | 100% |" in report
    assert "does not modify the reliability score" in report


def test_render_report_rejects_mismatched_source_lineage(tmp_path) -> None:
    settings = _settings(tmp_path)
    workspace = Workspace(settings)
    claims = workspace.write_json_artifact(
        "claims_test",
        "extract_claims.json",
        {
            "run_id": "claims_test",
            "summary": "Claims.",
            "sources": [_source("paper_1", "a" * 64)],
        },
    )
    comparison = workspace.write_json_artifact(
        "compare_test",
        "compare_results.json",
        {
            "run_id": "compare_test",
            "summary": "Comparison.",
            "conclusion_stability": "Unclear.",
            "sources": [_source("paper_1", "c" * 64), _source("repro_1", "b" * 64)],
        },
    )
    score = workspace.write_json_artifact(
        "score_test",
        "reliability_score.json",
        {
            "run_id": "score_test",
            "overall_score": None,
            "reliability_band": "insufficient",
            "conclusion_confidence": 0.2,
            "summary": "Insufficient.",
            "dimensions": [
                {
                    "name": "reproduction_result_agreement",
                    "score": None,
                    "assessment_status": "insufficient_evidence",
                    "rationale": "Insufficient.",
                }
            ],
            "reproduction_verdict": "Insufficient.",
            "experimental_rigor_verdict": "Insufficient.",
            "sources": [_source("paper_1", "a" * 64), _source("repro_1", "b" * 64)],
        },
    )

    with pytest.raises(ArtifactLineageError, match="does not match"):
        render_report(
            AppContext(settings=settings),
            claims_artifact_path=claims.relative_path,
            comparison_artifact_path=comparison.relative_path,
            score_artifact_path=score.relative_path,
            title="Mismatched audit",
        )

    run_manifests = list(settings.reproscope_workspace.glob("report_*/run_manifest.json"))
    assert len(run_manifests) == 1
    failed_manifest = RunManifest.model_validate(workspace.read_json_artifact(str(run_manifests[0])))
    assert failed_manifest.status is RunStatus.FAILED
    assert failed_manifest.error_code == "ARTIFACT_LINEAGE_ERROR"


def test_render_report_rejects_same_source_from_different_claim_run(tmp_path) -> None:
    settings = _settings(tmp_path)
    workspace = Workspace(settings)
    source = _source("paper_1", "a" * 64)
    reproduction_source = _source("repro_1", "b" * 64)
    claims_a = workspace.write_json_artifact(
        "claims_a",
        "extract_claims.json",
        {"run_id": "claims_a", "summary": "Claims A.", "sources": [source]},
    )
    claims_b = workspace.write_json_artifact(
        "claims_b",
        "extract_claims.json",
        {"run_id": "claims_b", "summary": "Claims B.", "sources": [source]},
    )
    comparison = workspace.write_json_artifact(
        "compare_test",
        "compare_results.json",
        {
            "run_id": "compare_test",
            "summary": "Comparison.",
            "conclusion_stability": "Unclear.",
            "sources": [source, reproduction_source],
            "parent_artifacts": [parent_artifact_reference("claims", claims_a).model_dump(mode="json")],
        },
    )
    score = workspace.write_json_artifact(
        "score_test",
        "reliability_score.json",
        {
            "run_id": "score_test",
            "overall_score": None,
            "reliability_band": "insufficient",
            "conclusion_confidence": 0.2,
            "summary": "Insufficient.",
            "dimensions": [
                {
                    "name": "reproduction_result_agreement",
                    "score": None,
                    "assessment_status": "insufficient_evidence",
                    "rationale": "Insufficient.",
                }
            ],
            "reproduction_verdict": "Insufficient.",
            "experimental_rigor_verdict": "Insufficient.",
            "sources": [source, reproduction_source],
            "parent_artifacts": [
                parent_artifact_reference("claims", claims_a).model_dump(mode="json"),
                parent_artifact_reference("comparison", comparison).model_dump(mode="json"),
            ],
        },
    )

    with pytest.raises(ArtifactLineageError, match="exact supplied claims artifact"):
        render_report(
            AppContext(settings=settings),
            claims_artifact_path=claims_b.relative_path,
            comparison_artifact_path=comparison.relative_path,
            score_artifact_path=score.relative_path,
            title="Mixed-run audit",
        )


def test_workspace_rejects_report_input_outside_artifact_root(tmp_path) -> None:
    settings = _settings(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(PathPolicyError, match="outside REPROSCOPE_WORKSPACE"):
        Workspace(settings).read_json_artifact(str(outside))
