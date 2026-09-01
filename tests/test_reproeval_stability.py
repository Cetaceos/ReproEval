from __future__ import annotations

import json
from pathlib import Path

import pytest

from hy3_reproeval.benchmark import BenchmarkMode, DatasetBenchmarkResult, run_dataset_benchmark
from hy3_reproeval.cli import main
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.models import DimensionId, DimensionStatus, QualityBand
from hy3_reproeval.stability import BenchmarkStabilityResult, analyze_benchmark_stability


def _public_manifest() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dataset" / "sample_dataset.json"


async def _write_stability_runs(tmp_path: Path) -> list[Path]:
    baseline = await run_dataset_benchmark(_public_manifest(), mode=BenchmarkMode.REPLAY)
    paths: list[Path] = []
    for index, digest_character in enumerate(("A", "B", "C"), start=1):
        run = baseline.model_copy(deep=True)
        run.dataset_freeze_sha256 = "F" * 64
        run.judge_record_index_sha256 = digest_character * 64
        run.judge_run_id = digest_character.lower() * 32
        medium = next(report for report in run.groups[0].reports if report.report_id == "sample-report-medium-v1")
        if index == 2:
            medium.overall_score = 83
            reasoning = next(
                dimension for dimension in medium.dimensions if dimension.dimension is DimensionId.REASONING_CONSISTENCY
            )
            reasoning.score = 2
        if index == 3:
            medium.overall_score = 70
            medium.quality_band = QualityBand.MIXED
            reasoning = next(
                dimension for dimension in medium.dimensions if dimension.dimension is DimensionId.REASONING_CONSISTENCY
            )
            reasoning.score = 1
        path = tmp_path / f"benchmark-run-{index}.json"
        path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


async def test_stability_analyzes_three_distinct_frozen_runs(tmp_path: Path) -> None:
    paths = await _write_stability_runs(tmp_path)

    result = analyze_benchmark_stability(paths)

    assert result.run_count == 3
    assert result.dataset_freeze_sha256 == "F" * 64
    assert result.overall.protocol_coverage_ready is True
    assert result.overall.repeated_run_target_met is True
    assert result.overall.quality_band_flip_count == 1
    assert result.overall.score_stddev_target_met is False
    medium = next(report for report in result.reports if report.report_id == "sample-report-medium-v1")
    assert medium.mean_score == pytest.approx((85 + 83 + 70) / 3, abs=1e-6)
    assert medium.score_stddev is not None and medium.score_stddev > 5
    assert medium.quality_band_flip is True
    reasoning = next(
        dimension for dimension in medium.dimensions if dimension.dimension is DimensionId.REASONING_CONSISTENCY
    )
    assert reasoning.assessed_coverage == 1
    assert reasoning.score_range is not None and reasoning.score_range >= 1


async def test_stability_rejects_reused_judge_record_index(tmp_path: Path) -> None:
    paths = await _write_stability_runs(tmp_path)
    duplicate = DatasetBenchmarkResult.model_validate_json(paths[1].read_text(encoding="utf-8"))
    duplicate.judge_record_index_sha256 = "A" * 64
    duplicate.warnings.append("Make the result bytes distinct while reusing one Judge index.")
    paths[1].write_text(duplicate.model_dump_json(indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="distinct Judge Record index"):
        analyze_benchmark_stability(paths)


async def test_stability_rejects_reused_judge_run_id(tmp_path: Path) -> None:
    paths = await _write_stability_runs(tmp_path)
    duplicate = DatasetBenchmarkResult.model_validate_json(paths[1].read_text(encoding="utf-8"))
    duplicate.judge_run_id = "a" * 32
    paths[1].write_text(duplicate.model_dump_json(indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="distinct Judge run ID"):
        analyze_benchmark_stability(paths)


async def test_stability_rejects_freeze_mismatch(tmp_path: Path) -> None:
    paths = await _write_stability_runs(tmp_path)
    mismatched = DatasetBenchmarkResult.model_validate_json(paths[2].read_text(encoding="utf-8"))
    mismatched.dataset_freeze_sha256 = "D" * 64
    paths[2].write_text(mismatched.model_dump_json(indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="do not share one Dataset, Freeze, Rubric, and mode"):
        analyze_benchmark_stability(paths)


async def test_stability_marks_missing_dimension_coverage_as_partial(tmp_path: Path) -> None:
    paths = await _write_stability_runs(tmp_path)
    partial = DatasetBenchmarkResult.model_validate_json(paths[2].read_text(encoding="utf-8"))
    dimension = partial.groups[0].reports[0].dimensions[-1]
    dimension.status = DimensionStatus.INSUFFICIENT_EVIDENCE
    dimension.score = None
    paths[2].write_text(partial.model_dump_json(indent=2) + "\n", encoding="utf-8")

    result = analyze_benchmark_stability(paths)

    assert result.overall.protocol_coverage_ready is False
    assert result.overall.score_stddev_target_met is None
    assert any("stability claims are partial" in warning for warning in result.warnings)


async def test_cli_writes_benchmark_stability_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = await _write_stability_runs(tmp_path)
    output = tmp_path / "stability.json"
    argv = ["analyze-benchmark-stability"]
    for path in paths:
        argv.extend(["--benchmark", str(path)])
    argv.extend(["--output", str(output)])

    assert main(argv) == 0
    assert Path(capsys.readouterr().out.strip()) == output
    result = BenchmarkStabilityResult.model_validate_json(output.read_text(encoding="utf-8"))
    assert result.overall.protocol_coverage_ready is True


def test_stability_requires_at_least_two_runs(tmp_path: Path) -> None:
    path = tmp_path / "one.json"
    path.write_text(json.dumps({}), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="at least two"):
        analyze_benchmark_stability([path])
