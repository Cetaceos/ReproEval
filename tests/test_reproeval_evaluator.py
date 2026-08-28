from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.evaluator import evaluate_case_file
from hy3_reproeval.models import (
    DimensionId,
    DimensionStatus,
    ErrorCode,
    EvaluationMode,
    EvaluationResult,
    EvaluationStatus,
    QualityBand,
)


def _base_report() -> str:
    return """# Reproduction Review

## Executive summary

The reproduced Accuracy is 0.876 [paper@L3-L4] [results@rows:1-5].

## Evidence and limitations

There is insufficient evidence to attribute the difference to one component.

## Next steps

Run the registered ablation and report confidence intervals.
"""


def _base_manifest() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "case_id": "case-1",
        "scenario": "reproduction",
        "report_path": "report.md",
        "sources": [
            {"source_id": "paper", "locators": ["L3-L4"]},
            {"source_id": "results", "locators": ["rows:1-5"]},
        ],
        "claims": [
            {
                "claim_id": "accuracy",
                "marker": "reproduced Accuracy",
                "required_source_ids": ["paper", "results"],
            }
        ],
        "numeric_expectations": [
            {
                "fact_id": "accuracy",
                "label": "Accuracy is",
                "expected": "0.876",
                "absolute_tolerance": "0.0001",
                "critical": True,
            }
        ],
        "required_sections": [
            {"section_id": "summary", "heading": "Executive summary"},
            {"section_id": "limitations", "heading": "Evidence and limitations"},
            {"section_id": "next", "heading": "Next steps"},
        ],
        "uncertainty": {
            "required": True,
            "accepted_phrases": ["insufficient evidence"],
        },
        "artifacts": [],
    }


def _write_case(tmp_path: Path, report: str, manifest: dict[str, object] | None = None) -> Path:
    (tmp_path / "report.md").write_text(report, encoding="utf-8")
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(manifest or _base_manifest()), encoding="utf-8")
    return case_path


def _dimension(result: EvaluationResult, dimension: DimensionId):
    return next(item for item in result.dimensions if item.dimension is dimension)


def test_deterministic_evaluation_scores_registered_checks_and_marks_semantic_gaps(tmp_path: Path) -> None:
    result = evaluate_case_file(_write_case(tmp_path, _base_report()))

    assert result.status is EvaluationStatus.PARTIAL
    assert result.evaluation_mode is EvaluationMode.DETERMINISTIC_ONLY
    assert result.provisional is True
    assert result.assessed_weight == pytest.approx(0.75)
    assert result.overall_score == 100
    assert result.quality_band is QualityBand.EXCELLENT
    assert len(result.case_manifest_sha256) == 64
    assert len(result.rubric_sha256) == 64
    assert _dimension(result, DimensionId.REASONING_CONSISTENCY).status is DimensionStatus.INSUFFICIENT_EVIDENCE
    assert _dimension(result, DimensionId.CLARITY_ACTIONABILITY).status is DimensionStatus.INSUFFICIENT_EVIDENCE


def test_fabricated_citation_forces_traceability_failure_and_hard_cap(tmp_path: Path) -> None:
    report = _base_report().replace("[paper@L3-L4]", "[fabricated@L1-L2]")

    result = evaluate_case_file(_write_case(tmp_path, report))

    assert result.applied_hard_cap == 40
    assert result.overall_score == 40
    assert _dimension(result, DimensionId.EVIDENCE_TRACEABILITY).score == 0
    assert ErrorCode.FABRICATED_CITATION in {
        finding.error_code for finding in result.findings if finding.error_code is not None
    }


def test_critical_numeric_error_forces_numeric_dimension_failure_and_cap(tmp_path: Path) -> None:
    report = _base_report().replace("Accuracy is 0.876", "Accuracy is 0.500")

    result = evaluate_case_file(_write_case(tmp_path, report))

    assert result.applied_hard_cap == 50
    assert result.overall_score == 50
    assert _dimension(result, DimensionId.NUMERICAL_CONSISTENCY).score == 0


def test_artifact_hash_mismatch_is_a_lineage_error(tmp_path: Path) -> None:
    artifact = tmp_path / "score.json"
    artifact.write_text('{"score": 90}', encoding="utf-8")
    manifest = _base_manifest()
    manifest["artifacts"] = [
        {
            "artifact_id": "score",
            "path": "score.json",
            "sha256": hashlib.sha256(b"different").hexdigest(),
        }
    ]

    result = evaluate_case_file(_write_case(tmp_path, _base_report(), manifest))

    assert result.applied_hard_cap == 40
    assert ErrorCode.ARTIFACT_LINEAGE_ERROR in {
        finding.error_code for finding in result.findings if finding.error_code is not None
    }


def test_missing_registered_artifact_is_a_lineage_error(tmp_path: Path) -> None:
    manifest = _base_manifest()
    manifest["artifacts"] = [
        {
            "artifact_id": "missing-score",
            "path": "missing.json",
            "sha256": hashlib.sha256(b"missing").hexdigest(),
        }
    ]

    result = evaluate_case_file(_write_case(tmp_path, _base_report(), manifest))

    assert result.applied_hard_cap == 40
    assert any(
        finding.error_code is ErrorCode.ARTIFACT_LINEAGE_ERROR and "missing" in finding.message
        for finding in result.findings
    )


def test_low_coverage_abstains_from_overall_score(tmp_path: Path) -> None:
    manifest = {
        "schema_version": "1.0",
        "case_id": "low-coverage",
        "scenario": "generic",
        "report_path": "report.md",
        "required_sections": [{"section_id": "summary", "heading": "Summary"}],
    }

    result = evaluate_case_file(_write_case(tmp_path, "# Report\n\n## Summary\n\nText.\n", manifest))

    assert result.status is EvaluationStatus.INSUFFICIENT
    assert result.assessed_weight == pytest.approx(0.10)
    assert result.overall_score is None
    assert result.quality_band is QualityBand.INSUFFICIENT


def test_report_path_cannot_escape_manifest_directory(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("outside", encoding="utf-8")
    manifest = _base_manifest()
    manifest["report_path"] = f"../{outside.name}"
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="escapes the manifest directory"):
        evaluate_case_file(case_path)


def test_missing_uncertainty_disclosure_is_classified_as_overconfidence(tmp_path: Path) -> None:
    report = _base_report().replace(
        "There is insufficient evidence to attribute the difference to one component.",
        "The difference is certainly caused by one component.",
    )

    result = evaluate_case_file(_write_case(tmp_path, report))

    assert result.applied_hard_cap == 60
    assert _dimension(result, DimensionId.UNCERTAINTY_HANDLING).score == 0
    assert ErrorCode.OVERCONFIDENCE in {
        finding.error_code for finding in result.findings if finding.error_code is not None
    }
