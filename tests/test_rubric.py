from __future__ import annotations

from hy3_reproscope_mcp.models import ReliabilityScoreResult
from hy3_reproscope_mcp.rubric import normalize_score


def test_low_rubric_coverage_does_not_produce_overall_score() -> None:
    result = ReliabilityScoreResult.model_validate(
        {
            "run_id": "score_test",
            "overall_score": 90,
            "reliability_band": "strong",
            "conclusion_confidence": 0.7,
            "summary": "Only baseline evidence was available.",
            "dimensions": [
                {
                    "name": "baseline_fairness",
                    "score": 90,
                    "rationale": "The baseline protocol is documented.",
                }
            ],
            "reproduction_verdict": "Not enough evidence.",
            "experimental_rigor_verdict": "Partially assessed.",
        }
    )

    normalize_score(result, has_reproduction=True)

    assert result.rubric_coverage == 0.15
    assert result.overall_score is None
    assert result.reliability_band.value == "insufficient"
    assert all(
        dimension.assessment_status.value == "insufficient_evidence"
        for dimension in result.dimensions
        if dimension.score is None
    )
    assert any(warning.code == "RUBRIC_PARTIAL_COVERAGE" for warning in result.warnings)
