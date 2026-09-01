from __future__ import annotations

import json
from pathlib import Path

import pytest

from hy3_reproeval.cli import main
from hy3_reproeval.dataset import DatasetSplit, validate_dataset_manifest
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.models import Scenario
from hy3_reproeval.p1_transfer_dataset import (
    P1_TRANSFER_DATASET_ID,
    build_p1_transfer_dataset_files,
    materialize_p1_transfer_dataset,
)


def test_p1_transfer_builder_writes_and_validates_canonical_dataset(tmp_path: Path) -> None:
    output = tmp_path / "p1"

    result = materialize_p1_transfer_dataset(output)
    validation = validate_dataset_manifest(output / "dataset.json")

    assert result.dataset_id == P1_TRANSFER_DATASET_ID
    assert result.group_count == 5
    assert result.report_count == 15
    assert result.mutation_count == 10
    assert validation.valid is True
    assert validation.group_count == 5
    assert validation.report_count == 15
    assert validation.mutation_count == 10
    assert validation.scenario_counts == {Scenario.TRANSFER: 5}
    assert validation.split_counts == {
        DatasetSplit.DEVELOPMENT: 1,
        DatasetSplit.VALIDATION: 2,
        DatasetSplit.TEST: 2,
    }
    assert validation.warnings == ["Dataset contains no human-reviewed report labels."]


def test_p1_transfer_builder_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    materialize_p1_transfer_dataset(first)
    materialize_p1_transfer_dataset(second)

    first_files = {path.relative_to(first).as_posix(): path.read_bytes() for path in first.rglob("*") if path.is_file()}
    second_files = {
        path.relative_to(second).as_posix(): path.read_bytes() for path in second.rglob("*") if path.is_file()
    }
    assert first_files == second_files == build_p1_transfer_dataset_files()


def test_p1_transfer_check_rejects_tampering(tmp_path: Path) -> None:
    output = tmp_path / "p1"
    materialize_p1_transfer_dataset(output)
    report = next(output.glob("groups/*/medium_report.md"))
    report.write_text(report.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="differ from canonical"):
        materialize_p1_transfer_dataset(output, check=True)


def test_p1_transfer_builder_refuses_nonempty_output(tmp_path: Path) -> None:
    output = tmp_path / "p1"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="absent or empty"):
        materialize_p1_transfer_dataset(output)


def test_p1_transfer_cli_writes_dataset(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "p1"

    assert main(["build-p1-transfer-dataset", "--output", str(output)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_count"] == 15
    assert main(["build-p1-transfer-dataset", "--output", str(output), "--check"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["verified_existing"] is True
