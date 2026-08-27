from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.errors import ArtifactLineageError, EvidenceGraphValidationError
from hy3_reproscope_mcp.lineage import validate_transfer_graph_artifact_lineage
from hy3_reproscope_mcp.models import EvidenceGraphEdge
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import (
    assess_transfer,
    audit_repository,
    build_transfer_evidence_graph,
    extract_solution_profile,
    render_transfer_report,
)
from hy3_reproscope_mcp.transfer_graph import require_validated_transfer_graph, validate_transfer_graph
from hy3_reproscope_mcp.transfer_models import SolutionProfileResult, TransferAssessmentResult
from hy3_reproscope_mcp.workspace import parent_artifact_reference


class FakeHy3Client:
    def __init__(self, payloads: dict[type[BaseModel], dict[str, Any]]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[Sequence[Mapping[str, str]], type[BaseModel]]] = []

    async def complete_structured(
        self,
        messages: Sequence[Mapping[str, str]],
        response_model: type[BaseModel],
        **_: Any,
    ) -> BaseModel:
        self.calls.append((messages, response_model))
        return response_model.model_validate(self.payloads[response_model])

    async def close(self) -> None:
        return None


def _settings(tmp_path) -> Settings:
    return Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(tmp_path),
        REPROSCOPE_WORKSPACE=tmp_path / "artifacts",
    )


def _citation(source_id: str) -> dict[str, str]:
    return {
        "source_id": source_id,
        "support": "supports",
        "locator": "L1",
        "rationale": "The source directly supports this assessment.",
    }


def _profile_payload() -> dict[str, Any]:
    return {
        "run_id": "model_profile",
        "summary": "The source describes a modular edge inference solution.",
        "objectives": [
            {
                "objective_id": "objective_1",
                "statement": "Reduce inference latency.",
                "success_criteria": ["p95 latency below 20 ms"],
                "citations": [_citation("solution_1")],
            }
        ],
        "components": [
            {
                "component_id": "component_1",
                "name": "Feature encoder",
                "responsibility": "Produces compact input features.",
                "interfaces": ["tensor input", "embedding output"],
                "citations": [_citation("solution_1")],
            },
            {
                "component_id": "component_1",
                "name": "Duplicate encoder",
                "responsibility": "This duplicate should be removed locally.",
            },
        ],
        "dependencies": [
            {
                "dependency_id": "dependency_1",
                "name": "GPU runtime",
                "dependency_type": "hardware",
                "required_condition": "CUDA-capable GPU",
                "replaceable": True,
                "citations": [_citation("solution_1")],
            }
        ],
        "assumptions": [
            {
                "assumption_id": "assumption_1",
                "statement": "A CUDA-capable GPU is available.",
                "scope": "deployment",
                "criticality": "high",
                "citations": [_citation("solution_1")],
            }
        ],
        "resource_requirements": [
            {
                "resource_id": "resource_1",
                "resource_type": "compute",
                "requirement": "CUDA-capable GPU",
                "flexibility": "A CPU fallback is not documented.",
                "citations": [_citation("solution_1")],
            }
        ],
    }


def _assessment_payload() -> dict[str, Any]:
    dimension_names = [
        "evidence_reliability",
        "assumption_compatibility",
        "dependency_feasibility",
        "resource_feasibility",
        "adaptation_manageability",
        "validation_readiness",
    ]
    return {
        "run_id": "model_transfer",
        "solution_profile_run_id": "model_profile",
        "summary": "Transfer is feasible only after replacing the GPU-specific runtime.",
        "target_context_summary": "The target is a CPU-only edge device with a 30 ms latency budget.",
        "overall_score": 99,
        "feasibility_band": "promising",
        "conclusion_confidence": 0.78,
        "dimensions": [
            {
                "name": name,
                "score": 84,
                "rationale": "The supplied source and target context support a conditional assessment.",
                "citations": [_citation("solution_1"), _citation("target_1")],
            }
            for name in dimension_names
        ],
        "assumption_assessments": [
            {
                "assumption_id": "assumption_1",
                "compatibility": "incompatible",
                "target_condition": "Only a CPU runtime is available.",
                "rationale": "The target context conflicts with the source deployment assumption.",
                "citations": [_citation("solution_1"), _citation("target_1")],
            },
            {
                "assumption_id": "invented_assumption",
                "compatibility": "compatible",
                "target_condition": "Unknown.",
                "rationale": "This relation should be removed locally.",
            },
        ],
        "component_assessments": [
            {
                "component_id": "component_1",
                "reuse_level": "adapt",
                "rationale": "The interface can remain while the runtime changes.",
                "required_changes": ["export to a CPU-compatible runtime"],
                "citations": [_citation("solution_1"), _citation("target_1")],
            },
            {
                "component_id": "invented_component",
                "reuse_level": "direct",
                "rationale": "This relation should be removed locally.",
            },
        ],
        "dependency_assessments": [
            {
                "dependency_id": "dependency_1",
                "status": "unsatisfied",
                "target_condition": "The target has no CUDA runtime.",
                "rationale": "The documented execution provider cannot run in the target context.",
                "required_action": "Select and benchmark a CPU execution provider.",
                "citations": [_citation("solution_1"), _citation("target_1")],
            }
        ],
        "resource_assessments": [
            {
                "resource_id": "resource_1",
                "status": "unsatisfied",
                "target_condition": "Only CPU compute is available.",
                "rationale": "The source requirement is absent from the target.",
                "required_action": "Establish CPU latency and memory feasibility.",
                "citations": [_citation("solution_1"), _citation("target_1")],
            }
        ],
        "transferable_strengths": ["The component interface is explicit."],
        "required_adaptations": [
            {
                "adaptation_id": "adaptation_1",
                "affected_component_ids": ["component_1", "invented_component"],
                "change": "Replace the GPU runtime.",
                "reason": "The target has no CUDA-capable GPU.",
                "estimated_effort": "medium",
                "citations": [_citation("target_1")],
            }
        ],
        "risks": [
            {
                "risk_id": "risk_1",
                "category": "performance",
                "level": "high",
                "description": "CPU latency may exceed the target budget.",
                "mitigation": "Benchmark an exported model on the target device.",
                "citations": [_citation("target_1")],
            }
        ],
        "validation_plan": [
            {
                "step_id": "step_1",
                "objective": "Measure target latency.",
                "method": "Run a representative benchmark on the target device.",
                "success_criteria": ["p95 latency below 30 ms"],
                "prerequisites": ["CPU-compatible model export"],
                "citations": [_citation("target_1")],
            }
        ],
    }


@pytest.mark.asyncio
async def test_transfer_workflow_writes_lineage_validated_report(tmp_path) -> None:
    solution_path = tmp_path / "solution.md"
    target_path = tmp_path / "target.md"
    repository_path = tmp_path / "repository"
    solution_path.write_text(
        "The feature encoder targets p95 latency below 20 ms and requires a CUDA-capable GPU.",
        encoding="utf-8",
    )
    target_path.write_text(
        "The target is a CPU-only edge device with a p95 latency budget below 30 ms.",
        encoding="utf-8",
    )
    repository_path.mkdir()
    (repository_path / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "0.1.0"\ndependencies = ["torch>=2"]\n',
        encoding="utf-8",
    )
    fake = FakeHy3Client(
        {
            SolutionProfileResult: _profile_payload(),
            TransferAssessmentResult: _assessment_payload(),
        }
    )
    app = AppContext(settings=_settings(tmp_path), hy3_client=fake)

    profile = await extract_solution_profile(
        app,
        solution_paths=[str(solution_path)],
        focus="deployment dependencies",
    )
    repository_audit = audit_repository(app, repository_path=str(repository_path))
    assessment = await assess_transfer(
        app,
        solution_paths=[str(solution_path)],
        target_context_paths=[str(target_path)],
        solution_profile_artifact_path=profile.artifacts[0].relative_path,
        focus="CPU-only deployment",
        repository_audit_artifact_path=repository_audit.artifacts[0].relative_path,
    )
    graph = build_transfer_evidence_graph(
        app,
        solution_profile_artifact_path=profile.artifacts[0].relative_path,
        transfer_assessment_artifact_path=assessment.artifacts[0].relative_path,
    )
    report = render_transfer_report(
        app,
        solution_profile_artifact_path=profile.artifacts[0].relative_path,
        transfer_assessment_artifact_path=assessment.artifacts[0].relative_path,
        transfer_graph_artifact_path=graph.artifacts[0].relative_path,
        title="CPU edge transfer assessment",
    )

    assert len(fake.calls) == 2
    assert len(profile.components) == 1
    assert any(warning.code == "DUPLICATE_SOLUTION_PROFILE_ID" for warning in profile.warnings)
    assert assessment.solution_profile_run_id == profile.run_id
    assert assessment.repository_audit_run_id == repository_audit.run_id
    assert assessment.overall_score == 84
    assert assessment.feasibility_band.value == "conditional"
    assert [item.assumption_id for item in assessment.assumption_assessments] == ["assumption_1"]
    assert [item.component_id for item in assessment.component_assessments] == ["component_1"]
    assert assessment.dependency_assessments[0].status.value == "unsatisfied"
    assert assessment.resource_assessments[0].status.value == "unsatisfied"
    assert assessment.required_adaptations[0].affected_component_ids == ["component_1"]
    warning_codes = {warning.code for warning in assessment.warnings}
    assert "UNKNOWN_TRANSFER_ASSUMPTION_ID" in warning_codes
    assert "UNKNOWN_TRANSFER_COMPONENT_ID" in warning_codes
    assert "NO_TARGET_PERFORMANCE_PREDICTION" in warning_codes
    assert "TRANSFER_BLOCKERS_PRESENT" in warning_codes
    assert "REPOSITORY_AUDIT_CALLER_ASSOCIATED" in warning_codes
    assert [parent.role for parent in assessment.parent_artifacts] == [
        "solution_profile",
        "repository_audit",
    ]
    assert assessment.parent_artifacts[0].run_id == profile.run_id
    transfer_prompt = fake.calls[1][0][-1]["content"]
    assert "repository_audit" in transfer_prompt
    assert "LOCKFILE_NOT_FOUND" in transfer_prompt
    dependency_dimension = next(
        dimension for dimension in assessment.dimensions if dimension.name.value == "dependency_feasibility"
    )
    assert any("LOCKFILE_NOT_FOUND" in gap for gap in dependency_dimension.evidence_gaps)
    assert graph.graph_validated is True
    serialized_keys = list(graph.model_dump(mode="json"))
    assert serialized_keys.index("graph_validated") < serialized_keys.index("nodes")
    assert graph.model_dump(mode="json")["graph_validated"] is True
    assert graph.source_run_ids == [profile.run_id, assessment.run_id]
    assert graph.metrics.profile_entity_evidence_coverage == 1
    assert graph.metrics.assumption_assessment_coverage == 1
    assert graph.metrics.component_assessment_coverage == 1
    assert graph.metrics.dependency_assessment_coverage == 1
    assert graph.metrics.resource_assessment_coverage == 1
    assert graph.metrics.invalidated_condition_count == 3
    assert graph.metrics.transferred_component_count == 1
    assert graph.metrics.high_risk_count == 1
    assert graph.metrics.validation_step_count == 1
    assert graph.metrics.source_closure_ratio == 1
    assert report.source_run_ids == [profile.run_id, assessment.run_id]
    assert report.transfer_graph_run_id == graph.run_id
    assert report.graph_validated is True
    assert len(report.artifact_inventory) == 3
    markdown = (tmp_path / "artifacts" / report.report_path).read_text(encoding="utf-8")
    assert "# CPU edge transfer assessment" in markdown
    assert "## Assumption compatibility" in markdown
    assert "## Dependency and resource feasibility" in markdown
    assert "## Transfer evidence graph" in markdown
    assert "graph_validated=true" in markdown
    assert "does not predict point performance" in markdown
    manifest = json.loads((tmp_path / "artifacts" / report.manifest_path).read_text(encoding="utf-8"))
    assert manifest["graph_validated"] is True

    invalid_graph = graph.model_copy(deep=True)
    invalid_graph.edges.append(
        EvidenceGraphEdge(
            edge_id="transfer-edge:invalid",
            edge_type="adapted_for",
            source_node_id="assessment:transfer",
            target_node_id="project-context:1",
            evidence_kind="inferred",
            rationale="This endpoint pair is not allowed.",
        )
    )
    with pytest.raises(EvidenceGraphValidationError, match="Illegal adapted_for endpoints"):
        validate_transfer_graph(invalid_graph)

    unmarked_graph = graph.model_copy(update={"graph_validated": False})
    with pytest.raises(EvidenceGraphValidationError, match="graph_validated=true"):
        require_validated_transfer_graph(unmarked_graph)

    wrong_lineage = graph.model_copy(deep=True)
    wrong_lineage.source_run_ids[0] = "other_profile"
    with pytest.raises(ArtifactLineageError, match="not built from the supplied"):
        validate_transfer_graph_artifact_lineage(
            wrong_lineage,
            profile,
            assessment,
            profile_artifact=parent_artifact_reference("solution_profile", profile.artifacts[0]),
            assessment_artifact=parent_artifact_reference(
                "transfer_assessment",
                assessment.artifacts[0],
            ),
        )


@pytest.mark.asyncio
async def test_transfer_assessment_rejects_changed_solution_source(tmp_path) -> None:
    solution_path = tmp_path / "solution.md"
    target_path = tmp_path / "target.md"
    solution_path.write_text("The source requires a CUDA-capable GPU.", encoding="utf-8")
    target_path.write_text("The target provides CPU compute only.", encoding="utf-8")
    fake = FakeHy3Client({SolutionProfileResult: _profile_payload()})
    app = AppContext(settings=_settings(tmp_path), hy3_client=fake)
    profile = await extract_solution_profile(app, solution_paths=[str(solution_path)], focus=None)
    solution_path.write_text("The source now supports a CPU runtime.", encoding="utf-8")

    with pytest.raises(ArtifactLineageError, match="does not match"):
        await assess_transfer(
            app,
            solution_paths=[str(solution_path)],
            target_context_paths=[str(target_path)],
            solution_profile_artifact_path=profile.artifacts[0].relative_path,
            focus=None,
        )

    assert len(fake.calls) == 1
