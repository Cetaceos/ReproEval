"""Foundational data models shared by tools and application services."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.21"


class StrictModel(BaseModel):
    """Base model that rejects undeclared model output fields."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SourceType(StrEnum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"
    PYTHON = "python"
    TOML = "toml"
    CSV = "csv"
    JSON = "json"
    JSONL = "jsonl"
    YAML = "yaml"
    LOG = "log"


class EvidenceKind(StrEnum):
    OBSERVED = "observed"
    DETERMINISTICALLY_DERIVED = "deterministically_derived"
    COMPUTED = "computed"
    INFERRED = "inferred"
    SPECULATIVE = "speculative"
    UNKNOWN = "unknown"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ClaimType(StrEnum):
    MAIN_RESULT = "main_result"
    ABLATION = "ablation"
    BASELINE = "baseline"
    DATASET = "dataset"
    METHOD = "method"
    EFFICIENCY = "efficiency"
    LIMITATION = "limitation"
    OTHER = "other"


class EvidenceSupport(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    MENTIONS = "mentions"
    MISSING = "missing"
    UNCLEAR = "unclear"


class EvidenceGraphNodeType(StrEnum):
    CLAIM = "claim"
    OBJECTIVE = "objective"
    COMPONENT = "component"
    DEPENDENCY = "dependency"
    RESOURCE = "resource"
    ASSUMPTION = "assumption"
    EXPERIMENT = "experiment"
    METRIC = "metric"
    REPORTED_RESULT = "reported_result"
    REPRODUCTION_RESULT = "reproduction_result"
    REPRODUCTION_RUN = "reproduction_run"
    ARTIFACT = "artifact"
    PROJECT_CONTEXT = "project_context"
    EVIDENCE_GAP = "evidence_gap"
    ASSESSMENT = "assessment"
    ADAPTATION = "adaptation"
    RISK = "risk"
    VALIDATION_STEP = "validation_step"
    DOMAIN_PROFILE = "domain_profile"
    DOMAIN_FINDING = "domain_finding"


class EvidenceGraphEdgeType(StrEnum):
    REPORTED_BY = "reported_by"
    MEASURED_BY = "measured_by"
    SUPPORTS = "supports"
    PARTIALLY_SUPPORTS = "partially_supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    DEPENDS_ON = "depends_on"
    INVALIDATED_BY = "invalidated_by"
    MISSING_FOR = "missing_for"
    TRANSFERRED_TO = "transferred_to"
    COMPATIBLE_WITH = "compatible_with"
    ADAPTED_FOR = "adapted_for"
    VALIDATED_BY = "validated_by"


class DifferenceSeverity(StrEnum):
    NONE = "none"
    MINOR = "minor"
    MATERIAL = "material"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class MetricScale(StrEnum):
    FRACTION = "fraction"
    PERCENTAGE = "percentage"
    LINEAR = "linear"
    DECIBEL = "decibel"
    UNKNOWN = "unknown"


class ReliabilityBand(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


class DimensionAssessmentStatus(StrEnum):
    ASSESSED = "assessed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class MetricComparisonStatus(StrEnum):
    COMPUTED = "computed"
    MISSING_PAPER_VALUE = "missing_paper_value"
    UNMATCHED_REPRODUCTION_METRIC = "unmatched_reproduction_metric"
    AMBIGUOUS_REPRODUCTION_GROUP = "ambiguous_reproduction_group"
    METRIC_ALIAS_MISMATCH = "metric_alias_mismatch"
    UNRESOLVED_METRIC_SCALE = "unresolved_metric_scale"
    UNRESOLVED_METRIC_UNIT = "unresolved_metric_unit"
    INCOMPATIBLE_METRIC_SCALE = "incompatible_metric_scale"


class SettingCheckStatus(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    AMBIGUOUS = "ambiguous"
    MISSING_IN_PAPER = "missing_in_paper"
    MISSING_IN_REPRODUCTION = "missing_in_reproduction"


class ReliabilityDimension(StrEnum):
    RESULT_AGREEMENT = "reproduction_result_agreement"
    SETUP_TRANSPARENCY = "experiment_setup_transparency"
    BASELINE_FAIRNESS = "baseline_fairness"
    ABLATION_QUALITY = "ablation_quality"
    STATISTICAL_REPORTING = "statistical_reporting"
    DATA_IMPLEMENTATION_AVAILABILITY = "data_implementation_availability"


class AssessmentScope(StrEnum):
    PAPER_ONLY = "paper_only"
    PAPER_AND_REPRODUCTION = "paper_and_reproduction"


class DomainProfileMode(StrEnum):
    GENERIC = "generic"
    ISAC_PHY = "isac_phy"
    AUTO = "auto"


class DomainProfileName(StrEnum):
    GENERIC = "generic"
    ISAC_PHY = "isac_phy"


class ProfileRequestSource(StrEnum):
    TOOL_PARAMETER = "tool_parameter"
    USER_INSTRUCTION = "user_instruction"


class DomainActivationSource(StrEnum):
    EXPLICIT_PARAMETER = "explicit_parameter"
    USER_INSTRUCTION = "user_instruction"
    AUTO_DETECTION = "auto_detection"
    DEFAULT_GENERIC = "default_generic"


class ISACSystemType(StrEnum):
    COEXISTENCE = "coexistence"
    DUAL_FUNCTION = "dual_function"
    FULLY_INTEGRATED = "fully_integrated"
    SENSING_ASSISTED_COMMUNICATION = "sensing_assisted_communication"
    COMMUNICATION_ASSISTED_SENSING = "communication_assisted_sensing"
    UNKNOWN = "unknown"


class ISACSensingTopology(StrEnum):
    MONOSTATIC = "monostatic"
    BISTATIC = "bistatic"
    MULTISTATIC = "multistatic"
    PASSIVE = "passive"
    ACTIVE = "active"
    NETWORKED = "networked"
    UNKNOWN = "unknown"


class ISACWaveform(StrEnum):
    OFDM = "OFDM"
    MIMO_OFDM = "MIMO_OFDM"
    FMCW = "FMCW"
    OTFS = "OTFS"
    SINGLE_CARRIER = "single_carrier"
    PULSED_RADAR = "pulsed_radar"
    HYBRID_WAVEFORM = "hybrid_waveform"
    CUSTOM_WAVEFORM = "custom_waveform"
    UNKNOWN = "unknown"


class ISACResearchMethod(StrEnum):
    THEORETICAL_BOUND = "theoretical_bound"
    WAVEFORM_DESIGN = "waveform_design"
    BEAMFORMING = "beamforming"
    RESOURCE_ALLOCATION = "resource_allocation"
    PARAMETER_ESTIMATION = "parameter_estimation"
    DETECTION = "detection"
    LOCALIZATION = "localization"
    LEARNING_BASED = "learning_based"
    NETWORK_LEVEL = "network_level"
    EXPERIMENTAL_PROTOTYPE = "experimental_prototype"
    DATASET_PAPER = "dataset_paper"
    SURVEY = "survey"
    UNKNOWN = "unknown"


class ISACEvidenceLevel(StrEnum):
    ANALYTICAL_ONLY = "analytical_only"
    SIMULATION = "simulation"
    HARDWARE_IN_THE_LOOP = "hardware_in_the_loop"
    SDR_PROTOTYPE = "SDR_prototype"
    OVER_THE_AIR = "over_the_air"
    REAL_WORLD_DATASET = "real_world_dataset"
    UNKNOWN = "unknown"


class DomainFindingStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    RISK = "risk"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class SourceReference(StrictModel):
    """Stable location of evidence in an input source."""

    source_id: str = Field(min_length=1, description="Stable identifier within the run")
    source_path: str = Field(min_length=1, description="Canonical source path recorded by the workspace")
    source_type: SourceType
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$", description="SHA-256 of the source content")
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)
    column: str | None = None
    excerpt: str | None = Field(default=None, max_length=1000)


class EvidenceItem(StrictModel):
    statement: str = Field(min_length=1)
    kind: EvidenceKind
    source_references: list[SourceReference] = Field(default_factory=list)


class ArtifactReference(StrictModel):
    run_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    schema_version: str = SCHEMA_VERSION


class ArtifactIntegrity(StrictModel):
    algorithm: Literal["sha256"] = "sha256"
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ParentArtifactReference(ArtifactReference):
    role: str = Field(min_length=1)


class ArtifactAuditEntry(ParentArtifactReference):
    direct_parents: list[ParentArtifactReference] = Field(default_factory=list)


class ToolWarning(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source_references: list[SourceReference] = Field(default_factory=list)


class ToolResultBase(StrictModel):
    run_id: str = Field(min_length=1)
    schema_version: str = SCHEMA_VERSION
    artifact_integrity: ArtifactIntegrity | None = None
    parent_artifacts: list[ParentArtifactReference] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    warnings: list[ToolWarning] = Field(default_factory=list)
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    profile_versions: dict[str, str] = Field(default_factory=dict)
    registry_hashes: dict[str, str] = Field(default_factory=dict)


class EvidenceCitation(StrictModel):
    """A compact citation emitted by Hy3 that points to a loaded source."""

    source_id: str = Field(min_length=1)
    support: EvidenceSupport
    locator: str = Field(min_length=1, max_length=200)
    quote_or_value: str | None = Field(default=None, max_length=500)
    rationale: str = Field(min_length=1, max_length=1000)
    source_reference: SourceReference | None = Field(
        default=None,
        description="Server-validated full reference for the cited source segment.",
    )


GraphProperty = str | int | float | bool | None


class EvidenceGraphNode(StrictModel):
    node_id: str = Field(min_length=1, max_length=200)
    node_type: EvidenceGraphNodeType
    label: str = Field(min_length=1, max_length=500)
    evidence_kind: EvidenceKind
    source_references: list[SourceReference] = Field(default_factory=list)
    properties: dict[str, GraphProperty] = Field(default_factory=dict)


class EvidenceGraphEdge(StrictModel):
    edge_id: str = Field(min_length=1, max_length=200)
    edge_type: EvidenceGraphEdgeType
    source_node_id: str = Field(min_length=1, max_length=200)
    target_node_id: str = Field(min_length=1, max_length=200)
    evidence_kind: EvidenceKind
    rationale: str = Field(min_length=1, max_length=1000)
    source_references: list[SourceReference] = Field(default_factory=list)


class EvidenceGraphMetrics(StrictModel):
    claim_evidence_coverage: float = Field(ge=0, le=1)
    claim_source_coverage: float = Field(ge=0, le=1)
    reproduction_assessment_coverage: float = Field(ge=0, le=1)
    contradiction_ratio: float = Field(ge=0, le=1)
    orphan_claim_count: int = Field(ge=0)
    source_closure_ratio: float = Field(ge=0, le=1)
    experiment_setting_coverage: float = Field(ge=0, le=1)
    reproduction_support_ratio: float = Field(ge=0, le=1)
    reproduction_partial_support_ratio: float = Field(ge=0, le=1)
    invalidated_assumption_count: int = Field(ge=0)


class ReproClaim(StrictModel):
    claim_id: str = Field(min_length=1)
    claim_type: ClaimType
    statement: str = Field(min_length=1)
    reported_value: str | None = None
    conditions: list[str] = Field(default_factory=list)
    citations: list[EvidenceCitation] = Field(default_factory=list)
    reproducibility_impact: str = Field(min_length=1)


class ExperimentSetting(StrictModel):
    name: str = Field(min_length=1)
    value: str | None = None
    disclosed: bool
    citations: list[EvidenceCitation] = Field(default_factory=list)


class MissingDetail(StrictModel):
    item: str = Field(min_length=1)
    impact: str = Field(min_length=1)
    severity: DifferenceSeverity
    citations: list[EvidenceCitation] = Field(default_factory=list)


class DomainProfileActivation(StrictModel):
    requested_profile: DomainProfileMode = DomainProfileMode.GENERIC
    detected_profile: DomainProfileName = DomainProfileName.GENERIC
    effective_profile: DomainProfileName = DomainProfileName.GENERIC
    profile_version: str = Field(min_length=1)
    confidence: float = Field(default=0, ge=0, le=1)
    activation_source: DomainActivationSource = DomainActivationSource.DEFAULT_GENERIC
    matched_signals: list[str] = Field(default_factory=list)
    ambiguous_signals: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)


class ISACMetricObservation(StrictModel):
    canonical_name: str = Field(min_length=1)
    reported_name: str = Field(min_length=1)
    reported_value: str | None = None
    unit: str | None = None
    scale: MetricScale = MetricScale.UNKNOWN
    required_context_present: list[str] = Field(default_factory=list)
    missing_required_context: list[str] = Field(default_factory=list)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class ISACAssumptionObservation(StrictModel):
    name: str = Field(min_length=1)
    value: str | None = None
    evidence_kind: EvidenceKind = EvidenceKind.UNKNOWN
    citations: list[EvidenceCitation] = Field(default_factory=list)


class DomainFinding(StrictModel):
    rule_id: str = Field(pattern=r"^ISAC-R\d{3}$")
    status: DomainFindingStatus
    summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_kind: EvidenceKind = EvidenceKind.UNKNOWN
    citations: list[EvidenceCitation] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    review_required: bool = False
    affects_score: Literal[False] = False


class ISACProfileAnalysis(StrictModel):
    system_type: ISACSystemType = ISACSystemType.UNKNOWN
    sensing_topologies: list[ISACSensingTopology] = Field(default_factory=list)
    waveforms: list[ISACWaveform] = Field(default_factory=list)
    research_methods: list[ISACResearchMethod] = Field(default_factory=list)
    evidence_level: ISACEvidenceLevel = ISACEvidenceLevel.UNKNOWN
    classification_citations: list[EvidenceCitation] = Field(default_factory=list)
    metrics: list[ISACMetricObservation] = Field(default_factory=list)
    assumptions: list[ISACAssumptionObservation] = Field(default_factory=list)
    findings: list[DomainFinding] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ExtractClaimsResult(ToolResultBase):
    summary: str = Field(min_length=1)
    core_claims: list[ReproClaim] = Field(default_factory=list)
    experiment_settings: list[ExperimentSetting] = Field(default_factory=list)
    missing_details: list[MissingDetail] = Field(default_factory=list)
    evidence_quality_notes: list[str] = Field(default_factory=list)
    domain_profile_activation: DomainProfileActivation | None = None
    isac_analysis: ISACProfileAnalysis | None = None


class MetricDataQuality(StrictModel):
    total_count: int = Field(ge=1)
    valid_numeric_count: int = Field(ge=1)
    missing_count: int = Field(ge=0)
    non_numeric_count: int = Field(ge=0)
    non_finite_count: int = Field(ge=0)
    valid_ratio: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_partition(self) -> Self:
        partition_total = self.valid_numeric_count + self.missing_count + self.non_numeric_count + self.non_finite_count
        if partition_total != self.total_count:
            raise ValueError("metric data-quality counts must partition total_count")
        expected_ratio = self.valid_numeric_count / self.total_count
        if abs(self.valid_ratio - expected_ratio) > 1e-6:
            raise ValueError("metric data-quality valid_ratio does not match the counts")
        return self


class MetricComparison(StrictModel):
    metric: str = Field(min_length=1)
    canonical_metric: str | None = None
    reproduction_source_id: str | None = None
    reproduction_column: str | None = None
    paper_value: float | None = None
    normalized_paper_value: float | None = None
    reproduced_value: float | None = None
    reproduced_stddev: float | None = Field(default=None, ge=0)
    sample_count: int | None = Field(default=None, ge=1)
    data_quality: MetricDataQuality | None = None
    absolute_delta: float | None = None
    relative_delta_percent: float | None = None
    unit: str | None = None
    paper_scale: MetricScale = MetricScale.UNKNOWN
    reproduction_scale: MetricScale = MetricScale.UNKNOWN
    normalized_scale: MetricScale = MetricScale.UNKNOWN
    scale_conversion: str | None = None
    higher_is_better: bool | None = None
    computation_status: MetricComparisonStatus = MetricComparisonStatus.UNMATCHED_REPRODUCTION_METRIC
    severity: DifferenceSeverity
    conclusion: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class GroupMetricComparison(MetricComparison):
    group: dict[str, str] = Field(min_length=1)


class GroupMetricStabilitySummary(StrictModel):
    metric: str = Field(min_length=1)
    canonical_metric: str | None = None
    reproduction_source_id: str = Field(min_length=1)
    reproduction_column: str = Field(min_length=1)
    group_by: list[str] = Field(min_length=1)
    group_count: int = Field(ge=2)
    group_mean: float
    group_mean_stddev: float = Field(ge=0)
    minimum_group: dict[str, str] = Field(min_length=1)
    minimum_value: float
    maximum_group: dict[str, str] = Field(min_length=1)
    maximum_value: float
    value_range: float = Field(ge=0)
    normalized_paper_value: float | None = None
    normalized_scale: MetricScale = MetricScale.UNKNOWN
    range_percent_of_reported: float | None = Field(default=None, ge=0)
    max_absolute_paper_delta: float | None = Field(default=None, ge=0)
    max_delta_group: dict[str, str] | None = None


class SettingDifference(StrictModel):
    setting: str = Field(min_length=1)
    paper_value: str | None = None
    reproduction_value: str | None = None
    severity: DifferenceSeverity
    likely_effect: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)


class DeterministicSettingCheck(StrictModel):
    setting: str = Field(min_length=1)
    paper_values: list[str] = Field(default_factory=list)
    reproduction_values: list[str] = Field(default_factory=list)
    status: SettingCheckStatus
    paper_citations: list[EvidenceCitation] = Field(default_factory=list)
    reproduction_citations: list[EvidenceCitation] = Field(default_factory=list)


class ClaimRelationDiagnostics(StrictModel):
    total_claim_count: int = Field(default=0, ge=0)
    assessed_claim_count: int = Field(default=0, ge=0)
    fully_supported_count: int = Field(default=0, ge=0)
    partially_supported_count: int = Field(default=0, ge=0)
    contradicted_count: int = Field(default=0, ge=0)
    unassessed_claim_count: int = Field(default=0, ge=0)
    claim_relation_coverage: float | None = Field(default=None, ge=0, le=1)
    unassessed_claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_partition(self) -> Self:
        relation_count = self.fully_supported_count + self.partially_supported_count + self.contradicted_count
        if self.assessed_claim_count != relation_count:
            raise ValueError("assessed_claim_count must equal the three relation counts")
        if self.total_claim_count != self.assessed_claim_count + self.unassessed_claim_count:
            raise ValueError("claim relation counts must partition total_claim_count")
        if self.unassessed_claim_count != len(self.unassessed_claim_ids):
            raise ValueError("unassessed_claim_count must match unassessed_claim_ids")
        if len(set(self.unassessed_claim_ids)) != len(self.unassessed_claim_ids):
            raise ValueError("unassessed_claim_ids must be unique")
        if self.total_claim_count == 0:
            if self.claim_relation_coverage is not None:
                raise ValueError("claim_relation_coverage must be null when no claims are available")
        else:
            expected_coverage = self.assessed_claim_count / self.total_claim_count
            if self.claim_relation_coverage is None or abs(self.claim_relation_coverage - expected_coverage) > 1e-6:
                raise ValueError("claim_relation_coverage does not match the claim relation counts")
        return self


class CompareReproductionResult(ToolResultBase):
    claims_run_id: str | None = None
    group_filters: dict[str, str] = Field(default_factory=dict)
    group_by: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    metric_comparisons: list[MetricComparison] = Field(default_factory=list)
    group_metric_comparisons: list[GroupMetricComparison] = Field(default_factory=list)
    group_stability_summaries: list[GroupMetricStabilitySummary] = Field(default_factory=list)
    deterministic_setting_checks: list[DeterministicSettingCheck] = Field(default_factory=list)
    setting_differences: list[SettingDifference] = Field(default_factory=list)
    supported_claim_ids: list[str] = Field(default_factory=list)
    partially_supported_claim_ids: list[str] = Field(default_factory=list)
    contradicted_claim_ids: list[str] = Field(default_factory=list)
    claim_relation_diagnostics: ClaimRelationDiagnostics = Field(default_factory=ClaimRelationDiagnostics)
    unresolved_questions: list[str] = Field(default_factory=list)
    conclusion_stability: str = Field(min_length=1)


class ScoreDimension(StrictModel):
    name: ReliabilityDimension
    score: float | None = Field(default=None, ge=0, le=100)
    assessment_status: DimensionAssessmentStatus = DimensionAssessmentStatus.ASSESSED
    weight: float = Field(default=0, ge=0, le=1)
    rationale: str = Field(min_length=1)
    citations: list[EvidenceCitation] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)


class ReliabilityScoreResult(ToolResultBase):
    repository_audit_run_id: str | None = None
    group_filters: dict[str, str] = Field(default_factory=dict)
    overall_score: float | None = Field(default=None, ge=0, le=100)
    reliability_band: ReliabilityBand
    conclusion_confidence: float = Field(ge=0, le=1)
    assessment_scope: AssessmentScope = AssessmentScope.PAPER_ONLY
    evidence_coverage: float = Field(default=0, ge=0, le=1)
    rubric_coverage: float = Field(default=0, ge=0, le=1)
    summary: str = Field(min_length=1)
    dimensions: list[ScoreDimension] = Field(min_length=1)
    reproduction_verdict: str = Field(min_length=1)
    experimental_rigor_verdict: str = Field(min_length=1)
    major_strengths: list[str] = Field(default_factory=list)
    major_risks: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)


class RenderReportResult(ToolResultBase):
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    source_run_ids: list[str] = Field(min_length=3, max_length=3)
    evidence_graph_run_id: str | None = None
    artifact_inventory: list[ArtifactAuditEntry] = Field(min_length=3)


class BuildEvidenceGraphResult(ToolResultBase):
    summary: str = Field(min_length=1)
    # Keep the completion marker before the potentially large graph payload so
    # clients that truncate tool output can still observe the validation gate.
    graph_validated: bool = Field(
        default=False,
        description="True only after the graph passed deterministic validation.",
    )
    source_run_ids: list[str] = Field(min_length=3, max_length=3)
    nodes: list[EvidenceGraphNode] = Field(default_factory=list)
    edges: list[EvidenceGraphEdge] = Field(default_factory=list)
    metrics: EvidenceGraphMetrics


class RunStatusEvent(StrictModel):
    status: RunStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunManifest(StrictModel):
    run_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    schema_version: str = SCHEMA_VERSION
    artifact_integrity: ArtifactIntegrity | None = None
    status: RunStatus = RunStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status_history: list[RunStatusEvent] = Field(min_length=1)
    sources: list[SourceReference] = Field(default_factory=list)
    parent_artifacts: list[ParentArtifactReference] = Field(default_factory=list)
    artifacts: list[ArtifactReference] = Field(default_factory=list)
    profile_versions: dict[str, str] = Field(default_factory=dict)
    registry_hashes: dict[str, str] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None


class RunRecoverySnapshot(StrictModel):
    """Read-only recovery guidance derived from one persisted run manifest."""

    run_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    schema_version: str = SCHEMA_VERSION
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    artifact_count: int = Field(ge=0)
    parent_artifact_count: int = Field(ge=0)
    reusable_artifacts: list[ArtifactReference] = Field(default_factory=list)
    recovery_action: Literal["reuse_completed", "restart_from_recorded_inputs", "inspect_only"]
    resume_from: Literal["completed_artifacts", "recorded_inputs", "manual_inspection"]
    recovery_reason: str = Field(min_length=1)
    error_code: str | None = None
