from __future__ import annotations

import pytest
from pydantic import ValidationError

from hy3_reproscope_mcp.models import (
    ClaimRelationDiagnostics,
    EvidenceItem,
    EvidenceKind,
    MetricComparison,
    MetricDataQuality,
    ReliabilityScoreResult,
    SourceReference,
    SourceType,
)


def test_source_reference_requires_sha256_and_one_based_locations() -> None:
    reference = SourceReference(
        source_id="paper-1",
        source_path="paper.md",
        source_type=SourceType.MARKDOWN,
        content_hash="a" * 64,
        line_start=1,
        line_end=2,
        excerpt="Evidence text",
    )

    evidence = EvidenceItem(
        statement="The paper reports the metric.",
        kind=EvidenceKind.OBSERVED,
        source_references=[reference],
    )

    assert evidence.source_references[0].content_hash == "a" * 64

    derived = EvidenceItem(
        statement="Python recalculated the aggregate.",
        kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
        source_references=[reference],
    )
    assert derived.kind.value == "deterministically_derived"


def test_source_reference_rejects_invalid_hash() -> None:
    with pytest.raises(ValidationError):
        SourceReference(
            source_id="paper-1",
            source_path="paper.md",
            source_type=SourceType.MARKDOWN,
            content_hash="not-a-sha256",
        )


def test_reliability_score_rejects_out_of_range_dimension() -> None:
    with pytest.raises(ValidationError):
        ReliabilityScoreResult.model_validate(
            {
                "run_id": "score_test",
                "overall_score": 90,
                "reliability_band": "strong",
                "conclusion_confidence": 0.8,
                "summary": "Summary",
                "dimensions": [
                    {
                        "name": "baseline_fairness",
                        "score": 101,
                        "weight": 1,
                        "rationale": "Out of range",
                    }
                ],
                "reproduction_verdict": "Supported",
                "experimental_rigor_verdict": "Strong",
            }
        )


def test_reliability_dimension_can_be_explicitly_unassessed() -> None:
    result = ReliabilityScoreResult.model_validate(
        {
            "run_id": "score_test",
            "overall_score": None,
            "reliability_band": "insufficient",
            "conclusion_confidence": 0.2,
            "summary": "The evidence is insufficient.",
            "dimensions": [
                {
                    "name": "reproduction_result_agreement",
                    "score": None,
                    "assessment_status": "insufficient_evidence",
                    "rationale": "No independent reproduction was supplied.",
                }
            ],
            "reproduction_verdict": "Not assessed.",
            "experimental_rigor_verdict": "Not assessed.",
        }
    )

    assert result.overall_score is None
    assert result.dimensions[0].score is None
    assert result.dimensions[0].assessment_status.value == "insufficient_evidence"


def test_strict_models_reject_non_finite_values() -> None:
    with pytest.raises(ValidationError):
        MetricComparison(
            metric="accuracy",
            paper_value=float("nan"),
            severity="unknown",
            conclusion="The value is invalid.",
        )


@pytest.mark.parametrize(
    "override",
    [
        {"total_count": 5},
        {"valid_ratio": 0.4},
    ],
)
def test_metric_data_quality_rejects_inconsistent_partition(override) -> None:
    payload = {
        "total_count": 4,
        "valid_numeric_count": 2,
        "missing_count": 1,
        "non_numeric_count": 1,
        "non_finite_count": 0,
        "valid_ratio": 0.5,
        **override,
    }

    with pytest.raises(ValidationError):
        MetricDataQuality.model_validate(payload)


def test_claim_relation_diagnostics_accepts_consistent_partition() -> None:
    diagnostics = ClaimRelationDiagnostics(
        total_claim_count=4,
        assessed_claim_count=3,
        fully_supported_count=1,
        partially_supported_count=1,
        contradicted_count=1,
        unassessed_claim_count=1,
        claim_relation_coverage=0.75,
        unassessed_claim_ids=["claim_2"],
    )

    assert diagnostics.claim_relation_coverage == pytest.approx(0.75)


@pytest.mark.parametrize(
    "override",
    [
        {"assessed_claim_count": 2},
        {"total_claim_count": 5},
        {"unassessed_claim_count": 2},
        {"claim_relation_coverage": 0.5},
        {"unassessed_claim_ids": ["claim_2", "claim_2"], "unassessed_claim_count": 2, "total_claim_count": 5},
    ],
)
def test_claim_relation_diagnostics_rejects_inconsistent_partition(override) -> None:
    payload = {
        "total_claim_count": 4,
        "assessed_claim_count": 3,
        "fully_supported_count": 1,
        "partially_supported_count": 1,
        "contradicted_count": 1,
        "unassessed_claim_count": 1,
        "claim_relation_coverage": 0.75,
        "unassessed_claim_ids": ["claim_2"],
        **override,
    }

    with pytest.raises(ValidationError):
        ClaimRelationDiagnostics.model_validate(payload)
