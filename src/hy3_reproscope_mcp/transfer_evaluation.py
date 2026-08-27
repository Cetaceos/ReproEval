"""Repeatable offline evaluation for the technology-transfer workflow."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .config import Settings
from .evaluation import (
    EvaluationCheck,
    OfflineEvaluationResult,
    OfflineEvaluationSuiteResult,
    ReplayHy3Client,
)
from .models import RunManifest, RunStatus
from .server import AppContext
from .tools import (
    assess_transfer,
    build_transfer_evidence_graph,
    extract_solution_profile,
    render_transfer_report,
)
from .workspace import Workspace


async def run_transfer_offline_evaluation(
    *,
    project_root: Path,
    fixture_path: Path,
    workspace_path: Path,
) -> OfflineEvaluationResult:
    """Run the three transfer tools and evaluate deterministic workflow invariants."""

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
    solution_paths = [str(project_root / path) for path in inputs["solution"]]
    target_context_paths = [str(project_root / path) for path in inputs["target_context"]]

    try:
        profile = await extract_solution_profile(
            app,
            solution_paths=solution_paths,
            focus=inputs.get("profile_focus"),
        )
        assessment = await assess_transfer(
            app,
            solution_paths=solution_paths,
            target_context_paths=target_context_paths,
            solution_profile_artifact_path=_primary_artifact(profile),
            focus=inputs.get("assessment_focus"),
        )
        graph = build_transfer_evidence_graph(
            app,
            solution_profile_artifact_path=_primary_artifact(profile),
            transfer_assessment_artifact_path=_primary_artifact(assessment),
        )
        report = render_transfer_report(
            app,
            solution_profile_artifact_path=_primary_artifact(profile),
            transfer_assessment_artifact_path=_primary_artifact(assessment),
            transfer_graph_artifact_path=_primary_artifact(graph),
            title=fixture["report_title"],
        )
    finally:
        await app.close()

    expectations = fixture["expectations"]
    checks: list[EvaluationCheck] = []
    _add_check(
        checks,
        "objective_ids",
        expectations["objective_ids"],
        [item.objective_id for item in profile.objectives],
    )
    _add_check(
        checks,
        "component_ids",
        expectations["component_ids"],
        [item.component_id for item in profile.components],
    )
    _add_check(
        checks,
        "dependency_ids",
        expectations["dependency_ids"],
        [item.dependency_id for item in profile.dependencies],
    )
    _add_check(
        checks,
        "assumption_ids",
        expectations["assumption_ids"],
        [item.assumption_id for item in profile.assumptions],
    )
    _add_check(
        checks,
        "resource_ids",
        expectations["resource_ids"],
        [item.resource_id for item in profile.resource_requirements],
    )
    citation_count = _profile_citation_count(profile)
    _add_check(
        checks,
        "minimum_profile_citations",
        expected=f">={expectations['minimum_profile_citations']}",
        actual=citation_count,
        passed=citation_count >= expectations["minimum_profile_citations"],
    )

    score_expectation = expectations["score"]
    if score_expectation["overall"] is None:
        _add_check(checks, "overall_score", None, assessment.overall_score)
    else:
        _add_float_check(checks, "overall_score", score_expectation["overall"], assessment.overall_score)
    _add_check(checks, "feasibility_band", score_expectation["band"], assessment.feasibility_band.value)
    _add_float_check(checks, "rubric_coverage", score_expectation["rubric_coverage"], assessment.rubric_coverage)
    _add_float_check(checks, "evidence_coverage", score_expectation["evidence_coverage"], assessment.evidence_coverage)
    expected_abstention = bool(score_expectation.get("abstain", False))
    actual_abstention = assessment.overall_score is None and assessment.feasibility_band.value == "insufficient"
    _add_check(checks, "abstention_behavior", expected_abstention, actual_abstention)
    _add_check(checks, "performance_prediction_suppressed", False, assessment.performance_prediction_provided)
    _add_check(checks, "legal_conclusion_suppressed", False, assessment.legal_conclusion_provided)

    expected_warnings = score_expectation.get("warning_codes", [])
    actual_warnings = sorted(warning.code for warning in assessment.warnings)
    _add_check(
        checks,
        "assessment_warning_codes",
        expected=sorted(expected_warnings),
        actual=actual_warnings,
        passed=set(expected_warnings).issubset(actual_warnings),
    )
    _add_mapping_checks(
        checks,
        "assumption",
        expectations.get("assumption_compatibility", {}),
        {item.assumption_id: item.compatibility.value for item in assessment.assumption_assessments},
    )
    _add_mapping_checks(
        checks,
        "component",
        expectations.get("component_reuse", {}),
        {item.component_id: item.reuse_level.value for item in assessment.component_assessments},
    )
    _add_mapping_checks(
        checks,
        "dependency",
        expectations.get("dependency_statuses", {}),
        {item.dependency_id: item.status.value for item in assessment.dependency_assessments},
    )
    _add_mapping_checks(
        checks,
        "resource",
        expectations.get("resource_statuses", {}),
        {item.resource_id: item.status.value for item in assessment.resource_assessments},
    )
    _add_check(
        checks,
        "validation_step_ids",
        expectations.get("validation_step_ids", []),
        [item.step_id for item in assessment.validation_plan],
    )
    _add_check(checks, "profile_parent_run_id", profile.run_id, assessment.parent_artifacts[0].run_id)
    graph_expectation = expectations["graph"]
    _add_check(checks, "graph_validated", True, graph.graph_validated)
    _add_float_check(
        checks,
        "graph_source_closure",
        graph_expectation["source_closure_ratio"],
        graph.metrics.source_closure_ratio,
    )
    _add_float_check(
        checks,
        "graph_profile_evidence_coverage",
        graph_expectation["profile_entity_evidence_coverage"],
        graph.metrics.profile_entity_evidence_coverage,
    )
    _add_check(
        checks,
        "graph_invalidated_conditions",
        graph_expectation["invalidated_condition_count"],
        graph.metrics.invalidated_condition_count,
    )
    _add_check(
        checks,
        "graph_transferred_components",
        graph_expectation["transferred_component_count"],
        graph.metrics.transferred_component_count,
    )
    _add_check(
        checks,
        "graph_high_risks",
        graph_expectation["high_risk_count"],
        graph.metrics.high_risk_count,
    )
    _add_check(
        checks,
        "graph_validation_steps",
        graph_expectation["validation_step_count"],
        graph.metrics.validation_step_count,
    )

    report_text = (workspace.workspace_path / report.report_path).read_text(encoding="utf-8")
    for section in expectations["report_sections"]:
        _add_check(checks, f"report_section_{section}", True, section in report_text)
    for expected_text in expectations.get("report_contains", []):
        _add_check(checks, f"report_contains_{expected_text}", True, expected_text in report_text)

    tool_results = [profile, assessment, graph, report]
    lifecycle_statuses = [
        _run_manifest(workspace, result.artifacts[-1].relative_path).status.value for result in tool_results
    ]
    _add_check(
        checks,
        "all_run_manifests_completed",
        [RunStatus.COMPLETED.value] * len(tool_results),
        lifecycle_statuses,
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
            "profile": _primary_artifact(profile),
            "assessment": _primary_artifact(assessment),
            "graph": _primary_artifact(graph),
            "report": report.report_path,
            "report_manifest": report.manifest_path,
            "report_run_manifest": report.artifacts[-1].relative_path,
        },
    )


async def run_transfer_offline_evaluation_suite(
    *,
    project_root: Path,
    fixture_paths: Sequence[Path],
    workspace_path: Path,
) -> OfflineEvaluationSuiteResult:
    """Run transfer cases in isolated workspaces and aggregate their checks."""

    if not fixture_paths:
        raise ValueError("At least one transfer evaluation fixture is required.")

    cases: list[OfflineEvaluationResult] = []
    seen_case_ids: set[str] = set()
    for fixture_path in fixture_paths:
        result = await run_transfer_offline_evaluation(
            project_root=project_root,
            fixture_path=fixture_path,
            workspace_path=workspace_path / fixture_path.stem,
        )
        if result.case_id in seen_case_ids:
            raise ValueError(f"Duplicate transfer evaluation case_id: {result.case_id}.")
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


def _profile_citation_count(profile: Any) -> int:
    groups = (
        profile.objectives,
        profile.components,
        profile.dependencies,
        profile.assumptions,
        profile.resource_requirements,
        profile.implementation_signals,
        profile.license_signals,
        profile.provenance_signals,
        profile.evidence_gaps,
    )
    return sum(len(item.citations) for group in groups for item in group)


def _primary_artifact(result: Any) -> str:
    if not result.artifacts:
        raise RuntimeError(f"{type(result).__name__} did not produce a primary artifact.")
    return result.artifacts[0].relative_path


def _run_manifest(workspace: Workspace, path: str) -> RunManifest:
    return RunManifest.model_validate(workspace.read_json_artifact(path))


def _add_mapping_checks(
    checks: list[EvaluationCheck],
    prefix: str,
    expected: dict[str, str],
    actual: dict[str, str],
) -> None:
    for item_id, expected_status in expected.items():
        _add_check(checks, f"{prefix}_{item_id}", expected_status, actual.get(item_id))


def _add_float_check(
    checks: list[EvaluationCheck],
    name: str,
    expected: float,
    actual: float | None,
) -> None:
    passed = actual is not None and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
    _add_check(checks, name, expected, actual, passed=passed)


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
