"""Aggregate deterministic validation results with the public rubric."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from . import __version__
from .models import (
    DimensionId,
    DimensionResult,
    DimensionStatus,
    EvaluationMode,
    EvaluationResult,
    EvaluationStatus,
    FindingSeverity,
    FindingStatus,
    QualityBand,
    ValidatorFinding,
)
from .rubric import RubricDefinition, load_public_rubric
from .validators import RawCheck, load_evaluation_case, run_deterministic_validators


def evaluate_case_file(path: str | Path, *, rubric: RubricDefinition | None = None) -> EvaluationResult:
    active_rubric = rubric or load_public_rubric()
    loaded = load_evaluation_case(path)
    checks = run_deterministic_validators(loaded)
    findings = _build_findings(checks, active_rubric)
    dimensions = _aggregate_dimensions(checks, active_rubric)
    assessed_weight = round(
        sum(item.weight for item in dimensions if item.status is DimensionStatus.ASSESSED),
        10,
    )
    provisional = any(item.status is DimensionStatus.INSUFFICIENT_EVIDENCE for item in dimensions)
    failed_caps = [finding.hard_cap for finding in findings if finding.status is FindingStatus.FAILED]
    applied_hard_cap = min((cap for cap in failed_caps if cap is not None), default=None)

    warnings = _coverage_warnings(dimensions)
    if assessed_weight < active_rubric.minimum_assessed_weight:
        status = EvaluationStatus.INSUFFICIENT
        overall_score = None
        quality_band = QualityBand.INSUFFICIENT
        warnings.append(
            f"Assessed rubric weight {assessed_weight:.2f} is below the "
            f"{active_rubric.minimum_assessed_weight:.2f} reporting threshold."
        )
    else:
        normalized = _normalized_score(dimensions, assessed_weight)
        overall_score = round(min(normalized, applied_hard_cap) if applied_hard_cap is not None else normalized, 2)
        quality_band = _quality_band(overall_score, active_rubric)
        status = EvaluationStatus.PARTIAL if provisional else EvaluationStatus.COMPLETE
        if applied_hard_cap is not None and overall_score == applied_hard_cap:
            warnings.append(f"Overall score was limited by deterministic hard cap {applied_hard_cap:.2f}.")

    return EvaluationResult(
        engine_version=__version__,
        rubric_version=active_rubric.rubric_version,
        rubric_sha256=_rubric_sha256(active_rubric),
        case_id=loaded.case.case_id,
        case_manifest_sha256=loaded.manifest_sha256,
        scenario=loaded.case.scenario,
        report_sha256=loaded.report_sha256,
        evaluation_mode=EvaluationMode.DETERMINISTIC_ONLY,
        status=status,
        provisional=provisional,
        assessed_weight=assessed_weight,
        overall_score=overall_score,
        quality_band=quality_band,
        applied_hard_cap=applied_hard_cap,
        dimensions=dimensions,
        findings=findings,
        warnings=warnings,
    )


def _build_findings(checks: list[RawCheck], rubric: RubricDefinition) -> list[ValidatorFinding]:
    findings: list[ValidatorFinding] = []
    for check in checks:
        status = FindingStatus.PASSED if check.passed else FindingStatus.FAILED
        severity = FindingSeverity.INFO if check.passed else check.severity_on_failure
        hard_cap = None
        if not check.passed and check.hard_cap_eligible:
            hard_cap = rubric.hard_caps.get(check.error_code)
        findings.append(
            ValidatorFinding(
                finding_id=check.check_id,
                validator=check.validator,
                status=status,
                severity=severity,
                message=check.message,
                dimensions=list(check.dimensions),
                error_code=None if check.passed else check.error_code,
                evidence=list(check.evidence),
                hard_cap=hard_cap,
            )
        )
    return findings


def _aggregate_dimensions(checks: list[RawCheck], rubric: RubricDefinition) -> list[DimensionResult]:
    by_dimension: dict[DimensionId, list[RawCheck]] = defaultdict(list)
    for check in checks:
        for dimension in check.dimensions:
            by_dimension[dimension].append(check)

    results: list[DimensionResult] = []
    for definition in rubric.dimensions:
        dimension_checks = by_dimension.get(definition.id, [])
        if not dimension_checks:
            results.append(
                DimensionResult(
                    dimension=definition.id,
                    weight=definition.weight,
                    status=DimensionStatus.INSUFFICIENT_EVIDENCE,
                    rationale="No deterministic or semantic assessment is available for this dimension.",
                )
            )
            continue
        passed = sum(check.passed for check in dimension_checks)
        critical_failure = any(
            not check.passed and check.severity_on_failure is FindingSeverity.CRITICAL for check in dimension_checks
        )
        score = 0.0 if critical_failure else _ratio_score(passed / len(dimension_checks))
        results.append(
            DimensionResult(
                dimension=definition.id,
                weight=definition.weight,
                status=DimensionStatus.ASSESSED,
                score=score,
                rationale=(
                    f"{passed}/{len(dimension_checks)} deterministic checks passed"
                    + ("; a critical failure forced this dimension to 0." if critical_failure else ".")
                ),
                finding_ids=[check.check_id for check in dimension_checks],
            )
        )
    return results


def _ratio_score(ratio: float) -> float:
    if ratio == 1:
        return 4.0
    if ratio >= 0.75:
        return 3.0
    if ratio >= 0.5:
        return 2.0
    if ratio > 0:
        return 1.0
    return 0.0


def _normalized_score(dimensions: list[DimensionResult], assessed_weight: float) -> float:
    weighted = sum(
        (dimension.score or 0.0) / 4 * dimension.weight
        for dimension in dimensions
        if dimension.status is DimensionStatus.ASSESSED
    )
    return weighted / assessed_weight * 100


def _quality_band(score: float, rubric: RubricDefinition) -> QualityBand:
    thresholds = rubric.quality_thresholds
    if score >= thresholds.excellent:
        return QualityBand.EXCELLENT
    if score >= thresholds.strong:
        return QualityBand.STRONG
    if score >= thresholds.mixed:
        return QualityBand.MIXED
    return QualityBand.WEAK


def _coverage_warnings(dimensions: list[DimensionResult]) -> list[str]:
    missing = [
        dimension.dimension.value
        for dimension in dimensions
        if dimension.status is DimensionStatus.INSUFFICIENT_EVIDENCE
    ]
    if not missing:
        return []
    return ["Provisional deterministic-only evaluation; unassessed dimensions: " + ", ".join(missing) + "."]


def _rubric_sha256(rubric: RubricDefinition) -> str:
    canonical = json.dumps(rubric.model_dump(mode="json"), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()
