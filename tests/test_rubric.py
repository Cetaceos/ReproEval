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


def test_empty_score_summary_sections_are_derived_from_normalized_dimensions() -> None:
    result = ReliabilityScoreResult.model_validate(
        {
            "run_id": "score_test",
            "overall_score": 50,
            "reliability_band": "weak",
            "conclusion_confidence": 0.6,
            "summary": "Mixed evidence.",
            "dimensions": [
                {
                    "name": "reproduction_result_agreement",
                    "score": 80,
                    "rationale": "The registered artifact matched.",
                },
                {
                    "name": "experiment_setup_transparency",
                    "score": 40,
                    "rationale": "Environment details are incomplete.",
                    "evidence_gaps": ["operating system version"],
                },
            ],
            "reproduction_verdict": "One artifact matched.",
            "experimental_rigor_verdict": "Incomplete.",
        }
    )

    normalize_score(result, has_reproduction=True)

    assert result.major_strengths == ["reproduction_result_agreement (80/100): The registered artifact matched."]
    assert result.major_risks[0] == ("experiment_setup_transparency (40/100): Environment details are incomplete.")
    assert result.recommended_checks[0] == (
        "Resolve experiment_setup_transparency evidence gap: operating system version"
    )
    assert any(warning.code == "SCORE_SUMMARY_SECTIONS_DERIVED" for warning in result.warnings)


def test_model_supplied_score_summary_sections_are_preserved() -> None:
    result = ReliabilityScoreResult.model_validate(
        {
            "run_id": "score_test",
            "overall_score": 80,
            "reliability_band": "strong",
            "conclusion_confidence": 0.8,
            "summary": "Strong evidence.",
            "dimensions": [
                {
                    "name": "reproduction_result_agreement",
                    "score": 80,
                    "rationale": "The artifact matched.",
                }
            ],
            "reproduction_verdict": "Matched.",
            "experimental_rigor_verdict": "Partially assessed.",
            "major_strengths": ["Model strength."],
            "major_risks": ["Model risk."],
            "recommended_checks": ["Model check."],
        }
    )

    normalize_score(result, has_reproduction=True)

    assert result.major_strengths == ["Model strength."]
    assert result.major_risks == ["Model risk."]
    assert result.recommended_checks == ["Model check."]
    assert all(warning.code != "SCORE_SUMMARY_SECTIONS_DERIVED" for warning in result.warnings)


def test_chinese_score_fallbacks_use_readable_dimension_names() -> None:
    result = ReliabilityScoreResult.model_validate(
        {
            "run_id": "score_zh",
            "overall_score": 90,
            "reliability_band": "strong",
            "conclusion_confidence": 0.8,
            "summary": "现有证据有限。",
            "dimensions": [
                {
                    "name": "reproduction_result_agreement",
                    "score": 40,
                    "rationale": "当前复现证据有限。",
                    "evidence_gaps": ["独立重复实验"],
                }
            ],
            "reproduction_verdict": "证据不足。",
            "experimental_rigor_verdict": "证据不足。",
        }
    )

    normalize_score(result, has_reproduction=False, output_language="zh-CN")

    assert result.major_strengths == ["已评估维度均未达到 70/100 的优势阈值。"]
    assert result.major_risks[0].startswith("证据不足 复现结果一致性")
    assert result.recommended_checks[0].startswith("补充复现结果一致性的证据缺口")
    missing = next(warning for warning in result.warnings if warning.code == "RUBRIC_DIMENSION_MISSING")
    assert "实验设置透明度" in missing.message
    assert "experiment_setup_transparency" not in missing.message
