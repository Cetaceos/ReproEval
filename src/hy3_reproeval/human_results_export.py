"""Deterministic, de-identified export of final human-consensus results."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import __version__
from .benchmark import DatasetBenchmarkResult
from .consensus import AnnotationConsensusResult
from .errors import EvaluationInputError
from .models import DimensionId, StrictModel

MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MANIFEST_NAME = "export_manifest.json"
PublicHumanResultPath = Literal[
    "consensus_dimensions.csv",
    "consensus_reports.csv",
    "run_metrics.csv",
    "summary.md",
    "system_human_comparison.csv",
    "tier_metrics.csv",
]


class PublicHumanResultFile(StrictModel):
    path: PublicHumanResultPath
    bytes: int = Field(ge=1, le=MAX_OUTPUT_BYTES)
    sha256: str = Field(pattern=r"^[A-F0-9]{64}$")


class HumanResultsExportManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    consensus_input_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    benchmark_input_sha256s: list[str] = Field(min_length=2)
    judge_record_index_sha256s: list[str] = Field(min_length=2)
    judge_run_ids: list[str] = Field(min_length=2)
    report_count: int = Field(ge=1)
    dimension_count: int = Field(ge=1)
    comparison_count: int = Field(ge=1)
    tier_metric_count: int = Field(ge=1)
    outputs: list[PublicHumanResultFile] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_inventory(self) -> HumanResultsExportManifest:
        run_count = len(self.benchmark_input_sha256s)
        if not (run_count == len(self.judge_record_index_sha256s) == len(self.judge_run_ids)):
            raise ValueError("human result lineage lists must have equal lengths")
        if len(set(self.benchmark_input_sha256s)) != run_count:
            raise ValueError("Benchmark input fingerprints must be unique")
        if len(set(self.judge_record_index_sha256s)) != run_count:
            raise ValueError("Judge Record Index fingerprints must be unique")
        if len(set(self.judge_run_ids)) != run_count:
            raise ValueError("Judge run IDs must be unique")
        for label, values in (
            ("Benchmark input", self.benchmark_input_sha256s),
            ("Judge Record Index", self.judge_record_index_sha256s),
        ):
            if any(
                len(value) != 64 or any(character not in "0123456789ABCDEF" for character in value) for value in values
            ):
                raise ValueError(f"{label} fingerprints must be uppercase SHA-256 values")
        if any(
            len(value) != 32 or any(character not in "0123456789abcdef" for character in value)
            for value in self.judge_run_ids
        ):
            raise ValueError("Judge run IDs must be lowercase 32-character hexadecimal values")
        expected = {
            "consensus_dimensions.csv",
            "consensus_reports.csv",
            "run_metrics.csv",
            "summary.md",
            "system_human_comparison.csv",
            "tier_metrics.csv",
        }
        paths = [item.path for item in self.outputs]
        if set(paths) != expected or paths != sorted(paths):
            raise ValueError("human result outputs must match the canonical sorted inventory")
        if self.dimension_count != self.report_count * len(DimensionId):
            raise ValueError("dimension_count must cover every Rubric dimension for every report")
        if self.comparison_count != self.report_count * run_count:
            raise ValueError("comparison_count must cover every report in every Judge run")
        if self.tier_metric_count != run_count * 3:
            raise ValueError("tier_metric_count must cover high, medium, and low in every Judge run")
        return self


class HumanResultsExport(StrictModel):
    output_root: str
    dataset_id: str
    run_count: int = Field(ge=2)
    report_count: int = Field(ge=1)
    files: list[str]


class HumanResultsVerification(StrictModel):
    output_root: str
    dataset_id: str
    dataset_version: str
    engine_version: str
    run_count: int = Field(ge=2)
    report_count: int = Field(ge=1)
    file_count: Literal[7] = 7
    manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    valid: Literal[True] = True


def export_human_consensus_results(
    consensus_path: str | Path,
    benchmark_paths: list[str | Path],
    output_dir: str | Path,
) -> HumanResultsExport:
    """Validate private lineage and write a de-identified, closed public result bundle."""

    consensus, consensus_payload = _load_consensus(consensus_path)
    if not consensus.consensus_ready:
        raise EvaluationInputError("human consensus is not ready for public export")
    benchmarks_with_payloads = [_load_benchmark(path) for path in benchmark_paths]
    if len(benchmarks_with_payloads) < 2:
        raise EvaluationInputError("human result export requires at least two independent Judge runs")
    benchmarks = [item[0] for item in benchmarks_with_payloads]
    _validate_lineage(consensus, benchmarks)

    report_rows, dimension_rows = _consensus_rows(consensus, benchmarks[0])
    comparison_rows, run_rows, tier_rows = _comparison_rows(consensus, benchmarks)
    payloads = {
        "consensus_reports.csv": _csv_bytes(
            ["group_id", "report_id", "split", "quality_tier", "report_sha256", "assessed_weight", "human_score"],
            report_rows,
        ),
        "consensus_dimensions.csv": _csv_bytes(
            ["group_id", "report_id", "split", "quality_tier", "dimension", "status", "score", "error_codes", "source"],
            dimension_rows,
        ),
        "system_human_comparison.csv": _csv_bytes(
            [
                "run",
                "judge_run_id",
                "report_id",
                "split",
                "quality_tier",
                "human_score",
                "system_score",
                "signed_error",
                "absolute_error",
            ],
            comparison_rows,
        ),
        "run_metrics.csv": _csv_bytes(
            ["run", "judge_run_id", "report_count", "coverage", "spearman", "mean_absolute_error"],
            run_rows,
        ),
        "tier_metrics.csv": _csv_bytes(
            [
                "run",
                "judge_run_id",
                "quality_tier",
                "report_count",
                "mean_human_score",
                "mean_system_score",
                "mean_signed_error",
                "mean_absolute_error",
            ],
            tier_rows,
        ),
        "summary.md": _render_summary(consensus, report_rows, run_rows, tier_rows).encode("utf-8"),
    }
    output_root = Path(output_dir).expanduser().resolve()
    if output_root.exists() and not output_root.is_dir():
        raise EvaluationInputError("human results output path must be a directory")
    if output_root.exists() and any(output_root.iterdir()):
        raise EvaluationInputError("human results output directory must be absent or empty")
    if not output_root.parent.is_dir():
        raise EvaluationInputError(f"human results output parent does not exist: {output_root.parent.as_posix()}")
    output_root.mkdir(exist_ok=True)
    for name, payload in payloads.items():
        (output_root / name).write_bytes(payload)

    manifest = HumanResultsExportManifest(
        engine_version=__version__,
        dataset_id=consensus.dataset_id,
        dataset_version=consensus.dataset_version,
        dataset_manifest_sha256=consensus.dataset_manifest_sha256,
        dataset_freeze_sha256=consensus.dataset_freeze_sha256 or "",
        rubric_version=consensus.rubric_version,
        rubric_sha256=consensus.rubric_sha256,
        consensus_input_sha256=_sha256(consensus_payload),
        benchmark_input_sha256s=[_sha256(item[1]) for item in benchmarks_with_payloads],
        judge_record_index_sha256s=[item.judge_record_index_sha256 or "" for item in benchmarks],
        judge_run_ids=[item.judge_run_id or "" for item in benchmarks],
        report_count=len(report_rows),
        dimension_count=len(dimension_rows),
        comparison_count=len(comparison_rows),
        tier_metric_count=len(tier_rows),
        outputs=[
            PublicHumanResultFile(path=name, bytes=len(payload), sha256=_sha256(payload))
            for name, payload in sorted(payloads.items())
        ],
    )
    (output_root / MANIFEST_NAME).write_bytes(_json_bytes(manifest.model_dump(mode="json")))
    return HumanResultsExport(
        output_root=output_root.as_posix(),
        dataset_id=manifest.dataset_id,
        run_count=len(benchmarks),
        report_count=manifest.report_count,
        files=[*sorted(payloads), MANIFEST_NAME],
    )


def verify_human_consensus_results(output_dir: str | Path) -> HumanResultsVerification:
    """Verify the closed inventory, hashes, schemas, and row counts of a public human-results bundle."""

    output_root = Path(output_dir).expanduser().resolve()
    if not output_root.is_dir():
        raise EvaluationInputError(f"human results directory does not exist: {output_root.as_posix()}")
    manifest_payload = _read_limited(output_root / MANIFEST_NAME, MAX_MANIFEST_BYTES, "human results manifest")
    try:
        manifest = HumanResultsExportManifest.model_validate_json(manifest_payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid human results manifest: {exc}") from exc
    expected = {MANIFEST_NAME, *(item.path for item in manifest.outputs)}
    entries = list(output_root.iterdir())
    if {entry.name for entry in entries} != expected or any(
        not entry.is_file() or entry.is_symlink() for entry in entries
    ):
        raise EvaluationInputError("human results directory does not match the closed manifest inventory")
    for item in manifest.outputs:
        payload = _read_limited(output_root / item.path, MAX_OUTPUT_BYTES, f"human result '{item.path}'")
        if len(payload) != item.bytes or _sha256(payload) != item.sha256:
            raise EvaluationInputError(f"human result fingerprint changed: {item.path}")
    _verify_csv_rows(output_root / "consensus_reports.csv", manifest.report_count)
    _verify_csv_rows(output_root / "consensus_dimensions.csv", manifest.dimension_count)
    _verify_csv_rows(output_root / "system_human_comparison.csv", manifest.comparison_count)
    _verify_csv_rows(output_root / "run_metrics.csv", len(manifest.judge_run_ids))
    _verify_csv_rows(output_root / "tier_metrics.csv", manifest.tier_metric_count)
    return HumanResultsVerification(
        output_root=output_root.as_posix(),
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        engine_version=manifest.engine_version,
        run_count=len(manifest.judge_run_ids),
        report_count=manifest.report_count,
        manifest_sha256=_sha256(manifest_payload),
    )


def _load_consensus(path: str | Path) -> tuple[AnnotationConsensusResult, bytes]:
    payload = _read_limited(Path(path).expanduser().resolve(), MAX_INPUT_BYTES, "annotation consensus")
    try:
        return AnnotationConsensusResult.model_validate_json(payload), payload
    except ValueError as exc:
        raise EvaluationInputError(f"invalid annotation consensus: {exc}") from exc


def _load_benchmark(path: str | Path) -> tuple[DatasetBenchmarkResult, bytes]:
    payload = _read_limited(Path(path).expanduser().resolve(), MAX_INPUT_BYTES, "Dataset Benchmark result")
    try:
        return DatasetBenchmarkResult.model_validate_json(payload), payload
    except ValueError as exc:
        raise EvaluationInputError(f"invalid Dataset Benchmark result: {exc}") from exc


def _validate_lineage(consensus: AnnotationConsensusResult, benchmarks: list[DatasetBenchmarkResult]) -> None:
    if consensus.dataset_freeze_sha256 is None:
        raise EvaluationInputError("public human result export requires a Dataset Freeze binding")
    identity = (
        consensus.dataset_id,
        consensus.dataset_version,
        consensus.dataset_manifest_sha256,
        consensus.dataset_freeze_sha256,
        consensus.rubric_version,
        consensus.rubric_sha256,
    )
    target = {report.report_id: report for report in consensus.reports}
    if len(target) != consensus.target_report_count:
        raise EvaluationInputError("consensus report inventory is incomplete or duplicated")
    if any(report.human_score is None for report in target.values()):
        raise EvaluationInputError("consensus contains a report without a publishable human score")
    run_ids: set[str] = set()
    index_hashes: set[str] = set()
    baseline_tiers: dict[str, str] | None = None
    for benchmark in benchmarks:
        actual = (
            benchmark.dataset_id,
            benchmark.dataset_version,
            benchmark.dataset_manifest_sha256,
            benchmark.dataset_freeze_sha256,
            benchmark.rubric_version,
            benchmark.rubric_sha256,
        )
        if actual != identity:
            raise EvaluationInputError("Benchmark result does not match the final human consensus lineage")
        if benchmark.judge_run_id is None or benchmark.judge_record_index_sha256 is None:
            raise EvaluationInputError("Benchmark result is not bound to an online Judge run")
        if benchmark.judge_run_id in run_ids or benchmark.judge_record_index_sha256 in index_hashes:
            raise EvaluationInputError("Benchmark Judge runs and indexes must be independent")
        run_ids.add(benchmark.judge_run_id)
        index_hashes.add(benchmark.judge_record_index_sha256)
        reports = {
            item.report_id: (group.group_id, group.split, item) for group in benchmark.groups for item in group.reports
        }
        tiers = {report_id: reports[report_id][2].quality_tier.value for report_id in target if report_id in reports}
        if baseline_tiers is None:
            baseline_tiers = tiers
        elif tiers != baseline_tiers:
            raise EvaluationInputError("Benchmark quality tiers changed across Judge runs")
        for report_id, human in target.items():
            system_entry = reports.get(report_id)
            if system_entry is None:
                raise EvaluationInputError(f"Benchmark report does not match consensus report '{report_id}'")
            group_id, split, system = system_entry
            if group_id != human.group_id or split is not human.split or system.report_sha256 != human.report_sha256:
                raise EvaluationInputError(f"Benchmark report does not match consensus report '{report_id}'")
            if system.provisional or system.overall_score is None:
                raise EvaluationInputError(f"Benchmark report is not fully scored: {report_id}")


def _consensus_rows(
    consensus: AnnotationConsensusResult,
    benchmark: DatasetBenchmarkResult,
) -> tuple[list[list[object]], list[list[object]]]:
    system = {item.report_id: item for group in benchmark.groups for item in group.reports}
    report_rows: list[list[object]] = []
    dimension_rows: list[list[object]] = []
    for report in sorted(consensus.reports, key=lambda item: item.report_id):
        tier = system[report.report_id].quality_tier.value
        report_rows.append(
            [
                report.group_id,
                report.report_id,
                report.split.value,
                tier,
                report.report_sha256,
                _number(report.assessed_weight),
                _number(report.human_score),
            ]
        )
        for dimension in sorted(report.dimensions, key=lambda item: item.dimension.value):
            dimension_rows.append(
                [
                    report.group_id,
                    report.report_id,
                    report.split.value,
                    tier,
                    dimension.dimension.value,
                    dimension.status.value,
                    _number(dimension.score),
                    ";".join(item.value for item in dimension.error_codes),
                    dimension.source.value,
                ]
            )
    return report_rows, dimension_rows


def _comparison_rows(
    consensus: AnnotationConsensusResult,
    benchmarks: list[DatasetBenchmarkResult],
) -> tuple[list[list[object]], list[list[object]], list[list[object]]]:
    human = {report.report_id: report for report in consensus.reports}
    comparison_rows: list[list[object]] = []
    run_rows: list[list[object]] = []
    tier_rows: list[list[object]] = []
    for run, benchmark in enumerate(benchmarks, start=1):
        system = {item.report_id: item for group in benchmark.groups for item in group.reports}
        human_scores: list[float] = []
        system_scores: list[float] = []
        for report_id in sorted(human):
            human_report = human[report_id]
            system_report = system[report_id]
            human_score = float(human_report.human_score or 0)
            system_score = float(system_report.overall_score or 0)
            human_scores.append(human_score)
            system_scores.append(system_score)
            comparison_rows.append(
                [
                    run,
                    benchmark.judge_run_id,
                    report_id,
                    human_report.split.value,
                    system_report.quality_tier.value,
                    _number(human_score),
                    _number(system_score),
                    _number(system_score - human_score),
                    _number(abs(system_score - human_score)),
                ]
            )
        run_rows.append(
            [
                run,
                benchmark.judge_run_id,
                len(human_scores),
                _number(len(human_scores) / consensus.target_report_count),
                _number(_spearman(system_scores, human_scores)),
                _number(
                    statistics.fmean(abs(left - right) for left, right in zip(system_scores, human_scores, strict=True))
                ),
            ]
        )
        for tier in ("high", "medium", "low"):
            tier_comparisons = [row for row in comparison_rows if row[0] == run and row[4] == tier]
            human_by_tier = [float(row[5]) for row in tier_comparisons]
            system_by_tier = [float(row[6]) for row in tier_comparisons]
            signed_by_tier = [float(row[7]) for row in tier_comparisons]
            absolute_by_tier = [float(row[8]) for row in tier_comparisons]
            if not tier_comparisons:
                raise EvaluationInputError(f"Judge run {run} has no target reports for quality tier '{tier}'")
            tier_rows.append(
                [
                    run,
                    benchmark.judge_run_id,
                    tier,
                    len(tier_comparisons),
                    _number(statistics.fmean(human_by_tier)),
                    _number(statistics.fmean(system_by_tier)),
                    _number(statistics.fmean(signed_by_tier)),
                    _number(statistics.fmean(absolute_by_tier)),
                ]
            )
    return comparison_rows, run_rows, tier_rows


def _render_summary(
    consensus: AnnotationConsensusResult,
    report_rows: list[list[object]],
    run_rows: list[list[object]],
    tier_rows: list[list[object]],
) -> str:
    pooled = consensus.agreement.pooled_metrics
    tier_scores: dict[str, list[float]] = {}
    for row in report_rows:
        tier_scores.setdefault(str(row[3]), []).append(float(row[6]))
    lines = [
        "# ReproEval De-identified Human Consensus Results",
        "",
        "## Experiment identity",
        "",
        f"- Dataset: `{consensus.dataset_id}` version `{consensus.dataset_version}`",
        f"- Dataset Freeze SHA-256: `{consensus.dataset_freeze_sha256}`",
        f"- Rubric: `{consensus.rubric_version}` (`{consensus.rubric_sha256}`)",
        f"- Consensus reports: {consensus.consensus_report_count}/{consensus.target_report_count}",
        f"- Resolved adjudication items: {consensus.adjudication_resolved_item_count}/"
        f"{consensus.adjudication_required_item_count}",
        "",
        "## Human agreement",
        "",
        f"- Exact dimension-score agreement: {_percent(pooled.exact_score_agreement)}",
        f"- Within-one-point agreement: {_percent(pooled.within_one_point_agreement)}",
        f"- Quadratic-weighted Cohen's Kappa: {_number(pooled.quadratic_weighted_kappa)}",
        f"- Mean absolute dimension-score difference: {_number(pooled.mean_absolute_score_difference)}",
        "",
        "## Final consensus by registered quality tier",
        "",
        "| Tier | Reports | Mean human score |",
        "| --- | ---: | ---: |",
    ]
    for tier in ("high", "medium", "low"):
        scores = tier_scores.get(tier, [])
        lines.append(f"| `{tier}` | {len(scores)} | {_number(statistics.fmean(scores) if scores else None)} |")
    lines.extend(
        [
            "",
            "## System-human comparison",
            "",
            "| Run | Coverage | Spearman | MAE |",
            "| ---: | ---: | ---: | ---: |",
        ]
    )
    for row in run_rows:
        lines.append(f"| {row[0]} | {_percent(float(row[3]))} | {row[4]} | {row[5]} |")
    lines.extend(
        [
            "",
            "## Calibration by registered quality tier",
            "",
            "Positive signed error means that the system score is higher than the final human consensus.",
            "",
            "| Run | Tier | Mean human | Mean system | Mean signed error | MAE |",
            "| ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in tier_rows:
        lines.append(f"| {row[0]} | `{row[2]}` | {row[4]} | {row[5]} | {row[6]} | {row[7]} |")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- The source papers are real, but the tiered reports are curator drafts and registered Mutations.",
            "- The Pilot evaluates reproducibility readiness; it did not execute third-party software.",
            "- Reviewer identity and expertise are self-attested, not externally certified.",
            "- This bundle intentionally excludes reviewer IDs, Bundle IDs, rationales, private paths, "
            "and raw model responses.",
            "- Strong rank correlation does not establish score calibration or scientific correctness.",
        ]
    )
    return "\n".join(lines) + "\n"


def _spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_ranks = _ranks(left)
    right_ranks = _ranks(right)
    left_mean = statistics.fmean(left_ranks)
    right_mean = statistics.fmean(right_ranks)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left_ranks, right_ranks, strict=True))
    denominator = math.sqrt(
        sum((value - left_mean) ** 2 for value in left_ranks) * sum((value - right_mean) ** 2 for value in right_ranks)
    )
    return round(numerator / denominator, 6) if denominator else None


def _ranks(values: list[float]) -> list[float]:
    ranks = [0.0] * len(values)
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2
        for original_index, _ in ordered[index:end]:
            ranks[original_index] = rank
        index = end
    return ranks


def _csv_bytes(header: list[str], rows: list[list[object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _verify_csv_rows(path: Path, expected_count: int) -> None:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise EvaluationInputError(f"cannot parse public human result CSV '{path.name}': {exc}") from exc
    if len(rows) != expected_count:
        raise EvaluationInputError(f"public human result row count changed: {path.name}")


def _read_limited(path: Path, limit: int, label: str) -> bytes:
    try:
        if not path.is_file() or path.is_symlink():
            raise EvaluationInputError(f"{label} is not a regular file: {path.as_posix()}")
        if path.stat().st_size > limit:
            raise EvaluationInputError(f"{label} exceeds the {limit}-byte limit")
        return path.read_bytes()
    except OSError as exc:
        raise EvaluationInputError(f"cannot read {label}: {exc}") from exc


def _number(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.4f}%"


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()
