"""Run explicit and conservative-auto ISAC cases against a real Hy3 endpoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from importlib.metadata import version
from pathlib import Path
from typing import Any

try:
    from scripts.live_validation_security import enforce_live_summary_security
except ModuleNotFoundError:  # Direct ``python scripts/run_live_isac_validation.py`` invocation.
    from live_validation_security import enforce_live_summary_security

from hy3_reproscope_mcp import __version__
from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.models import DomainProfileMode, ProfileRequestSource, RunManifest
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import extract_claims
from hy3_reproscope_mcp.workspace import Workspace

LIVE_OPT_IN = "REPROSCOPE_RUN_LIVE"


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


def _summary(workspace: Workspace, result: Any, *, case: str) -> dict[str, Any]:
    manifest, manifest_reference = _read_run_manifest(workspace, result.run_id)
    activation = result.domain_profile_activation
    analysis = result.isac_analysis
    activation_reason = activation.activation_source.value
    if activation.matched_signals:
        activation_reason += "; matched_signals=" + ",".join(activation.matched_signals)
    elif activation.ambiguous_signals:
        activation_reason += "; ambiguous_signals=" + ",".join(activation.ambiguous_signals)
    if activation.warnings:
        activation_reason += "; warnings=" + " | ".join(activation.warnings)
    return {
        "case": case,
        "run_id": result.run_id,
        "requested_profile": activation.requested_profile.value,
        "effective_profile": activation.effective_profile.value,
        "activation_reason": activation_reason,
        "isac_analysis_present": analysis is not None,
        "metric_count": len(analysis.metrics) if analysis else 0,
        "assumption_count": len(analysis.assumptions) if analysis else 0,
        "finding_count": len(analysis.findings) if analysis else 0,
        "risk_finding_count": sum(finding.status.value == "risk" for finding in analysis.findings) if analysis else 0,
        "warnings": sorted({warning.code for warning in result.warnings}),
        "artifacts": _artifact_summary([*manifest.artifacts, manifest_reference]),
        "run_manifest": {
            "status": manifest.status.value,
            "status_history": [event.status.value for event in manifest.status_history],
        },
    }


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
    isac_path = project_root / "examples" / "sample_isac_paper.md"
    radar_path = project_root / "examples" / "sample_radar_note.md"
    app = AppContext(settings=settings)
    workspace = Workspace(settings)
    try:
        explicit = await extract_claims(
            app,
            paper_paths=[str(isac_path)],
            focus="ISAC system type, metrics, assumptions, risk rules, and evidence citations",
            domain_profile=DomainProfileMode.ISAC_PHY,
            profile_request_source=ProfileRequestSource.TOOL_PARAMETER,
        )
        auto_positive = await extract_claims(
            app,
            paper_paths=[str(isac_path)],
            focus="conservative automatic ISAC activation and citation-gated findings",
            domain_profile=DomainProfileMode.AUTO,
            profile_request_source=ProfileRequestSource.TOOL_PARAMETER,
        )
        auto_negative = await extract_claims(
            app,
            paper_paths=[str(radar_path)],
            focus="confirm radar-only material does not automatically activate ISAC",
            domain_profile=DomainProfileMode.AUTO,
            profile_request_source=ProfileRequestSource.TOOL_PARAMETER,
        )
    finally:
        await app.close()

    cases = [
        _summary(workspace, explicit, case="explicit_isac"),
        _summary(workspace, auto_positive, case="auto_isac_positive"),
        _summary(workspace, auto_negative, case="auto_radar_negative"),
    ]
    return {
        "status": "passed",
        "package_version": __version__,
        "distribution_version": distribution_version,
        "provider": settings.resolved_api_provider(),
        "model": settings.hy3_model,
        "cases": cases,
        "assertions": {
            "explicit_effective_profile": cases[0]["effective_profile"],
            "auto_positive_effective_profile": cases[1]["effective_profile"],
            "auto_negative_effective_profile": cases[2]["effective_profile"],
            "all_manifests_completed": all(case["run_manifest"]["status"] == "completed" for case in cases),
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
