from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.evidence_graph import build_graph
from hy3_reproscope_mcp.loaders import load_sources
from hy3_reproscope_mcp.models import (
    CompareReproductionResult,
    DomainProfileMode,
    DomainProfileName,
    ExtractClaimsResult,
    ReliabilityScoreResult,
)
from hy3_reproscope_mcp.profiles import registry
from hy3_reproscope_mcp.profiles.isac_phy import detect_isac_profile
from hy3_reproscope_mcp.renderer import render_markdown_report
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import extract_claims

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeHy3Client:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[Sequence[Mapping[str, str]]] = []

    async def complete_structured(
        self,
        messages: Sequence[Mapping[str, str]],
        response_model: type[BaseModel],
        **_: Any,
    ) -> BaseModel:
        self.calls.append(messages)
        return response_model.model_validate(self.payload)

    async def close(self) -> None:
        return None


def _settings(tmp_path, allowed_root: Path | None = None) -> Settings:
    return Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(allowed_root or tmp_path),
        REPROSCOPE_WORKSPACE=tmp_path / "artifacts",
    )


def _citation() -> dict[str, str]:
    return {
        "source_id": "paper_1",
        "support": "mentions",
        "locator": "L1",
        "rationale": "The current paper states this condition.",
    }


def test_isac_registry_is_versioned_and_bounded() -> None:
    metrics = registry.isac_document("metrics")
    assumptions = registry.isac_document("assumptions")
    rules = registry.isac_document("risk_rules")

    assert metrics.version == "1.0.0"
    assert len(metrics.payload["metrics"]) == 24
    assert len(assumptions.payload["assumptions"]) >= 20
    assert len(rules.payload["rules"]) == 12
    assert all(len(value) == 64 for value in registry.isac_hashes().values())
    metrics.payload["metrics"].clear()
    assert len(registry.isac_document("metrics").payload["metrics"]) == 24


def test_isac_detector_requires_joint_evidence(tmp_path) -> None:
    radar_path = PROJECT_ROOT / "examples" / "sample_radar_note.md"
    radar_bundle = load_sources(
        [str(radar_path)],
        role="paper",
        settings=_settings(tmp_path, PROJECT_ROOT),
        source_id_prefix="paper",
    )

    result = detect_isac_profile(radar_bundle)

    assert result.detected is False
    assert result.confidence < 0.80


@pytest.mark.asyncio
async def test_generic_profile_remains_default(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    paper_path.write_text("The method reports accuracy 0.91.", encoding="utf-8")
    fake = FakeHy3Client(
        {
            "run_id": "model_run",
            "summary": "A generic empirical claim was found.",
        }
    )
    app = AppContext(settings=_settings(tmp_path), hy3_client=fake)

    result = await extract_claims(app, paper_paths=[str(paper_path)], focus=None)

    assert result.domain_profile_activation is not None
    assert result.domain_profile_activation.effective_profile is DomainProfileName.GENERIC
    assert result.isac_analysis is None
    assert set(result.profile_versions) == {"generic_profile"}
    prompt = fake.calls[0][-1]["content"]
    assert '"isac_profile_context": null' in prompt


@pytest.mark.asyncio
async def test_auto_isac_profile_normalizes_registry_and_evidence_boundaries(tmp_path) -> None:
    fixture = json.loads((PROJECT_ROOT / "evals" / "synthetic_isac_profile.json").read_text(encoding="utf-8"))
    paper_path = PROJECT_ROOT / fixture["inputs"]["paper"]
    fake = FakeHy3Client(fixture["response"])
    app = AppContext(settings=_settings(tmp_path, PROJECT_ROOT), hy3_client=fake)

    result = await extract_claims(
        app,
        paper_paths=[str(paper_path)],
        focus=None,
        domain_profile=DomainProfileMode(fixture["inputs"]["domain_profile"]),
    )

    expectations = fixture["expectations"]
    activation = result.domain_profile_activation
    assert activation is not None
    assert activation.effective_profile.value == expectations["effective_profile"]
    assert activation.confidence >= expectations["minimum_confidence"]
    assert result.isac_analysis is not None
    assert [metric.canonical_name for metric in result.isac_analysis.metrics] == expectations["metric_names"]
    assert [assumption.name for assumption in result.isac_analysis.assumptions] == expectations["assumption_names"]
    assert len(result.isac_analysis.findings) == expectations["finding_count"]
    assert result.isac_analysis.findings[0].status.value == "unknown"
    assert result.isac_analysis.findings[1].status.value == "warning"
    assert all(finding.affects_score is False for finding in result.isac_analysis.findings)
    warning_codes = {warning.code for warning in result.warnings}
    assert set(expectations["warning_codes"]).issubset(warning_codes)
    assert set(result.registry_hashes) == {
        "isac_taxonomy",
        "isac_metrics",
        "isac_assumptions",
        "isac_risk_rules",
    }

    manifest_path = tmp_path / "artifacts" / result.run_id / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["profile_versions"]["isac_profile"] == "1.0.0"
    assert manifest["registry_hashes"] == result.registry_hashes


@pytest.mark.asyncio
async def test_explicit_isac_profile_downgrades_unsupported_classification(tmp_path) -> None:
    fixture = json.loads(
        (PROJECT_ROOT / "evals" / "synthetic_isac_insufficient_evidence.json").read_text(encoding="utf-8")
    )
    paper_path = PROJECT_ROOT / fixture["inputs"]["paper"]
    fake = FakeHy3Client(fixture["response"])
    app = AppContext(settings=_settings(tmp_path, PROJECT_ROOT), hy3_client=fake)

    result = await extract_claims(
        app,
        paper_paths=[str(paper_path)],
        focus=None,
        domain_profile=DomainProfileMode(fixture["inputs"]["domain_profile"]),
    )

    expectations = fixture["expectations"]
    activation = result.domain_profile_activation
    assert activation is not None
    assert activation.detected_profile.value == expectations["detected_profile"]
    assert activation.effective_profile.value == expectations["effective_profile"]
    assert result.isac_analysis is not None
    assert result.isac_analysis.system_type.value == expectations["system_type"]
    assert result.isac_analysis.evidence_level.value == expectations["evidence_level"]
    assert result.isac_analysis.waveforms == []
    assert result.isac_analysis.research_methods == []
    assert len(result.isac_analysis.findings) == expectations["finding_count"]
    assert all(finding.status.value == "unknown" for finding in result.isac_analysis.findings)
    warning_codes = {warning.code for warning in result.warnings}
    assert set(expectations["warning_codes"]).issubset(warning_codes)


def test_isac_findings_enter_existing_graph_and_report() -> None:
    claims = ExtractClaimsResult.model_validate(
        {
            "run_id": "claims_1",
            "summary": "ISAC claims",
            "domain_profile_activation": {
                "requested_profile": "isac_phy",
                "detected_profile": "isac_phy",
                "effective_profile": "isac_phy",
                "profile_version": "1.0.0",
                "confidence": 0.95,
                "activation_source": "explicit_parameter",
            },
            "isac_analysis": {
                "system_type": "fully_integrated",
                "research_methods": ["beamforming"],
                "evidence_level": "simulation",
                "findings": [
                    {
                        "rule_id": "ISAC-R006",
                        "status": "unknown",
                        "summary": "The weight sweep is not established.",
                        "rationale": "No evidence was supplied.",
                        "missing_evidence": ["Weight sweep or Pareto evidence"],
                    }
                ],
            },
        }
    )
    comparison = CompareReproductionResult(
        run_id="compare_1",
        summary="No reproduction metrics were supplied.",
        conclusion_stability="Unknown.",
    )
    score = ReliabilityScoreResult.model_validate(
        {
            "run_id": "score_1",
            "overall_score": None,
            "reliability_band": "insufficient",
            "conclusion_confidence": 0,
            "summary": "Insufficient evidence.",
            "dimensions": [
                {
                    "name": "reproduction_result_agreement",
                    "score": None,
                    "assessment_status": "insufficient_evidence",
                    "rationale": "No reproduction was supplied.",
                }
            ],
            "reproduction_verdict": "Not assessed.",
            "experimental_rigor_verdict": "Not assessed.",
        }
    )

    graph = build_graph(run_id="graph_1", claims=claims, comparison=comparison, score=score)
    markdown = render_markdown_report(
        title="ISAC audit",
        claims=claims,
        comparison=comparison,
        score=score,
        graph=graph,
        artifact_inventory=[],
    )

    assert any(node.node_type.value == "domain_profile" for node in graph.nodes)
    assert any(node.node_type.value == "domain_finding" for node in graph.nodes)
    assert "## ISAC physical-layer audit" in markdown
    assert "ISAC-R006" in markdown
