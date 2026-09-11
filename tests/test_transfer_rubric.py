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


def test_chinese_transfer_fallbacks_use_readable_dimension_names() -> None:
    result = TransferAssessmentResult(
        run_id="transfer_zh",
        solution_profile_run_id="solution_zh",
        summary="现有证据有限。",
        target_context_summary="目标环境信息不完整。",
        overall_score=90,
        feasibility_band="promising",
        conclusion_confidence=0.8,
        dimensions=[
            {
                "name": "evidence_reliability",
                "score": 40,
                "rationale": "当前来源证据有限。",
            }
        ],
    )

    normalize_transfer_assessment(result, output_language="zh-CN")

    missing = next(warning for warning in result.warnings if warning.code == "TRANSFER_DIMENSION_MISSING")
    assert "前提条件兼容性" in missing.message
    assert "assumption_compatibility" not in missing.message
    assert all(
        dimension.rationale == "该固定迁移评估维度没有返回有证据支持的判断。" for dimension in result.dimensions[1:]
    )
    assert all(warning.message for warning in result.warnings)
