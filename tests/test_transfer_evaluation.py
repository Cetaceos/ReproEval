from __future__ import annotations

from pathlib import Path

import pytest

from hy3_reproscope_mcp.transfer_evaluation import (
    run_transfer_offline_evaluation,
    run_transfer_offline_evaluation_suite,
)


@pytest.mark.asyncio
async def test_transfer_offline_evaluation_replays_complete_workflow(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixture = project_root / "evals" / "synthetic_transfer.json"

    result = await run_transfer_offline_evaluation(
        project_root=project_root,
        fixture_path=fixture,
        workspace_path=tmp_path / "artifacts",
    )

    assert result.status == "passed"
    assert result.passed_checks == result.total_checks
    assert result.total_checks >= 20
    assert result.expected_abstention is False
    assert result.correct_abstention is None
    assert result.artifacts["report"].endswith("/transfer_report.md")
    assert result.artifacts["report_run_manifest"].endswith("/run_manifest.json")


@pytest.mark.asyncio
async def test_transfer_offline_suite_measures_correct_abstention(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixture_paths = [
        project_root / "evals" / "synthetic_transfer.json",
        project_root / "evals" / "synthetic_transfer_insufficient_evidence.json",
    ]

    result = await run_transfer_offline_evaluation_suite(
        project_root=project_root,
        fixture_paths=fixture_paths,
        workspace_path=tmp_path / "suite-artifacts",
    )

    assert result.status == "passed"
    assert result.passed_cases == result.total_cases == 2
    assert result.passed_checks == result.total_checks
    assert result.correct_abstentions == result.total_abstention_cases == 1
    assert result.correct_abstention_rate == 1
    assert all("/" in case.artifacts["report"] for case in result.cases)


@pytest.mark.asyncio
async def test_transfer_offline_suite_rejects_duplicate_case_ids(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixture = project_root / "evals" / "synthetic_transfer.json"

    with pytest.raises(ValueError, match="Duplicate transfer evaluation case_id"):
        await run_transfer_offline_evaluation_suite(
            project_root=project_root,
            fixture_paths=[fixture, fixture],
            workspace_path=tmp_path / "suite-artifacts",
        )
