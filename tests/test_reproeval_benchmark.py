from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hy3_reproeval.benchmark import (
    BenchmarkAttackResult,
    BenchmarkMode,
    BenchmarkReportResult,
    _adversarial_metrics,
    _group_metrics,
    run_dataset_benchmark,
)
from hy3_reproeval.dataset import AdversarialAttackType, DatasetSplit, validate_dataset_manifest
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.models import DimensionId, ErrorCode, EvaluationMode, EvaluationStatus, QualityBand


def _public_manifest() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dataset" / "sample_dataset.json"


def _public_adversarial_manifest() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dataset" / "sample_adversarial_dataset.json"


def _report_result(report_id: str, tier: str, score: float) -> BenchmarkReportResult:
    return BenchmarkReportResult(
        report_id=report_id,
        quality_tier=tier,
        case_id=f"case-{report_id}",
        report_sha256=("A" * 64),
        evaluation_mode=EvaluationMode.HYBRID,
        status=EvaluationStatus.COMPLETE,
        provisional=False,
        ranking_eligible=True,
        assessed_weight=1,
        overall_score=score,
        quality_band=QualityBand.STRONG,
        expected_error_codes=[],
        observed_error_codes=[],
        detected_expected_error_codes=[],
        missing_expected_error_codes=[],
        unexpected_error_codes=[],
    )


async def test_deterministic_benchmark_withholds_provisional_ranking_metrics() -> None:
    result = await run_dataset_benchmark(_public_manifest())

    assert result.benchmark_mode is BenchmarkMode.DETERMINISTIC
    assert result.overall.group_count == 1
    assert result.overall.report_count == 3
    assert result.overall.ranking_eligible_report_count == 0
    assert result.overall.ranking_score_coverage == 0
    assert result.overall.pairwise_accuracy is None
    assert result.overall.complete_order_accuracy is None
    assert result.overall.macro_spearman_correlation is None
    assert result.overall.detected_expected_error_count == 3
    assert result.overall.expected_error_count == 7
    assert result.overall.error_label_recall == pytest.approx(3 / 7, abs=1e-6)
    assert any("excluded from ordering" in warning for warning in result.warnings)


async def test_replay_benchmark_computes_group_isolated_ranking_metrics() -> None:
    result = await run_dataset_benchmark(_public_manifest(), mode="replay")

    assert result.benchmark_mode is BenchmarkMode.REPLAY
    assert result.overall.ranking_score_coverage == 1
    assert result.overall.expected_pair_count == 3
    assert result.overall.evaluated_pair_count == 3
    assert result.overall.pairwise_accuracy == 1
    assert result.overall.complete_order_accuracy == 1
    assert result.overall.macro_spearman_correlation == 1
    assert result.overall.error_label_recall == 1
    assert result.splits[DatasetSplit.DEVELOPMENT] == result.overall
    scores = {report.report_id: report.overall_score for report in result.groups[0].reports}
    assert scores == {
        "sample-report-high-v1": 100,
        "sample-report-medium-v1": 85,
        "sample-report-low-v1": 25.75,
    }


async def test_public_adversarial_fixture_reports_deterministic_attack_metrics() -> None:
    result = await run_dataset_benchmark(_public_adversarial_manifest())

    assert result.overall.adversarial.adversarial_report_count == 1
    assert result.overall.adversarial.fully_detected_report_count == 1
    assert result.overall.adversarial.attack_instance_count == 2
    assert result.overall.adversarial.attack_detection_rate == 1
    assert result.overall.adversarial.attack_false_acceptance_rate == 0
    assert result.overall.adversarial.expected_error_count == 3
    assert result.overall.adversarial.error_label_recall == 1
    assert any("not held-out robustness evidence" in warning for warning in result.warnings)


async def test_benchmark_rejects_an_unknown_mode() -> None:
    with pytest.raises(EvaluationInputError, match="unsupported dataset benchmark mode"):
        await run_dataset_benchmark(_public_manifest(), mode="unknown")


def test_group_metrics_count_a_tie_as_evaluated_but_incorrect() -> None:
    metrics = _group_metrics(
        [
            _report_result("high", "high", 80),
            _report_result("medium", "medium", 80),
            _report_result("low", "low", 20),
        ]
    )

    assert metrics.evaluated_pair_count == 3
    assert metrics.correct_pair_count == 2
    assert metrics.tied_pair_count == 1
    assert metrics.pairwise_accuracy == pytest.approx(2 / 3, abs=1e-6)
    assert metrics.complete_order_correct is False


def test_group_metrics_exclude_adversarial_tier_from_unlabeled_order() -> None:
    metrics = _group_metrics(
        [
            _report_result("high", "high", 100),
            _report_result("medium", "medium", 80),
            _report_result("low", "low", 20),
            _report_result("adversarial", "adversarial", 99),
        ]
    )

    assert metrics.report_count == 4
    assert metrics.ranking_candidate_report_count == 3
    assert metrics.ranking_eligible_report_count == 3
    assert metrics.expected_pair_count == 3
    assert metrics.complete_order_correct is True


def test_adversarial_metrics_report_complete_partial_and_per_type_detection() -> None:
    adversarial = _report_result("adversarial", "adversarial", 99)
    adversarial.attacks = [
        BenchmarkAttackResult(
            attack_id="attack-citation",
            attack_type=AdversarialAttackType.FABRICATED_AUTHORITY,
            target_dimensions=[DimensionId.EVIDENCE_TRACEABILITY],
            expected_error_codes=[ErrorCode.FABRICATED_CITATION, ErrorCode.UNSUPPORTED_CLAIM],
            detected_error_codes=[ErrorCode.FABRICATED_CITATION, ErrorCode.UNSUPPORTED_CLAIM],
            missing_error_codes=[],
            detected=True,
        ),
        BenchmarkAttackResult(
            attack_id="attack-verbosity",
            attack_type=AdversarialAttackType.TERMINOLOGY_STUFFING,
            target_dimensions=[DimensionId.CLARITY_ACTIONABILITY],
            expected_error_codes=[ErrorCode.VERBOSITY_WITHOUT_EVIDENCE],
            detected_error_codes=[],
            missing_error_codes=[ErrorCode.VERBOSITY_WITHOUT_EVIDENCE],
            detected=False,
        ),
    ]

    metrics = _adversarial_metrics([adversarial, _report_result("high", "high", 100)])

    assert metrics.adversarial_report_count == 1
    assert metrics.fully_detected_report_count == 0
    assert metrics.report_detection_rate == 0
    assert metrics.attack_instance_count == 2
    assert metrics.detected_attack_instance_count == 1
    assert metrics.attack_detection_rate == 0.5
    assert metrics.attack_false_acceptance_rate == 0.5
    assert metrics.error_label_recall == pytest.approx(2 / 3, abs=1e-6)
    assert (
        metrics.by_attack_type[AdversarialAttackType.FABRICATED_AUTHORITY].attack_detection_rate
        == 1
    )
    assert (
        metrics.by_attack_type[AdversarialAttackType.TERMINOLOGY_STUFFING].attack_detection_rate
        == 0
    )


def test_adversarial_metrics_are_undefined_without_registered_attacks() -> None:
    metrics = _adversarial_metrics([_report_result("high", "high", 100)])

    assert metrics.attack_instance_count == 0
    assert metrics.attack_detection_rate is None
    assert metrics.attack_false_acceptance_rate is None
    assert metrics.error_label_recall is None


def test_dataset_rejects_tampered_registered_judge_record(tmp_path: Path) -> None:
    source = _public_manifest().parent
    target = tmp_path / "dataset"
    shutil.copytree(source, target)
    record_path = target / "medium_judge_record.json"
    record_path.write_bytes(record_path.read_bytes() + b"\n")

    with pytest.raises(EvaluationInputError, match="Judge record SHA-256"):
        validate_dataset_manifest(target / "sample_dataset.json")


def test_dataset_requires_judge_record_path_and_hash_together(tmp_path: Path) -> None:
    source = _public_manifest().parent
    target = tmp_path / "dataset"
    shutil.copytree(source, target)
    manifest_path = target / "sample_dataset.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["groups"][0]["reports"][0]["judge_record_sha256"]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="declared together"):
        validate_dataset_manifest(manifest_path)
