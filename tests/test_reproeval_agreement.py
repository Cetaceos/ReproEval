from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from hy3_reproeval.agreement import AdjudicationReason, analyze_annotation_agreement
from hy3_reproeval.benchmark import BenchmarkMode, run_dataset_benchmark
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.models import DimensionId


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _public_manifest() -> Path:
    return _project_root() / "examples" / "dataset" / "sample_dataset.json"


def _public_synthetic_bundle() -> Path:
    return _project_root() / "examples" / "annotations" / "synthetic_annotation_bundle.json"


def _validation_dataset(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    target = tmp_path / "dataset"
    shutil.copytree(_public_manifest().parent, target)
    manifest_path = target / "sample_dataset.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["groups"][0]["split"] = "validation"
    manifest_path.write_bytes(json.dumps(manifest, ensure_ascii=True, indent=2).encode("utf-8") + b"\n")
    return manifest_path, manifest


def _dimensions(score: int) -> list[dict[str, object]]:
    return [
        {
            "dimension": dimension,
            "status": "assessed",
            "score": score,
            "rationale": f"Independent annotation rationale for {dimension} at score {score}.",
            "evidence_lines": [5],
            "error_codes": [],
        }
        for dimension in (
            "factual_accuracy",
            "evidence_traceability",
            "numerical_consistency",
            "reasoning_consistency",
            "uncertainty_handling",
            "content_completeness",
            "clarity_actionability",
        )
    ]


def _human_bundle(
    manifest_path: Path,
    manifest: dict[str, object],
    *,
    annotator_id: str,
    bundle_id: str,
    scores: dict[str, int],
) -> dict[str, object]:
    group = manifest["groups"][0]
    return {
        "schema_version": "1.0",
        "annotation_bundle_id": bundle_id,
        "annotation_source": "human",
        "annotation_round": "independent",
        "annotation_date": "2026-08-31",
        "dataset_id": manifest["dataset_id"],
        "dataset_version": manifest["dataset_version"],
        "dataset_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest().upper(),
        "rubric_version": "0.1.0",
        "rubric_sha256": "1B1F6F8A425C1B84AAE88EFDA8E21950F2CF603325414316AEA773A1CD68F40A",
        "annotator": {
            "annotator_id": annotator_id,
            "expertise_description": "De-identified research reader for agreement protocol testing.",
            "independent_annotation": True,
            "blind_to_system_scores": True,
            "rubric_training_completed": True,
            "conflict_of_interest_disclosed": True,
            "conflict_of_interest_present": False,
        },
        "annotations": [
            {
                "group_id": group["group_id"],
                "report_id": report["report_id"],
                "report_sha256": report["report_sha256"],
                "dimensions": _dimensions(scores[report["quality_tier"]]),
            }
            for report in group["reports"]
        ],
    }


def _write_bundle(path: Path, payload: dict[str, object]) -> Path:
    path.write_bytes(json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8") + b"\n")
    return path


def _two_bundles(tmp_path: Path) -> tuple[Path, dict[str, object], Path, Path]:
    manifest_path, manifest = _validation_dataset(tmp_path)
    first = _write_bundle(
        tmp_path / "annotator-a.json",
        _human_bundle(
            manifest_path,
            manifest,
            annotator_id="annotator-a",
            bundle_id="bundle-a",
            scores={"high": 4, "medium": 3, "low": 1},
        ),
    )
    second = _write_bundle(
        tmp_path / "annotator-b.json",
        _human_bundle(
            manifest_path,
            manifest,
            annotator_id="annotator-b",
            bundle_id="bundle-b",
            scores={"high": 4, "medium": 2, "low": 0},
        ),
    )
    return manifest_path, manifest, first, second


def test_complete_double_annotation_produces_auditable_agreement(tmp_path: Path) -> None:
    manifest_path, _, first, second = _two_bundles(tmp_path)

    result = analyze_annotation_agreement(manifest_path, [first, second])

    assert result.agreement_ready is True
    assert result.eligible_annotator_count == 2
    assert result.eligible_report_count == 3
    assert result.annotator_pair_count == 1
    assert result.pooled_metrics.comparison_count == 21
    assert result.pooled_metrics.assessed_pair_count == 21
    assert result.pooled_metrics.exact_score_agreement == pytest.approx(1 / 3, abs=1e-6)
    assert result.pooled_metrics.within_one_point_agreement == 1
    assert result.pooled_metrics.mean_absolute_score_difference == pytest.approx(2 / 3, abs=1e-6)
    assert result.pooled_metrics.quadratic_weighted_kappa is not None
    assert result.pooled_metrics.quadratic_weighted_kappa > 0.7
    assert result.adjudication_item_count == 0


def test_score_gap_and_status_mismatch_enter_adjudication_queue(tmp_path: Path) -> None:
    manifest_path, _, first, second = _two_bundles(tmp_path)
    payload = json.loads(second.read_text(encoding="utf-8"))
    payload["annotations"][1]["dimensions"][0]["score"] = 0
    payload["annotations"][1]["dimensions"][3].update(
        status="insufficient_evidence",
        score=None,
        evidence_lines=[],
    )
    _write_bundle(second, payload)

    result = analyze_annotation_agreement(manifest_path, [first, second])

    assert result.adjudication_item_count == 2
    assert {item.reason for item in result.adjudication_items} == {
        AdjudicationReason.SCORE_GAP,
        AdjudicationReason.STATUS_MISMATCH,
    }
    assert any(item.dimension is DimensionId.FACTUAL_ACCURACY for item in result.adjudication_items)
    assert result.pooled_metrics.assessed_pair_count == 20


def test_system_human_comparison_uses_bound_replay_benchmark(tmp_path: Path) -> None:
    manifest_path, _, first, second = _two_bundles(tmp_path)
    benchmark = asyncio.run(run_dataset_benchmark(manifest_path, mode=BenchmarkMode.REPLAY))
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_bytes((benchmark.model_dump_json(indent=2) + "\n").encode("utf-8"))

    result = analyze_annotation_agreement(
        manifest_path,
        [first, second],
        benchmark_result_path=benchmark_path,
    )

    assert result.system_human is not None
    assert result.system_human.complete_coverage is True
    assert result.system_human.matched_report_count == 3
    assert result.system_human.coverage == 1
    assert result.system_human.spearman_correlation == 1
    assert result.system_human.mean_absolute_error is not None
    assert len(result.system_human.reports) == 3


def test_system_human_comparison_rejects_wrong_dataset_fingerprint(tmp_path: Path) -> None:
    manifest_path, _, first, second = _two_bundles(tmp_path)
    benchmark = asyncio.run(run_dataset_benchmark(manifest_path, mode=BenchmarkMode.REPLAY))
    payload = benchmark.model_dump(mode="json")
    payload["dataset_manifest_sha256"] = "A" * 64
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_bytes(json.dumps(payload, ensure_ascii=True).encode("utf-8"))

    with pytest.raises(EvaluationInputError, match="does not match the current Dataset Manifest"):
        analyze_annotation_agreement(
            manifest_path,
            [first, second],
            benchmark_result_path=benchmark_path,
        )


def test_system_human_comparison_rejects_wrong_rubric_fingerprint(tmp_path: Path) -> None:
    manifest_path, _, first, second = _two_bundles(tmp_path)
    benchmark = asyncio.run(run_dataset_benchmark(manifest_path, mode=BenchmarkMode.REPLAY))
    payload = benchmark.model_dump(mode="json")
    payload["rubric_sha256"] = "A" * 64
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_bytes(json.dumps(payload, ensure_ascii=True).encode("utf-8"))

    with pytest.raises(EvaluationInputError, match="different Rubric"):
        analyze_annotation_agreement(
            manifest_path,
            [first, second],
            benchmark_result_path=benchmark_path,
        )


def test_public_synthetic_fixture_cannot_become_agreement_evidence() -> None:
    result = analyze_annotation_agreement(_public_manifest(), [_public_synthetic_bundle()])

    assert result.agreement_ready is False
    assert result.eligible_annotator_count == 0
    assert result.annotator_pair_count == 0
    assert result.pooled_metrics.comparison_count == 0
    assert result.pooled_metrics.quadratic_weighted_kappa is None
    assert any("not benchmark-ready" in warning for warning in result.warnings)
