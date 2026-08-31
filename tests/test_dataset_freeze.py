from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from hy3_reproeval.dataset import DatasetSplit
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.freeze import (
    DatasetFreeze,
    FrozenFileRole,
    _readiness,
    create_dataset_freeze,
    verify_dataset_freeze,
)


def _public_manifest() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dataset" / "sample_adversarial_dataset.json"


def _write_freeze(path: Path, freeze: DatasetFreeze) -> None:
    path.write_text(freeze.model_dump_json(indent=2) + "\n", encoding="utf-8")


def test_create_freeze_inventories_all_registered_public_inputs() -> None:
    freeze = create_dataset_freeze(_public_manifest())

    assert freeze.group_count == 1
    assert freeze.report_count == 4
    assert freeze.file_count == 12
    assert freeze.readiness.meets_p0_dataset_targets is False
    assert freeze.readiness.unmet_requirements == [
        "at least 12 source groups",
        "a validation split",
        "a test split",
        "at least 8 adversarial reports",
    ]
    assert freeze.files == sorted(freeze.files, key=lambda item: item.path)
    assert {role for item in freeze.files for role in item.roles} == {
        FrozenFileRole.DATASET_MANIFEST,
        FrozenFileRole.EVALUATION_CASE,
        FrozenFileRole.REPORT,
        FrozenFileRole.MUTATION_MANIFEST,
    }


def test_freeze_includes_registered_judge_records() -> None:
    manifest = _public_manifest().with_name("sample_dataset.json")
    freeze = create_dataset_freeze(manifest)

    judge_records = [item for item in freeze.files if FrozenFileRole.JUDGE_RECORD in item.roles]
    assert len(judge_records) == 3


def test_readiness_accepts_declared_p0_dataset_targets() -> None:
    readiness = _readiness(
        12,
        {
            DatasetSplit.DEVELOPMENT: 4,
            DatasetSplit.VALIDATION: 4,
            DatasetSplit.TEST: 4,
        },
        8,
    )

    assert readiness.meets_p0_dataset_targets is True
    assert readiness.unmet_requirements == []


def test_verify_freeze_accepts_unchanged_dataset(tmp_path: Path) -> None:
    freeze = create_dataset_freeze(_public_manifest())
    freeze_path = tmp_path / "dataset-freeze.json"
    _write_freeze(freeze_path, freeze)

    result = verify_dataset_freeze(freeze_path, _public_manifest())

    assert result.valid is True
    assert result.freeze_sha256 == freeze.freeze_sha256
    assert result.file_count == freeze.file_count


def test_verify_freeze_rejects_tampered_canonical_payload(tmp_path: Path) -> None:
    freeze = create_dataset_freeze(_public_manifest())
    freeze_path = tmp_path / "dataset-freeze.json"
    _write_freeze(freeze_path, freeze)
    payload = json.loads(freeze_path.read_text(encoding="utf-8"))
    payload["dataset_version"] = "tampered"
    freeze_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="canonical payload"):
        verify_dataset_freeze(freeze_path, _public_manifest())


def test_verify_freeze_rejects_changed_registered_report(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    shutil.copytree(_public_manifest().parent, dataset_root)
    manifest_path = dataset_root / _public_manifest().name
    freeze = create_dataset_freeze(manifest_path)
    freeze_path = tmp_path / "dataset-freeze.json"
    _write_freeze(freeze_path, freeze)
    report_path = dataset_root / "adversarial_report.md"
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="SHA-256 does not match"):
        verify_dataset_freeze(freeze_path, manifest_path)


def test_freeze_includes_case_evidence_artifacts(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    shutil.copytree(_public_manifest().parent, dataset_root)
    artifact_path = dataset_root / "registered-evidence.json"
    artifact_path.write_text('{"registered": true}\n', encoding="utf-8")
    artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest().upper()
    for case_path in dataset_root.glob("*_case.json"):
        payload = json.loads(case_path.read_text(encoding="utf-8"))
        payload["artifacts"] = [
            {
                "artifact_id": "registered-evidence",
                "path": artifact_path.name,
                "sha256": artifact_sha256,
            }
        ]
        case_path.write_text(json.dumps(payload), encoding="utf-8")

    freeze = create_dataset_freeze(dataset_root / _public_manifest().name)
    artifact = next(item for item in freeze.files if item.path == artifact_path.name)

    assert artifact.roles == [FrozenFileRole.EVIDENCE_ARTIFACT]
    assert artifact.sha256 == artifact_sha256
    assert freeze.file_count == 13


def test_strict_freeze_rejects_development_fixture_below_p0_targets() -> None:
    with pytest.raises(EvaluationInputError, match="does not meet P0 freeze requirements"):
        create_dataset_freeze(_public_manifest(), require_p0_ready=True)
