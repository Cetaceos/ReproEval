from __future__ import annotations

from pathlib import Path

from hy3_reproeval.benchmark import BenchmarkMode, DatasetBenchmarkResult
from hy3_reproeval.cli import main
from hy3_reproeval.dataset import DatasetValidationResult, MutationReplayResult
from hy3_reproeval.models import EvaluationMode, EvaluationResult, EvaluationStatus
from hy3_reproeval.pairwise import ComparisonPreference, PairwiseComparisonResult


def test_cli_evaluates_public_sample_to_json(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    case_path = project_root / "examples" / "evaluation" / "sample_case.json"
    output_path = tmp_path / "evaluation.json"

    assert main(["evaluate-report", "--case", str(case_path), "--output", str(output_path)]) == 0

    result = EvaluationResult.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert result.case_id == "sample-reproduction-report-v1"
    assert result.overall_score == 100


def test_cli_replays_public_semantic_judge_sample_without_credentials(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    case_path = project_root / "examples" / "evaluation" / "sample_case.json"
    record_path = project_root / "examples" / "evaluation" / "sample_judge_record.json"
    output_path = tmp_path / "hybrid-evaluation.json"

    assert (
        main(
            [
                "evaluate-report",
                "--case",
                str(case_path),
                "--judge",
                "replay",
                "--judge-record",
                str(record_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    result = EvaluationResult.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert result.evaluation_mode is EvaluationMode.HYBRID
    assert result.status is EvaluationStatus.COMPLETE
    assert result.provisional is False
    assert result.overall_score == 96.25


def test_cli_replays_public_blinded_pairwise_sample(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_path = tmp_path / "pairwise-result.json"

    assert (
        main(
            [
                "compare-reports",
                "--left-case",
                str(project_root / "examples" / "evaluation" / "sample_case.json"),
                "--right-case",
                str(project_root / "examples" / "evaluation" / "sample_case_variant.json"),
                "--comparison-id",
                "sample-pairwise-v1",
                "--repeats",
                "3",
                "--judge",
                "replay",
                "--judge-record",
                str(project_root / "examples" / "evaluation" / "sample_pairwise_judge_bundle.json"),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    result = PairwiseComparisonResult.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert result.final_preference is ComparisonPreference.LEFT
    assert result.left.final_score_mean == 97.5
    assert result.right.final_score_mean == 81.25
    assert result.preference_flip_rate == 0
    assert result.observed_position_delta_max == 1.875


def test_cli_validates_public_three_tier_dataset(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_path = tmp_path / "dataset-validation.json"

    assert (
        main(
            [
                "validate-dataset",
                "--manifest",
                str(project_root / "examples" / "dataset" / "sample_dataset.json"),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    result = DatasetValidationResult.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert result.valid is True
    assert result.group_count == 1
    assert result.report_count == 3
    assert result.mutation_count == 2
    assert result.judge_record_count == 3


def test_cli_replays_public_mutation(capsys) -> None:
    project_root = Path(__file__).resolve().parents[1]

    assert (
        main(
            [
                "replay-mutation",
                "--manifest",
                str(project_root / "examples" / "dataset" / "medium_mutation.json"),
                "--root",
                str(project_root / "examples" / "dataset"),
            ]
        )
        == 0
    )
    result = MutationReplayResult.model_validate_json(capsys.readouterr().out)
    assert result.mutation_id == "sample-medium-mutation-v1"
    assert result.wrote_output is False


def test_cli_runs_public_replay_benchmark(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_path = tmp_path / "dataset-benchmark.json"

    assert (
        main(
            [
                "benchmark-dataset",
                "--manifest",
                str(project_root / "examples" / "dataset" / "sample_dataset.json"),
                "--mode",
                "replay",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    result = DatasetBenchmarkResult.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert result.benchmark_mode is BenchmarkMode.REPLAY
    assert result.overall.pairwise_accuracy == 1
    assert result.overall.complete_order_accuracy == 1
    assert result.overall.macro_spearman_correlation == 1
