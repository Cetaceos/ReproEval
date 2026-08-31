from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from hy3_reproeval.annotations import validate_annotation_bundles
from hy3_reproeval.dataset import DatasetSplit
from hy3_reproeval.errors import EvaluationInputError


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _public_manifest() -> Path:
    return _project_root() / "examples" / "dataset" / "sample_dataset.json"


def _public_synthetic_bundle() -> Path:
    return _project_root() / "examples" / "annotations" / "synthetic_annotation_bundle.json"


def _dimensions() -> list[dict[str, object]]:
    return [
        {
            "dimension": dimension,
            "status": "assessed",
            "score": 4,
            "rationale": f"Independent annotation rationale for {dimension}.",
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


def _validation_dataset(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    target = tmp_path / "dataset"
    shutil.copytree(_public_manifest().parent, target)
    manifest_path = target / "sample_dataset.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["groups"][0]["split"] = "validation"
    payload = json.dumps(manifest, ensure_ascii=True, indent=2).encode("utf-8") + b"\n"
    manifest_path.write_bytes(payload)
    return manifest_path, manifest


def _human_bundle(
    manifest_path: Path,
    manifest: dict[str, object],
    *,
    annotator_id: str,
    bundle_id: str,
) -> dict[str, object]:
    reports = manifest["groups"][0]["reports"]
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
            "expertise_description": "De-identified research reader for protocol testing.",
            "independent_annotation": True,
            "blind_to_system_scores": True,
            "rubric_training_completed": True,
            "conflict_of_interest_disclosed": True,
            "conflict_of_interest_present": False,
        },
        "annotations": [
            {
                "group_id": manifest["groups"][0]["group_id"],
                "report_id": report["report_id"],
                "report_sha256": report["report_sha256"],
                "dimensions": _dimensions(),
            }
            for report in reports
        ],
    }


def _write_bundle(path: Path, payload: dict[str, object]) -> Path:
    path.write_bytes(json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8") + b"\n")
    return path


def test_public_synthetic_annotation_fixture_is_never_benchmark_eligible() -> None:
    result = validate_annotation_bundles(_public_manifest(), [_public_synthetic_bundle()])

    assert result.bundle_count == 1
    assert result.annotation_count == 1
    assert result.human_annotation_count == 0
    assert result.synthetic_annotation_count == 1
    assert result.split_annotation_counts == {DatasetSplit.DEVELOPMENT: 1}
    assert result.benchmark_ready is False
    assert any("never count as human" in warning for warning in result.warnings)


def test_two_complete_blind_human_bundles_make_validation_split_ready(tmp_path: Path) -> None:
    manifest_path, manifest = _validation_dataset(tmp_path)
    first = _write_bundle(
        tmp_path / "annotator-a.json",
        _human_bundle(manifest_path, manifest, annotator_id="annotator-a", bundle_id="bundle-a"),
    )
    second = _write_bundle(
        tmp_path / "annotator-b.json",
        _human_bundle(manifest_path, manifest, annotator_id="annotator-b", bundle_id="bundle-b"),
    )

    result = validate_annotation_bundles(manifest_path, [first, second])

    assert result.annotator_count == 2
    assert result.annotation_count == 6
    assert result.human_annotation_count == 6
    assert result.benchmark_target_report_count == 3
    assert result.independently_double_annotated_report_count == 3
    assert result.benchmark_ready is True


def test_annotation_rejects_report_hash_mismatch(tmp_path: Path) -> None:
    manifest_path, manifest = _validation_dataset(tmp_path)
    bundle = _human_bundle(manifest_path, manifest, annotator_id="annotator-a", bundle_id="bundle-a")
    bundle["annotations"][0]["report_sha256"] = "A" * 64
    path = _write_bundle(tmp_path / "annotation.json", bundle)

    with pytest.raises(EvaluationInputError, match="metadata mismatch"):
        validate_annotation_bundles(manifest_path, [path])


def test_annotation_rejects_evidence_line_outside_report(tmp_path: Path) -> None:
    manifest_path, manifest = _validation_dataset(tmp_path)
    bundle = _human_bundle(manifest_path, manifest, annotator_id="annotator-a", bundle_id="bundle-a")
    bundle["annotations"][0]["dimensions"][0]["evidence_lines"] = [999]
    path = _write_bundle(tmp_path / "annotation.json", bundle)

    with pytest.raises(EvaluationInputError, match="outside the report"):
        validate_annotation_bundles(manifest_path, [path])


def test_annotation_rejects_duplicate_independent_annotator(tmp_path: Path) -> None:
    manifest_path, manifest = _validation_dataset(tmp_path)
    first = _write_bundle(
        tmp_path / "bundle-a.json",
        _human_bundle(manifest_path, manifest, annotator_id="same-annotator", bundle_id="bundle-a"),
    )
    second = _write_bundle(
        tmp_path / "bundle-b.json",
        _human_bundle(manifest_path, manifest, annotator_id="same-annotator", bundle_id="bundle-b"),
    )

    with pytest.raises(EvaluationInputError, match="multiple independent"):
        validate_annotation_bundles(manifest_path, [first, second])


def test_annotation_rejects_error_code_from_another_dimension(tmp_path: Path) -> None:
    manifest_path, manifest = _validation_dataset(tmp_path)
    bundle = _human_bundle(manifest_path, manifest, annotator_id="annotator-a", bundle_id="bundle-a")
    bundle["annotations"][0]["dimensions"][0]["score"] = 2
    bundle["annotations"][0]["dimensions"][0]["error_codes"] = ["numeric_error"]
    path = _write_bundle(tmp_path / "annotation.json", bundle)

    with pytest.raises(EvaluationInputError, match="incompatible error codes"):
        validate_annotation_bundles(manifest_path, [path])
