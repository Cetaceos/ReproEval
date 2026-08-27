"""Fixed rubric and deterministic aggregation for transfer assessments."""

from __future__ import annotations

from .models import DimensionAssessmentStatus, ToolWarning
from .transfer_models import (
    AssumptionCompatibility,
    TransferAssessmentResult,
    TransferConditionStatus,
    TransferDimension,
    TransferDimensionScore,
    TransferFeasibilityBand,
    TransferRiskLevel,
)

MIN_ASSESSED_WEIGHT = 0.50
MIN_PROMISING_RUBRIC_COVERAGE = 0.80

TRANSFER_RUBRIC_WEIGHTS: dict[TransferDimension, float] = {
    TransferDimension.EVIDENCE_RELIABILITY: 0.20,
    TransferDimension.ASSUMPTION_COMPATIBILITY: 0.20,
    TransferDimension.DEPENDENCY_FEASIBILITY: 0.15,
    TransferDimension.RESOURCE_FEASIBILITY: 0.15,
    TransferDimension.ADAPTATION_MANAGEABILITY: 0.15,
    TransferDimension.VALIDATION_READINESS: 0.15,
}

TRANSFER_RUBRIC_DESCRIPTIONS: dict[TransferDimension, str] = {
    TransferDimension.EVIDENCE_RELIABILITY: (
        "How well the source materials support the solution's claimed behavior, boundaries, and implementation state."
    ),
    TransferDimension.ASSUMPTION_COMPATIBILITY: (
        "Whether critical source assumptions remain valid in the supplied target context."
    ),
    TransferDimension.DEPENDENCY_FEASIBILITY: (
        "Whether required data, software, hardware, services, interfaces, and external systems can be satisfied."
    ),
    TransferDimension.RESOURCE_FEASIBILITY: (
        "Whether the target context can provide the required compute, data, latency, staffing, and operational budget."
    ),
    TransferDimension.ADAPTATION_MANAGEABILITY: (
        "Whether required changes are bounded, identifiable, and feasible without invalidating the core approach."
    ),
    TransferDimension.VALIDATION_READINESS: (
        "Whether testable success criteria, representative data, baselines, and staged validation steps are available."
    ),
}


def transfer_rubric_payload() -> list[dict[str, str | float]]:
    return [
        {
            "name": dimension.value,
            "weight": weight,
            "description": TRANSFER_RUBRIC_DESCRIPTIONS[dimension],
        }
        for dimension, weight in TRANSFER_RUBRIC_WEIGHTS.items()
    ]


def normalize_transfer_assessment(result: TransferAssessmentResult) -> None:
    """Apply fixed dimensions and weights, then calculate a conservative local verdict."""

    supplied: dict[TransferDimension, TransferDimensionScore] = {}
    duplicate_dimensions: set[TransferDimension] = set()
    for dimension in result.dimensions:
        if dimension.name in supplied:
            duplicate_dimensions.add(dimension.name)
            continue
        supplied[dimension.name] = dimension

    normalized: list[TransferDimensionScore] = []
    missing_dimensions: list[TransferDimension] = []
    for name, weight in TRANSFER_RUBRIC_WEIGHTS.items():
        dimension = supplied.get(name)
        if dimension is None:
            missing_dimensions.append(name)
            dimension = TransferDimensionScore(
                name=name,
                score=None,
                assessment_status=DimensionAssessmentStatus.INSUFFICIENT_EVIDENCE,
                rationale="No evidence-grounded assessment was returned for this fixed transfer dimension.",
                evidence_gaps=["dimension assessment missing"],
            )
        elif dimension.assessment_status is DimensionAssessmentStatus.INSUFFICIENT_EVIDENCE:
            dimension.score = None
        elif dimension.score is None:
            dimension.assessment_status = DimensionAssessmentStatus.INSUFFICIENT_EVIDENCE
        dimension.weight = weight
        normalized.append(dimension)

    result.dimensions = normalized
    result.rubric_coverage = round(
        sum(dimension.weight for dimension in result.dimensions if dimension.score is not None),
        2,
    )
    blockers_present = (
        any(item.compatibility is AssumptionCompatibility.INCOMPATIBLE for item in result.assumption_assessments)
        or any(item.status is TransferConditionStatus.UNSATISFIED for item in result.dependency_assessments)
        or any(item.status is TransferConditionStatus.UNSATISFIED for item in result.resource_assessments)
    )
    if result.rubric_coverage >= MIN_ASSESSED_WEIGHT:
        score = round(
            sum(dimension.score * dimension.weight for dimension in result.dimensions if dimension.score is not None)
            / result.rubric_coverage,
            2,
        )
        band = transfer_feasibility_band(score)
        if band is TransferFeasibilityBand.PROMISING and (
            result.rubric_coverage < MIN_PROMISING_RUBRIC_COVERAGE
            or any(risk.level is TransferRiskLevel.HIGH for risk in result.risks)
            or blockers_present
        ):
            band = TransferFeasibilityBand.CONDITIONAL
    else:
        score = None
        band = TransferFeasibilityBand.INSUFFICIENT
        result.conclusion_confidence = min(result.conclusion_confidence, 0.5)

    if result.overall_score != score or result.feasibility_band is not band:
        result.warnings.append(
            ToolWarning(
                code="TRANSFER_SCORE_NORMALIZED",
                message="Overall transfer score and feasibility band were recalculated from the fixed local rubric.",
            )
        )
    result.overall_score = score
    result.feasibility_band = band
    result.evidence_coverage = round(
        sum(dimension.weight for dimension in result.dimensions if dimension.score is not None and dimension.citations),
        2,
    )
    result.performance_prediction_provided = False
    result.legal_conclusion_provided = False
    result.warnings.extend(
        [
            ToolWarning(
                code="CONDITIONAL_TRANSFER_ASSESSMENT",
                message=(
                    "This assessment is conditional on the supplied target context and must be validated with "
                    "representative measurements before an engineering decision."
                ),
            ),
            ToolWarning(
                code="NO_TARGET_PERFORMANCE_PREDICTION",
                message="No point performance prediction is provided without target-context measurements.",
            ),
            ToolWarning(
                code="LICENSE_SIGNALS_NOT_LEGAL_ADVICE",
                message="License and provenance signals are screening evidence, not a legal conclusion.",
            ),
        ]
    )
    if result.rubric_coverage < 1:
        result.warnings.append(
            ToolWarning(
                code="TRANSFER_RUBRIC_PARTIAL_COVERAGE",
                message=(
                    f"Only {result.rubric_coverage:.0%} of the fixed transfer rubric had enough evidence to score; "
                    "unassessed dimensions were excluded rather than treated as zero."
                ),
            )
        )
    if blockers_present:
        result.warnings.append(
            ToolWarning(
                code="TRANSFER_BLOCKERS_PRESENT",
                message=(
                    "At least one source assumption, dependency, or resource requirement is unsatisfied in the "
                    "target context; a promising verdict is not allowed until the blocker is resolved."
                ),
            )
        )
    if missing_dimensions:
        result.warnings.append(
            ToolWarning(
                code="TRANSFER_DIMENSION_MISSING",
                message="Missing transfer dimensions were marked as insufficient evidence: "
                + ", ".join(dimension.value for dimension in missing_dimensions),
            )
        )
    if duplicate_dimensions:
        result.warnings.append(
            ToolWarning(
                code="TRANSFER_DIMENSION_DUPLICATED",
                message="Only the first assessment was kept for duplicated transfer dimensions: "
                + ", ".join(dimension.value for dimension in sorted(duplicate_dimensions, key=str)),
            )
        )


def transfer_feasibility_band(score: float) -> TransferFeasibilityBand:
    if score >= 80:
        return TransferFeasibilityBand.PROMISING
    if score >= 60:
        return TransferFeasibilityBand.CONDITIONAL
    return TransferFeasibilityBand.HIGH_RISK
