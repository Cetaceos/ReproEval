from __future__ import annotations

from pathlib import Path

from hy3_reproeval.agreement import AnnotationAgreementResult
from hy3_reproeval.annotations import AnnotationValidationResult
from hy3_reproeval.benchmark import BenchmarkMode, DatasetBenchmarkResult
from hy3_reproeval.cli import main
from hy3_reproeval.consensus import AnnotationConsensusResult
from hy3_reproeval.dataset import DatasetValidationResult, MutationReplayResult
from hy3_reproeval.freeze import DatasetFreeze, DatasetFreezeVerification
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


def test_cli_creates_and_verifies_public_dataset_freeze(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    manifest_path = project_root / "examples" / "dataset" / "sample_adversarial_dataset.json"
    freeze_path = tmp_path / "dataset-freeze.json"
    verification_path = tmp_path / "dataset-freeze-verification.json"

    assert (
        main(
            [
                "freeze-dataset",
                "--manifest",
                str(manifest_path),
                "--output",
                str(freeze_path),
            ]
        )
        == 0
    )
    freeze = DatasetFreeze.model_validate_json(freeze_path.read_text(encoding="utf-8"))
    assert freeze.file_count == 12
    assert freeze.readiness.meets_p0_dataset_targets is False

    assert (
        main(
            [
                "verify-dataset-freeze",
                "--freeze",
                str(freeze_path),
                "--manifest",
                str(manifest_path),
                "--output",
                str(verification_path),
            ]
        )
        == 0
    )
    verification = DatasetFreezeVerification.model_validate_json(
        verification_path.read_text(encoding="utf-8")
    )
    assert verification.valid is True
    assert verification.freeze_sha256 == freeze.freeze_sha256


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


def test_cli_validates_public_synthetic_annotation_fixture(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_path = tmp_path / "annotation-validation.json"

    assert (
        main(
            [
                "validate-annotations",
                "--manifest",
                str(project_root / "examples" / "dataset" / "sample_dataset.json"),
                "--bundle",
                str(project_root / "examples" / "annotations" / "synthetic_annotation_bundle.json"),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    result = AnnotationValidationResult.model_validate_json(output_path.read_bytes())
    assert result.synthetic_annotation_count == 1
    assert result.human_annotation_count == 0
    assert result.benchmark_ready is False


def test_cli_refuses_to_promote_synthetic_annotations_to_agreement_evidence(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_path = tmp_path / "annotation-agreement.json"

    assert (
        main(
            [
                "analyze-annotations",
                "--manifest",
                str(project_root / "examples" / "dataset" / "sample_dataset.json"),
                "--bundle",
                str(project_root / "examples" / "annotations" / "synthetic_annotation_bundle.json"),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    result = AnnotationAgreementResult.model_validate_json(output_path.read_bytes())
    assert result.agreement_ready is False
    assert result.eligible_annotator_count == 0
    assert result.pooled_metrics.quadratic_weighted_kappa is None


def test_cli_refuses_to_finalize_synthetic_annotations_as_consensus(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_path = tmp_path / "annotation-consensus.json"

    assert (
        main(
            [
                "finalize-annotations",
                "--manifest",
                str(project_root / "examples" / "dataset" / "sample_dataset.json"),
                "--bundle",
                str(project_root / "examples" / "annotations" / "synthetic_annotation_bundle.json"),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    result = AnnotationConsensusResult.model_validate_json(output_path.read_bytes())
    assert result.consensus_ready is False
    assert result.target_report_count == 0
    assert result.consensus_report_count == 0
