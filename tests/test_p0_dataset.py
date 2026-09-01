from __future__ import annotations

import json
from pathlib import Path

import pytest

from hy3_reproeval.cli import main
from hy3_reproeval.dataset import AdversarialAttackType, DatasetSplit, validate_dataset_manifest
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.freeze import create_dataset_freeze
from hy3_reproeval.p0_dataset import (
    P0_ADVERSARIAL_REPORT_COUNT,
    P0_GROUP_COUNT,
    P0_REPORT_COUNT,
    materialize_p0_dataset,
)


def test_p0_dataset_meets_declared_protocol_targets(tmp_path: Path) -> None:
    dataset_root = tmp_path / "p0-dataset"

    build = materialize_p0_dataset(dataset_root)
    validation = validate_dataset_manifest(dataset_root / "dataset.json")
    freeze = create_dataset_freeze(dataset_root / "dataset.json", require_p0_ready=True)

    assert build.group_count == P0_GROUP_COUNT
    assert build.report_count == P0_REPORT_COUNT
    assert build.adversarial_report_count == P0_ADVERSARIAL_REPORT_COUNT
    assert validation.group_count == P0_GROUP_COUNT
    assert validation.report_count == P0_REPORT_COUNT
    assert validation.split_counts == {
        DatasetSplit.DEVELOPMENT: 4,
        DatasetSplit.VALIDATION: 4,
        DatasetSplit.TEST: 4,
    }
    assert validation.adversarial_report_count == P0_ADVERSARIAL_REPORT_COUNT
    assert set(validation.attack_type_counts) == set(AdversarialAttackType)
    assert freeze.readiness.meets_p0_dataset_targets is True


def test_p0_dataset_check_verifies_exact_canonical_bytes(tmp_path: Path) -> None:
    dataset_root = tmp_path / "p0-dataset"
    materialize_p0_dataset(dataset_root)

    checked = materialize_p0_dataset(dataset_root, check=True)

    assert checked.wrote_files is False
    assert checked.verified_existing is True


def test_p0_dataset_check_rejects_tampering(tmp_path: Path) -> None:
    dataset_root = tmp_path / "p0-dataset"
    materialize_p0_dataset(dataset_root)
    report_path = next(dataset_root.glob("groups/*/high_report.md"))
    report_path.write_text(report_path.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="differ from canonical generation"):
        materialize_p0_dataset(dataset_root, check=True)


def test_p0_dataset_write_rejects_nonempty_output(tmp_path: Path) -> None:
    dataset_root = tmp_path / "p0-dataset"
    dataset_root.mkdir()
    (dataset_root / "unrelated.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="absent or empty"):
        materialize_p0_dataset(dataset_root)


def test_p0_dataset_write_rejects_file_output(tmp_path: Path) -> None:
    output_path = tmp_path / "p0-dataset"
    output_path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="must be a directory"):
        materialize_p0_dataset(output_path)


def test_cli_builds_and_checks_p0_dataset(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dataset_root = tmp_path / "p0-dataset"

    assert main(["build-p0-dataset", "--output", str(dataset_root)]) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["wrote_files"] is True

    assert main(["build-p0-dataset", "--output", str(dataset_root), "--check"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["verified_existing"] is True
