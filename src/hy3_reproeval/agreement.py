"""Human-human agreement, adjudication queues, and optional system-human comparison."""

from __future__ import annotations

import hashlib
import statistics
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations
from pathlib import Path
from typing import Literal

from pydantic import Field

from . import __version__
from .annotations import (
    AnnotationBundle,
    AnnotationRound,
    AnnotationValidationResult,
    DimensionAnnotation,
    ReportAnnotation,
    is_benchmark_eligible,
    load_validated_annotation_bundles,
    validate_annotation_bundles,
)
from .benchmark import DatasetBenchmarkResult
from .dataset import DatasetSplit, LoadedDatasetManifest, load_dataset_manifest
from .errors import EvaluationInputError
from .models import DimensionId, DimensionStatus, StrictModel
from .rubric import RubricDefinition, load_public_rubric
from .validators import load_evaluation_case

MAX_BENCHMARK_RESULT_BYTES = 32 * 1024 * 1024


class AdjudicationReason(StrEnum):
    STATUS_MISMATCH = "status_mismatch"
    SCORE_GAP = "score_gap"
    ERROR_CODE_MISMATCH = "error_code_mismatch"


class AgreementMetrics(StrictModel):
    comparison_count: int = Field(ge=0)
    assessed_pair_count: int = Field(ge=0)
    status_agreement: float | None = Field(default=None, ge=0, le=1)
    exact_score_agreement: float | None = Field(default=None, ge=0, le=1)
    within_one_point_agreement: float | None = Field(default=None, ge=0, le=1)
    mean_absolute_score_difference: float | None = Field(default=None, ge=0, le=4)
    quadratic_weighted_kappa: float | None = Field(default=None, ge=-1, le=1)
    error_code_set_agreement: float | None = Field(default=None, ge=0, le=1)


class DimensionAgreement(StrictModel):
    dimension: DimensionId
    metrics: AgreementMetrics


class AnnotatorPairAgreement(StrictModel):
    annotator_a: str
    annotator_b: str
    shared_report_count: int = Field(ge=1)
    metrics: AgreementMetrics
    dimensions: list[DimensionAgreement] = Field(min_length=7, max_length=7)


class RepeatStability(StrictModel):
    annotator_id: str
    independent_bundle_id: str
    repeat_bundle_id: str
    shared_report_count: int = Field(ge=0)
    metrics: AgreementMetrics
    dimensions: list[DimensionAgreement] = Field(min_length=7, max_length=7)


class AdjudicationItem(StrictModel):
    report_id: str
    dimension: DimensionId
    annotator_a: str
    annotator_b: str
    reason: AdjudicationReason
    status_a: DimensionStatus
    status_b: DimensionStatus
    score_a: int | None = Field(default=None, ge=0, le=4)
    score_b: int | None = Field(default=None, ge=0, le=4)
    absolute_score_gap: int | None = Field(default=None, ge=0, le=4)


class SystemHumanReportComparison(StrictModel):
    report_id: str
    split: DatasetSplit
    human_score_mean: float = Field(ge=0, le=100)
    human_score_stddev: float = Field(ge=0)
    human_rater_count: int = Field(ge=1)
    system_score: float = Field(ge=0, le=100)
    absolute_error: float = Field(ge=0, le=100)


class SystemHumanAgreement(StrictModel):
    benchmark_result_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    target_report_count: int = Field(ge=0)
    matched_report_count: int = Field(ge=0)
    coverage: float | None = Field(default=None, ge=0, le=1)
    spearman_correlation: float | None = Field(default=None, ge=-1, le=1)
    mean_absolute_error: float | None = Field(default=None, ge=0, le=100)
    complete_coverage: bool
    reports: list[SystemHumanReportComparison]


class AnnotationAgreementResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_sha256: str | None = Field(default=None, pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    annotation_validation: AnnotationValidationResult
    agreement_ready: bool
    eligible_annotator_count: int = Field(ge=0)
    eligible_report_count: int = Field(ge=0)
    annotator_pair_count: int = Field(ge=0)
    pooled_metrics: AgreementMetrics
    dimensions: list[DimensionAgreement] = Field(min_length=7, max_length=7)
    annotator_pairs: list[AnnotatorPairAgreement]
    repeat_stability_count: int = Field(ge=0)
    repeat_stability: list[RepeatStability]
    adjudication_item_count: int = Field(ge=0)
    adjudication_items: list[AdjudicationItem]
    system_human: SystemHumanAgreement | None = None
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Observation:
    report_id: str
    dimension: DimensionId
    annotator_a: str
    annotator_b: str
    annotation_a: DimensionAnnotation
    annotation_b: DimensionAnnotation


def analyze_annotation_agreement(
    dataset_path: str | Path,
    bundle_paths: list[str | Path],
    *,
    benchmark_result_path: str | Path | None = None,
    dataset_freeze_path: str | Path | None = None,
) -> AnnotationAgreementResult:
    """Analyze eligible independent human annotations without inventing missing evidence."""

    validation = validate_annotation_bundles(
        dataset_path,
        bundle_paths,
        dataset_freeze_path=dataset_freeze_path,
    )
    dataset = load_dataset_manifest(dataset_path)
    rubric = load_public_rubric()
    bundles = load_validated_annotation_bundles(bundle_paths, validation)
    inventory = _report_inventory(dataset)
    by_report: dict[str, dict[str, ReportAnnotation]] = defaultdict(dict)
    for bundle in bundles:
        for annotation in bundle.annotations:
            split = inventory[annotation.report_id][1]
            if is_benchmark_eligible(bundle, split):
                by_report[annotation.report_id][bundle.annotator.annotator_id] = annotation

    observations: list[_Observation] = []
    pair_observations: dict[tuple[str, str], list[_Observation]] = defaultdict(list)
    for report_id, annotations_by_annotator in sorted(by_report.items()):
        for annotator_a, annotator_b in combinations(sorted(annotations_by_annotator), 2):
            dimensions_a = _dimensions_by_id(annotations_by_annotator[annotator_a])
            dimensions_b = _dimensions_by_id(annotations_by_annotator[annotator_b])
            for dimension in DimensionId:
                observation = _Observation(
                    report_id=report_id,
                    dimension=dimension,
                    annotator_a=annotator_a,
                    annotator_b=annotator_b,
                    annotation_a=dimensions_a[dimension],
                    annotation_b=dimensions_b[dimension],
                )
                observations.append(observation)
                pair_observations[(annotator_a, annotator_b)].append(observation)

    dimensions = [
        DimensionAgreement(
            dimension=dimension,
            metrics=_agreement_metrics([item for item in observations if item.dimension is dimension]),
        )
        for dimension in DimensionId
    ]
    pair_results = [
        AnnotatorPairAgreement(
            annotator_a=annotator_a,
            annotator_b=annotator_b,
            shared_report_count=len({item.report_id for item in items}),
            metrics=_agreement_metrics(items),
            dimensions=[
                DimensionAgreement(
                    dimension=dimension,
                    metrics=_agreement_metrics([item for item in items if item.dimension is dimension]),
                )
                for dimension in DimensionId
            ],
        )
        for (annotator_a, annotator_b), items in sorted(pair_observations.items())
    ]
    repeat_stability = _repeat_stability(bundles, inventory)
    adjudication_items = _adjudication_items(observations)
    system_human = (
        _system_human_agreement(
            benchmark_result_path,
            dataset,
            rubric,
            validation.rubric_sha256,
            validation.dataset_freeze_sha256,
            inventory,
            by_report,
        )
        if benchmark_result_path is not None
        else None
    )
    warnings = list(validation.warnings)
    if not validation.benchmark_ready:
        warnings.append(
            "Agreement analysis is not benchmark-ready until every validation/test report is double annotated."
        )
    pooled_metrics = _agreement_metrics(observations)
    if pooled_metrics.quadratic_weighted_kappa is None:
        warnings.append(
            "Quadratic weighted Kappa is undefined because scored pairs are absent or have no expected variance."
        )
    if adjudication_items:
        warnings.append(f"{len(adjudication_items)} pairwise dimension disagreements require adjudication.")
    if any(item.shared_report_count == 0 for item in repeat_stability):
        warnings.append("At least one repeat Bundle shares no validation/test report with its independent parent.")
    if system_human is not None and not system_human.complete_coverage:
        warnings.append("System-human comparison does not cover every validation/test report.")
    eligible_annotators = {annotator_id for annotations in by_report.values() for annotator_id in annotations}
    return AnnotationAgreementResult(
        engine_version=__version__,
        dataset_id=validation.dataset_id,
        dataset_version=validation.dataset_version,
        dataset_manifest_sha256=validation.dataset_manifest_sha256,
        dataset_freeze_sha256=validation.dataset_freeze_sha256,
        rubric_version=validation.rubric_version,
        rubric_sha256=validation.rubric_sha256,
        annotation_validation=validation,
        agreement_ready=validation.benchmark_ready,
        eligible_annotator_count=len(eligible_annotators),
        eligible_report_count=len(by_report),
        annotator_pair_count=len(pair_results),
        pooled_metrics=pooled_metrics,
        dimensions=dimensions,
        annotator_pairs=pair_results,
        repeat_stability_count=len(repeat_stability),
        repeat_stability=repeat_stability,
        adjudication_item_count=len(adjudication_items),
        adjudication_items=adjudication_items,
        system_human=system_human,
        warnings=warnings,
    )


def _report_inventory(dataset: LoadedDatasetManifest) -> dict[str, tuple[str, DatasetSplit, str, str]]:
    inventory: dict[str, tuple[str, DatasetSplit, str, str]] = {}
    for group in dataset.manifest.groups:
        for report in group.reports:
            loaded = load_evaluation_case(dataset.resolve(report.case_path, "evaluation case"))
            inventory[report.report_id] = (
                group.group_id,
                group.split,
                report.report_sha256,
                loaded.case.case_id,
            )
    return inventory


def _dimensions_by_id(annotation: ReportAnnotation) -> dict[DimensionId, DimensionAnnotation]:
    return {item.dimension: item for item in annotation.dimensions}


def _repeat_stability(
    bundles: list[AnnotationBundle],
    inventory: dict[str, tuple[str, DatasetSplit, str, str]],
) -> list[RepeatStability]:
    by_id = {bundle.annotation_bundle_id: bundle for bundle in bundles}
    results: list[RepeatStability] = []
    for repeat in sorted(
        (bundle for bundle in bundles if bundle.annotation_round is AnnotationRound.REPEAT),
        key=lambda bundle: bundle.annotation_bundle_id,
    ):
        parent = by_id[repeat.parent_annotation_bundle_ids[0]]
        parent_reports = {annotation.report_id: annotation for annotation in parent.annotations}
        repeat_reports = {annotation.report_id: annotation for annotation in repeat.annotations}
        shared_reports = sorted(
            report_id
            for report_id in set(parent_reports) & set(repeat_reports)
            if inventory[report_id][1] in {DatasetSplit.VALIDATION, DatasetSplit.TEST}
        )
        observations: list[_Observation] = []
        for report_id in shared_reports:
            parent_dimensions = _dimensions_by_id(parent_reports[report_id])
            repeat_dimensions = _dimensions_by_id(repeat_reports[report_id])
            observations.extend(
                _Observation(
                    report_id=report_id,
                    dimension=dimension,
                    annotator_a=parent.annotator.annotator_id,
                    annotator_b=repeat.annotator.annotator_id,
                    annotation_a=parent_dimensions[dimension],
                    annotation_b=repeat_dimensions[dimension],
                )
                for dimension in DimensionId
            )
        results.append(
            RepeatStability(
                annotator_id=repeat.annotator.annotator_id,
                independent_bundle_id=parent.annotation_bundle_id,
                repeat_bundle_id=repeat.annotation_bundle_id,
                shared_report_count=len(shared_reports),
                metrics=_agreement_metrics(observations),
                dimensions=[
                    DimensionAgreement(
                        dimension=dimension,
                        metrics=_agreement_metrics([item for item in observations if item.dimension is dimension]),
                    )
                    for dimension in DimensionId
                ],
            )
        )
    return results


def _agreement_metrics(observations: list[_Observation]) -> AgreementMetrics:
    comparison_count = len(observations)
    status_matches = sum(item.annotation_a.status is item.annotation_b.status for item in observations)
    assessed = [
        item
        for item in observations
        if item.annotation_a.status is DimensionStatus.ASSESSED and item.annotation_b.status is DimensionStatus.ASSESSED
    ]
    scores_a = [int(item.annotation_a.score) for item in assessed if item.annotation_a.score is not None]
    scores_b = [int(item.annotation_b.score) for item in assessed if item.annotation_b.score is not None]
    differences = [abs(left - right) for left, right in zip(scores_a, scores_b, strict=True)]
    error_matches = sum(
        set(item.annotation_a.error_codes) == set(item.annotation_b.error_codes) for item in observations
    )
    return AgreementMetrics(
        comparison_count=comparison_count,
        assessed_pair_count=len(assessed),
        status_agreement=_ratio(status_matches, comparison_count),
        exact_score_agreement=_ratio(sum(difference == 0 for difference in differences), len(differences)),
        within_one_point_agreement=_ratio(sum(difference <= 1 for difference in differences), len(differences)),
        mean_absolute_score_difference=(round(statistics.fmean(differences), 6) if differences else None),
        quadratic_weighted_kappa=_quadratic_weighted_kappa(scores_a, scores_b),
        error_code_set_agreement=_ratio(error_matches, comparison_count),
    )


def _adjudication_items(observations: list[_Observation]) -> list[AdjudicationItem]:
    results: list[AdjudicationItem] = []
    for item in observations:
        left = item.annotation_a
        right = item.annotation_b
        if left.status is not right.status:
            reason = AdjudicationReason.STATUS_MISMATCH
            gap = None
        elif left.status is DimensionStatus.ASSESSED and right.status is DimensionStatus.ASSESSED:
            if left.score is None or right.score is None:  # pragma: no cover - schema invariant
                continue
            gap = abs(left.score - right.score)
            if gap <= 1:
                if set(left.error_codes) == set(right.error_codes):
                    continue
                reason = AdjudicationReason.ERROR_CODE_MISMATCH
            else:
                reason = AdjudicationReason.SCORE_GAP
        else:
            continue
        results.append(
            AdjudicationItem(
                report_id=item.report_id,
                dimension=item.dimension,
                annotator_a=item.annotator_a,
                annotator_b=item.annotator_b,
                reason=reason,
                status_a=left.status,
                status_b=right.status,
                score_a=left.score,
                score_b=right.score,
                absolute_score_gap=gap,
            )
        )
    return results


def _system_human_agreement(
    benchmark_result_path: str | Path,
    dataset: LoadedDatasetManifest,
    rubric: RubricDefinition,
    rubric_sha256: str,
    dataset_freeze_sha256: str | None,
    inventory: dict[str, tuple[str, DatasetSplit, str, str]],
    by_report: dict[str, dict[str, ReportAnnotation]],
) -> SystemHumanAgreement:
    path = Path(benchmark_result_path).expanduser().resolve()
    payload = _read_limited(path, MAX_BENCHMARK_RESULT_BYTES, "benchmark result")
    try:
        benchmark = DatasetBenchmarkResult.model_validate_json(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid benchmark result: {exc}") from exc
    expected_identity = (
        dataset.manifest.dataset_id,
        dataset.manifest.dataset_version,
        dataset.manifest_sha256,
    )
    actual_identity = (benchmark.dataset_id, benchmark.dataset_version, benchmark.dataset_manifest_sha256)
    if actual_identity != expected_identity:
        raise EvaluationInputError("benchmark result does not match the current Dataset Manifest")
    if benchmark.rubric_version != rubric.rubric_version or benchmark.rubric_sha256 != rubric_sha256:
        raise EvaluationInputError("benchmark result uses a different Rubric")
    if benchmark.dataset_freeze_sha256 != dataset_freeze_sha256:
        raise EvaluationInputError("benchmark result uses a different Dataset Freeze fingerprint")
    _validate_benchmark_inventory(benchmark, dataset, inventory)
    system_reports = {report.report_id: report for group in benchmark.groups for report in group.reports}
    target_reports = {
        report_id
        for report_id, (_, split, _, _) in inventory.items()
        if split in {DatasetSplit.VALIDATION, DatasetSplit.TEST}
    }
    comparisons: list[SystemHumanReportComparison] = []
    for report_id in sorted(target_reports):
        human_scores = [
            score
            for annotation in by_report.get(report_id, {}).values()
            if (score := _human_report_score(annotation, rubric)) is not None
        ]
        system = system_reports[report_id]
        if len(human_scores) < 2 or system.overall_score is None or system.provisional:
            continue
        human_mean = statistics.fmean(human_scores)
        comparisons.append(
            SystemHumanReportComparison(
                report_id=report_id,
                split=inventory[report_id][1],
                human_score_mean=round(human_mean, 6),
                human_score_stddev=round(statistics.pstdev(human_scores), 6),
                human_rater_count=len(human_scores),
                system_score=system.overall_score,
                absolute_error=round(abs(system.overall_score - human_mean), 6),
            )
        )
    human_values = [item.human_score_mean for item in comparisons]
    system_values = [item.system_score for item in comparisons]
    return SystemHumanAgreement(
        benchmark_result_sha256=_sha256(payload),
        target_report_count=len(target_reports),
        matched_report_count=len(comparisons),
        coverage=_ratio(len(comparisons), len(target_reports)),
        spearman_correlation=_spearman(system_values, human_values),
        mean_absolute_error=(
            round(statistics.fmean(item.absolute_error for item in comparisons), 6) if comparisons else None
        ),
        complete_coverage=bool(target_reports) and len(comparisons) == len(target_reports),
        reports=comparisons,
    )


def _validate_benchmark_inventory(
    benchmark: DatasetBenchmarkResult,
    dataset: LoadedDatasetManifest,
    inventory: dict[str, tuple[str, DatasetSplit, str, str]],
) -> None:
    expected_groups = {
        group.group_id: (group.split, group.scenario, {report.report_id for report in group.reports})
        for group in dataset.manifest.groups
    }
    if {group.group_id for group in benchmark.groups} != set(expected_groups):
        raise EvaluationInputError("benchmark result group inventory does not match the dataset")
    observed_reports: set[str] = set()
    for group in benchmark.groups:
        expected_split, expected_scenario, expected_reports = expected_groups[group.group_id]
        if (
            group.split is not expected_split
            or group.scenario is not expected_scenario
            or {report.report_id for report in group.reports} != expected_reports
        ):
            raise EvaluationInputError(f"benchmark result group '{group.group_id}' does not match the dataset")
        for report in group.reports:
            if (
                report.report_id in observed_reports
                or report.report_sha256 != inventory[report.report_id][2]
                or report.case_id != inventory[report.report_id][3]
            ):
                raise EvaluationInputError(f"benchmark result report '{report.report_id}' does not match the dataset")
            observed_reports.add(report.report_id)
    if observed_reports != set(inventory):
        raise EvaluationInputError("benchmark result report inventory does not match the dataset")


def _human_report_score(annotation: ReportAnnotation, rubric: RubricDefinition) -> float | None:
    assessed = [item for item in annotation.dimensions if item.status is DimensionStatus.ASSESSED]
    assessed_weight = sum(rubric.dimension(item.dimension).weight for item in assessed)
    if assessed_weight < rubric.minimum_assessed_weight:
        return None
    weighted = sum(
        (float(item.score) / 4.0) * rubric.dimension(item.dimension).weight
        for item in assessed
        if item.score is not None
    )
    score = (weighted / assessed_weight) * 100.0
    hard_caps = [
        rubric.hard_caps[error] for item in assessed for error in item.error_codes if error in rubric.hard_caps
    ]
    if hard_caps:
        score = min(score, *hard_caps)
    return round(score, 6)


def _quadratic_weighted_kappa(scores_a: list[int], scores_b: list[int]) -> float | None:
    if not scores_a or len(scores_a) != len(scores_b):
        return None
    maximum_distance = 16.0
    observed_disagreement = statistics.fmean(
        ((left - right) ** 2) / maximum_distance for left, right in zip(scores_a, scores_b, strict=True)
    )
    counts_a = [scores_a.count(score) / len(scores_a) for score in range(5)]
    counts_b = [scores_b.count(score) / len(scores_b) for score in range(5)]
    expected_disagreement = sum(
        counts_a[left] * counts_b[right] * (((left - right) ** 2) / maximum_distance)
        for left in range(5)
        for right in range(5)
    )
    if expected_disagreement <= 1e-12:
        return None
    value = 1.0 - (observed_disagreement / expected_disagreement)
    return round(max(-1.0, min(1.0, value)), 6)


def _spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    ranks_left = _average_ranks(left)
    ranks_right = _average_ranks(right)
    mean_left = statistics.fmean(ranks_left)
    mean_right = statistics.fmean(ranks_right)
    numerator = sum(
        (left_rank - mean_left) * (right_rank - mean_right)
        for left_rank, right_rank in zip(ranks_left, ranks_right, strict=True)
    )
    denominator_left = sum((rank - mean_left) ** 2 for rank in ranks_left)
    denominator_right = sum((rank - mean_right) ** 2 for rank in ranks_right)
    denominator = (denominator_left * denominator_right) ** 0.5
    if denominator <= 1e-12:
        return None
    return round(max(-1.0, min(1.0, numerator / denominator)), 6)


def _average_ranks(values: list[float]) -> list[float]:
    ranks = [0.0] * len(values)
    ordered = sorted(range(len(values)), key=values.__getitem__)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[cursor]]:
            end += 1
        average_rank = ((cursor + 1) + end) / 2.0
        for index in ordered[cursor:end]:
            ranks[index] = average_rank
        cursor = end
    return ranks


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _read_limited(path: Path, maximum_bytes: int, label: str) -> bytes:
    if not path.is_file():
        raise EvaluationInputError(f"{label} does not exist or is not a file: {path.as_posix()}")
    if path.stat().st_size > maximum_bytes:
        raise EvaluationInputError(f"{label} exceeds {maximum_bytes} bytes: {path.as_posix()}")
    return path.read_bytes()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()
