from __future__ import annotations

from hy3_reproscope_mcp.transfer_models import TransferAssessmentResult
from hy3_reproscope_mcp.transfer_rubric import normalize_transfer_assessment


def test_transfer_rubric_abstains_when_less_than_half_is_assessed() -> None:
    result = TransferAssessmentResult(
        run_id="transfer_test",
        solution_profile_run_id="solution_test",
        summary="Only source evidence reliability could be assessed.",
        target_context_summary="The target context omits dependencies and resources.",
        overall_score=92,
        feasibility_band="promising",
        conclusion_confidence=0.8,
        dimensions=[
            {
                "name": "evidence_reliability",
                "score": 92,
                "rationale": "The source solution is documented.",
            }
        ],
    )

    normalize_transfer_assessment(result)

    assert result.overall_score is None
    assert result.feasibility_band.value == "insufficient"
    assert result.conclusion_confidence == 0.5
    assert result.rubric_coverage == 0.2
    assert len(result.dimensions) == 6
    assert result.performance_prediction_provided is False
    assert result.legal_conclusion_provided is False
    warning_codes = {warning.code for warning in result.warnings}
    assert "TRANSFER_RUBRIC_PARTIAL_COVERAGE" in warning_codes
    assert "NO_TARGET_PERFORMANCE_PREDICTION" in warning_codes
    assert "LICENSE_SIGNALS_NOT_LEGAL_ADVICE" in warning_codes
