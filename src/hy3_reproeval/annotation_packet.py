"""Blinded work-packet preparation and strict human Bundle finalization."""

from __future__ import annotations

import hashlib
import re
import secrets
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import Field, field_validator, model_validator

from . import __version__
from .annotations import (
    MAX_HUMAN_EVIDENCE_LINES,
    AnnotationBundle,
    AnnotationRound,
    AnnotationSource,
    AnnotatorProfile,
    DimensionAnnotation,
    ReportAnnotation,
    SourceEvidenceReference,
    allowed_annotation_error_codes,
)
from .dataset import DatasetSplit, LoadedDatasetManifest, load_dataset_manifest, validate_dataset_manifest
from .errors import EvaluationInputError
from .evaluator import _rubric_sha256
from .freeze import verify_dataset_freeze
from .models import DimensionId, DimensionStatus, ErrorCode, StrictModel
from .rubric import load_public_rubric
from .validators import LoadedEvaluationCase, load_evaluation_case

ANNOTATOR_DIR = "annotator"
ASSIGNMENT_NAME = "assignment.json"
RESPONSES_NAME = "responses.json"
REPORTS_DIR = "reports"
SOURCES_DIR = "sources"
COORDINATOR_NAME = "coordinator_manifest.json"
MAX_PACKET_FILE_BYTES = 16 * 1024 * 1024
_SOURCE_REQUIRED_DIMENSIONS = {
    DimensionId.FACTUAL_ACCURACY,
    DimensionId.EVIDENCE_TRACEABILITY,
    DimensionId.NUMERICAL_CONSISTENCY,
}
_ModelT = TypeVar("_ModelT", bound=StrictModel)
_DISPLAY_LINE_PATTERN = re.compile(r"^(?:L)?0*([1-9][0-9]*)$", re.IGNORECASE)


class AssignmentRubricDimension(StrictModel):
    dimension: DimensionId
    label: str
    weight: float = Field(gt=0, le=1)
    anchors: dict[int, str]
    allowed_error_codes: list[ErrorCode]


class BlindedAssignmentSource(StrictModel):
    source_id: str = Field(pattern=r"^source-[0-9]{3}$")
    source_path: str = Field(pattern=r"^sources/item-[0-9]{3}-source-[0-9]{3}\.[A-Za-z0-9]+$")
    source_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    numbered_source_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    source_line_count: int = Field(ge=1)


class BlindedAssignmentItem(StrictModel):
    item_id: str = Field(pattern=r"^item-[0-9]{3}$")
    report_path: str = Field(pattern=r"^reports/item-[0-9]{3}\.[A-Za-z0-9]+$")
    report_line_count: int = Field(ge=1)
    sources: list[BlindedAssignmentSource] = Field(min_length=1)


class BlindedAnnotationAssignment(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    assignment_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    annotation_bundle_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    annotator_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    dataset_id: str
    dataset_version: str
    dataset_freeze_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    instructions: list[str] = Field(min_length=1)
    rubric: list[AssignmentRubricDimension] = Field(min_length=7, max_length=7)
    items: list[BlindedAssignmentItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> BlindedAnnotationAssignment:
        if {item.dimension for item in self.rubric} != set(DimensionId):
            raise ValueError("assignment Rubric must contain every public dimension")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("assignment item IDs must be unique")
        for item in self.items:
            source_ids = [source.source_id for source in item.sources]
            source_paths = [source.source_path for source in item.sources]
            if len(source_ids) != len(set(source_ids)) or len(source_paths) != len(set(source_paths)):
                raise ValueError("assignment source IDs and paths must be unique within each item")
        return self


class DraftAnnotatorProfile(StrictModel):
    expertise_description: str = Field(default="", max_length=2000)
    independent_annotation: bool | None = None
    blind_to_system_scores: bool | None = None
    rubric_training_completed: bool | None = None
    conflict_of_interest_disclosed: bool | None = None
    conflict_of_interest_present: bool | None = None


class DraftSourceEvidence(StrictModel):
    source_id: str = Field(pattern=r"^source-[0-9]{3}$")
    evidence_lines: list[int] = Field(min_length=1, max_length=MAX_HUMAN_EVIDENCE_LINES)

    @model_validator(mode="before")
    @classmethod
    def accept_human_friendly_lines_key(cls, value: object) -> object:
        if not isinstance(value, dict) or "lines" not in value:
            return value
        payload = dict(value)
        if "evidence_lines" in payload:
            raise ValueError("source evidence cannot define both lines and evidence_lines")
        payload["evidence_lines"] = payload.pop("lines")
        return payload

    @field_validator("evidence_lines", mode="before")
    @classmethod
    def parse_display_line_ids(cls, value: object) -> object:
        return _parse_display_line_ids(value)

    @model_validator(mode="after")
    def validate_lines(self) -> DraftSourceEvidence:
        if any(line < 1 for line in self.evidence_lines):
            raise ValueError("source evidence lines must be positive")
        if len(self.evidence_lines) != len(set(self.evidence_lines)):
            raise ValueError("source evidence lines must be unique")
        return self


class DraftDimensionResponse(StrictModel):
    dimension: DimensionId
    status: DimensionStatus | None = None
    score: int | None = Field(default=None, ge=0, le=4)
    rationale: str = Field(default="", max_length=2000)
    evidence_lines: list[int] = Field(default_factory=list, max_length=MAX_HUMAN_EVIDENCE_LINES)
    source_evidence: list[DraftSourceEvidence] = Field(default_factory=list, max_length=8)
    error_codes: list[ErrorCode] = Field(default_factory=list)

    @field_validator("evidence_lines", mode="before")
    @classmethod
    def parse_display_line_ids(cls, value: object) -> object:
        return _parse_display_line_ids(value)


class DraftItemResponse(StrictModel):
    item_id: str = Field(pattern=r"^item-[0-9]{3}$")
    dimensions: list[DraftDimensionResponse] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_dimensions(self) -> DraftItemResponse:
        dimensions = [item.dimension for item in self.dimensions]
        if set(dimensions) != set(DimensionId) or len(dimensions) != len(set(dimensions)):
            raise ValueError("response item must contain every public dimension exactly once")
        for item in self.dimensions:
            source_ids = [reference.source_id for reference in item.source_evidence]
            if len(source_ids) != len(set(source_ids)):
                raise ValueError("response source evidence IDs must be unique within each dimension")
        return self


class DraftAnnotationResponses(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    assignment_id: str
    annotation_bundle_id: str
    annotator_id: str
    annotation_date: str | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    annotator_profile: DraftAnnotatorProfile
    responses: list[DraftItemResponse] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_items(self) -> DraftAnnotationResponses:
        item_ids = [item.item_id for item in self.responses]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("response item IDs must be unique")
        return self


def _parse_display_line_ids(value: object) -> object:
    if not isinstance(value, list):
        return value
    normalized: list[object] = []
    for line in value:
        if not isinstance(line, str):
            normalized.append(line)
            continue
        match = _DISPLAY_LINE_PATTERN.fullmatch(line.strip())
        if match is None:
            raise ValueError(f"invalid displayed line identifier: {line!r}")
        normalized.append(int(match.group(1)))
    return normalized


class CoordinatorSource(StrictModel):
    source_id: str = Field(pattern=r"^source-[0-9]{3}$")
    artifact_id: str
    artifact_path: str
    source_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    copied_source_path: str = Field(pattern=r"^annotator/sources/item-[0-9]{3}-source-[0-9]{3}\.[A-Za-z0-9]+$")
    copied_source_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    source_line_count: int = Field(ge=1)


class CoordinatorItem(StrictModel):
    item_id: str = Field(pattern=r"^item-[0-9]{3}$")
    group_id: str
    report_id: str
    report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    copied_report_path: str = Field(pattern=r"^annotator/reports/item-[0-9]{3}\.[A-Za-z0-9]+$")
    copied_report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    report_line_count: int = Field(ge=1)
    sources: list[CoordinatorSource] = Field(min_length=1)


class AnnotationPacketCoordinator(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    engine_version: str
    assignment_id: str
    annotation_bundle_id: str
    annotator_id: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    assignment_path: Literal["annotator/assignment.json"] = "annotator/assignment.json"
    assignment_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    responses_path: Literal["annotator/responses.json"] = "annotator/responses.json"
    item_count: int = Field(ge=1)
    items: list[CoordinatorItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_items(self) -> AnnotationPacketCoordinator:
        if self.item_count != len(self.items):
            raise ValueError("coordinator item_count does not match inventory")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("coordinator item IDs must be unique")
        return self


class AnnotationPacketResult(StrictModel):
    output_root: str
    assignment_id: str
    annotator_id: str
    item_count: int = Field(ge=1)
    annotator_directory: str
    coordinator_manifest: str


def prepare_annotation_packet(
    dataset_path: str | Path,
    dataset_freeze_path: str | Path,
    output_dir: str | Path,
    *,
    assignment_id: str,
    annotator_id: str,
    annotation_bundle_id: str,
) -> AnnotationPacketResult:
    """Create a randomized blind packet for one independent human annotator."""

    validate_dataset_manifest(dataset_path)
    dataset = load_dataset_manifest(dataset_path)
    freeze = verify_dataset_freeze(dataset_freeze_path, dataset_path)
    rubric = load_public_rubric()
    rubric_sha256 = _rubric_sha256(rubric)
    output_root = _prepare_empty_output(output_dir)
    annotator_root = output_root / ANNOTATOR_DIR
    report_root = annotator_root / REPORTS_DIR
    source_root = annotator_root / SOURCES_DIR
    report_root.mkdir(parents=True)
    source_root.mkdir()

    inventory: list[tuple[str, str, LoadedEvaluationCase, str]] = []
    for group in dataset.manifest.groups:
        if group.split not in {DatasetSplit.VALIDATION, DatasetSplit.TEST}:
            continue
        for report in group.reports:
            loaded = load_evaluation_case(dataset.resolve(report.case_path, "evaluation case"))
            if not loaded.case.artifacts:
                raise EvaluationInputError(f"annotation report '{report.report_id}' has no registered source artifacts")
            inventory.append((group.group_id, report.report_id, loaded, report.report_sha256))
    if not inventory:
        raise EvaluationInputError("annotation packet requires at least one validation or test report")
    secrets.SystemRandom().shuffle(inventory)

    assignment_items: list[BlindedAssignmentItem] = []
    coordinator_items: list[CoordinatorItem] = []
    response_items: list[DraftItemResponse] = []
    for number, (group_id, report_id, loaded, report_sha256) in enumerate(inventory, start=1):
        item_id = f"item-{number:03d}"
        suffix = _safe_suffix(loaded.report_path)
        relative_report = f"{REPORTS_DIR}/{item_id}{suffix}"
        copied_path = annotator_root / relative_report
        payload = _read_limited(loaded.report_path, MAX_PACKET_FILE_BYTES, "annotation source report")
        if _sha256(payload) != report_sha256:
            raise EvaluationInputError(f"annotation source report hash changed: {report_id}")
        numbered_report, line_count = _numbered_text(payload, f"annotation source report '{report_id}'")
        copied_path.write_bytes(numbered_report)

        assignment_sources: list[BlindedAssignmentSource] = []
        coordinator_sources: list[CoordinatorSource] = []
        for source_number, artifact in enumerate(
            sorted(loaded.case.artifacts, key=lambda item: item.artifact_id), start=1
        ):
            source_id = f"source-{source_number:03d}"
            source_path = _resolve_case_file(loaded.root, artifact.path, "annotation source material")
            source_payload = _read_limited(source_path, MAX_PACKET_FILE_BYTES, "annotation source material")
            source_sha256 = _sha256(source_payload)
            if source_sha256 != artifact.sha256.upper():
                raise EvaluationInputError(f"annotation source material hash changed: {artifact.artifact_id}")
            source_suffix = _safe_suffix(source_path)
            relative_source = f"{SOURCES_DIR}/{item_id}-{source_id}{source_suffix}"
            numbered_source, source_line_count = _numbered_text(
                source_payload,
                f"annotation source material '{artifact.artifact_id}'",
            )
            (annotator_root / relative_source).write_bytes(numbered_source)
            numbered_source_sha256 = _sha256(numbered_source)
            assignment_sources.append(
                BlindedAssignmentSource(
                    source_id=source_id,
                    source_path=relative_source,
                    source_sha256=source_sha256,
                    numbered_source_sha256=numbered_source_sha256,
                    source_line_count=source_line_count,
                )
            )
            coordinator_sources.append(
                CoordinatorSource(
                    source_id=source_id,
                    artifact_id=artifact.artifact_id,
                    artifact_path=artifact.path,
                    source_sha256=source_sha256,
                    copied_source_path=f"{ANNOTATOR_DIR}/{relative_source}",
                    copied_source_sha256=numbered_source_sha256,
                    source_line_count=source_line_count,
                )
            )
        assignment_items.append(
            BlindedAssignmentItem(
                item_id=item_id,
                report_path=relative_report,
                report_line_count=line_count,
                sources=assignment_sources,
            )
        )
        coordinator_items.append(
            CoordinatorItem(
                item_id=item_id,
                group_id=group_id,
                report_id=report_id,
                report_sha256=report_sha256,
                copied_report_path=f"{ANNOTATOR_DIR}/{relative_report}",
                copied_report_sha256=_sha256(numbered_report),
                report_line_count=line_count,
                sources=coordinator_sources,
            )
        )
        response_items.append(
            DraftItemResponse(
                item_id=item_id,
                dimensions=[DraftDimensionResponse(dimension=dimension.id) for dimension in rubric.dimensions],
            )
        )

    assignment = BlindedAnnotationAssignment(
        assignment_id=assignment_id,
        annotation_bundle_id=annotation_bundle_id,
        annotator_id=annotator_id,
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        dataset_freeze_sha256=freeze.freeze_sha256,
        rubric_version=rubric.rubric_version,
        rubric_sha256=rubric_sha256,
        instructions=[
            "Work independently and do not seek system scores, quality tiers, mutation labels, "
            "or another annotator's responses.",
            "Read each neutral report and its source materials; every displayed line uses the canonical "
            "L000001-style identifier.",
            "For assessed dimensions, provide a 0-4 score, concise rationale, and one or more report evidence lines.",
            "For assessed factual_accuracy, evidence_traceability, and numerical_consistency dimensions, "
            "also provide source_evidence using the neutral source ID and canonical source line numbers.",
            "Use insufficient_evidence without a score when the report cannot support an assessment.",
            "Complete the profile declarations and annotation_date in responses.json before returning "
            "the annotator directory.",
        ],
        rubric=[
            AssignmentRubricDimension(
                dimension=dimension.id,
                label=dimension.label,
                weight=dimension.weight,
                anchors=dimension.anchors,
                allowed_error_codes=allowed_annotation_error_codes(dimension.id),
            )
            for dimension in rubric.dimensions
        ],
        items=assignment_items,
    )
    responses = DraftAnnotationResponses(
        assignment_id=assignment_id,
        annotation_bundle_id=annotation_bundle_id,
        annotator_id=annotator_id,
        annotator_profile=DraftAnnotatorProfile(),
        responses=response_items,
    )
    assignment_path = annotator_root / ASSIGNMENT_NAME
    responses_path = annotator_root / RESPONSES_NAME
    _write_json(assignment_path, assignment)
    _write_json(responses_path, responses)
    coordinator = AnnotationPacketCoordinator(
        engine_version=__version__,
        assignment_id=assignment_id,
        annotation_bundle_id=annotation_bundle_id,
        annotator_id=annotator_id,
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        dataset_manifest_sha256=dataset.manifest_sha256,
        dataset_freeze_sha256=freeze.freeze_sha256,
        rubric_version=rubric.rubric_version,
        rubric_sha256=rubric_sha256,
        assignment_sha256=_file_sha256(assignment_path),
        item_count=len(coordinator_items),
        items=coordinator_items,
    )
    _write_json(output_root / COORDINATOR_NAME, coordinator)
    return AnnotationPacketResult(
        output_root=output_root.as_posix(),
        assignment_id=assignment_id,
        annotator_id=annotator_id,
        item_count=len(coordinator_items),
        annotator_directory=annotator_root.as_posix(),
        coordinator_manifest=(output_root / COORDINATOR_NAME).as_posix(),
    )


def finalize_annotation_packet(
    dataset_path: str | Path,
    dataset_freeze_path: str | Path,
    packet_dir: str | Path,
    output_path: str | Path,
) -> AnnotationBundle:
    """Verify one completed blind packet and emit a strict independent human Bundle."""

    validate_dataset_manifest(dataset_path)
    dataset = load_dataset_manifest(dataset_path)
    freeze = verify_dataset_freeze(dataset_freeze_path, dataset_path)
    rubric = load_public_rubric()
    rubric_sha256 = _rubric_sha256(rubric)
    root = Path(packet_dir).expanduser().resolve()
    coordinator = _load_model(root / COORDINATOR_NAME, AnnotationPacketCoordinator, "coordinator manifest")
    assignment_path = _resolve_inside(root, coordinator.assignment_path, "assignment")
    responses_path = _resolve_inside(root, coordinator.responses_path, "responses")
    assignment = _load_model(assignment_path, BlindedAnnotationAssignment, "blinded assignment")
    responses = _load_model(responses_path, DraftAnnotationResponses, "annotation responses")
    identity = (
        coordinator.dataset_id,
        coordinator.dataset_version,
        coordinator.dataset_manifest_sha256,
        coordinator.dataset_freeze_sha256,
        coordinator.rubric_version,
        coordinator.rubric_sha256,
    )
    current = (
        dataset.manifest.dataset_id,
        dataset.manifest.dataset_version,
        dataset.manifest_sha256,
        freeze.freeze_sha256,
        rubric.rubric_version,
        rubric_sha256,
    )
    if identity != current:
        raise EvaluationInputError("annotation packet uses a different Dataset, Freeze, or Rubric")
    loaded_by_item = _verify_coordinator_inventory(dataset, coordinator)
    if _file_sha256(assignment_path) != coordinator.assignment_sha256:
        raise EvaluationInputError("blinded assignment fingerprint changed")
    shared = (
        coordinator.assignment_id,
        coordinator.annotation_bundle_id,
        coordinator.annotator_id,
    )
    if shared != (assignment.assignment_id, assignment.annotation_bundle_id, assignment.annotator_id):
        raise EvaluationInputError("blinded assignment identity does not match coordinator manifest")
    if shared != (responses.assignment_id, responses.annotation_bundle_id, responses.annotator_id):
        raise EvaluationInputError("annotation response identity does not match coordinator manifest")
    assignment_ids = [item.item_id for item in assignment.items]
    coordinator_ids = [item.item_id for item in coordinator.items]
    response_ids = [item.item_id for item in responses.responses]
    if assignment_ids != coordinator_ids or set(response_ids) != set(coordinator_ids):
        raise EvaluationInputError("annotation packet item inventories do not match")
    _verify_packet_copies(root, coordinator, assignment, loaded_by_item)
    profile = _completed_profile(responses)
    if responses.annotation_date is None:
        raise EvaluationInputError("annotation responses must declare annotation_date")
    response_by_id = {item.item_id: item for item in responses.responses}
    coordinator_by_id = {item.item_id: item for item in coordinator.items}
    annotations: list[ReportAnnotation] = []
    for item_id in coordinator_ids:
        mapped = coordinator_by_id[item_id]
        response = response_by_id[item_id]
        source_inventory = {
            source.source_id: (source.artifact_id, source.source_line_count) for source in mapped.sources
        }
        annotations.append(
            ReportAnnotation(
                group_id=mapped.group_id,
                report_id=mapped.report_id,
                report_sha256=mapped.report_sha256,
                dimensions=[
                    _completed_dimension(item, mapped.report_line_count, source_inventory)
                    for item in response.dimensions
                ],
            )
        )
    bundle = AnnotationBundle(
        annotation_bundle_id=coordinator.annotation_bundle_id,
        annotation_source=AnnotationSource.HUMAN,
        annotation_round=AnnotationRound.INDEPENDENT,
        annotation_date=responses.annotation_date,
        dataset_id=coordinator.dataset_id,
        dataset_version=coordinator.dataset_version,
        dataset_manifest_sha256=coordinator.dataset_manifest_sha256,
        dataset_freeze_sha256=coordinator.dataset_freeze_sha256,
        rubric_version=coordinator.rubric_version,
        rubric_sha256=coordinator.rubric_sha256,
        annotator=profile,
        annotations=annotations,
    )
    target = Path(output_path).expanduser().resolve()
    if target.exists():
        raise EvaluationInputError(f"annotation Bundle output already exists: {target.as_posix()}")
    if not target.parent.is_dir():
        raise EvaluationInputError(f"annotation Bundle parent directory does not exist: {target.parent.as_posix()}")
    _write_json(target, bundle)
    return bundle


def _prepare_empty_output(path: str | Path) -> Path:
    output = Path(path).expanduser().resolve()
    if output.exists() and not output.is_dir():
        raise EvaluationInputError("annotation packet output path must be a directory")
    if not output.parent.is_dir():
        raise EvaluationInputError(f"annotation packet parent directory does not exist: {output.parent.as_posix()}")
    if output.exists() and any(output.iterdir()):
        raise EvaluationInputError("annotation packet output directory must be absent or empty")
    output.mkdir(exist_ok=True)
    return output


def _verify_packet_copies(
    root: Path,
    coordinator: AnnotationPacketCoordinator,
    assignment: BlindedAnnotationAssignment,
    loaded_by_item: dict[str, LoadedEvaluationCase],
) -> None:
    assignment_by_id = {item.item_id: item for item in assignment.items}
    for item in coordinator.items:
        loaded = loaded_by_item[item.item_id]
        copied = _resolve_inside(root, item.copied_report_path, "blinded report")
        payload = _read_limited(copied, MAX_PACKET_FILE_BYTES, "blinded report")
        source_report = _read_limited(loaded.report_path, MAX_PACKET_FILE_BYTES, "annotation source report")
        expected_payload, expected_line_count = _numbered_text(
            source_report,
            f"annotation source report '{item.report_id}'",
        )
        if payload != expected_payload or _sha256(payload) != item.copied_report_sha256:
            raise EvaluationInputError(f"blinded report fingerprint changed: {item.item_id}")
        assignment_item = assignment_by_id[item.item_id]
        expected_assignment_path = item.copied_report_path.removeprefix(f"{ANNOTATOR_DIR}/")
        if (
            assignment_item.report_path != expected_assignment_path
            or expected_line_count != item.report_line_count
            or assignment_item.report_line_count != expected_line_count
        ):
            raise EvaluationInputError(f"blinded report metadata changed: {item.item_id}")

        assignment_sources = {source.source_id: source for source in assignment_item.sources}
        if set(assignment_sources) != {source.source_id for source in item.sources}:
            raise EvaluationInputError(f"blinded source inventory changed: {item.item_id}")
        for source in item.sources:
            original_path = _resolve_case_file(loaded.root, source.artifact_path, "annotation source material")
            original_payload = _read_limited(
                original_path,
                MAX_PACKET_FILE_BYTES,
                "annotation source material",
            )
            if _sha256(original_payload) != source.source_sha256:
                raise EvaluationInputError(f"annotation source material fingerprint changed: {item.item_id}")
            expected_source, expected_source_lines = _numbered_text(
                original_payload,
                f"annotation source material '{source.artifact_id}'",
            )
            copied_source = _resolve_inside(root, source.copied_source_path, "blinded source material")
            copied_source_payload = _read_limited(
                copied_source,
                MAX_PACKET_FILE_BYTES,
                "blinded source material",
            )
            if (
                copied_source_payload != expected_source
                or _sha256(copied_source_payload) != source.copied_source_sha256
            ):
                raise EvaluationInputError(f"blinded source fingerprint changed: {item.item_id}/{source.source_id}")
            assignment_source = assignment_sources[source.source_id]
            expected_source_path = source.copied_source_path.removeprefix(f"{ANNOTATOR_DIR}/")
            if (
                assignment_source.source_path != expected_source_path
                or assignment_source.source_sha256 != source.source_sha256
                or assignment_source.numbered_source_sha256 != source.copied_source_sha256
                or assignment_source.source_line_count != expected_source_lines
                or source.source_line_count != expected_source_lines
            ):
                raise EvaluationInputError(f"blinded source metadata changed: {item.item_id}/{source.source_id}")


def _verify_coordinator_inventory(
    dataset: LoadedDatasetManifest,
    coordinator: AnnotationPacketCoordinator,
) -> dict[str, LoadedEvaluationCase]:
    expected = {
        (group.group_id, report.report_id): (
            report.report_sha256,
            load_evaluation_case(dataset.resolve(report.case_path, "evaluation case")),
        )
        for group in dataset.manifest.groups
        if group.split in {DatasetSplit.VALIDATION, DatasetSplit.TEST}
        for report in group.reports
    }
    actual_keys = [(item.group_id, item.report_id) for item in coordinator.items]
    if len(set(actual_keys)) != len(coordinator.items) or set(actual_keys) != set(expected):
        raise EvaluationInputError("coordinator inventory must contain every validation/test report exactly once")
    loaded_by_item: dict[str, LoadedEvaluationCase] = {}
    for item in coordinator.items:
        expected_report_sha256, loaded = expected[(item.group_id, item.report_id)]
        if item.report_sha256 != expected_report_sha256:
            raise EvaluationInputError(f"coordinator report fingerprint changed: {item.item_id}")
        expected_artifacts = sorted(loaded.case.artifacts, key=lambda artifact: artifact.artifact_id)
        if len(item.sources) != len(expected_artifacts):
            raise EvaluationInputError(f"coordinator source inventory changed: {item.item_id}")
        for source_number, (source, artifact) in enumerate(zip(item.sources, expected_artifacts, strict=True), start=1):
            if (
                source.source_id != f"source-{source_number:03d}"
                or source.artifact_id != artifact.artifact_id
                or source.artifact_path != artifact.path
                or source.source_sha256 != artifact.sha256.upper()
            ):
                raise EvaluationInputError(f"coordinator source inventory changed: {item.item_id}")
        loaded_by_item[item.item_id] = loaded
    return loaded_by_item


def _completed_profile(responses: DraftAnnotationResponses) -> AnnotatorProfile:
    draft = responses.annotator_profile
    declarations = (
        draft.independent_annotation,
        draft.blind_to_system_scores,
        draft.rubric_training_completed,
        draft.conflict_of_interest_disclosed,
        draft.conflict_of_interest_present,
    )
    if not draft.expertise_description.strip() or any(value is None for value in declarations):
        raise EvaluationInputError("annotation responses must complete every annotator profile field")
    if (
        not draft.independent_annotation
        or not draft.blind_to_system_scores
        or not draft.rubric_training_completed
        or not draft.conflict_of_interest_disclosed
        or draft.conflict_of_interest_present
    ):
        raise EvaluationInputError(
            "independent packet finalization requires a trained, system-score-blind, "
            "conflict-free annotator declaration"
        )
    return AnnotatorProfile(
        annotator_id=responses.annotator_id,
        expertise_description=draft.expertise_description,
        independent_annotation=bool(draft.independent_annotation),
        blind_to_system_scores=bool(draft.blind_to_system_scores),
        rubric_training_completed=bool(draft.rubric_training_completed),
        conflict_of_interest_disclosed=bool(draft.conflict_of_interest_disclosed),
        conflict_of_interest_present=bool(draft.conflict_of_interest_present),
    )


def _completed_dimension(
    item: DraftDimensionResponse,
    line_count: int,
    source_inventory: dict[str, tuple[str, int]],
) -> DimensionAnnotation:
    if item.status is None or not item.rationale.strip():
        raise EvaluationInputError(f"annotation dimension '{item.dimension}' is incomplete")
    if any(line < 1 or line > line_count for line in item.evidence_lines):
        raise EvaluationInputError(f"annotation evidence line is outside blinded report for '{item.dimension}'")
    if (
        item.status is DimensionStatus.ASSESSED
        and item.dimension in _SOURCE_REQUIRED_DIMENSIONS
        and not item.source_evidence
    ):
        raise EvaluationInputError(f"annotation dimension '{item.dimension}' requires source evidence")
    source_evidence: list[SourceEvidenceReference] = []
    for reference in item.source_evidence:
        mapped = source_inventory.get(reference.source_id)
        if mapped is None:
            raise EvaluationInputError(
                f"annotation source evidence uses unknown source '{reference.source_id}' for '{item.dimension}'"
            )
        artifact_id, source_line_count = mapped
        if any(line > source_line_count for line in reference.evidence_lines):
            raise EvaluationInputError(
                f"annotation source evidence line is outside '{reference.source_id}' for '{item.dimension}'"
            )
        source_evidence.append(
            SourceEvidenceReference(
                source_id=artifact_id,
                evidence_lines=reference.evidence_lines,
            )
        )
    try:
        return DimensionAnnotation(
            dimension=item.dimension,
            status=item.status,
            score=item.score,
            rationale=item.rationale,
            evidence_lines=item.evidence_lines,
            source_evidence=source_evidence,
            error_codes=item.error_codes,
        )
    except ValueError as exc:
        raise EvaluationInputError(f"invalid completed annotation dimension '{item.dimension}': {exc}") from exc


def _resolve_inside(root: Path, relative: str, label: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise EvaluationInputError(f"{label} path is missing or escapes packet root: {relative}")
    return path


def _load_model(path: Path, model_type: type[_ModelT], label: str) -> _ModelT:
    payload = _read_limited(path, MAX_PACKET_FILE_BYTES, label)
    try:
        return model_type.model_validate_json(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid {label}: {exc}") from exc


def _read_limited(path: Path, maximum_bytes: int, label: str) -> bytes:
    if not path.is_file():
        raise EvaluationInputError(f"{label} does not exist: {path.as_posix()}")
    if path.stat().st_size > maximum_bytes:
        raise EvaluationInputError(f"{label} exceeds {maximum_bytes} bytes")
    return path.read_bytes()


def _numbered_text(payload: bytes, label: str) -> tuple[bytes, int]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvaluationInputError(f"{label} must be UTF-8 text") from exc
    lines = text.splitlines()
    line_count = len(lines)
    if line_count < 1:
        raise EvaluationInputError(f"{label} must contain at least one line")
    numbered = "".join(f"L{line_number:06d} | {line}\n" for line_number, line in enumerate(lines, start=1))
    return numbered.encode("utf-8"), line_count


def _safe_suffix(path: Path) -> str:
    suffix = path.suffix.lower() if path.suffix else ".txt"
    return suffix if suffix[1:].isalnum() else ".txt"


def _resolve_case_file(root: Path, relative: str, label: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise EvaluationInputError(f"{label} path is missing or escapes case root: {relative}")
    return path


def _write_json(path: Path, model: StrictModel) -> None:
    path.write_bytes((model.model_dump_json(indent=2) + "\n").encode("utf-8"))


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()
