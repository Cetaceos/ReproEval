"""Deterministic review-bundle export for Benchmark and Stability results."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from . import __version__
from .benchmark import DatasetBenchmarkResult
from .errors import EvaluationInputError
from .models import StrictModel
from .stability import (
    MAX_BENCHMARK_RESULT_BYTES,
    BenchmarkStabilityResult,
    analyze_benchmark_stability,
)

MAX_STABILITY_RESULT_BYTES = 32 * 1024 * 1024
MAX_EXPORT_MANIFEST_BYTES = 1024 * 1024
MAX_EXPORTED_RESULT_BYTES = 16 * 1024 * 1024
EXPORT_MANIFEST_NAME = "export_manifest.json"
ExportedResultPath = Literal[
    "benchmark_runs.csv",
    "dimension_stability.csv",
    "report_stability.csv",
    "summary.md",
]


class ResultsExport(StrictModel):
    output_root: str
    dataset_id: str
    run_count: int = Field(ge=2)
    files: list[str]


class ExportedResultFile(StrictModel):
    path: ExportedResultPath
    bytes: int = Field(ge=1, le=MAX_EXPORTED_RESULT_BYTES)
    sha256: str = Field(pattern=r"^[A-F0-9]{64}$")


class ResultsExportManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    run_count: int = Field(ge=2)
    stability_result_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    benchmark_result_sha256s: list[str] = Field(min_length=2)
    judge_record_index_sha256s: list[str] = Field(min_length=2)
    judge_run_ids: list[str] = Field(min_length=2)
    outputs: list[ExportedResultFile] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_inventory(self) -> ResultsExportManifest:
        if not (
            len(self.benchmark_result_sha256s)
            == len(self.judge_record_index_sha256s)
            == len(self.judge_run_ids)
            == self.run_count
        ):
            raise ValueError("export lineage lists must match run_count")
        for label, values in (
            ("Benchmark result", self.benchmark_result_sha256s),
            ("Judge Record Index", self.judge_record_index_sha256s),
        ):
            if any(
                len(value) != 64 or any(character not in "0123456789ABCDEF" for character in value) for value in values
            ):
                raise ValueError(f"{label} fingerprints must be uppercase SHA-256 values")
            if len(values) != len(set(values)):
                raise ValueError(f"{label} fingerprints must be unique")
        if len(self.judge_run_ids) != len(set(self.judge_run_ids)):
            raise ValueError("Judge run IDs must be unique")
        expected_paths = {
            "benchmark_runs.csv",
            "dimension_stability.csv",
            "report_stability.csv",
            "summary.md",
        }
        paths = [item.path for item in self.outputs]
        if set(paths) != expected_paths or paths != sorted(paths):
            raise ValueError("export outputs must contain the canonical sorted public result inventory")
        return self


class ResultsExportVerification(StrictModel):
    output_root: str
    dataset_id: str
    dataset_version: str
    engine_version: str
    run_count: int = Field(ge=2)
    file_count: Literal[5] = 5
    manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    valid: Literal[True] = True


def export_benchmark_results(
    benchmark_paths: list[str | Path],
    stability_path: str | Path,
    output_dir: str | Path,
) -> ResultsExport:
    """Verify one repeated-run lineage and write a deterministic Markdown/CSV review bundle."""

    stability, stability_sha256 = _load_stability(stability_path)
    recomputed = analyze_benchmark_stability(benchmark_paths)
    if recomputed.model_dump(exclude={"engine_version"}) != stability.model_dump(exclude={"engine_version"}):
        raise EvaluationInputError("Stability result does not match the supplied Benchmark inputs")
    benchmarks = [_load_benchmark(path) for path in benchmark_paths]
    output_root = Path(output_dir).expanduser().resolve()
    if output_root.exists() and not output_root.is_dir():
        raise EvaluationInputError("results export output path must be a directory")
    if output_root.exists() and any(output_root.iterdir()):
        raise EvaluationInputError("results export directory must be absent or empty")
    if not output_root.parent.is_dir():
        raise EvaluationInputError(f"results export parent directory does not exist: {output_root.parent.as_posix()}")
    output_root.mkdir(exist_ok=True)

    payloads = {
        "summary.md": _render_summary(benchmarks, stability).encode("utf-8"),
        "benchmark_runs.csv": _render_runs_csv(benchmarks).encode("utf-8"),
        "report_stability.csv": _render_reports_csv(stability).encode("utf-8"),
        "dimension_stability.csv": _render_dimensions_csv(stability).encode("utf-8"),
    }
    for name, payload in payloads.items():
        (output_root / name).write_bytes(payload)
    manifest = ResultsExportManifest(
        engine_version=__version__,
        dataset_id=stability.dataset_id,
        dataset_version=stability.dataset_version,
        dataset_manifest_sha256=stability.dataset_manifest_sha256,
        dataset_freeze_sha256=stability.dataset_freeze_sha256,
        rubric_version=stability.rubric_version,
        rubric_sha256=stability.rubric_sha256,
        run_count=stability.run_count,
        stability_result_sha256=stability_sha256,
        benchmark_result_sha256s=stability.benchmark_result_sha256s,
        judge_record_index_sha256s=stability.judge_record_index_sha256s,
        judge_run_ids=stability.judge_run_ids,
        outputs=[
            ExportedResultFile(path=name, bytes=len(payload), sha256=_sha256(payload))
            for name, payload in sorted(payloads.items())
        ],
    )
    (output_root / EXPORT_MANIFEST_NAME).write_bytes(_json_bytes(manifest.model_dump(mode="json")))
    return ResultsExport(
        output_root=output_root.as_posix(),
        dataset_id=stability.dataset_id,
        run_count=stability.run_count,
        files=[*sorted(payloads), EXPORT_MANIFEST_NAME],
    )


def verify_results_export(output_dir: str | Path) -> ResultsExportVerification:
    """Verify the closed public inventory and hashes of one result export bundle."""

    output_root = Path(output_dir).expanduser().resolve()
    if not output_root.is_dir():
        raise EvaluationInputError(f"results export directory does not exist: {output_root.as_posix()}")
    manifest_path = output_root / EXPORT_MANIFEST_NAME
    manifest_payload = _read_limited(manifest_path, MAX_EXPORT_MANIFEST_BYTES, "results export manifest")
    try:
        manifest = ResultsExportManifest.model_validate_json(manifest_payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid results export manifest: {exc}") from exc
    expected_paths = {EXPORT_MANIFEST_NAME, *(item.path for item in manifest.outputs)}
    entries = list(output_root.iterdir())
    actual_paths = {entry.name for entry in entries}
    if actual_paths != expected_paths or any(not entry.is_file() or entry.is_symlink() for entry in entries):
        raise EvaluationInputError("results export directory does not match the closed manifest inventory")
    for item in manifest.outputs:
        payload = _read_limited(output_root / item.path, MAX_EXPORTED_RESULT_BYTES, f"exported result '{item.path}'")
        if len(payload) != item.bytes or _sha256(payload) != item.sha256:
            raise EvaluationInputError(f"exported result fingerprint changed: {item.path}")
    return ResultsExportVerification(
        output_root=output_root.as_posix(),
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        engine_version=manifest.engine_version,
        run_count=manifest.run_count,
        manifest_sha256=_sha256(manifest_payload),
    )


def _load_benchmark(path: str | Path) -> DatasetBenchmarkResult:
    resolved = Path(path).expanduser().resolve()
    payload = _read_limited(resolved, MAX_BENCHMARK_RESULT_BYTES, "Dataset Benchmark result")
    try:
        return DatasetBenchmarkResult.model_validate_json(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid Dataset Benchmark result: {exc}") from exc


def _load_stability(path: str | Path) -> tuple[BenchmarkStabilityResult, str]:
    resolved = Path(path).expanduser().resolve()
    payload = _read_limited(resolved, MAX_STABILITY_RESULT_BYTES, "Benchmark Stability result")
    try:
        return BenchmarkStabilityResult.model_validate_json(payload), _sha256(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid Benchmark Stability result: {exc}") from exc


def _render_summary(benchmarks: list[DatasetBenchmarkResult], stability: BenchmarkStabilityResult) -> str:
    overall = stability.overall
    lines = [
        "# ReproEval Benchmark Review Bundle",
        "",
        "## Experiment identity",
        "",
        f"- Dataset: `{stability.dataset_id}` version `{stability.dataset_version}`",
        f"- Dataset Freeze SHA-256: `{stability.dataset_freeze_sha256}`",
        f"- Rubric: `{stability.rubric_version}` (`{stability.rubric_sha256}`)",
        f"- Independent Judge runs: {stability.run_count}",
        "",
        "## Benchmark runs",
        "",
        "| Run | Pairwise accuracy | Complete-order accuracy | Macro Spearman | Error-label recall | "
        "Adversarial detection |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for index, benchmark in enumerate(benchmarks, start=1):
        metrics = benchmark.overall
        lines.append(
            f"| {index} | {_pct(metrics.pairwise_accuracy)} | {_pct(metrics.complete_order_accuracy)} | "
            f"{_number(metrics.macro_spearman_correlation)} | {_pct(metrics.error_label_recall)} | "
            f"{_pct(metrics.adversarial.attack_detection_rate)} |"
        )
    lines.extend(
        [
            "",
            "## Repeated-run stability",
            "",
            f"- Fully scored reports: {overall.fully_scored_report_count}/{overall.report_count}",
            f"- Mean report score standard deviation: {_number(overall.mean_report_score_stddev)}",
            f"- Maximum report score standard deviation: {_number(overall.maximum_report_score_stddev)}",
            f"- Preregistered standard-deviation target: <= {_number(overall.score_stddev_target)} "
            f"(`{'met' if overall.score_stddev_target_met else 'not met'}`)",
            f"- Quality-band flips: {overall.quality_band_flip_count}/{overall.report_count}",
            f"- Ranking-eligibility flips: {overall.ranking_eligibility_flip_count}",
            f"- Evaluation-status flips: {overall.evaluation_status_flip_count}",
            "",
            "## Dimension stability",
            "",
            "| Dimension | Coverage | Mean report stddev | Maximum report stddev | Status flips |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in overall.dimensions:
        lines.append(
            f"| `{item.dimension.value}` | {_pct(item.fully_assessed_report_coverage)} | "
            f"{_number(item.mean_report_score_stddev)} | {_number(item.maximum_report_score_stddev)} | "
            f"{item.report_status_flip_count} |"
        )
    volatile = sorted(
        (report for report in stability.reports if (report.score_stddev or 0) > 0),
        key=lambda report: (-(report.score_stddev or 0), report.report_id),
    )
    lines.extend(["", "## Non-zero report variation", ""])
    if volatile:
        lines.extend(
            [
                "| Report | Tier | Mean score | Score stddev | Score range | Band flip |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for report in volatile:
            lines.append(
                f"| `{report.report_id}` | `{report.quality_tier.value}` | {_number(report.mean_score)} | "
                f"{_number(report.score_stddev)} | {_number(report.score_range)} | "
                f"{'yes' if report.quality_band_flip else 'no'} |"
            )
    else:
        lines.append("No report had non-zero total-score variation.")
    lines.extend(["", "## Boundaries", ""])
    lines.extend(f"- {warning}" for warning in stability.warnings)
    lines.append("- Synthetic labels and model stability are not substitutes for blinded expert annotation.")
    return "\n".join(lines) + "\n"


def _render_runs_csv(benchmarks: list[DatasetBenchmarkResult]) -> str:
    rows = []
    for index, benchmark in enumerate(benchmarks, start=1):
        metrics = benchmark.overall
        rows.append(
            [
                index,
                benchmark.judge_run_id,
                benchmark.judge_record_index_sha256,
                metrics.report_count,
                metrics.ranking_score_coverage,
                metrics.pairwise_accuracy,
                metrics.complete_order_accuracy,
                metrics.macro_spearman_correlation,
                metrics.error_label_recall,
                metrics.adversarial.report_detection_rate,
                metrics.adversarial.attack_detection_rate,
                metrics.adversarial.attack_false_acceptance_rate,
                metrics.adversarial.error_label_recall,
            ]
        )
    return _csv(
        [
            "run",
            "judge_run_id",
            "judge_record_index_sha256",
            "report_count",
            "ranking_score_coverage",
            "pairwise_accuracy",
            "complete_order_accuracy",
            "macro_spearman_correlation",
            "error_label_recall",
            "adversarial_report_detection_rate",
            "adversarial_attack_detection_rate",
            "adversarial_attack_false_acceptance_rate",
            "adversarial_error_label_recall",
        ],
        rows,
    )


def _render_reports_csv(stability: BenchmarkStabilityResult) -> str:
    rows = [
        [
            report.report_id,
            report.group_id,
            report.split.value,
            report.quality_tier.value,
            report.mean_score,
            report.score_stddev,
            report.score_range,
            report.score_coverage,
            report.quality_band_flip,
            report.ranking_eligibility_flip,
            report.evaluation_status_flip,
        ]
        for report in stability.reports
    ]
    return _csv(
        [
            "report_id",
            "group_id",
            "split",
            "quality_tier",
            "mean_score",
            "score_stddev",
            "score_range",
            "score_coverage",
            "quality_band_flip",
            "ranking_eligibility_flip",
            "evaluation_status_flip",
        ],
        rows,
    )


def _render_dimensions_csv(stability: BenchmarkStabilityResult) -> str:
    return _csv(
        [
            "dimension",
            "report_count",
            "fully_assessed_report_count",
            "fully_assessed_report_coverage",
            "mean_report_score_stddev",
            "maximum_report_score_stddev",
            "report_status_flip_count",
        ],
        [
            [
                item.dimension.value,
                item.report_count,
                item.fully_assessed_report_count,
                item.fully_assessed_report_coverage,
                item.mean_report_score_stddev,
                item.maximum_report_score_stddev,
                item.report_status_flip_count,
            ]
            for item in stability.overall.dimensions
        ],
    )


def _csv(header: list[str], rows: list[list[Any]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue()


def _read_limited(path: Path, maximum_bytes: int, label: str) -> bytes:
    if not path.is_file():
        raise EvaluationInputError(f"{label} does not exist: {path.as_posix()}")
    if path.stat().st_size > maximum_bytes:
        raise EvaluationInputError(f"{label} exceeds {maximum_bytes} bytes")
    return path.read_bytes()


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6g}"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
