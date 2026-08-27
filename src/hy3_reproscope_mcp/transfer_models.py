"""Structured models for conditional technology-transfer assessment."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from .models import (
    ArtifactAuditEntry,
    DifferenceSeverity,
    DimensionAssessmentStatus,
    EvidenceCitation,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    StrictModel,
    ToolResultBase,
)


class AssumptionCompatibility(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNCERTAIN = "uncertain"
    MISSING_TARGET_EVIDENCE = "missing_target_evidence"


class ComponentReuseLevel(StrEnum):
    DIRECT = "direct"
    ADAPT = "adapt"
    REPLACE = "replace"
    UNKNOWN = "unknown"


class TransferRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class AdaptationEffort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class TransferConditionStatus(StrEnum):
    SATISFIED = "satisfied"
    CONDITIONAL = "conditional"
    UNSATISFIED = "unsatisfied"
    UNKNOWN = "unknown"


class TransferDimension(StrEnum):
    EVIDENCE_RELIABILITY = "evidence_reliability"
    ASSUMPTION_COMPATIBILITY = "assumption_compatibility"
    DEPENDENCY_FEASIBILITY = "dependency_feasibility"
    RESOURCE_FEASIBILITY = "resource_feasibility"
    ADAPTATION_MANAGEABILITY = "adaptation_manageability"
    VALIDATION_READINESS = "validation_readiness"


class TransferFeasibilityBand(StrEnum):
    PROMISING = "promising"
    CONDITIONAL = "conditional"
    HIGH_RISK = "high_risk"
    INSUFFICIENT = "insufficient"


class SolutionObjective(StrictModel):
    objective_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    success_criteria: list[str] = Field(default_factory=list)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class SolutionComponent(StrictModel):
    component_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    responsibility: str = Field(min_length=1)
    interfaces: list[str] = Field(default_factory=list)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class SolutionDependency(StrictModel):
    dependency_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    dependency_type: str = Field(min_length=1)
    required_condition: str = Field(min_length=1)
    replaceable: bool | None = None
    citations: list[EvidenceCitation] = Field(default_factory=list)


class SolutionAssumption(StrictModel):
    assumption_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    criticality: TransferRiskLevel
    citations: list[EvidenceCitation] = Field(default_factory=list)


class ResourceRequirement(StrictModel):
    resource_id: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    requirement: str = Field(min_length=1)
    flexibility: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class SolutionSignal(StrictModel):
    signal: str = Field(min_length=1)
    implication: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class SolutionEvidenceGap(StrictModel):
    item: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    severity: DifferenceSeverity
    citations: list[EvidenceCitation] = Field(default_factory=list)


class SolutionProfileResult(ToolResultBase):
    summary: str = Field(min_length=1)
    objectives: list[SolutionObjective] = Field(default_factory=list)
    components: list[SolutionComponent] = Field(default_factory=list)
    dependencies: list[SolutionDependency] = Field(default_factory=list)
    assumptions: list[SolutionAssumption] = Field(default_factory=list)
    resource_requirements: list[ResourceRequirement] = Field(default_factory=list)
    implementation_signals: list[SolutionSignal] = Field(default_factory=list)
    license_signals: list[SolutionSignal] = Field(default_factory=list)
    provenance_signals: list[SolutionSignal] = Field(default_factory=list)
    evidence_gaps: list[SolutionEvidenceGap] = Field(default_factory=list)


class AssumptionAssessment(StrictModel):
    assumption_id: str = Field(min_length=1)
    compatibility: AssumptionCompatibility
    target_condition: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class ComponentReuseAssessment(StrictModel):
    component_id: str = Field(min_length=1)
    reuse_level: ComponentReuseLevel
    rationale: str = Field(min_length=1)
    required_changes: list[str] = Field(default_factory=list)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class DependencyAssessment(StrictModel):
    dependency_id: str = Field(min_length=1)
    status: TransferConditionStatus
    target_condition: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    required_action: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class ResourceAssessment(StrictModel):
    resource_id: str = Field(min_length=1)
    status: TransferConditionStatus
    target_condition: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    required_action: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class RequiredAdaptation(StrictModel):
    adaptation_id: str = Field(min_length=1)
    affected_component_ids: list[str] = Field(default_factory=list)
    change: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    estimated_effort: AdaptationEffort
    citations: list[EvidenceCitation] = Field(default_factory=list)


class TransferRisk(StrictModel):
    risk_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    level: TransferRiskLevel
    description: str = Field(min_length=1)
    mitigation: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class ValidationStep(StrictModel):
    step_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    method: str = Field(min_length=1)
    success_criteria: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class TransferDimensionScore(StrictModel):
    name: TransferDimension
    score: float | None = Field(default=None, ge=0, le=100)
    assessment_status: DimensionAssessmentStatus = DimensionAssessmentStatus.ASSESSED
    weight: float = Field(default=0, ge=0, le=1)
    rationale: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)


class TransferAssessmentResult(ToolResultBase):
    solution_profile_run_id: str = Field(min_length=1)
    repository_audit_run_id: str | None = None
    summary: str = Field(min_length=1)
    target_context_summary: str = Field(min_length=1)
    overall_score: float | None = Field(default=None, ge=0, le=100)
    feasibility_band: TransferFeasibilityBand
    conclusion_confidence: float = Field(ge=0, le=1)
    evidence_coverage: float = Field(default=0, ge=0, le=1)
    rubric_coverage: float = Field(default=0, ge=0, le=1)
    dimensions: list[TransferDimensionScore] = Field(min_length=1)
    assumption_assessments: list[AssumptionAssessment] = Field(default_factory=list)
    component_assessments: list[ComponentReuseAssessment] = Field(default_factory=list)
    dependency_assessments: list[DependencyAssessment] = Field(default_factory=list)
    resource_assessments: list[ResourceAssessment] = Field(default_factory=list)
    transferable_strengths: list[str] = Field(default_factory=list)
    required_adaptations: list[RequiredAdaptation] = Field(default_factory=list)
    risks: list[TransferRisk] = Field(default_factory=list)
    validation_plan: list[ValidationStep] = Field(default_factory=list)
    performance_prediction_provided: Literal[False] = False
    legal_conclusion_provided: Literal[False] = False


class TransferGraphMetrics(StrictModel):
    source_closure_ratio: float = Field(ge=0, le=1)
    profile_entity_evidence_coverage: float = Field(ge=0, le=1)
    assumption_assessment_coverage: float = Field(ge=0, le=1)
    component_assessment_coverage: float = Field(ge=0, le=1)
    dependency_assessment_coverage: float = Field(ge=0, le=1)
    resource_assessment_coverage: float = Field(ge=0, le=1)
    invalidated_condition_count: int = Field(ge=0)
    transferred_component_count: int = Field(ge=0)
    high_risk_count: int = Field(ge=0)
    validation_step_count: int = Field(ge=0)


class BuildTransferGraphResult(ToolResultBase):
    summary: str = Field(min_length=1)
    # Keep the completion marker before the potentially large graph payload so
    # clients that truncate tool output can still observe the validation gate.
    graph_validated: bool = Field(
        default=False,
        description="True only after the graph passed deterministic validation.",
    )
    source_run_ids: list[str] = Field(min_length=2, max_length=2)
    nodes: list[EvidenceGraphNode] = Field(default_factory=list)
    edges: list[EvidenceGraphEdge] = Field(default_factory=list)
    metrics: TransferGraphMetrics


class RenderTransferReportResult(ToolResultBase):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    source_run_ids: list[str] = Field(min_length=2, max_length=2)
    transfer_graph_run_id: str | None = None
    # Keep the graph validation marker on the report response as well as on the
    # transfer_graph.json artifact so clients do not need to open a second file.
    graph_validated: bool | None = None
    artifact_inventory: list[ArtifactAuditEntry] = Field(min_length=2, max_length=3)
