"""Versioned models for deterministic report evaluation."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scenario(StrEnum):
    REPRODUCTION = "reproduction"
    TRANSFER = "transfer"
    GENERIC = "generic"


class DimensionId(StrEnum):
    FACTUAL_ACCURACY = "factual_accuracy"
    EVIDENCE_TRACEABILITY = "evidence_traceability"
    NUMERICAL_CONSISTENCY = "numerical_consistency"
    REASONING_CONSISTENCY = "reasoning_consistency"
    UNCERTAINTY_HANDLING = "uncertainty_handling"
    CONTENT_COMPLETENESS = "content_completeness"
    CLARITY_ACTIONABILITY = "clarity_actionability"


class ErrorCode(StrEnum):
    UNSUPPORTED_CLAIM = "unsupported_claim"
    FABRICATED_CITATION = "fabricated_citation"
    CITATION_MISMATCH = "citation_mismatch"
    NUMERIC_ERROR = "numeric_error"
    UNIT_ERROR = "unit_error"
    SETTING_OMISSION = "setting_omission"
    REASONING_GAP = "reasoning_gap"
    OVERCONFIDENCE = "overconfidence"
    MISSING_LIMITATION = "missing_limitation"
    VERBOSITY_WITHOUT_EVIDENCE = "verbosity_without_evidence"
    FORMAT_VIOLATION = "format_violation"
    ARTIFACT_LINEAGE_ERROR = "artifact_lineage_error"


class FindingStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class FindingSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DimensionStatus(StrEnum):
    ASSESSED = "assessed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvaluationStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class EvaluationMode(StrEnum):
    DETERMINISTIC_ONLY = "deterministic_only"
    HYBRID = "hybrid"


class QualityBand(StrEnum):
    EXCELLENT = "excellent"
    STRONG = "strong"
    MIXED = "mixed"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"


class SourceSpec(StrictModel):
    source_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    locators: list[str] = Field(min_length=1)

    @field_validator("locators")
    @classmethod
    def locators_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("source locators must be unique")
        return value


class ClaimExpectation(StrictModel):
    claim_id: str = Field(min_length=1)
    marker: str = Field(min_length=1, description="Literal text used to locate the claim in the report.")
    required_source_ids: list[str] = Field(default_factory=list)

    @field_validator("required_source_ids")
    @classmethod
    def required_sources_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("required source IDs must be unique")
        return value


class NumericExpectation(StrictModel):
    fact_id: str = Field(min_length=1)
    label: str = Field(min_length=1, description="Literal label on the line containing the value.")
    expected: Decimal
    absolute_tolerance: Decimal = Field(default=Decimal("0"), ge=0)
    unit: str | None = None
    critical: bool = True


class SectionExpectation(StrictModel):
    section_id: str = Field(min_length=1)
    heading: str = Field(min_length=1)


class UncertaintyExpectation(StrictModel):
    required: bool = True
    accepted_phrases: list[str] = Field(min_length=1)

    @field_validator("accepted_phrases")
    @classmethod
    def phrases_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("accepted uncertainty phrases must be unique")
        return value


class ArtifactExpectation(StrictModel):
    artifact_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")


class EvaluationCase(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    case_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    scenario: Scenario
    report_path: str = Field(min_length=1)
    sources: list[SourceSpec] = Field(default_factory=list)
    claims: list[ClaimExpectation] = Field(default_factory=list)
    numeric_expectations: list[NumericExpectation] = Field(default_factory=list)
    required_sections: list[SectionExpectation] = Field(default_factory=list)
    uncertainty: UncertaintyExpectation | None = None
    artifacts: list[ArtifactExpectation] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_at_least_one_check(self) -> EvaluationCase:
        if not any(
            (
                self.claims,
                self.numeric_expectations,
                self.required_sections,
                self.uncertainty,
                self.artifacts,
            )
        ):
            raise ValueError("evaluation case must define at least one deterministic check")
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source IDs must be unique")
        self._require_unique_ids("claim", [item.claim_id for item in self.claims])
        self._require_unique_ids("numeric fact", [item.fact_id for item in self.numeric_expectations])
        self._require_unique_ids("section", [item.section_id for item in self.required_sections])
        self._require_unique_ids("artifact", [item.artifact_id for item in self.artifacts])
        known_sources = set(source_ids)
        unknown = sorted(
            {
                source_id
                for claim in self.claims
                for source_id in claim.required_source_ids
                if source_id not in known_sources
            }
        )
        if unknown:
            raise ValueError(f"claim expectations reference unknown sources: {', '.join(unknown)}")
        return self

    @staticmethod
    def _require_unique_ids(label: str, identifiers: list[str]) -> None:
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"{label} IDs must be unique")


class EvidenceLocation(StrictModel):
    path: str
    line: int | None = Field(default=None, ge=1)
    excerpt: str | None = None


class ValidatorFinding(StrictModel):
    finding_id: str
    validator: str
    status: FindingStatus
    severity: FindingSeverity
    message: str
    dimensions: list[DimensionId]
    error_code: ErrorCode | None = None
    evidence: list[EvidenceLocation] = Field(default_factory=list)
    hard_cap: float | None = Field(default=None, ge=0, le=100)


class DimensionResult(StrictModel):
    dimension: DimensionId
    weight: float = Field(gt=0, le=1)
    status: DimensionStatus
    score: float | None = Field(default=None, ge=0, le=4)
    rationale: str
    finding_ids: list[str] = Field(default_factory=list)


class EvaluationResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    case_id: str
    case_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    scenario: Scenario
    report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    evaluation_mode: EvaluationMode
    status: EvaluationStatus
    provisional: bool
    assessed_weight: float = Field(ge=0, le=1)
    overall_score: float | None = Field(default=None, ge=0, le=100)
    quality_band: QualityBand
    applied_hard_cap: float | None = Field(default=None, ge=0, le=100)
    dimensions: list[DimensionResult]
    findings: list[ValidatorFinding]
    warnings: list[str] = Field(default_factory=list)
