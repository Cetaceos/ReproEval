from __future__ import annotations

from pathlib import Path

from hy3_reproeval.cli import main
from hy3_reproeval.models import EvaluationMode, EvaluationResult, EvaluationStatus


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
