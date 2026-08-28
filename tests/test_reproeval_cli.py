from __future__ import annotations

from pathlib import Path

from hy3_reproeval.cli import main
from hy3_reproeval.models import EvaluationResult


def test_cli_evaluates_public_sample_to_json(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    case_path = project_root / "examples" / "evaluation" / "sample_case.json"
    output_path = tmp_path / "evaluation.json"

    assert main(["evaluate-report", "--case", str(case_path), "--output", str(output_path)]) == 0

    result = EvaluationResult.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert result.case_id == "sample-reproduction-report-v1"
    assert result.overall_score == 100
