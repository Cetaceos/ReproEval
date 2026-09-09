from __future__ import annotations

import json
from pathlib import Path

import pytest

from hy3_reproeval.cli import main
from hy3_reproeval.dataset import DatasetDifficulty, DatasetSplit, StudyMode, validate_dataset_manifest
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.real_pilot import (
    REAL_PILOT_GROUP_COUNT,
    REAL_PILOT_REPORT_COUNT,
    materialize_real_pilot,
)


def test_real_pilot_uses_open_access_sources_and_draft_labels(tmp_path: Path) -> None:
    root = tmp_path / "real-paper-pilot"

    build = materialize_real_pilot(root)
    validation = validate_dataset_manifest(root / "dataset.json")
    manifest = json.loads((root / "dataset.json").read_text(encoding="utf-8"))

    assert build.group_count == REAL_PILOT_GROUP_COUNT
    assert build.report_count == REAL_PILOT_REPORT_COUNT
    assert validation.group_count == REAL_PILOT_GROUP_COUNT
    assert validation.report_count == REAL_PILOT_REPORT_COUNT
    assert validation.open_access_group_count == REAL_PILOT_GROUP_COUNT
    assert validation.reproducibility_readiness_group_count == REAL_PILOT_GROUP_COUNT
    assert validation.result_reproduction_group_count == 0
    assert validation.curator_draft_report_count == REAL_PILOT_GROUP_COUNT
    assert validation.human_reviewed_report_count == 0
    assert validation.hard_group_count == 4
    assert validation.source_asset_count == 30
    assert validation.locally_verified_source_count == 6
    assert manifest["schema_version"] == "1.2"
    assert validation.split_counts == {
        DatasetSplit.DEVELOPMENT: 2,
        DatasetSplit.VALIDATION: 2,
        DatasetSplit.TEST: 2,
    }
    assert all(group["study_mode"] == StudyMode.REPRODUCIBILITY_READINESS for group in manifest["groups"])
    assert sum(group["difficulty"] == DatasetDifficulty.HARD for group in manifest["groups"]) == 4
    assert all(group["provenance"]["kind"] == "open_access" for group in manifest["groups"])
    assert all(group["provenance"]["paper_sha256"] for group in manifest["groups"])
    assert all(len(group["provenance"]["source_assets"]) == 5 for group in manifest["groups"])
    assert all(group["provenance"]["archive_url"].startswith("https://doi.org/") for group in manifest["groups"])
    assert any("construction hypotheses" in warning for warning in validation.warnings)


def test_real_pilot_packets_are_substantive_and_do_not_claim_execution(tmp_path: Path) -> None:
    root = tmp_path / "real-paper-pilot"
    materialize_real_pilot(root)

    packets = sorted(root.glob("groups/*/source_material.md"))
    assert len(packets) == REAL_PILOT_GROUP_COUNT
    assert all(len(path.read_text(encoding="utf-8").splitlines()) >= 35 for path in packets)
    assert all("ReproEval did not install or execute" in path.read_text(encoding="utf-8") for path in packets)
    assert all("## Verified paper evidence" in path.read_text(encoding="utf-8") for path in packets)
    assert all("### E05" in path.read_text(encoding="utf-8") for path in packets)
    assert not list(root.rglob("*.pdf"))


def test_real_pilot_rejects_tampered_local_source_asset(tmp_path: Path) -> None:
    root = tmp_path / "real-paper-pilot"
    materialize_real_pilot(root)
    packet = next(root.glob("groups/*/source_material.md"))
    packet.write_text(packet.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match=r"source asset .* SHA-256 does not match"):
        validate_dataset_manifest(root / "dataset.json")


def test_real_pilot_check_rejects_tampering(tmp_path: Path) -> None:
    root = tmp_path / "real-paper-pilot"
    materialize_real_pilot(root)
    report = next(root.glob("groups/*/high_report.md"))
    report.write_text(report.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="differ from canonical generation"):
        materialize_real_pilot(root, check=True)


def test_cli_builds_and_checks_real_pilot(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "real-paper-pilot"

    assert main(["build-real-paper-pilot", "--output", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["wrote_files"] is True

    assert main(["build-real-paper-pilot", "--output", str(root), "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["verified_existing"] is True
