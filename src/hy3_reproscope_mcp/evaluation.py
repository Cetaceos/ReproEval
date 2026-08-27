"""Repeatable offline evaluation for the complete ReproScope workflow."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .models import (
    RunManifest,
    RunStatus,
)
from .server import AppContext
from .tools import (
    build_evidence_graph,
    compare_results,
    extract_claims,
    render_report,
    score_paper,
)
from .workspace import Workspace


class EvaluationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    name: str = Field(min_length=1)
    passed: bool
    expected: Any
    actual: Any


class OfflineEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    case_id: str = Field(min_length=1)
    status: Literal["passed", "failed"]
    expected_abstention: bool = False
    correct_abstention: bool | None = None
    passed_checks: int = Field(ge=0)
    total_checks: int = Field(ge=1)
    checks: list[EvaluationCheck] = Field(min_length=1)
    artifacts: dict[str, str] = Field(default_factory=dict)


class OfflineEvaluationSuiteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    status: Literal["passed", "failed"]
    passed_cases: int = Field(ge=0)
    total_cases: int = Field(ge=1)
    passed_checks: int = Field(ge=0)
    total_checks: int = Field(ge=1)
    correct_abstentions: int = Field(ge=0)
    total_abstention_cases: int = Field(ge=0)
    correct_abstention_rate: float | None = Field(default=None, ge=0, le=1)
    cases: list[OfflineEvaluationResult] = Field(min_length=1)


class ReplayHy3Client:
    """Return checked-in structured responses through the normal Hy3 client contract."""

    def __init__(self, responses: Mapping[str, dict[str, Any]]) -> None:
        self.responses = dict(responses)

    async def complete_structured(
        self,
        messages: Sequence[Mapping[str, str]],
        response_model: type[BaseModel],
        **_: Any,
    ) -> BaseModel:
        del messages
        try:
            payload = self.responses[response_model.__name__]
        except KeyError as exc:
            raise RuntimeError(f"No replay response for {response_model.__name__}.") from exc
        return response_model.model_validate(payload)

    async def close(self) -> None:
        return None


async def run_offline_evaluation(
    *,
    project_root: Path,
    fixture_path: Path,
    workspace_path: Path,
) -> OfflineEvaluationResult:
    """Run all five tools and evaluate deterministic workflow invariants."""

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    settings = Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(project_root),
        REPROSCOPE_WORKSPACE=workspace_path,
    )
    workspace = Workspace(settings)
    app = AppContext(
        settings=settings,
        hy3_client=ReplayHy3Client(fixture["responses"]),
    )
    inputs = fixture["inputs"]
    paper_path = project_root / inputs["paper"]
    reproduction_paths = [str(project_root / path) for path in inputs["reproduction"]]

    try:
        claims = await extract_claims(
            app,
            paper_paths=[str(paper_path)],
            focus=inputs.get("focus"),
        )
        comparison = await compare_results(
            app,
            paper_paths=[str(paper_path)],
            reproduction_paths=reproduction_paths,
            metric_hints=inputs.get("metric_hints", []),
            claims_artifact_path=_primary_artifact(claims),
        )
        score = await score_paper(
            app,
            paper_paths=[str(paper_path)],
            reproduction_paths=reproduction_paths,
            rubric_focus=inputs.get("rubric_focus", []),
            claims_artifact_path=_primary_artifact(claims),
            comparison_artifact_path=_primary_artifact(comparison),
        )
        graph = build_evidence_graph(
            app,
            claims_artifact_path=_primary_artifact(claims),
            comparison_artifact_path=_primary_artifact(comparison),
            score_artifact_path=_primary_artifact(score),
        )
        report = render_report(
            app,
            claims_artifact_path=_primary_artifact(claims),
            comparison_artifact_path=_primary_artifact(comparison),
            score_artifact_path=_primary_artifact(score),
            evidence_graph_artifact_path=_primary_artifact(graph),
            title=fixture["report_title"],
        )
    finally:
        await app.close()

    expectations = fixture["expectations"]
    checks: list[EvaluationCheck] = []
    _add_check(
        checks,
        "claim_ids",
        expected=expectations["claim_ids"],
        actual=[claim.claim_id for claim in claims.core_claims],
    )
    claim_citation_count = sum(len(claim.citations) for claim in claims.core_claims)
    _add_check(
        checks,
        "minimum_claim_citations",
        expected=f">={expectations['minimum_claim_citations']}",
        actual=claim_citation_count,
        passed=claim_citation_count >= expectations["minimum_claim_citations"],
    )

    metric_expectation = expectations["metric"]
    metric = next(
        item
        for item in comparison.metric_comparisons
        if (item.canonical_metric or item.metric) == metric_expectation["name"]
    )
    _add_check(checks, "metric_status", expected=metric_expectation["status"], actual=metric.computation_status.value)
    _add_float_check(checks, "metric_mean", metric_expectation["mean"], metric.reproduced_value)
    _add_check(checks, "metric_sample_count", metric_expectation["sample_count"], metric.sample_count)
    _add_float_check(checks, "metric_absolute_delta", metric_expectation["absolute_delta"], metric.absolute_delta)
    _add_float_check(
        checks,
        "metric_relative_delta_percent",
        metric_expectation["relative_delta_percent"],
        metric.relative_delta_percent,
    )
    _add_float_check(
        checks,
        "claim_relation_coverage",
        expectations["claim_relation_coverage"],
        comparison.claim_relation_diagnostics.claim_relation_coverage,
    )

    setting_statuses = {check.setting: check.status.value for check in comparison.deterministic_setting_checks}
    for setting, expected_status in expectations["setting_statuses"].items():
        _add_check(
            checks,
            f"setting_{setting}",
            expected=expected_status,
            actual=setting_statuses.get(setting),
        )

    score_expectation = expectations["score"]
    if score_expectation["overall"] is None:
        _add_check(checks, "overall_score", expected=None, actual=score.overall_score)
    else:
        _add_float_check(checks, "overall_score", score_expectation["overall"], score.overall_score)
    _add_check(checks, "reliability_band", score_expectation["band"], score.reliability_band.value)
    _add_float_check(checks, "rubric_coverage", score_expectation["rubric_coverage"], score.rubric_coverage)
    expected_abstention = bool(score_expectation.get("abstain", False))
    actual_abstention = score.overall_score is None and score.reliability_band.value == "insufficient"
    _add_check(
        checks,
        "abstention_behavior",
        expected=expected_abstention,
        actual=actual_abstention,
    )
    expected_score_warnings = score_expectation.get("warning_codes")
    if expected_score_warnings is not None:
        actual_score_warnings = sorted(warning.code for warning in score.warnings)
        _add_check(
            checks,
            "score_warning_codes",
            expected=sorted(expected_score_warnings),
            actual=actual_score_warnings,
            passed=set(expected_score_warnings).issubset(actual_score_warnings),
        )
    _add_check(checks, "graph_validated", True, graph.graph_validated)

    report_text = (workspace.workspace_path / report.report_path).read_text(encoding="utf-8")
    for section in expectations["report_sections"]:
        _add_check(
            checks,
            f"report_section_{section}",
            expected=True,
            actual=section in report_text,
        )
    for expected_text in expectations.get("report_contains", []):
        _add_check(
            checks,
            f"report_contains_{expected_text}",
            expected=True,
            actual=expected_text in report_text,
        )

    tool_results = [claims, comparison, score, graph, report]
    lifecycle_statuses = {
        result.run_id: _run_manifest(workspace, result.artifacts[-1].relative_path).status.value
        for result in tool_results
    }
    _add_check(
        checks,
        "all_run_manifests_completed",
        expected=[RunStatus.COMPLETED.value] * len(tool_results),
        actual=list(lifecycle_statuses.values()),
    )

    passed_checks = sum(check.passed for check in checks)
    return OfflineEvaluationResult(
        case_id=fixture["case_id"],
        status="passed" if passed_checks == len(checks) else "failed",
        expected_abstention=expected_abstention,
        correct_abstention=actual_abstention if expected_abstention else None,
        passed_checks=passed_checks,
        total_checks=len(checks),
        checks=checks,
        artifacts={
            "claims": _primary_artifact(claims),
            "comparison": _primary_artifact(comparison),
            "score": _primary_artifact(score),
            "graph": _primary_artifact(graph),
            "report": report.report_path,
            "report_manifest": report.manifest_path,
            "report_run_manifest": report.artifacts[-1].relative_path,
        },
    )


async def run_offline_evaluation_suite(
    *,
    project_root: Path,
    fixture_paths: Sequence[Path],
    workspace_path: Path,
) -> OfflineEvaluationSuiteResult:
    """Run multiple offline cases in isolated subdirectories and aggregate results."""

    if not fixture_paths:
        raise ValueError("At least one offline evaluation fixture is required.")

    cases: list[OfflineEvaluationResult] = []
    seen_case_ids: set[str] = set()
    for fixture_path in fixture_paths:
        case_workspace = workspace_path / fixture_path.stem
        result = await run_offline_evaluation(
            project_root=project_root,
            fixture_path=fixture_path,
            workspace_path=case_workspace,
        )
        if result.case_id in seen_case_ids:
            raise ValueError(f"Duplicate offline evaluation case_id: {result.case_id}.")
        seen_case_ids.add(result.case_id)
        result.artifacts = {
            role: str(Path(fixture_path.stem) / relative_path).replace("\\", "/")
            for role, relative_path in result.artifacts.items()
        }
        cases.append(result)

    total_abstention_cases = sum(case.expected_abstention for case in cases)
    correct_abstentions = sum(case.correct_abstention is True for case in cases)
    passed_cases = sum(case.status == "passed" for case in cases)
    passed_checks = sum(case.passed_checks for case in cases)
    total_checks = sum(case.total_checks for case in cases)
    return OfflineEvaluationSuiteResult(
        status="passed" if passed_cases == len(cases) else "failed",
        passed_cases=passed_cases,
        total_cases=len(cases),
        passed_checks=passed_checks,
        total_checks=total_checks,
        correct_abstentions=correct_abstentions,
        total_abstention_cases=total_abstention_cases,
        correct_abstention_rate=(correct_abstentions / total_abstention_cases if total_abstention_cases else None),
        cases=cases,
    )


def _primary_artifact(result: Any) -> str:
    if not result.artifacts:
        raise RuntimeError(f"{type(result).__name__} did not produce a primary artifact.")
    return result.artifacts[0].relative_path


def _run_manifest(workspace: Workspace, path: str) -> RunManifest:
    return RunManifest.model_validate(workspace.read_json_artifact(path))


def _add_float_check(
    checks: list[EvaluationCheck],
    name: str,
    expected: float,
    actual: float | None,
) -> None:
    passed = actual is not None and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
    _add_check(checks, name, expected=expected, actual=actual, passed=passed)


def _add_check(
    checks: list[EvaluationCheck],
    name: str,
    expected: Any,
    actual: Any,
    *,
    passed: bool | None = None,
) -> None:
    checks.append(
        EvaluationCheck(
            name=name,
            passed=actual == expected if passed is None else passed,
            expected=expected,
            actual=actual,
        )
    )
