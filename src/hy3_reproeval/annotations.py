"""De-identified human annotation contracts for ReproEval report datasets."""

from __future__ import annotations

import hashlib
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from . import __version__
from .dataset import DatasetSplit, LoadedDatasetManifest, load_dataset_manifest, validate_dataset_manifest
from .errors import EvaluationInputError
from .evaluator import _rubric_sha256
from .freeze import optional_dataset_freeze_sha256
from .models import DimensionId, DimensionStatus, ErrorCode, StrictModel
from .rubric import load_public_rubric
from .validators import load_evaluation_case

MAX_ANNOTATION_BUNDLE_BYTES = 8 * 1024 * 1024
MAX_ANNOTATION_BUNDLES = 32

_DIMENSION_ERROR_CODES = {
    DimensionId.FACTUAL_ACCURACY: {ErrorCode.UNSUPPORTED_CLAIM},
    DimensionId.EVIDENCE_TRACEABILITY: {
        ErrorCode.FABRICATED_CITATION,
        ErrorCode.CITATION_MISMATCH,
        ErrorCode.ARTIFACT_LINEAGE_ERROR,
    },
    DimensionId.NUMERICAL_CONSISTENCY: {ErrorCode.NUMERIC_ERROR, ErrorCode.UNIT_ERROR},
    DimensionId.REASONING_CONSISTENCY: {ErrorCode.REASONING_GAP},
    DimensionId.UNCERTAINTY_HANDLING: {ErrorCode.OVERCONFIDENCE, ErrorCode.MISSING_LIMITATION},
    DimensionId.CONTENT_COMPLETENESS: {ErrorCode.SETTING_OMISSION, ErrorCode.FORMAT_VIOLATION},
    DimensionId.CLARITY_ACTIONABILITY: {
        ErrorCode.VERBOSITY_WITHOUT_EVIDENCE,
        ErrorCode.ACTIONABILITY_GAP,
    },
}


class AnnotationSource(StrEnum):
    HUMAN = "human"
    SYNTHETIC_PROTOCOL_FIXTURE = "synthetic_protocol_fixture"


class AnnotationRound(StrEnum):
    INDEPENDENT = "independent"
    ADJUDICATION = "adjudication"
    REPEAT = "repeat"


class AnnotatorProfile(StrictModel):
    annotator_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    expertise_description: str = Field(min_length=1, max_length=500)
    independent_annotation: bool
    blind_to_system_scores: bool
    rubric_training_completed: bool
    conflict_of_interest_disclosed: bool
    conflict_of_interest_present: bool


class DimensionAnnotation(StrictModel):
    dimension: DimensionId
    status: DimensionStatus
    score: int | None = Field(default=None, ge=0, le=4)
    rationale: str = Field(min_length=1, max_length=2000)
    evidence_lines: list[int] = Field(default_factory=list, max_length=8)
    error_codes: list[ErrorCode] = Field(default_factory=list)

    @field_validator("evidence_lines")
    @classmethod
    def validate_evidence_lines(cls, value: list[int]) -> list[int]:
        if any(line < 1 for line in value):
            raise ValueError("annotation evidence lines must be positive")
        if len(value) != len(set(value)):
            raise ValueError("annotation evidence lines must be unique")
        return value

    @model_validator(mode="after")
    def validate_assessment(self) -> DimensionAnnotation:
        if self.status is DimensionStatus.ASSESSED:
            if self.score is None:
                raise ValueError("assessed annotation dimension requires a score")
            if not self.evidence_lines:
                raise ValueError("assessed annotation dimension requires report evidence lines")
        elif self.score is not None:
            raise ValueError("insufficient_evidence annotation dimension cannot define a score")
        if len(self.error_codes) != len(set(self.error_codes)):
            raise ValueError("annotation error codes must be unique")
        invalid = set(self.error_codes) - _DIMENSION_ERROR_CODES[self.dimension]
        if invalid:
            names = ", ".join(sorted(error.value for error in invalid))
            raise ValueError(f"annotation dimension contains incompatible error codes: {names}")
        if self.score == 4 and self.error_codes:
            raise ValueError("a score of 4 cannot declare an error code")
        return self


class ReportAnnotation(StrictModel):
    group_id: str
    report_id: str
    report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dimensions: list[DimensionAnnotation] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def require_all_dimensions(self) -> ReportAnnotation:
        dimensions = [annotation.dimension for annotation in self.dimensions]
        if set(dimensions) != set(DimensionId) or len(dimensions) != len(set(dimensions)):
            raise ValueError("report annotation must contain every public Rubric dimension exactly once")
        return self


class AnnotationBundle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    annotation_bundle_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    annotation_source: AnnotationSource
    annotation_round: AnnotationRound
    annotation_date: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_sha256: str | None = Field(default=None, pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    annotator: AnnotatorProfile
    parent_annotation_bundle_ids: list[str] = Field(default_factory=list, max_length=32)
    annotations: list[ReportAnnotation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle_inventory(self) -> AnnotationBundle:
        report_ids = [annotation.report_id for annotation in self.annotations]
        if len(report_ids) != len(set(report_ids)):
            raise ValueError("annotation bundle report IDs must be unique")
        if len(self.parent_annotation_bundle_ids) != len(set(self.parent_annotation_bundle_ids)):
            raise ValueError("parent annotation Bundle IDs must be unique")
        if self.annotation_round is AnnotationRound.INDEPENDENT and self.parent_annotation_bundle_ids:
            raise ValueError("independent annotation Bundle cannot declare parent Bundles")
        if self.annotation_round is AnnotationRound.REPEAT and len(self.parent_annotation_bundle_ids) != 1:
            raise ValueError("repeat annotation Bundle requires exactly one parent Bundle")
        if self.annotation_round is AnnotationRound.ADJUDICATION and len(self.parent_annotation_bundle_ids) < 2:
            raise ValueError("adjudication annotation Bundle requires at least two parent Bundles")
        if (
            self.annotation_source is AnnotationSource.SYNTHETIC_PROTOCOL_FIXTURE
            and self.annotation_round is not AnnotationRound.INDEPENDENT
        ):
            raise ValueError("synthetic protocol fixtures cannot represent repeat or adjudication rounds")
        return self


class AnnotationBundleSummary(StrictModel):
    annotation_bundle_id: str
    annotation_bundle_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    annotation_source: AnnotationSource
    annotation_round: AnnotationRound
    annotator_id: str
    annotation_count: int = Field(ge=1)
    benchmark_eligible_annotation_count: int = Field(ge=0)


class AnnotationValidationResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_sha256: str | None = Field(default=None, pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    bundle_count: int = Field(ge=1)
    annotator_count: int = Field(ge=1)
    annotation_count: int = Field(ge=1)
    human_annotation_count: int = Field(ge=0)
    synthetic_annotation_count: int = Field(ge=0)
    annotated_report_count: int = Field(ge=1)
    dataset_report_coverage: float = Field(ge=0, le=1)
    split_annotation_counts: dict[DatasetSplit, int]
    benchmark_target_report_count: int = Field(ge=0)
    independently_double_annotated_report_count: int = Field(ge=0)
    benchmark_ready: bool
    bundles: list[AnnotationBundleSummary]
    warnings: list[str] = Field(default_factory=list)


def validate_annotation_bundles(
    dataset_path: str | Path,
    bundle_paths: list[str | Path],
    *,
    dataset_freeze_path: str | Path | None = None,
) -> AnnotationValidationResult:
    if not bundle_paths:
        raise EvaluationInputError("at least one annotation bundle is required")
    if len(bundle_paths) > MAX_ANNOTATION_BUNDLES:
        raise EvaluationInputError(f"annotation bundle count exceeds {MAX_ANNOTATION_BUNDLES}")
    validate_dataset_manifest(dataset_path)
    dataset = load_dataset_manifest(dataset_path)
    expected_freeze_sha256 = optional_dataset_freeze_sha256(dataset_freeze_path, dataset_path)
    rubric = load_public_rubric()
    rubric_sha256 = _rubric_sha256(rubric)
    inventory = _report_inventory(dataset)
    bundles: list[tuple[AnnotationBundle, str]] = []
    for raw_path in bundle_paths:
        path = Path(raw_path).expanduser().resolve()
        payload = _read_limited(path, MAX_ANNOTATION_BUNDLE_BYTES, "annotation bundle")
        try:
            bundle = AnnotationBundle.model_validate_json(payload)
        except ValueError as exc:
            raise EvaluationInputError(f"invalid annotation bundle: {exc}") from exc
        _validate_bundle_identity(
            bundle,
            dataset,
            rubric.rubric_version,
            rubric_sha256,
            expected_freeze_sha256,
        )
        bundles.append((bundle, _sha256(payload)))

    bundle_freezes = {bundle.dataset_freeze_sha256 for bundle, _ in bundles}
    if len(bundle_freezes) != 1:
        raise EvaluationInputError("annotation bundles use inconsistent Dataset Freeze fingerprints")
    if expected_freeze_sha256 is None and next(iter(bundle_freezes)) is not None:
        raise EvaluationInputError("Freeze-bound annotation bundles require --dataset-freeze")
    dataset_freeze_sha256 = expected_freeze_sha256 or next(iter(bundle_freezes))

    bundle_ids = [bundle.annotation_bundle_id for bundle, _ in bundles]
    if len(bundle_ids) != len(set(bundle_ids)):
        raise EvaluationInputError("annotation bundle IDs must be unique")
    independent_annotators = [
        bundle.annotator.annotator_id for bundle, _ in bundles if bundle.annotation_round is AnnotationRound.INDEPENDENT
    ]
    if len(independent_annotators) != len(set(independent_annotators)):
        raise EvaluationInputError("one annotator cannot submit multiple independent annotation bundles")
    _validate_bundle_lineage(bundles)

    split_counts: Counter[DatasetSplit] = Counter()
    eligible_annotators_by_report: dict[str, set[str]] = {}
    annotated_reports: set[str] = set()
    human_annotations = 0
    synthetic_annotations = 0
    summaries: list[AnnotationBundleSummary] = []
    for bundle, bundle_sha256 in bundles:
        eligible_count = 0
        for annotation in bundle.annotations:
            inventory_item = inventory.get(annotation.report_id)
            if inventory_item is None:
                raise EvaluationInputError(f"annotation references unknown report '{annotation.report_id}'")
            group_id, split, report_sha256, line_count = inventory_item
            if annotation.group_id != group_id or annotation.report_sha256 != report_sha256:
                raise EvaluationInputError(f"annotation metadata mismatch for report '{annotation.report_id}'")
            _validate_annotation_lines(annotation, line_count)
            annotated_reports.add(annotation.report_id)
            split_counts[split] += 1
            if bundle.annotation_source is AnnotationSource.HUMAN:
                human_annotations += 1
            else:
                synthetic_annotations += 1
            if is_benchmark_eligible(bundle, split):
                eligible_count += 1
                eligible_annotators_by_report.setdefault(annotation.report_id, set()).add(bundle.annotator.annotator_id)
        summaries.append(
            AnnotationBundleSummary(
                annotation_bundle_id=bundle.annotation_bundle_id,
                annotation_bundle_sha256=bundle_sha256,
                annotation_source=bundle.annotation_source,
                annotation_round=bundle.annotation_round,
                annotator_id=bundle.annotator.annotator_id,
                annotation_count=len(bundle.annotations),
                benchmark_eligible_annotation_count=eligible_count,
            )
        )

    target_reports = {
        report_id
        for report_id, (_, split, _, _) in inventory.items()
        if split in {DatasetSplit.VALIDATION, DatasetSplit.TEST}
    }
    double_annotated = {
        report_id for report_id in target_reports if len(eligible_annotators_by_report.get(report_id, set())) >= 2
    }
    benchmark_ready = bool(target_reports) and double_annotated == target_reports
    warnings = _annotation_warnings(
        bundles,
        target_report_count=len(target_reports),
        double_annotated_count=len(double_annotated),
        benchmark_ready=benchmark_ready,
    )
    return AnnotationValidationResult(
        engine_version=__version__,
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        dataset_manifest_sha256=dataset.manifest_sha256,
        dataset_freeze_sha256=dataset_freeze_sha256,
        rubric_version=rubric.rubric_version,
        rubric_sha256=rubric_sha256,
        bundle_count=len(bundles),
        annotator_count=len({bundle.annotator.annotator_id for bundle, _ in bundles}),
        annotation_count=human_annotations + synthetic_annotations,
        human_annotation_count=human_annotations,
        synthetic_annotation_count=synthetic_annotations,
        annotated_report_count=len(annotated_reports),
        dataset_report_coverage=round(len(annotated_reports) / len(inventory), 6),
        split_annotation_counts=dict(split_counts),
        benchmark_target_report_count=len(target_reports),
        independently_double_annotated_report_count=len(double_annotated),
        benchmark_ready=benchmark_ready,
        bundles=summaries,
        warnings=warnings,
    )


def load_validated_annotation_bundles(
    bundle_paths: list[str | Path],
    validation: AnnotationValidationResult,
) -> list[AnnotationBundle]:
    """Reload Bundle bytes only when they still match a completed validation result."""

    expected_hashes = {summary.annotation_bundle_id: summary.annotation_bundle_sha256 for summary in validation.bundles}
    bundles: list[AnnotationBundle] = []
    for raw_path in bundle_paths:
        path = Path(raw_path).expanduser().resolve()
        payload = _read_limited(path, MAX_ANNOTATION_BUNDLE_BYTES, "annotation bundle")
        try:
            bundle = AnnotationBundle.model_validate_json(payload)
        except ValueError as exc:  # pragma: no cover - validation already parsed the same bytes
            raise EvaluationInputError(f"invalid annotation bundle: {exc}") from exc
        if expected_hashes.get(bundle.annotation_bundle_id) != _sha256(payload):
            raise EvaluationInputError("annotation bundle changed after validation")
        bundles.append(bundle)
    return bundles


def _validate_bundle_lineage(bundles: list[tuple[AnnotationBundle, str]]) -> None:
    by_id = {bundle.annotation_bundle_id: bundle for bundle, _ in bundles}
    for bundle, _ in bundles:
        if bundle.annotation_round is AnnotationRound.INDEPENDENT:
            continue
        unknown = sorted(set(bundle.parent_annotation_bundle_ids) - set(by_id))
        if unknown:
            raise EvaluationInputError(
                f"annotation bundle '{bundle.annotation_bundle_id}' references unknown parent Bundles: "
                + ", ".join(unknown)
            )
        parents = [by_id[parent_id] for parent_id in bundle.parent_annotation_bundle_ids]
        if any(
            parent.annotation_round is not AnnotationRound.INDEPENDENT
            or parent.annotation_source is not AnnotationSource.HUMAN
            for parent in parents
        ):
            raise EvaluationInputError("repeat and adjudication parents must be independent human Bundles")
        parent_annotators = {parent.annotator.annotator_id for parent in parents}
        if bundle.annotation_source is not AnnotationSource.HUMAN:
            raise EvaluationInputError("repeat and adjudication Bundles must have human provenance")
        profile = bundle.annotator
        if (
            not profile.blind_to_system_scores
            or not profile.rubric_training_completed
            or not profile.conflict_of_interest_disclosed
            or profile.conflict_of_interest_present
        ):
            raise EvaluationInputError(
                "repeat and adjudication annotators must be trained, system-score-blind, and conflict-free"
            )
        child_reports = {annotation.report_id for annotation in bundle.annotations}
        parent_report_sets = [{annotation.report_id for annotation in parent.annotations} for parent in parents]
        if bundle.annotation_round is AnnotationRound.REPEAT:
            if bundle.annotator.annotator_id not in parent_annotators:
                raise EvaluationInputError("repeat annotation Bundle must use the same annotator as its parent")
            if not child_reports.issubset(parent_report_sets[0]):
                raise EvaluationInputError("repeat annotation reports must be present in the parent Bundle")
        elif len(parent_annotators) < 2:
            raise EvaluationInputError("adjudication Bundle parents must represent at least two annotators")
        elif bundle.annotator.annotator_id in parent_annotators:
            raise EvaluationInputError("adjudicator must be distinct from the parent annotators")
        elif any(sum(report_id in reports for reports in parent_report_sets) < 2 for report_id in child_reports):
            raise EvaluationInputError("each adjudicated report must be present in at least two parent Bundles")


def _validate_bundle_identity(
    bundle: AnnotationBundle,
    dataset: LoadedDatasetManifest,
    rubric_version: str,
    rubric_sha256: str,
    expected_freeze_sha256: str | None,
) -> None:
    expected = (
        dataset.manifest.dataset_id,
        dataset.manifest.dataset_version,
        dataset.manifest_sha256,
        rubric_version,
        rubric_sha256,
    )
    actual = (
        bundle.dataset_id,
        bundle.dataset_version,
        bundle.dataset_manifest_sha256,
        bundle.rubric_version,
        bundle.rubric_sha256,
    )
    if actual != expected:
        raise EvaluationInputError(f"annotation bundle '{bundle.annotation_bundle_id}' identity does not match")
    if expected_freeze_sha256 is not None and bundle.dataset_freeze_sha256 != expected_freeze_sha256:
        raise EvaluationInputError(
            f"annotation bundle '{bundle.annotation_bundle_id}' does not match the verified Dataset Freeze"
        )


def _report_inventory(dataset: LoadedDatasetManifest) -> dict[str, tuple[str, DatasetSplit, str, int]]:
    inventory: dict[str, tuple[str, DatasetSplit, str, int]] = {}
    for group in dataset.manifest.groups:
        for entry in group.reports:
            loaded = load_evaluation_case(dataset.resolve(entry.case_path, "evaluation case"))
            line_count = len(loaded.report_text.splitlines() or [""])
            inventory[entry.report_id] = (group.group_id, group.split, entry.report_sha256, line_count)
    return inventory


def _validate_annotation_lines(annotation: ReportAnnotation, line_count: int) -> None:
    invalid = sorted(
        {line for dimension in annotation.dimensions for line in dimension.evidence_lines if line > line_count}
    )
    if invalid:
        raise EvaluationInputError(
            f"annotation for report '{annotation.report_id}' references lines outside the report: "
            + ", ".join(str(line) for line in invalid)
        )


def is_benchmark_eligible(bundle: AnnotationBundle, split: DatasetSplit) -> bool:
    """Return whether one Bundle may contribute a report annotation to benchmark analysis."""

    profile = bundle.annotator
    return (
        bundle.annotation_source is AnnotationSource.HUMAN
        and bundle.annotation_round is AnnotationRound.INDEPENDENT
        and split in {DatasetSplit.VALIDATION, DatasetSplit.TEST}
        and profile.independent_annotation
        and profile.blind_to_system_scores
        and profile.rubric_training_completed
        and profile.conflict_of_interest_disclosed
        and not profile.conflict_of_interest_present
    )


def _annotation_warnings(
    bundles: list[tuple[AnnotationBundle, str]],
    *,
    target_report_count: int,
    double_annotated_count: int,
    benchmark_ready: bool,
) -> list[str]:
    warnings: list[str] = []
    if any(bundle.annotation_source is AnnotationSource.SYNTHETIC_PROTOCOL_FIXTURE for bundle, _ in bundles):
        warnings.append("Synthetic annotation fixtures are protocol tests and never count as human labels.")
    if not any(bundle.annotation_source is AnnotationSource.HUMAN for bundle, _ in bundles):
        warnings.append("No human annotation bundle is present.")
    else:
        warnings.append("Human annotation provenance is self-attested metadata, not proof of identity or expertise.")
    if target_report_count == 0:
        warnings.append("Dataset contains no validation or test reports eligible for human benchmark analysis.")
    elif not benchmark_ready:
        warnings.append(
            f"Only {double_annotated_count}/{target_report_count} validation/test reports "
            "have two eligible independent annotations."
        )
    return warnings


def _read_limited(path: Path, maximum_bytes: int, label: str) -> bytes:
    if not path.is_file():
        raise EvaluationInputError(f"{label} does not exist or is not a file: {path.as_posix()}")
    if path.stat().st_size > maximum_bytes:
        raise EvaluationInputError(f"{label} exceeds {maximum_bytes} bytes: {path.as_posix()}")
    return path.read_bytes()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()
