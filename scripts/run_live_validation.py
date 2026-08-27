"""Run the synthetic ReproScope workflow against a real Hy3 endpoint."""

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
except ModuleNotFoundError:  # Direct ``python scripts/run_live_validation.py`` invocation.
    from live_validation_security import enforce_live_summary_security

from hy3_reproscope_mcp import __version__
from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.models import (
    BuildEvidenceGraphResult,
    CompareReproductionResult,
    ExtractClaimsResult,
    ReliabilityScoreResult,
    RenderReportResult,
    RunManifest,
)
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import (
    build_evidence_graph,
    compare_results,
    extract_claims,
    render_report,
    score_paper,
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
    relative_path = f"{run_id}/run_manifest.json"
    payload, reference = workspace.read_json_artifact_with_reference(relative_path)
    return RunManifest.model_validate(payload), reference


def _run_manifest_summary(manifest: RunManifest, manifest_reference: Any) -> dict[str, Any]:
    return {
        "relative_path": manifest_reference.relative_path,
        "status": manifest.status.value,
        "status_history": [event.status.value for event in manifest.status_history],
        "error_code": manifest.error_code,
    }


def _tool_summary(workspace: Workspace, result: Any) -> dict[str, Any]:
    manifest, manifest_reference = _read_run_manifest(workspace, result.run_id)
    return {
        "run_id": result.run_id,
        "warnings": sorted({warning.code for warning in result.warnings}),
        "artifacts": _artifact_summary([*manifest.artifacts, manifest_reference]),
        "run_manifest": _run_manifest_summary(manifest, manifest_reference),
    }


def _load_latest_result(
    workspace: Workspace,
    *,
    prefix: str,
    filename: str,
    model_type: type[Any],
) -> Any:
    matches = sorted(
        workspace.workspace_path.glob(f"{prefix}_*/{filename}"),
        key=lambda path: path.stat().st_mtime,
    )
    if not matches:
        raise RuntimeError(f"No completed {filename} artifact exists in {workspace.workspace_path}.")
    relative_path = matches[-1].relative_to(workspace.workspace_path).as_posix()
    return model_type.model_validate(workspace.read_json_artifact(relative_path))


def _elapsed_from_manifests(workspace: Workspace, results: list[Any]) -> float:
    manifests = [_read_run_manifest(workspace, result.run_id)[0] for result in results]
    started_at = min(manifest.created_at for manifest in manifests)
    finished_at = max(manifest.updated_at for manifest in manifests)
    return round((finished_at - started_at).total_seconds(), 3)


async def _run() -> dict[str, Any]:
    if os.getenv(LIVE_OPT_IN) != "1":
        raise RuntimeError(f"Set {LIVE_OPT_IN}=1 to enable the real Hy3 validation run.")
    distribution_version = version("hy3-reproeval")
    if distribution_version != __version__:
        raise RuntimeError(
            "Source and installed distribution versions differ: "
            f"source={__version__}, distribution={distribution_version}. Reinstall the package before live validation."
        )

    # Live validation is an explicit publication path. Reject instruction-like
    # evidence rather than sending it to Hy3 and rely on the summary gate below
    # to enforce the no-execution/no-secret contract.
    settings = Settings(REPROSCOPE_PROMPT_INJECTION_POLICY="reject")
    settings.require_api_key()
    project_root = Path(__file__).resolve().parents[1]
    paper_path = project_root / "examples" / "sample_paper.md"
    results_path = project_root / "examples" / "sample_results.csv"
    log_path = project_root / "examples" / "sample_train.log"
    app = AppContext(settings=settings)
    workspace = Workspace(settings)
    started_at = perf_counter()

    try:
        claims = await extract_claims(
            app,
            paper_paths=[str(paper_path)],
            focus="primary metrics, baselines, ablations, and missing reproduction details",
        )
        comparison = await compare_results(
            app,
            paper_paths=[str(paper_path)],
            reproduction_paths=[str(results_path), str(log_path)],
            metric_hints=["accuracy", "latency_ms"],
            claims_artifact_path=_artifact_path(claims),
        )
        score = await score_paper(
            app,
            paper_paths=[str(paper_path)],
            reproduction_paths=[str(results_path), str(log_path)],
            rubric_focus=["baseline fairness", "statistical reporting", "implementation transparency"],
            claims_artifact_path=_artifact_path(claims),
            comparison_artifact_path=_artifact_path(comparison),
        )
        graph = build_evidence_graph(
            app,
            claims_artifact_path=_artifact_path(claims),
            comparison_artifact_path=_artifact_path(comparison),
            score_artifact_path=_artifact_path(score),
        )
        report = render_report(
            app,
            claims_artifact_path=_artifact_path(claims),
            comparison_artifact_path=_artifact_path(comparison),
            score_artifact_path=_artifact_path(score),
            evidence_graph_artifact_path=_artifact_path(graph),
            title="Synthetic Reproduction Study Reliability Audit",
        )
    finally:
        await app.close()
    elapsed_seconds = round(perf_counter() - started_at, 3)
    return _build_summary(
        settings=settings,
        workspace=workspace,
        claims=claims,
        comparison=comparison,
        score=score,
        graph=graph,
        report=report,
        elapsed_seconds=elapsed_seconds,
    )


def _build_summary(
    *,
    settings: Settings,
    workspace: Workspace,
    claims: ExtractClaimsResult,
    comparison: CompareReproductionResult,
    score: ReliabilityScoreResult,
    graph: BuildEvidenceGraphResult,
    report: RenderReportResult,
    elapsed_seconds: float,
) -> dict[str, Any]:
    metric_summary = [
        {
            "metric": metric.metric,
            "status": metric.computation_status.value,
            "reproduced_value": metric.reproduced_value,
            "sample_count": metric.sample_count,
            "absolute_delta": metric.absolute_delta,
            "relative_delta_percent": metric.relative_delta_percent,
            "severity": metric.severity.value,
        }
        for metric in comparison.metric_comparisons
    ]
    return {
        "status": "passed",
        "package_version": __version__,
        "distribution_version": version("hy3-reproeval"),
        "version_consistent": version("hy3-reproeval") == __version__,
        "mcp_version": version("mcp"),
        "provider": settings.resolved_api_provider(),
        "model": settings.hy3_model,
        "reasoning_effort": settings.hy3_reasoning_effort,
        "elapsed_seconds": elapsed_seconds,
        "tools": {
            "extract_claims": {
                **_tool_summary(workspace, claims),
                "claim_count": len(claims.core_claims),
                "setting_count": len(claims.experiment_settings),
            },
            "compare_results": {
                **_tool_summary(workspace, comparison),
                "metrics": metric_summary,
                "setting_checks": {
                    check.setting: check.status.value for check in comparison.deterministic_setting_checks
                },
            },
            "score_paper": {
                **_tool_summary(workspace, score),
                "overall_score": score.overall_score,
                "band": score.reliability_band.value,
                "rubric_coverage": score.rubric_coverage,
            },
            "build_evidence_graph": {
                **_tool_summary(workspace, graph),
                "validated": graph.graph_validated,
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
            },
            "render_report": {
                **_tool_summary(workspace, report),
                "report_path": report.report_path,
                "report_manifest_path": report.manifest_path,
                "evidence_graph_run_id": report.evidence_graph_run_id,
            },
        },
    }


def _summarize_existing() -> dict[str, Any]:
    settings = Settings(REPROSCOPE_PROMPT_INJECTION_POLICY="reject")
    workspace = Workspace(settings)
    claims = _load_latest_result(
        workspace,
        prefix="claims",
        filename="extract_claims.json",
        model_type=ExtractClaimsResult,
    )
    comparison = _load_latest_result(
        workspace,
        prefix="compare",
        filename="compare_results.json",
        model_type=CompareReproductionResult,
    )
    score = _load_latest_result(
        workspace,
        prefix="score",
        filename="reliability_score.json",
        model_type=ReliabilityScoreResult,
    )
    graph = _load_latest_result(
        workspace,
        prefix="graph",
        filename="evidence_graph.json",
        model_type=BuildEvidenceGraphResult,
    )
    report = _load_latest_result(
        workspace,
        prefix="report",
        filename="report_manifest.json",
        model_type=RenderReportResult,
    )
    results = [claims, comparison, score, graph, report]
    return _build_summary(
        settings=settings,
        workspace=workspace,
        claims=claims,
        comparison=comparison,
        score=score,
        graph=graph,
        report=report,
        elapsed_seconds=_elapsed_from_manifests(workspace, results),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--summarize-existing",
        action="store_true",
        help="Summarize the latest completed workflow in REPROSCOPE_WORKSPACE without calling Hy3.",
    )
    args = parser.parse_args()
    result = _summarize_existing() if args.summarize_existing else asyncio.run(_run())
    enforce_live_summary_security(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
