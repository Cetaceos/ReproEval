# ruff: noqa: RUF001
"""Fixed reliability rubric used for deterministic score aggregation."""

from __future__ import annotations

from .models import (
    AssessmentScope,
    DimensionAssessmentStatus,
    ReliabilityBand,
    ReliabilityDimension,
    ReliabilityScoreResult,
    ScoreDimension,
    ToolWarning,
)

MIN_ASSESSED_WEIGHT = 0.50
MIN_STRONG_RUBRIC_COVERAGE = 0.80
DIMENSION_STRENGTH_THRESHOLD = 70
DIMENSION_RISK_THRESHOLD = 60

RUBRIC_WEIGHTS: dict[ReliabilityDimension, float] = {
    ReliabilityDimension.RESULT_AGREEMENT: 0.30,
    ReliabilityDimension.SETUP_TRANSPARENCY: 0.20,
    ReliabilityDimension.BASELINE_FAIRNESS: 0.15,
    ReliabilityDimension.ABLATION_QUALITY: 0.15,
    ReliabilityDimension.STATISTICAL_REPORTING: 0.10,
    ReliabilityDimension.DATA_IMPLEMENTATION_AVAILABILITY: 0.10,
}

RUBRIC_DESCRIPTIONS: dict[ReliabilityDimension, str] = {
    ReliabilityDimension.RESULT_AGREEMENT: (
        "How closely independent reproduction results support the paper's central empirical claims."
    ),
    ReliabilityDimension.SETUP_TRANSPARENCY: (
        "Completeness of datasets, preprocessing, splits, seeds, hyperparameters, environment, and compute details."
    ),
    ReliabilityDimension.BASELINE_FAIRNESS: (
        "Whether baselines use comparable data, tuning budgets, implementations, metrics, and evaluation protocols."
    ),
    ReliabilityDimension.ABLATION_QUALITY: (
        "Whether ablations isolate claimed contributions and include meaningful controls and sensitivity checks."
    ),
    ReliabilityDimension.STATISTICAL_REPORTING: (
        "Quality of repeated runs, uncertainty estimates, significance analysis, and variance reporting."
    ),
    ReliabilityDimension.DATA_IMPLEMENTATION_AVAILABILITY: (
        "Availability and usability of code, data, checkpoints, dependency versions, licenses, and run instructions."
    ),
}


def rubric_payload() -> list[dict[str, str | float]]:
    return [
        {
            "name": dimension.value,
            "weight": weight,
            "description": RUBRIC_DESCRIPTIONS[dimension],
        }
        for dimension, weight in RUBRIC_WEIGHTS.items()
    ]


def normalize_score(
    result: ReliabilityScoreResult,
    *,
    has_reproduction: bool,
    output_language: str = "en",
) -> None:
    """Apply fixed dimensions and weights, then calculate the aggregate locally."""

    supplied: dict[ReliabilityDimension, ScoreDimension] = {}
    duplicate_dimensions: set[ReliabilityDimension] = set()
    for dimension in result.dimensions:
        if dimension.name in supplied:
            duplicate_dimensions.add(dimension.name)
            continue
        supplied[dimension.name] = dimension

    normalized_dimensions: list[ScoreDimension] = []
    missing_dimensions: list[ReliabilityDimension] = []
    for name, weight in RUBRIC_WEIGHTS.items():
        dimension = supplied.get(name)
        if dimension is None:
            missing_dimensions.append(name)
            dimension = ScoreDimension(
                name=name,
                score=None,
                assessment_status=DimensionAssessmentStatus.INSUFFICIENT_EVIDENCE,
                rationale=_message(
                    output_language,
                    en="No evidence-grounded assessment was returned for this fixed rubric dimension.",
                    zh="该固定评估维度没有返回有证据支持的判断。",
                ),
                evidence_gaps=[_message(output_language, en="dimension assessment missing", zh="缺少该维度的评估")],
            )
        elif dimension.assessment_status is DimensionAssessmentStatus.INSUFFICIENT_EVIDENCE:
            dimension.score = None
        elif dimension.score is None:
            dimension.assessment_status = DimensionAssessmentStatus.INSUFFICIENT_EVIDENCE
        dimension.weight = weight
        normalized_dimensions.append(dimension)

    result.dimensions = normalized_dimensions
    result.assessment_scope = AssessmentScope.PAPER_AND_REPRODUCTION if has_reproduction else AssessmentScope.PAPER_ONLY
    if not has_reproduction:
        agreement = next(
            dimension for dimension in result.dimensions if dimension.name is ReliabilityDimension.RESULT_AGREEMENT
        )
        agreement.score = None
        agreement.assessment_status = DimensionAssessmentStatus.INSUFFICIENT_EVIDENCE
        agreement.rationale = _message(
            output_language,
            en="No independent reproduction evidence was supplied.",
            zh="未提供独立复现证据。",
        )
        reproduction_gap = _message(
            output_language,
            en="independent reproduction evidence",
            zh="独立复现证据",
        )
        if reproduction_gap not in agreement.evidence_gaps:
            agreement.evidence_gaps.append(reproduction_gap)
        result.conclusion_confidence = min(result.conclusion_confidence, 0.5)
        result.warnings.append(
            ToolWarning(
                code="PAPER_ONLY_ASSESSMENT",
                message=_message(
                    output_language,
                    en="The assessment cannot receive a strong rating without independent reproduction evidence.",
                    zh="缺少独立复现证据时，评估结果不能进入较强等级。",
                ),
            )
        )

    result.rubric_coverage = round(
        sum(dimension.weight for dimension in result.dimensions if dimension.score is not None),
        2,
    )
    if result.rubric_coverage >= MIN_ASSESSED_WEIGHT:
        normalized_score = round(
            sum(dimension.score * dimension.weight for dimension in result.dimensions if dimension.score is not None)
            / result.rubric_coverage,
            2,
        )
        normalized_band = reliability_band(normalized_score)
        if normalized_band is ReliabilityBand.STRONG and (
            not has_reproduction or result.rubric_coverage < MIN_STRONG_RUBRIC_COVERAGE
        ):
            normalized_band = ReliabilityBand.MODERATE
    else:
        normalized_score = None
        normalized_band = ReliabilityBand.INSUFFICIENT

    score_changed = (result.overall_score is None) != (normalized_score is None) or (
        result.overall_score is not None
        and normalized_score is not None
        and abs(result.overall_score - normalized_score) > 0.01
    )
    if score_changed or result.reliability_band is not normalized_band:
        result.warnings.append(
            ToolWarning(
                code="SCORE_NORMALIZED",
                message=_message(
                    output_language,
                    en="Overall score and band were deterministically recalculated from dimension weights.",
                    zh="总分和可靠性等级已根据固定维度权重在本地重新计算。",
                ),
            )
        )
    result.overall_score = normalized_score
    result.reliability_band = normalized_band
    result.evidence_coverage = round(
        sum(dimension.weight for dimension in result.dimensions if dimension.score is not None and dimension.citations),
        2,
    )
    if result.rubric_coverage < 1:
        result.warnings.append(
            ToolWarning(
                code="RUBRIC_PARTIAL_COVERAGE",
                message=_message(
                    output_language,
                    en=(
                        f"Only {result.rubric_coverage:.0%} of the fixed rubric had enough evidence to score; "
                        "unassessed dimensions were excluded rather than treated as zero."
                    ),
                    zh=(
                        f"固定量表中只有 {result.rubric_coverage:.0%} 的维度具有足够证据可评分；"
                        "未评估维度已排除，而不是按零分处理。"
                    ),
                ),
            )
        )
    if missing_dimensions:
        result.warnings.append(
            ToolWarning(
                code="RUBRIC_DIMENSION_MISSING",
                message=_message(
                    output_language,
                    en="Missing fixed rubric dimensions were marked as insufficient evidence: ",
                    zh="以下缺失的固定评估维度已标记为证据不足：",
                )
                + ", ".join(_dimension_label(dimension, output_language) for dimension in missing_dimensions),
            )
        )
    if duplicate_dimensions:
        result.warnings.append(
            ToolWarning(
                code="RUBRIC_DIMENSION_DUPLICATED",
                message=_message(
                    output_language,
                    en="Only the first assessment was kept for duplicated dimensions: ",
                    zh="以下重复维度仅保留第一项评估：",
                )
                + ", ".join(
                    _dimension_label(dimension, output_language) for dimension in sorted(duplicate_dimensions, key=str)
                ),
            )
        )
    _populate_empty_summary_sections(result, output_language=output_language)


def _populate_empty_summary_sections(result: ReliabilityScoreResult, *, output_language: str) -> None:
    """Derive missing narrative lists from the already-normalized rubric evidence."""

    derived_sections: list[str] = []
    if not result.major_strengths:
        result.major_strengths = [
            f"{_dimension_label(dimension.name, output_language)} ({dimension.score:.0f}/100): {dimension.rationale}"
            for dimension in result.dimensions
            if dimension.score is not None and dimension.score >= DIMENSION_STRENGTH_THRESHOLD
        ][:3]
        if not result.major_strengths:
            result.major_strengths = [
                _message(
                    output_language,
                    en=(
                        f"No assessed rubric dimension reached the "
                        f"{DIMENSION_STRENGTH_THRESHOLD}/100 strength threshold."
                    ),
                    zh=f"已评估维度均未达到 {DIMENSION_STRENGTH_THRESHOLD}/100 的优势阈值。",
                )
            ]
        derived_sections.append("major_strengths")

    if not result.major_risks:
        assessed_risks = [
            f"{_dimension_label(dimension.name, output_language)} ({dimension.score:.0f}/100): {dimension.rationale}"
            for dimension in result.dimensions
            if dimension.score is not None and dimension.score < DIMENSION_RISK_THRESHOLD
        ]
        evidence_risks = [
            f"{_message(output_language, en='Insufficient evidence for', zh='证据不足')} "
            f"{_dimension_label(dimension.name, output_language)}: "
            f"{dimension.evidence_gaps[0] if dimension.evidence_gaps else dimension.rationale}"
            for dimension in result.dimensions
            if dimension.score is None
        ]
        result.major_risks = [*assessed_risks, *evidence_risks][:3]
        if not result.major_risks:
            result.major_risks = [
                _message(
                    output_language,
                    en="No major rubric risk was identified from the supplied evidence.",
                    zh="根据现有证据，未识别到主要量表风险。",
                )
            ]
        derived_sections.append("major_risks")

    if not result.recommended_checks:
        result.recommended_checks = _recommended_checks_from_gaps(result, output_language=output_language)
        if not result.recommended_checks:
            result.recommended_checks = [
                _message(
                    output_language,
                    en="Preserve the recorded evidence and repeat the assessment on new inputs.",
                    zh="保留当前证据记录，并在获得新输入后重新评估。",
                )
            ]
        derived_sections.append("recommended_checks")

    if derived_sections:
        result.warnings.append(
            ToolWarning(
                code="SCORE_SUMMARY_SECTIONS_DERIVED",
                message=_message(
                    output_language,
                    en=(
                        "Empty narrative sections were deterministically derived from normalized rubric scores and "
                        "evidence gaps: "
                    ),
                    zh="以下空白说明部分已根据标准化量表得分和证据缺口在本地补充：",
                )
                + ", ".join(derived_sections)
                + ".",
            )
        )


def _recommended_checks_from_gaps(
    result: ReliabilityScoreResult,
    *,
    output_language: str,
) -> list[str]:
    checks: list[str] = []
    seen: set[str] = set()
    for dimension in result.dimensions:
        for gap in dimension.evidence_gaps:
            normalized = gap.strip()
            if not normalized or normalized.casefold() in seen:
                continue
            seen.add(normalized.casefold())
            if output_language == "zh-CN":
                checks.append(f"补充{_dimension_label(dimension.name, output_language)}的证据缺口：{normalized}")
            else:
                checks.append(f"Resolve {dimension.name.value} evidence gap: {normalized}")
            if len(checks) == 3:
                return checks
    return checks


_RELIABILITY_DIMENSION_LABELS_ZH = {
    ReliabilityDimension.RESULT_AGREEMENT: "复现结果一致性",
    ReliabilityDimension.SETUP_TRANSPARENCY: "实验设置透明度",
    ReliabilityDimension.BASELINE_FAIRNESS: "基线比较公平性",
    ReliabilityDimension.ABLATION_QUALITY: "消融实验质量",
    ReliabilityDimension.STATISTICAL_REPORTING: "统计报告完整性",
    ReliabilityDimension.DATA_IMPLEMENTATION_AVAILABILITY: "数据与实现可用性",
}


def _dimension_label(dimension: ReliabilityDimension, output_language: str) -> str:
    if output_language == "zh-CN":
        return _RELIABILITY_DIMENSION_LABELS_ZH[dimension]
    return dimension.value


def _message(output_language: str, *, en: str, zh: str) -> str:
    return zh if output_language == "zh-CN" else en


def reliability_band(score: float) -> ReliabilityBand:
    if score >= 80:
        return ReliabilityBand.STRONG
    if score >= 60:
        return ReliabilityBand.MODERATE
    if score >= 40:
        return ReliabilityBand.WEAK
    return ReliabilityBand.INSUFFICIENT
