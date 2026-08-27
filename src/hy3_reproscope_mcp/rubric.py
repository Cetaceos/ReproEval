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


def normalize_score(result: ReliabilityScoreResult, *, has_reproduction: bool) -> None:
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
                rationale="No evidence-grounded assessment was returned for this fixed rubric dimension.",
                evidence_gaps=["dimension assessment missing"],
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
        agreement.rationale = "No independent reproduction evidence was supplied."
        if "independent reproduction evidence" not in agreement.evidence_gaps:
            agreement.evidence_gaps.append("independent reproduction evidence")
        result.conclusion_confidence = min(result.conclusion_confidence, 0.5)
        result.warnings.append(
            ToolWarning(
                code="PAPER_ONLY_ASSESSMENT",
                message="The assessment cannot receive a strong rating without independent reproduction evidence.",
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
                message="Overall score and band were deterministically recalculated from dimension weights.",
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
                message=(
                    f"Only {result.rubric_coverage:.0%} of the fixed rubric had enough evidence to score; "
                    "unassessed dimensions were excluded rather than treated as zero."
                ),
            )
        )
    if missing_dimensions:
        result.warnings.append(
            ToolWarning(
                code="RUBRIC_DIMENSION_MISSING",
                message="Missing fixed rubric dimensions were marked as insufficient evidence: "
                + ", ".join(dimension.value for dimension in missing_dimensions),
            )
        )
    if duplicate_dimensions:
        result.warnings.append(
            ToolWarning(
                code="RUBRIC_DIMENSION_DUPLICATED",
                message="Only the first assessment was kept for duplicated dimensions: "
                + ", ".join(dimension.value for dimension in sorted(duplicate_dimensions, key=str)),
            )
        )


def reliability_band(score: float) -> ReliabilityBand:
    if score >= 80:
        return ReliabilityBand.STRONG
    if score >= 60:
        return ReliabilityBand.MODERATE
    if score >= 40:
        return ReliabilityBand.WEAK
    return ReliabilityBand.INSUFFICIENT
