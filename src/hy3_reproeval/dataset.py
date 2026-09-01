"""Versioned dataset and reproducible mutation contracts for ReproEval."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from . import __version__
from .errors import EvaluationInputError
from .evaluator import _rubric_sha256, evaluate_case_file
from .judge import MAX_JUDGE_RECORD_BYTES, load_judge_record
from .models import DimensionId, ErrorCode, FindingStatus, Scenario, StrictModel
from .rubric import load_public_rubric
from .validators import LoadedEvaluationCase, load_evaluation_case

MAX_DATASET_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_MUTATION_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_MUTATION_REPORT_BYTES = 4 * 1024 * 1024

_SEMANTIC_ONLY_ERRORS = {
    ErrorCode.REASONING_GAP,
    ErrorCode.VERBOSITY_WITHOUT_EVIDENCE,
    ErrorCode.ACTIONABILITY_GAP,
}


class DatasetSplit(StrEnum):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    TEST = "test"


class QualityTier(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ADVERSARIAL = "adversarial"


class AdversarialAttackType(StrEnum):
    LENGTH_INFLATION = "length_inflation"
    TERMINOLOGY_STUFFING = "terminology_stuffing"
    CONCLUSION_REPETITION = "conclusion_repetition"
    FABRICATED_AUTHORITY = "fabricated_authority"
    CALCULATION_CORRUPTION = "calculation_corruption"
    LIMITATION_SUPPRESSION = "limitation_suppression"
    UNSUPPORTED_OVERCONFIDENCE = "unsupported_overconfidence"


class ProvenanceKind(StrEnum):
    SYNTHETIC = "synthetic"
    OPEN_ACCESS = "open_access"


class MutationKind(StrEnum):
    REPLACE_ONCE = "replace_once"
    DELETE_ONCE = "delete_once"
    APPEND_TEXT = "append_text"


class ProvenanceRecord(StrictModel):
    kind: ProvenanceKind
    license: str = Field(min_length=1)
    source_group_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    acquisition_date: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    description: str = Field(min_length=1, max_length=1000)


class MutationOperation(StrictModel):
    operation_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    kind: MutationKind
    target: str | None = None
    replacement: str = ""
    expected_dimensions: list[DimensionId] = Field(min_length=1)
    expected_error_codes: list[ErrorCode] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_operation(self) -> MutationOperation:
        if self.kind in {MutationKind.REPLACE_ONCE, MutationKind.DELETE_ONCE} and not self.target:
            raise ValueError("replace/delete mutation requires a non-empty target")
        if self.kind is MutationKind.DELETE_ONCE and self.replacement:
            raise ValueError("delete mutation cannot define replacement text")
        if self.kind is MutationKind.APPEND_TEXT:
            if self.target is not None:
                raise ValueError("append mutation cannot define a target")
            if not self.replacement:
                raise ValueError("append mutation requires replacement text")
        if len(self.expected_dimensions) != len(set(self.expected_dimensions)):
            raise ValueError("expected mutation dimensions must be unique")
        if len(self.expected_error_codes) != len(set(self.expected_error_codes)):
            raise ValueError("expected mutation error codes must be unique")
        return self


class MutationManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    mutation_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    parent_report_id: str = Field(min_length=1)
    output_report_id: str = Field(min_length=1)
    parent_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)
    parent_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    output_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    operations: list[MutationOperation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> MutationManifest:
        if self.parent_report_id == self.output_report_id:
            raise ValueError("mutation parent and output report IDs must differ")
        operation_ids = [operation.operation_id for operation in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("mutation operation IDs must be unique")
        return self


class AdversarialAttack(StrictModel):
    attack_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    attack_type: AdversarialAttackType
    target_dimensions: list[DimensionId] = Field(min_length=1)
    expected_error_codes: list[ErrorCode] = Field(min_length=1)
    description: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_attack(self) -> AdversarialAttack:
        if len(self.target_dimensions) != len(set(self.target_dimensions)):
            raise ValueError("adversarial attack target dimensions must be unique")
        if len(self.expected_error_codes) != len(set(self.expected_error_codes)):
            raise ValueError("adversarial attack expected error codes must be unique")
        return self


class AdversarialSpec(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    attacks: list[AdversarialAttack] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> AdversarialSpec:
        attack_ids = [attack.attack_id for attack in self.attacks]
        if len(attack_ids) != len(set(attack_ids)):
            raise ValueError("adversarial attack IDs must be unique within a report")
        return self


class DatasetReportEntry(StrictModel):
    report_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    quality_tier: QualityTier
    case_path: str = Field(min_length=1)
    report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    label_source: Literal["reference_revision", "synthetic_mutation", "human_reviewed"]
    mutation_manifest_path: str | None = None
    judge_record_path: str | None = None
    judge_record_sha256: str | None = Field(default=None, pattern=r"^[A-F0-9]{64}$")
    expected_error_codes: list[ErrorCode] = Field(default_factory=list)
    adversarial_spec: AdversarialSpec | None = None

    @field_validator("expected_error_codes")
    @classmethod
    def expected_errors_must_be_unique(cls, value: list[ErrorCode]) -> list[ErrorCode]:
        if len(value) != len(set(value)):
            raise ValueError("expected report error codes must be unique")
        return value

    @model_validator(mode="after")
    def validate_label_contract(self) -> DatasetReportEntry:
        if self.label_source == "synthetic_mutation" and not self.mutation_manifest_path:
            raise ValueError("synthetic mutation report requires mutation_manifest_path")
        if self.quality_tier is QualityTier.HIGH and self.label_source == "synthetic_mutation":
            raise ValueError("high-quality reference cannot be labeled as a synthetic mutation")
        if self.quality_tier is QualityTier.ADVERSARIAL:
            if self.adversarial_spec is None:
                raise ValueError("adversarial report requires adversarial_spec")
            if self.label_source == "reference_revision":
                raise ValueError("adversarial report cannot use reference_revision as its label source")
            attack_errors = {error for attack in self.adversarial_spec.attacks for error in attack.expected_error_codes}
            if not attack_errors.issubset(set(self.expected_error_codes)):
                raise ValueError("adversarial attack errors must be declared by the report")
        elif self.adversarial_spec is not None:
            raise ValueError("only adversarial reports may define adversarial_spec")
        if (self.judge_record_path is None) != (self.judge_record_sha256 is None):
            raise ValueError("judge_record_path and judge_record_sha256 must be declared together")
        return self


class DatasetGroup(StrictModel):
    group_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    split: DatasetSplit
    scenario: Scenario
    provenance: ProvenanceRecord
    reports: list[DatasetReportEntry] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_group(self) -> DatasetGroup:
        report_ids = [report.report_id for report in self.reports]
        if len(report_ids) != len(set(report_ids)):
            raise ValueError("report IDs must be unique within a group")
        required = {QualityTier.HIGH, QualityTier.MEDIUM, QualityTier.LOW}
        actual = {report.quality_tier for report in self.reports}
        if not required.issubset(actual):
            missing = ", ".join(sorted(tier.value for tier in required - actual))
            raise ValueError(f"dataset group is missing required quality tiers: {missing}")
        if sum(report.quality_tier is QualityTier.HIGH for report in self.reports) != 1:
            raise ValueError("dataset group must contain exactly one high-quality reference")
        return self


class DatasetManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    dataset_version: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=2000)
    groups: list[DatasetGroup] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset_inventory(self) -> DatasetManifest:
        group_ids = [group.group_id for group in self.groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("dataset group IDs must be unique")
        report_ids = [report.report_id for group in self.groups for report in group.reports]
        if len(report_ids) != len(set(report_ids)):
            raise ValueError("dataset report IDs must be globally unique")
        report_hashes = [report.report_sha256 for group in self.groups for report in group.reports]
        if len(report_hashes) != len(set(report_hashes)):
            raise ValueError("dataset reports must have unique content hashes")
        source_hashes = [group.provenance.source_group_sha256 for group in self.groups]
        if len(source_hashes) != len(set(source_hashes)):
            raise ValueError("one source group cannot appear in multiple dataset groups or splits")
        attack_ids = [
            attack.attack_id
            for group in self.groups
            for report in group.reports
            if report.adversarial_spec is not None
            for attack in report.adversarial_spec.attacks
        ]
        if len(attack_ids) != len(set(attack_ids)):
            raise ValueError("adversarial attack IDs must be globally unique")
        return self


class MutationReplayResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    mutation_id: str
    parent_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    output_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    operation_count: int = Field(ge=1)
    output_path: str
    wrote_output: bool


class DatasetValidationResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    dataset_id: str
    dataset_version: str
    manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    valid: Literal[True] = True
    group_count: int = Field(ge=1)
    report_count: int = Field(ge=3)
    mutation_count: int = Field(ge=0)
    judge_record_count: int = Field(ge=0)
    split_counts: dict[DatasetSplit, int]
    tier_counts: dict[QualityTier, int]
    scenario_counts: dict[Scenario, int]
    deterministic_error_counts: dict[ErrorCode, int]
    human_reviewed_report_count: int = Field(ge=0)
    adversarial_report_count: int = Field(default=0, ge=0)
    attack_instance_count: int = Field(default=0, ge=0)
    attack_type_counts: dict[AdversarialAttackType, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _LoadedReport:
    entry: DatasetReportEntry
    loaded_case: LoadedEvaluationCase


@dataclass(frozen=True, slots=True)
class LoadedDatasetManifest:
    manifest: DatasetManifest
    manifest_path: Path
    root: Path
    manifest_sha256: str

    def resolve(self, raw_path: str, label: str = "dataset file") -> Path:
        return _resolve_registered_path(self.root, raw_path, label)


def load_dataset_manifest(path: str | Path) -> LoadedDatasetManifest:
    manifest_path = Path(path).expanduser().resolve()
    manifest_bytes = _read_limited(manifest_path, MAX_DATASET_MANIFEST_BYTES, "dataset manifest")
    try:
        manifest = DatasetManifest.model_validate_json(manifest_bytes)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid dataset manifest: {exc}") from exc
    return LoadedDatasetManifest(
        manifest=manifest,
        manifest_path=manifest_path,
        root=manifest_path.parent.resolve(),
        manifest_sha256=_sha256(manifest_bytes),
    )


def validate_dataset_manifest(path: str | Path) -> DatasetValidationResult:
    loaded_dataset = load_dataset_manifest(path)
    manifest = loaded_dataset.manifest
    root = loaded_dataset.root
    mutation_count = 0
    judge_record_count = 0
    deterministic_error_counts: Counter[ErrorCode] = Counter()
    attack_type_counts: Counter[AdversarialAttackType] = Counter()
    human_reviewed = 0
    rubric = load_public_rubric()
    rubric_sha256 = _rubric_sha256(rubric)

    for group in manifest.groups:
        loaded_reports = _load_group_reports(root, group)
        _validate_group_contract(group, loaded_reports)
        by_id = {item.entry.report_id: item for item in loaded_reports}
        for item in loaded_reports:
            if item.entry.adversarial_spec is not None:
                attack_type_counts.update(attack.attack_type for attack in item.entry.adversarial_spec.attacks)
            if item.entry.label_source == "human_reviewed":
                human_reviewed += 1
            actual_errors = _validate_expected_errors(item)
            deterministic_error_counts.update(actual_errors)
            if item.entry.judge_record_path is not None:
                judge_record_count += 1
                judge_record_path = _resolve_registered_path(root, item.entry.judge_record_path, "Judge record")
                judge_record_bytes = _read_limited(judge_record_path, MAX_JUDGE_RECORD_BYTES, "Judge record")
                if _sha256(judge_record_bytes) != item.entry.judge_record_sha256:
                    raise EvaluationInputError(f"report '{item.entry.report_id}' Judge record SHA-256 does not match")
                load_judge_record(judge_record_path, item.loaded_case, rubric, rubric_sha256)
            if item.entry.mutation_manifest_path:
                mutation_count += 1
                mutation_path = _resolve_registered_path(
                    root,
                    item.entry.mutation_manifest_path,
                    "mutation manifest",
                )
                mutation = _load_mutation_manifest(mutation_path)
                _validate_mutation_links(root, mutation, item, by_id)
                replay_mutation_manifest(mutation_path, root=root, write=False)

    split_counts = Counter(group.split for group in manifest.groups)
    tier_counts = Counter(report.quality_tier for group in manifest.groups for report in group.reports)
    scenario_counts = Counter(group.scenario for group in manifest.groups)
    warnings = _dataset_warnings(manifest, split_counts, tier_counts, human_reviewed)
    return DatasetValidationResult(
        engine_version=__version__,
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        manifest_sha256=loaded_dataset.manifest_sha256,
        group_count=len(manifest.groups),
        report_count=sum(len(group.reports) for group in manifest.groups),
        mutation_count=mutation_count,
        judge_record_count=judge_record_count,
        split_counts=dict(split_counts),
        tier_counts=dict(tier_counts),
        scenario_counts=dict(scenario_counts),
        deterministic_error_counts=dict(deterministic_error_counts),
        human_reviewed_report_count=human_reviewed,
        adversarial_report_count=tier_counts[QualityTier.ADVERSARIAL],
        attack_instance_count=sum(attack_type_counts.values()),
        attack_type_counts=dict(attack_type_counts),
        warnings=warnings,
    )


def replay_mutation_manifest(
    path: str | Path,
    *,
    root: str | Path | None = None,
    write: bool = False,
) -> MutationReplayResult:
    manifest_path = Path(path).expanduser().resolve()
    mutation = _load_mutation_manifest(manifest_path)
    active_root = Path(root).expanduser().resolve() if root is not None else manifest_path.parent.resolve()
    parent_path = _resolve_registered_path(active_root, mutation.parent_path, "mutation parent")
    output_path = _resolve_registered_path(active_root, mutation.output_path, "mutation output")
    parent_bytes = _read_limited(parent_path, MAX_MUTATION_REPORT_BYTES, "mutation parent report")
    if _sha256(parent_bytes) != mutation.parent_sha256:
        raise EvaluationInputError("mutation parent SHA-256 does not match its manifest")
    try:
        text = parent_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvaluationInputError("mutation parent report must be UTF-8 text") from exc
    for operation in mutation.operations:
        text = _apply_operation(text, operation)
    output_bytes = text.encode("utf-8")
    output_sha256 = _sha256(output_bytes)
    if output_sha256 != mutation.output_sha256:
        raise EvaluationInputError("replayed mutation output SHA-256 does not match its manifest")
    if write:
        if not output_path.parent.is_dir():
            raise EvaluationInputError(f"mutation output directory does not exist: {output_path.parent.as_posix()}")
        output_path.write_bytes(output_bytes)
    else:
        existing = _read_limited(output_path, MAX_MUTATION_REPORT_BYTES, "mutation output report")
        if existing != output_bytes:
            raise EvaluationInputError("stored mutation output does not match deterministic replay")
    return MutationReplayResult(
        mutation_id=mutation.mutation_id,
        parent_sha256=mutation.parent_sha256,
        output_sha256=output_sha256,
        operation_count=len(mutation.operations),
        output_path=output_path.relative_to(active_root).as_posix(),
        wrote_output=write,
    )


def _load_group_reports(root: Path, group: DatasetGroup) -> list[_LoadedReport]:
    loaded_reports: list[_LoadedReport] = []
    for entry in group.reports:
        case_path = _resolve_registered_path(root, entry.case_path, "evaluation case")
        loaded_case = load_evaluation_case(case_path)
        if loaded_case.case.scenario is not group.scenario:
            raise EvaluationInputError(f"report '{entry.report_id}' scenario does not match its dataset group")
        if loaded_case.report_sha256 != entry.report_sha256:
            raise EvaluationInputError(f"report '{entry.report_id}' SHA-256 does not match its dataset entry")
        loaded_reports.append(_LoadedReport(entry=entry, loaded_case=loaded_case))
    return loaded_reports


def _validate_group_contract(group: DatasetGroup, reports: list[_LoadedReport]) -> None:
    contracts = {
        _canonical_sha256(item.loaded_case.case.model_dump(mode="json", exclude={"case_id", "report_path"}))
        for item in reports
    }
    if len(contracts) != 1:
        raise EvaluationInputError(f"dataset group '{group.group_id}' uses multiple evaluation contracts")


def _validate_expected_errors(item: _LoadedReport) -> set[ErrorCode]:
    result = evaluate_case_file(item.loaded_case.manifest_path)
    actual = {
        finding.error_code
        for finding in result.findings
        if finding.status is FindingStatus.FAILED and finding.error_code is not None
    }
    expected = set(item.entry.expected_error_codes)
    expected_deterministic = expected - _SEMANTIC_ONLY_ERRORS
    missing = expected_deterministic - actual
    undeclared = actual - expected
    if missing:
        raise EvaluationInputError(
            f"report '{item.entry.report_id}' is missing expected deterministic errors: "
            + ", ".join(sorted(error.value for error in missing))
        )
    if undeclared:
        raise EvaluationInputError(
            f"report '{item.entry.report_id}' has undeclared deterministic errors: "
            + ", ".join(sorted(error.value for error in undeclared))
        )
    return actual


def _validate_mutation_links(
    root: Path,
    mutation: MutationManifest,
    output: _LoadedReport,
    reports_by_id: dict[str, _LoadedReport],
) -> None:
    if mutation.output_report_id != output.entry.report_id:
        raise EvaluationInputError("mutation output report ID does not match its dataset entry")
    parent = reports_by_id.get(mutation.parent_report_id)
    if parent is None:
        raise EvaluationInputError("mutation parent report ID is not in the same dataset group")
    parent_path = _resolve_registered_path(root, mutation.parent_path, "mutation parent")
    output_path = _resolve_registered_path(root, mutation.output_path, "mutation output")
    if parent_path != parent.loaded_case.report_path or output_path != output.loaded_case.report_path:
        raise EvaluationInputError("mutation report paths do not match their linked evaluation cases")
    if mutation.parent_sha256 != parent.entry.report_sha256 or mutation.output_sha256 != output.entry.report_sha256:
        raise EvaluationInputError("mutation report hashes do not match their linked dataset entries")
    operation_errors = {error for operation in mutation.operations for error in operation.expected_error_codes}
    report_errors = set(output.entry.expected_error_codes)
    if operation_errors != report_errors:
        raise EvaluationInputError("mutation operation errors do not close over the output report's expected errors")
    if output.entry.adversarial_spec is not None:
        operation_dimensions = {
            dimension for operation in mutation.operations for dimension in operation.expected_dimensions
        }
        attack_dimensions = {
            dimension for attack in output.entry.adversarial_spec.attacks for dimension in attack.target_dimensions
        }
        if not attack_dimensions.issubset(operation_dimensions):
            raise EvaluationInputError("adversarial attack dimensions must be covered by mutation operations")


def _apply_operation(text: str, operation: MutationOperation) -> str:
    if operation.kind is MutationKind.APPEND_TEXT:
        return text + operation.replacement
    assert operation.target is not None
    occurrence_count = text.count(operation.target)
    if occurrence_count != 1:
        raise EvaluationInputError(
            f"mutation operation '{operation.operation_id}' expected one target occurrence, found {occurrence_count}"
        )
    replacement = "" if operation.kind is MutationKind.DELETE_ONCE else operation.replacement
    return text.replace(operation.target, replacement, 1)


def _dataset_warnings(
    manifest: DatasetManifest,
    split_counts: Counter[DatasetSplit],
    tier_counts: Counter[QualityTier],
    human_reviewed: int,
) -> list[str]:
    warnings: list[str] = []
    missing_splits = [split.value for split in DatasetSplit if split_counts[split] == 0]
    if missing_splits:
        warnings.append("Dataset does not yet cover splits: " + ", ".join(missing_splits) + ".")
    if len(manifest.groups) < 12:
        warnings.append("Dataset is below the P0 target of 12 source groups.")
    if tier_counts[QualityTier.ADVERSARIAL] < 8:
        warnings.append("Dataset is below the planned target of 8 adversarial reports.")
    if human_reviewed == 0:
        warnings.append("Dataset contains no human-reviewed report labels.")
    return warnings


def _load_mutation_manifest(path: Path) -> MutationManifest:
    payload = _read_limited(path, MAX_MUTATION_MANIFEST_BYTES, "mutation manifest")
    try:
        return MutationManifest.model_validate_json(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid mutation manifest: {exc}") from exc


def _read_limited(path: Path, maximum_bytes: int, label: str) -> bytes:
    if not path.is_file():
        raise EvaluationInputError(f"{label} does not exist or is not a file: {path.as_posix()}")
    if path.stat().st_size > maximum_bytes:
        raise EvaluationInputError(f"{label} exceeds {maximum_bytes} bytes: {path.as_posix()}")
    return path.read_bytes()


def _resolve_registered_path(root: Path, raw_path: str, label: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise EvaluationInputError(f"{label} path must be relative to the dataset root")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise EvaluationInputError(f"{label} path escapes the dataset root: {raw_path}")
    return resolved


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _canonical_sha256(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return _sha256(canonical.encode("utf-8"))
