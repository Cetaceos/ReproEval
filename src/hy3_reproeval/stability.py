"""Cross-run stability analysis for frozen Dataset Benchmark artifacts."""

from __future__ import annotations

import hashlib
import statistics
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import __version__
from .benchmark import BenchmarkMode, BenchmarkReportResult, DatasetBenchmarkResult
from .dataset import DatasetSplit, QualityTier
from .errors import EvaluationInputError
from .models import DimensionId, DimensionStatus, EvaluationMode, QualityBand, StrictModel

MAX_BENCHMARK_RESULT_BYTES = 32 * 1024 * 1024
REPEATED_RUN_TARGET = 3
SCORE_STDDEV_TARGET = 5.0


class DimensionStability(StrictModel):
    dimension: DimensionId
    run_count: int = Field(ge=2)
    assessed_run_count: int = Field(ge=0)
    assessed_coverage: float = Field(ge=0, le=1)
    mean_score: float | None = Field(default=None, ge=0, le=4)
    score_stddev: float | None = Field(default=None, ge=0)
    score_range: float | None = Field(default=None, ge=0)
    status_flip: bool


class ReportStability(StrictModel):
    report_id: str
    group_id: str
    split: DatasetSplit
    quality_tier: QualityTier
    report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    run_count: int = Field(ge=2)
    score_observation_count: int = Field(ge=0)
    score_coverage: float = Field(ge=0, le=1)
    mean_score: float | None = Field(default=None, ge=0, le=100)
    score_stddev: float | None = Field(default=None, ge=0)
    score_range: float | None = Field(default=None, ge=0)
    quality_bands: list[QualityBand]
    quality_band_flip: bool
    ranking_eligibility_flip: bool
    evaluation_status_flip: bool
    dimensions: list[DimensionStability]

    @model_validator(mode="after")
    def validate_dimension_inventory(self) -> ReportStability:
        if {item.dimension for item in self.dimensions} != set(DimensionId):
            raise ValueError("report stability must contain every Rubric dimension exactly once")
        if len(self.dimensions) != len(DimensionId):
            raise ValueError("report stability dimensions must be unique")
        return self


class DimensionAggregateStability(StrictModel):
    dimension: DimensionId
    report_count: int = Field(ge=1)
    fully_assessed_report_count: int = Field(ge=0)
    fully_assessed_report_coverage: float = Field(ge=0, le=1)
    report_status_flip_count: int = Field(ge=0)
    mean_report_score_stddev: float | None = Field(default=None, ge=0)
    maximum_report_score_stddev: float | None = Field(default=None, ge=0)


class AggregateStabilityMetrics(StrictModel):
    report_count: int = Field(ge=1)
    fully_scored_report_count: int = Field(ge=0)
    fully_scored_report_coverage: float = Field(ge=0, le=1)
    quality_band_flip_count: int = Field(ge=0)
    quality_band_flip_rate: float = Field(ge=0, le=1)
    ranking_eligibility_flip_count: int = Field(ge=0)
    evaluation_status_flip_count: int = Field(ge=0)
    mean_report_score_stddev: float | None = Field(default=None, ge=0)
    maximum_report_score_stddev: float | None = Field(default=None, ge=0)
    score_stddev_target: float = Field(default=SCORE_STDDEV_TARGET, gt=0)
    score_stddev_target_met: bool | None = None
    repeated_run_target: int = Field(default=REPEATED_RUN_TARGET, ge=2)
    repeated_run_target_met: bool
    protocol_coverage_ready: bool
    dimensions: list[DimensionAggregateStability]


class BenchmarkStabilityResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    benchmark_mode: Literal[BenchmarkMode.REPLAY] = BenchmarkMode.REPLAY
    run_count: int = Field(ge=2)
    benchmark_result_sha256s: list[str]
    judge_record_index_sha256s: list[str]
    judge_run_ids: list[str]
    reports: list[ReportStability]
    overall: AggregateStabilityMetrics
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_run_inventory(self) -> BenchmarkStabilityResult:
        inventories = (
            self.benchmark_result_sha256s,
            self.judge_record_index_sha256s,
            self.judge_run_ids,
        )
        if any(len(inventory) != self.run_count for inventory in inventories):
            raise ValueError("stability run_count must match every run inventory")
        if any(len(inventory) != len(set(inventory)) for inventory in inventories):
            raise ValueError("stability run inventories must be unique")
        return self


def analyze_benchmark_stability(paths: Sequence[str | Path]) -> BenchmarkStabilityResult:
    """Analyze independent replay Benchmark runs bound to one frozen Dataset."""

    if len(paths) < 2:
        raise EvaluationInputError("benchmark stability analysis requires at least two result files")
    loaded = [_load_benchmark(path) for path in paths]
    benchmarks = [item[0] for item in loaded]
    result_hashes = [item[1] for item in loaded]
    _validate_run_identity(benchmarks, result_hashes)

    first = benchmarks[0]
    inventories = [_report_inventory(benchmark) for benchmark in benchmarks]
    reports = [_report_stability(report_id, inventories, len(benchmarks)) for report_id in sorted(inventories[0])]
    overall = _aggregate_stability(reports, len(benchmarks))
    warnings: list[str] = []
    if not overall.repeated_run_target_met:
        warnings.append(f"Repeated-run target is {REPEATED_RUN_TARGET}; only {len(benchmarks)} runs were supplied.")
    if not overall.protocol_coverage_ready:
        warnings.append(
            "At least one report or Rubric dimension lacks a score in one or more runs; stability claims are partial."
        )
    warnings.append(
        "Stability describes the supplied frozen runs only; it does not establish expert agreement or generalization."
    )
    return BenchmarkStabilityResult(
        engine_version=__version__,
        dataset_id=first.dataset_id,
        dataset_version=first.dataset_version,
        dataset_manifest_sha256=first.dataset_manifest_sha256,
        dataset_freeze_sha256=first.dataset_freeze_sha256,
        rubric_version=first.rubric_version,
        rubric_sha256=first.rubric_sha256,
        run_count=len(benchmarks),
        benchmark_result_sha256s=result_hashes,
        judge_record_index_sha256s=[_required_index_sha(benchmark) for benchmark in benchmarks],
        judge_run_ids=[_required_run_id(benchmark) for benchmark in benchmarks],
        reports=reports,
        overall=overall,
        warnings=warnings,
    )


def _load_benchmark(path: str | Path) -> tuple[DatasetBenchmarkResult, str]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise EvaluationInputError(f"Dataset Benchmark result does not exist: {resolved.as_posix()}")
    if resolved.stat().st_size > MAX_BENCHMARK_RESULT_BYTES:
        raise EvaluationInputError(f"Dataset Benchmark result exceeds {MAX_BENCHMARK_RESULT_BYTES} bytes")
    payload = resolved.read_bytes()
    try:
        result = DatasetBenchmarkResult.model_validate_json(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid Dataset Benchmark result: {exc}") from exc
    return result, hashlib.sha256(payload).hexdigest().upper()


def _validate_run_identity(benchmarks: list[DatasetBenchmarkResult], result_hashes: list[str]) -> None:
    if len(result_hashes) != len(set(result_hashes)):
        raise EvaluationInputError("benchmark stability inputs must be distinct result files")
    first = benchmarks[0]
    expected_identity = (
        first.dataset_id,
        first.dataset_version,
        first.dataset_manifest_sha256,
        first.dataset_freeze_sha256,
        first.rubric_version,
        first.rubric_sha256,
        first.benchmark_mode,
    )
    if first.benchmark_mode is not BenchmarkMode.REPLAY:
        raise EvaluationInputError("benchmark stability requires replay-mode Benchmark results")
    if first.dataset_freeze_sha256 is None:
        raise EvaluationInputError("benchmark stability requires Dataset Freeze-bound results")
    for benchmark in benchmarks[1:]:
        identity = (
            benchmark.dataset_id,
            benchmark.dataset_version,
            benchmark.dataset_manifest_sha256,
            benchmark.dataset_freeze_sha256,
            benchmark.rubric_version,
            benchmark.rubric_sha256,
            benchmark.benchmark_mode,
        )
        if identity != expected_identity:
            raise EvaluationInputError("benchmark stability inputs do not share one Dataset, Freeze, Rubric, and mode")
    index_hashes = [_required_index_sha(benchmark) for benchmark in benchmarks]
    run_ids = [_required_run_id(benchmark) for benchmark in benchmarks]
    if len(run_ids) != len(set(run_ids)):
        raise EvaluationInputError("each stability input must use a distinct Judge run ID")
    if len(index_hashes) != len(set(index_hashes)):
        raise EvaluationInputError("each stability input must use a distinct Judge Record index")
    inventories = [_inventory_identity(benchmark) for benchmark in benchmarks]
    if any(inventory != inventories[0] for inventory in inventories[1:]):
        raise EvaluationInputError("benchmark stability report inventories do not match")


def _required_index_sha(benchmark: DatasetBenchmarkResult) -> str:
    if benchmark.judge_record_index_sha256 is None:
        raise EvaluationInputError("benchmark stability requires an external Judge Record index for every run")
    return benchmark.judge_record_index_sha256


def _required_run_id(benchmark: DatasetBenchmarkResult) -> str:
    if benchmark.judge_run_id is None:
        raise EvaluationInputError("benchmark stability requires a Judge run ID for every input")
    return benchmark.judge_run_id


def _report_inventory(benchmark: DatasetBenchmarkResult) -> dict[str, tuple[str, DatasetSplit, BenchmarkReportResult]]:
    items = [
        (report.report_id, group.group_id, group.split, report)
        for group in benchmark.groups
        for report in group.reports
    ]
    report_ids = [item[0] for item in items]
    if len(report_ids) != len(set(report_ids)):
        raise EvaluationInputError("benchmark stability input contains duplicate report IDs")
    for report_id, _, _, report in items:
        if report.evaluation_mode is not EvaluationMode.HYBRID:
            raise EvaluationInputError(f"stability report '{report_id}' is not a Hybrid evaluation")
        if report.judge_record_sha256 is None:
            raise EvaluationInputError(f"stability report '{report_id}' is missing its Judge Record hash")
        dimensions = [dimension.dimension for dimension in report.dimensions]
        if len(dimensions) != len(set(dimensions)):
            raise EvaluationInputError(f"stability report '{report_id}' contains duplicate dimensions")
    return {report_id: (group_id, split, report) for report_id, group_id, split, report in items}


def _inventory_identity(benchmark: DatasetBenchmarkResult) -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    return tuple(
        sorted(
            (
                report.report_id,
                group.group_id,
                group.split.value,
                group.scenario.value,
                report.quality_tier.value,
                report.case_id,
                report.report_sha256,
            )
            for group in benchmark.groups
            for report in group.reports
        )
    )


def _report_stability(
    report_id: str,
    inventories: list[dict[str, tuple[str, DatasetSplit, BenchmarkReportResult]]],
    run_count: int,
) -> ReportStability:
    items = [inventory[report_id] for inventory in inventories]
    group_id, split, first = items[0]
    reports = [item[2] for item in items]
    scores = [report.overall_score for report in reports if report.overall_score is not None]
    bands = [report.quality_band for report in reports]
    eligibility = [report.ranking_eligible for report in reports]
    statuses = [report.status for report in reports]
    dimensions_by_run = [{item.dimension: item for item in report.dimensions} for report in reports]
    return ReportStability(
        report_id=report_id,
        group_id=group_id,
        split=split,
        quality_tier=first.quality_tier,
        report_sha256=first.report_sha256,
        run_count=run_count,
        score_observation_count=len(scores),
        score_coverage=_ratio(len(scores), run_count),
        mean_score=_mean(scores),
        score_stddev=_stddev(scores),
        score_range=_range(scores),
        quality_bands=bands,
        quality_band_flip=len(set(bands)) > 1,
        ranking_eligibility_flip=len(set(eligibility)) > 1,
        evaluation_status_flip=len(set(statuses)) > 1,
        dimensions=[_dimension_stability(dimension, dimensions_by_run, run_count) for dimension in DimensionId],
    )


def _dimension_stability(
    dimension: DimensionId,
    dimensions_by_run: list[dict[DimensionId, object]],
    run_count: int,
) -> DimensionStability:
    results = [mapping.get(dimension) for mapping in dimensions_by_run]
    statuses = [getattr(result, "status", DimensionStatus.INSUFFICIENT_EVIDENCE) for result in results]
    scores = [
        float(result.score)
        for result in results
        if result is not None and result.status is DimensionStatus.ASSESSED and result.score is not None
    ]
    return DimensionStability(
        dimension=dimension,
        run_count=run_count,
        assessed_run_count=len(scores),
        assessed_coverage=_ratio(len(scores), run_count),
        mean_score=_mean(scores),
        score_stddev=_stddev(scores),
        score_range=_range(scores),
        status_flip=len(set(statuses)) > 1,
    )


def _aggregate_stability(reports: list[ReportStability], run_count: int) -> AggregateStabilityMetrics:
    score_stddevs = [report.score_stddev for report in reports if report.score_stddev is not None]
    fully_scored = sum(report.score_observation_count == run_count for report in reports)
    dimension_groups: dict[DimensionId, list[DimensionStability]] = defaultdict(list)
    for report in reports:
        for dimension in report.dimensions:
            dimension_groups[dimension.dimension].append(dimension)
    dimensions = [_aggregate_dimension(dimension, dimension_groups[dimension], run_count) for dimension in DimensionId]
    repeated_ready = run_count >= REPEATED_RUN_TARGET
    coverage_ready = fully_scored == len(reports) and all(
        item.fully_assessed_report_count == item.report_count for item in dimensions
    )
    maximum_stddev = max(score_stddevs) if score_stddevs else None
    return AggregateStabilityMetrics(
        report_count=len(reports),
        fully_scored_report_count=fully_scored,
        fully_scored_report_coverage=_ratio(fully_scored, len(reports)),
        quality_band_flip_count=sum(report.quality_band_flip for report in reports),
        quality_band_flip_rate=_ratio(sum(report.quality_band_flip for report in reports), len(reports)),
        ranking_eligibility_flip_count=sum(report.ranking_eligibility_flip for report in reports),
        evaluation_status_flip_count=sum(report.evaluation_status_flip for report in reports),
        mean_report_score_stddev=_mean(score_stddevs),
        maximum_report_score_stddev=maximum_stddev,
        score_stddev_target_met=(maximum_stddev <= SCORE_STDDEV_TARGET) if repeated_ready and coverage_ready else None,
        repeated_run_target_met=repeated_ready,
        protocol_coverage_ready=repeated_ready and coverage_ready,
        dimensions=dimensions,
    )


def _aggregate_dimension(
    dimension: DimensionId,
    reports: list[DimensionStability],
    run_count: int,
) -> DimensionAggregateStability:
    fully_assessed = sum(report.assessed_run_count == run_count for report in reports)
    stddevs = [report.score_stddev for report in reports if report.score_stddev is not None]
    return DimensionAggregateStability(
        dimension=dimension,
        report_count=len(reports),
        fully_assessed_report_count=fully_assessed,
        fully_assessed_report_coverage=_ratio(fully_assessed, len(reports)),
        report_status_flip_count=sum(report.status_flip for report in reports),
        mean_report_score_stddev=_mean(stddevs),
        maximum_report_score_stddev=max(stddevs) if stddevs else None,
    )


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 6) if values else None


def _stddev(values: list[float]) -> float | None:
    return round(statistics.pstdev(values), 6) if len(values) >= 2 else None


def _range(values: list[float]) -> float | None:
    return round(max(values) - min(values), 6) if values else None


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6)
