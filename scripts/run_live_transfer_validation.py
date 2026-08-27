"""Run the technology-transfer workflow against a real Hy3 endpoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any

try:
    from scripts.live_validation_security import enforce_live_summary_security
except ModuleNotFoundError:  # Direct ``python scripts/run_live_transfer_validation.py`` invocation.
    from live_validation_security import enforce_live_summary_security

from hy3_reproscope_mcp import __version__
from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.models import RunManifest
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import (
    assess_transfer,
    audit_repository,
    build_transfer_evidence_graph,
    extract_solution_profile,
    render_transfer_report,
)
from hy3_reproscope_mcp.workspace import Workspace

LIVE_OPT_IN = "REPROSCOPE_RUN_LIVE"


def _artifact_path(result: Any) -> str:
    if not result.artifacts:
        raise RuntimeError(f"{type(result).__name__} did not produce an artifact.")
    return result.artifacts[0].relative_path


def _artifact_summary(artifacts: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "artifact_type": artifact.artifact_type,
            "relative_path": artifact.relative_path,
            "content_hash": artifact.content_hash,
            "payload_hash": artifact.payload_hash,
            "schema_version": artifact.schema_version,
        }
        for artifact in artifacts
    ]


def _read_run_manifest(workspace: Workspace, run_id: str) -> tuple[RunManifest, Any]:
    payload, reference = workspace.read_json_artifact_with_reference(f"{run_id}/run_manifest.json")
    return RunManifest.model_validate(payload), reference


def _tool_summary(workspace: Workspace, result: Any) -> dict[str, Any]:
    manifest, manifest_reference = _read_run_manifest(workspace, result.run_id)
    summary = {
        "run_id": result.run_id,
        "warnings": sorted({warning.code for warning in result.warnings}),
        "artifacts": _artifact_summary([*manifest.artifacts, manifest_reference]),
        "run_manifest": {
            "relative_path": manifest_reference.relative_path,
            "status": manifest.status.value,
            "status_history": [event.status.value for event in manifest.status_history],
            "error_code": manifest.error_code,
        },
    }
    if hasattr(result, "execution_preflight"):
        preflight = result.execution_preflight.model_dump(mode="json")
        # The absolute repository root is useful inside the server artifact,
        # but must not be copied into credential-free client/live evidence.
        preflight["allowed_root_configured"] = bool(preflight.pop("allowed_root", None))
        summary["execution_preflight"] = preflight
    if hasattr(result, "executed_repository_code"):
        summary["executed_repository_code"] = result.executed_repository_code
    return summary


async def _run() -> dict[str, Any]:
    if os.getenv(LIVE_OPT_IN) != "1":
        raise RuntimeError(f"Set {LIVE_OPT_IN}=1 to enable the real Hy3 validation run.")
    distribution_version = version("hy3-reproeval")
    if distribution_version != __version__:
        raise RuntimeError(
            "Source and installed distribution versions differ: "
            f"source={__version__}, distribution={distribution_version}. Reinstall the package before live validation."
        )

    settings = Settings(REPROSCOPE_PROMPT_INJECTION_POLICY="reject")
    settings.require_api_key()
    project_root = Path(__file__).resolve().parents[1]
    solution_path = project_root / "examples" / "sample_solution.md"
    target_path = project_root / "examples" / "sample_target_context.md"
    app = AppContext(settings=settings)
    workspace = Workspace(settings)
    started_at = perf_counter()

    try:
        profile = await extract_solution_profile(
            app,
            solution_paths=[str(solution_path)],
            focus="objectives, reusable components, dependencies, assumptions, resources, and validation gaps",
        )
        repository = audit_repository(app, repository_path=str(project_root))
        assessment = await assess_transfer(
            app,
            solution_paths=[str(solution_path)],
            target_context_paths=[str(target_path)],
            solution_profile_artifact_path=_artifact_path(profile),
            focus="conditional feasibility, dependency/resource blockers, adaptation effort, and validation plan",
            repository_audit_artifact_path=_artifact_path(repository),
        )
        graph = build_transfer_evidence_graph(
            app,
            solution_profile_artifact_path=_artifact_path(profile),
            transfer_assessment_artifact_path=_artifact_path(assessment),
        )
        report = render_transfer_report(
            app,
            solution_profile_artifact_path=_artifact_path(profile),
            transfer_assessment_artifact_path=_artifact_path(assessment),
            transfer_graph_artifact_path=_artifact_path(graph),
            title="Live 0.15.0 Technology Transfer Validation",
        )
    finally:
        await app.close()

    return {
        "status": "passed",
        "package_version": __version__,
        "distribution_version": distribution_version,
        "provider": settings.resolved_api_provider(),
        "model": settings.hy3_model,
        "elapsed_seconds": round(perf_counter() - started_at, 3),
        "tools": {
            "extract_solution_profile": _tool_summary(workspace, profile),
            "audit_repository": _tool_summary(workspace, repository),
            "assess_transfer": {
                **_tool_summary(workspace, assessment),
                "overall_score": assessment.overall_score,
                "feasibility_band": assessment.feasibility_band.value,
                "evidence_coverage": assessment.evidence_coverage,
                "rubric_coverage": assessment.rubric_coverage,
                "performance_prediction_provided": assessment.performance_prediction_provided,
                "legal_conclusion_provided": assessment.legal_conclusion_provided,
            },
            "build_transfer_graph": {
                **_tool_summary(workspace, graph),
                "validated": graph.graph_validated,
                "metrics": graph.metrics.model_dump(mode="json"),
            },
            "render_transfer_report": {
                **_tool_summary(workspace, report),
                "report_path": report.report_path,
                "manifest_path": report.manifest_path,
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    result = asyncio.run(_run())
    enforce_live_summary_security(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
