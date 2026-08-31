"""Group-isolated batch evaluation and ranking metrics for ReproEval datasets."""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable
from enum import StrEnum
from itertools import combinations
from pathlib import Path

from pydantic import Field

from . import __version__
from .dataset import (
    DatasetReportEntry,
    DatasetSplit,
    QualityTier,
    load_dataset_manifest,
    validate_dataset_manifest,
)
from .errors import EvaluationInputError
from .evaluator import evaluate_case_file, evaluate_case_file_hybrid
from .judge_batch import validate_judge_record_index
from .models import (
    ErrorCode,
    EvaluationMode,
    EvaluationResult,
    EvaluationStatus,
    FindingStatus,
    QualityBand,
    Scenario,
    StrictModel,
)

_ORDERED_TIERS = {
    QualityTier.HIGH: 3,
    QualityTier.MEDIUM: 2,
    QualityTier.LOW: 1,
}


class BenchmarkMode(StrEnum):
    DETERMINISTIC = "deterministic"
    REPLAY = "replay"


class BenchmarkReportResult(StrictModel):
    report_id: str
    quality_tier: QualityTier
    case_id: str
    report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    evaluation_mode: EvaluationMode
    status: EvaluationStatus
    provisional: bool
    ranking_eligible: bool
    assessed_weight: float = Field(ge=0, le=1)
    overall_score: float | None = Field(default=None, ge=0, le=100)
    quality_band: QualityBand
    applied_hard_cap: float | None = Field(default=None, ge=0, le=100)
    judge_record_sha256: str | None = Field(default=None, pattern=r"^[A-F0-9]{64}$")
    expected_error_codes: list[ErrorCode]
    observed_error_codes: list[ErrorCode]
    detected_expected_error_codes: list[ErrorCode]
    missing_expected_error_codes: list[ErrorCode]
    unexpected_error_codes: list[ErrorCode]


class GroupOrderingMetrics(StrictModel):
    report_count: int = Field(ge=3)
    ranking_candidate_report_count: int = Field(ge=3)
    ranking_eligible_report_count: int = Field(ge=0)
    ranking_score_coverage: float = Field(ge=0, le=1)
    expected_pair_count: int = Field(ge=1)
    evaluated_pair_count: int = Field(ge=0)
    pair_coverage: float = Field(ge=0, le=1)
    correct_pair_count: int = Field(ge=0)
    tied_pair_count: int = Field(ge=0)
    pairwise_accuracy: float | None = Field(default=None, ge=0, le=1)
    complete_order_evaluable: bool
    complete_order_correct: bool | None = None
    spearman_correlation: float | None = Field(default=None, ge=-1, le=1)
    expected_error_count: int = Field(ge=0)
    detected_expected_error_count: int = Field(ge=0)
    unexpected_error_count: int = Field(ge=0)
    error_label_recall: float | None = Field(default=None, ge=0, le=1)


class BenchmarkGroupResult(StrictModel):
    group_id: str
    split: DatasetSplit
    scenario: Scenario
    reports: list[BenchmarkReportResult] = Field(min_length=3)
    metrics: GroupOrderingMetrics


class AggregateBenchmarkMetrics(StrictModel):
    group_count: int = Field(ge=0)
    report_count: int = Field(ge=0)
    ranking_candidate_report_count: int = Field(ge=0)
    ranking_eligible_report_count: int = Field(ge=0)
    ranking_score_coverage: float | None = Field(default=None, ge=0, le=1)
    expected_pair_count: int = Field(ge=0)
    evaluated_pair_count: int = Field(ge=0)
    pair_coverage: float | None = Field(default=None, ge=0, le=1)
    correct_pair_count: int = Field(ge=0)
    tied_pair_count: int = Field(ge=0)
    pairwise_accuracy: float | None = Field(default=None, ge=0, le=1)
    complete_order_evaluable_group_count: int = Field(ge=0)
    complete_order_correct_group_count: int = Field(ge=0)
    complete_order_coverage: float | None = Field(default=None, ge=0, le=1)
    complete_order_accuracy: float | None = Field(default=None, ge=0, le=1)
    spearman_evaluable_group_count: int = Field(ge=0)
    macro_spearman_correlation: float | None = Field(default=None, ge=-1, le=1)
    expected_error_count: int = Field(ge=0)
    detected_expected_error_count: int = Field(ge=0)
    unexpected_error_count: int = Field(ge=0)
    error_label_recall: float | None = Field(default=None, ge=0, le=1)


class DatasetBenchmarkResult(StrictModel):
    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    engine_version: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    benchmark_mode: BenchmarkMode
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    judge_record_index_sha256: str | None = Field(default=None, pattern=r"^[A-F0-9]{64}$")
    groups: list[BenchmarkGroupResult] = Field(min_length=1)
    overall: AggregateBenchmarkMetrics
    splits: dict[DatasetSplit, AggregateBenchmarkMetrics]
    warnings: list[str] = Field(default_factory=list)


async def run_dataset_benchmark(
    path: str | Path,
    *,
    mode: BenchmarkMode | str = BenchmarkMode.DETERMINISTIC,
    judge_index_path: str | Path | None = None,
) -> DatasetBenchmarkResult:
    """Evaluate every registered report and aggregate only within source groups."""

    try:
        active_mode = BenchmarkMode(mode)
    except ValueError as exc:
        raise EvaluationInputError(f"unsupported dataset benchmark mode: {mode}") from exc
    if active_mode is BenchmarkMode.DETERMINISTIC and judge_index_path is not None:
        raise EvaluationInputError("Judge Record index requires replay benchmark mode")
    validation = validate_dataset_manifest(path)
    loaded_dataset = load_dataset_manifest(path)
    loaded_index = validate_judge_record_index(judge_index_path, path) if judge_index_path is not None else None
    group_results: list[BenchmarkGroupResult] = []
    rubric_versions: set[str] = set()
    rubric_hashes: set[str] = set()

    for group in loaded_dataset.manifest.groups:
        reports: list[BenchmarkReportResult] = []
        for entry in group.reports:
            case_path = loaded_dataset.resolve(entry.case_path, "evaluation case")
            if active_mode is BenchmarkMode.REPLAY:
                if loaded_index is not None:
                    record_path = loaded_index.record_paths_by_report_id[entry.report_id]
                elif entry.judge_record_path is not None:
                    record_path = loaded_dataset.resolve(entry.judge_record_path, "Judge record")
                else:
                    raise EvaluationInputError(
                        f"replay benchmark requires a Judge record for report '{entry.report_id}'"
                    )
                evaluation, _ = await evaluate_case_file_hybrid(case_path, judge_replay_path=record_path)
            else:
                evaluation = evaluate_case_file(case_path)
            rubric_versions.add(evaluation.rubric_version)
            rubric_hashes.add(evaluation.rubric_sha256)
            reports.append(_summarize_report(entry, evaluation))
        group_results.append(
            BenchmarkGroupResult(
                group_id=group.group_id,
                split=group.split,
                scenario=group.scenario,
                reports=reports,
                metrics=_group_metrics(reports),
            )
        )

    if len(rubric_versions) != 1 or len(rubric_hashes) != 1:
        raise EvaluationInputError("dataset benchmark reports were evaluated with multiple Rubric versions")
    warnings = list(validation.warnings)
    if any(
        report.label_source == "synthetic_mutation"
        for group in loaded_dataset.manifest.groups
        for report in group.reports
    ):
        warnings.append(
            "Synthetic mutation labels and replay records validate protocol behavior; "
            "they are not model-human benchmark evidence."
        )
    if active_mode is BenchmarkMode.DETERMINISTIC:
        warnings.append("Provisional deterministic-only scores are excluded from ordering metrics.")
    overall = _aggregate_metrics(group_results)
    if overall.complete_order_evaluable_group_count == 0:
        warnings.append("No source group has complete ranking evidence in this benchmark mode.")
    return DatasetBenchmarkResult(
        engine_version=__version__,
        dataset_id=loaded_dataset.manifest.dataset_id,
        dataset_version=loaded_dataset.manifest.dataset_version,
        dataset_manifest_sha256=loaded_dataset.manifest_sha256,
        benchmark_mode=active_mode,
        rubric_version=next(iter(rubric_versions)),
        rubric_sha256=next(iter(rubric_hashes)),
        judge_record_index_sha256=(loaded_index.index_sha256 if loaded_index is not None else None),
        groups=group_results,
        overall=overall,
        splits={
            split: _aggregate_metrics(item for item in group_results if item.split is split)
            for split in DatasetSplit
            if any(item.split is split for item in group_results)
        },
        warnings=warnings,
    )


def _summarize_report(entry: DatasetReportEntry, evaluation: EvaluationResult) -> BenchmarkReportResult:
    observed = {
        finding.error_code
        for finding in evaluation.findings
        if finding.status is FindingStatus.FAILED and finding.error_code is not None
    }
    expected = set(entry.expected_error_codes)
    return BenchmarkReportResult(
        report_id=entry.report_id,
        quality_tier=entry.quality_tier,
        case_id=evaluation.case_id,
        report_sha256=evaluation.report_sha256,
        evaluation_mode=evaluation.evaluation_mode,
        status=evaluation.status,
        provisional=evaluation.provisional,
        ranking_eligible=evaluation.overall_score is not None and not evaluation.provisional,
        assessed_weight=evaluation.assessed_weight,
        overall_score=evaluation.overall_score,
        quality_band=evaluation.quality_band,
        applied_hard_cap=evaluation.applied_hard_cap,
        judge_record_sha256=entry.judge_record_sha256,
        expected_error_codes=sorted(expected, key=str),
        observed_error_codes=sorted(observed, key=str),
        detected_expected_error_codes=sorted(expected & observed, key=str),
        missing_expected_error_codes=sorted(expected - observed, key=str),
        unexpected_error_codes=sorted(observed - expected, key=str),
    )


def _group_metrics(reports: list[BenchmarkReportResult]) -> GroupOrderingMetrics:
    ordered = [report for report in reports if report.quality_tier in _ORDERED_TIERS]
    expected_pairs = [
        pair
        for pair in combinations(ordered, 2)
        if _ORDERED_TIERS[pair[0].quality_tier] != _ORDERED_TIERS[pair[1].quality_tier]
    ]
    evaluated_pairs = 0
    correct_pairs = 0
    tied_pairs = 0
    for left, right in expected_pairs:
        if not left.ranking_eligible or not right.ranking_eligible:
            continue
        assert left.overall_score is not None and right.overall_score is not None
        evaluated_pairs += 1
        if left.overall_score == right.overall_score:
            tied_pairs += 1
            continue
        expected_left_higher = _ORDERED_TIERS[left.quality_tier] > _ORDERED_TIERS[right.quality_tier]
        if (left.overall_score > right.overall_score) is expected_left_higher:
            correct_pairs += 1

    ranking_eligible_count = sum(report.ranking_eligible for report in ordered)
    complete_evaluable = evaluated_pairs == len(expected_pairs)
    expected_errors = sum(len(report.expected_error_codes) for report in reports)
    detected_errors = sum(len(report.detected_expected_error_codes) for report in reports)
    unexpected_errors = sum(len(report.unexpected_error_codes) for report in reports)
    return GroupOrderingMetrics(
        report_count=len(reports),
        ranking_candidate_report_count=len(ordered),
        ranking_eligible_report_count=ranking_eligible_count,
        ranking_score_coverage=_ratio(ranking_eligible_count, len(ordered)) or 0.0,
        expected_pair_count=len(expected_pairs),
        evaluated_pair_count=evaluated_pairs,
        pair_coverage=_ratio(evaluated_pairs, len(expected_pairs)) or 0.0,
        correct_pair_count=correct_pairs,
        tied_pair_count=tied_pairs,
        pairwise_accuracy=_ratio(correct_pairs, evaluated_pairs),
        complete_order_evaluable=complete_evaluable,
        complete_order_correct=(correct_pairs == len(expected_pairs)) if complete_evaluable else None,
        spearman_correlation=_spearman(ordered) if complete_evaluable else None,
        expected_error_count=expected_errors,
        detected_expected_error_count=detected_errors,
        unexpected_error_count=unexpected_errors,
        error_label_recall=_ratio(detected_errors, expected_errors),
    )


def _aggregate_metrics(groups: Iterable[BenchmarkGroupResult]) -> AggregateBenchmarkMetrics:
    materialized = list(groups)
    report_count = sum(group.metrics.report_count for group in materialized)
    candidate_reports = sum(group.metrics.ranking_candidate_report_count for group in materialized)
    eligible_reports = sum(group.metrics.ranking_eligible_report_count for group in materialized)
    expected_pairs = sum(group.metrics.expected_pair_count for group in materialized)
    evaluated_pairs = sum(group.metrics.evaluated_pair_count for group in materialized)
    correct_pairs = sum(group.metrics.correct_pair_count for group in materialized)
    complete_evaluable = [group for group in materialized if group.metrics.complete_order_evaluable]
    complete_correct = sum(group.metrics.complete_order_correct is True for group in complete_evaluable)
    correlations = [
        group.metrics.spearman_correlation for group in materialized if group.metrics.spearman_correlation is not None
    ]
    expected_errors = sum(group.metrics.expected_error_count for group in materialized)
    detected_errors = sum(group.metrics.detected_expected_error_count for group in materialized)
    return AggregateBenchmarkMetrics(
        group_count=len(materialized),
        report_count=report_count,
        ranking_candidate_report_count=candidate_reports,
        ranking_eligible_report_count=eligible_reports,
        ranking_score_coverage=_ratio(eligible_reports, candidate_reports),
        expected_pair_count=expected_pairs,
        evaluated_pair_count=evaluated_pairs,
        pair_coverage=_ratio(evaluated_pairs, expected_pairs),
        correct_pair_count=correct_pairs,
        tied_pair_count=sum(group.metrics.tied_pair_count for group in materialized),
        pairwise_accuracy=_ratio(correct_pairs, evaluated_pairs),
        complete_order_evaluable_group_count=len(complete_evaluable),
        complete_order_correct_group_count=complete_correct,
        complete_order_coverage=_ratio(len(complete_evaluable), len(materialized)),
        complete_order_accuracy=_ratio(complete_correct, len(complete_evaluable)),
        spearman_evaluable_group_count=len(correlations),
        macro_spearman_correlation=round(statistics.fmean(correlations), 6) if correlations else None,
        expected_error_count=expected_errors,
        detected_expected_error_count=detected_errors,
        unexpected_error_count=sum(group.metrics.unexpected_error_count for group in materialized),
        error_label_recall=_ratio(detected_errors, expected_errors),
    )


def _spearman(reports: list[BenchmarkReportResult]) -> float | None:
    if len(reports) < 3 or any(not report.ranking_eligible for report in reports):
        return None
    scores = [report.overall_score for report in reports]
    assert all(score is not None for score in scores)
    expected = [float(_ORDERED_TIERS[report.quality_tier]) for report in reports]
    score_values = [float(score) for score in scores if score is not None]
    expected_ranks = _average_ranks(expected)
    score_ranks = _average_ranks(score_values)
    expected_mean = statistics.fmean(expected_ranks)
    score_mean = statistics.fmean(score_ranks)
    numerator = sum(
        (left - expected_mean) * (right - score_mean) for left, right in zip(expected_ranks, score_ranks, strict=True)
    )
    left_sum = sum((value - expected_mean) ** 2 for value in expected_ranks)
    right_sum = sum((value - score_mean) ** 2 for value in score_ranks)
    if left_sum == 0 or right_sum == 0:
        return None
    return round(numerator / math.sqrt(left_sum * right_sum), 6)


def _average_ranks(values: list[float]) -> list[float]:
    ranked = [0.0] * len(values)
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for original_index, _ in ordered[index:end]:
            ranked[original_index] = average_rank
        index = end
    return ranked


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)
