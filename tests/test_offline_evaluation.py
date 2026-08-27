from __future__ import annotations

import json
from pathlib import Path

import pytest

from hy3_reproscope_mcp.evaluation import (
    OfflineEvaluationResult,
    OfflineEvaluationSuiteResult,
    run_offline_evaluation,
    run_offline_evaluation_suite,
)


@pytest.mark.asyncio
async def test_offline_evaluation_replays_complete_workflow(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    repository_fixture = project_root / "evals" / "synthetic_reproduction.json"

    result = await run_offline_evaluation(
        project_root=project_root,
        fixture_path=repository_fixture,
        workspace_path=tmp_path / "artifacts",
    )

    assert result.status == "passed"
    assert result.passed_checks == result.total_checks
    assert result.total_checks >= 20
    assert result.expected_abstention is False
    assert result.correct_abstention is None
    assert result.artifacts["report"].endswith("/reproscope_report.md")
    assert result.artifacts["report_run_manifest"].endswith("/run_manifest.json")


@pytest.mark.asyncio
async def test_offline_evaluation_suite_measures_correct_abstention(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixture_paths = [
        project_root / "evals" / "synthetic_reproduction.json",
        project_root / "evals" / "synthetic_insufficient_evidence.json",
    ]

    result = await run_offline_evaluation_suite(
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


def test_checked_in_evaluation_schemas_match_result_models() -> None:
    project_root = Path(__file__).resolve().parents[1]
    schemas = {
        "offline_evaluation.schema.json": OfflineEvaluationResult,
        "offline_evaluation_suite.schema.json": OfflineEvaluationSuiteResult,
    }

    for filename, model in schemas.items():
        checked_in_schema = json.loads((project_root / "evals" / filename).read_text(encoding="utf-8"))
        assert checked_in_schema == model.model_json_schema()
