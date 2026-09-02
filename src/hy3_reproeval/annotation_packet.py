"""Blinded work-packet preparation and strict human Bundle finalization."""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import Field, model_validator

from . import __version__
from .annotations import (
    AnnotationBundle,
    AnnotationRound,
    AnnotationSource,
    AnnotatorProfile,
    DimensionAnnotation,
    ReportAnnotation,
    allowed_annotation_error_codes,
)
from .dataset import DatasetSplit, LoadedDatasetManifest, load_dataset_manifest, validate_dataset_manifest
from .errors import EvaluationInputError
from .evaluator import _rubric_sha256
from .freeze import verify_dataset_freeze
from .models import DimensionId, DimensionStatus, ErrorCode, StrictModel
from .rubric import load_public_rubric
from .validators import load_evaluation_case

ANNOTATOR_DIR = "annotator"
ASSIGNMENT_NAME = "assignment.json"
RESPONSES_NAME = "responses.json"
REPORTS_DIR = "reports"
COORDINATOR_NAME = "coordinator_manifest.json"
MAX_PACKET_FILE_BYTES = 16 * 1024 * 1024
_ModelT = TypeVar("_ModelT", bound=StrictModel)


class AssignmentRubricDimension(StrictModel):
    dimension: DimensionId
    label: str
    weight: float = Field(gt=0, le=1)
    anchors: dict[int, str]
    allowed_error_codes: list[ErrorCode]


class BlindedAssignmentItem(StrictModel):
    item_id: str = Field(pattern=r"^item-[0-9]{3}$")
    report_path: str = Field(pattern=r"^reports/item-[0-9]{3}\.[A-Za-z0-9]+$")
    report_line_count: int = Field(ge=1)


class BlindedAnnotationAssignment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
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
        return self


class DraftAnnotatorProfile(StrictModel):
    expertise_description: str = Field(default="", max_length=500)
    independent_annotation: bool | None = None
    blind_to_system_scores: bool | None = None
    rubric_training_completed: bool | None = None
    conflict_of_interest_disclosed: bool | None = None
    conflict_of_interest_present: bool | None = None


class DraftDimensionResponse(StrictModel):
    dimension: DimensionId
    status: DimensionStatus | None = None
    score: int | None = Field(default=None, ge=0, le=4)
    rationale: str = Field(default="", max_length=2000)
    evidence_lines: list[int] = Field(default_factory=list, max_length=8)
    error_codes: list[ErrorCode] = Field(default_factory=list)


class DraftItemResponse(StrictModel):
    item_id: str = Field(pattern=r"^item-[0-9]{3}$")
    dimensions: list[DraftDimensionResponse] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_dimensions(self) -> DraftItemResponse:
        dimensions = [item.dimension for item in self.dimensions]
        if set(dimensions) != set(DimensionId) or len(dimensions) != len(set(dimensions)):
            raise ValueError("response item must contain every public dimension exactly once")
        return self


class DraftAnnotationResponses(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
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


class CoordinatorItem(StrictModel):
    item_id: str = Field(pattern=r"^item-[0-9]{3}$")
    group_id: str
    report_id: str
    report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    copied_report_path: str = Field(pattern=r"^annotator/reports/item-[0-9]{3}\.[A-Za-z0-9]+$")
    copied_report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    report_line_count: int = Field(ge=1)


class AnnotationPacketCoordinator(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
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
    report_root.mkdir(parents=True)

    inventory: list[tuple[str, str, Path, str]] = []
    for group in dataset.manifest.groups:
        if group.split not in {DatasetSplit.VALIDATION, DatasetSplit.TEST}:
            continue
        for report in group.reports:
            loaded = load_evaluation_case(dataset.resolve(report.case_path, "evaluation case"))
            inventory.append((group.group_id, report.report_id, loaded.report_path, report.report_sha256))
    if not inventory:
        raise EvaluationInputError("annotation packet requires at least one validation or test report")
    secrets.SystemRandom().shuffle(inventory)

    assignment_items: list[BlindedAssignmentItem] = []
    coordinator_items: list[CoordinatorItem] = []
    response_items: list[DraftItemResponse] = []
    for number, (group_id, report_id, source_path, report_sha256) in enumerate(inventory, start=1):
        item_id = f"item-{number:03d}"
        suffix = source_path.suffix.lower() if source_path.suffix else ".txt"
        if not suffix[1:].isalnum():
            suffix = ".txt"
        relative_report = f"{REPORTS_DIR}/{item_id}{suffix}"
        copied_path = annotator_root / relative_report
        payload = _read_limited(source_path, MAX_PACKET_FILE_BYTES, "annotation source report")
        if _sha256(payload) != report_sha256:
            raise EvaluationInputError(f"annotation source report hash changed: {report_id}")
        copied_path.write_bytes(payload)
        line_count = _line_count(payload, f"annotation source report '{report_id}'")
        assignment_items.append(
            BlindedAssignmentItem(
                item_id=item_id,
                report_path=relative_report,
                report_line_count=line_count,
            )
        )
        coordinator_items.append(
            CoordinatorItem(
                item_id=item_id,
                group_id=group_id,
                report_id=report_id,
                report_sha256=report_sha256,
                copied_report_path=f"{ANNOTATOR_DIR}/{relative_report}",
                copied_report_sha256=_sha256(payload),
                report_line_count=line_count,
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
            "Read each neutral report with line numbers starting at 1 and assess all seven dimensions.",
            "For assessed dimensions, provide a 0-4 score, concise rationale, and one or more report evidence lines.",
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
    _verify_coordinator_inventory(dataset, coordinator)
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
    _verify_report_copies(root, coordinator, assignment)
    profile = _completed_profile(responses)
    if responses.annotation_date is None:
        raise EvaluationInputError("annotation responses must declare annotation_date")
    response_by_id = {item.item_id: item for item in responses.responses}
    coordinator_by_id = {item.item_id: item for item in coordinator.items}
    annotations: list[ReportAnnotation] = []
    for item_id in coordinator_ids:
        mapped = coordinator_by_id[item_id]
        response = response_by_id[item_id]
        annotations.append(
            ReportAnnotation(
                group_id=mapped.group_id,
                report_id=mapped.report_id,
                report_sha256=mapped.report_sha256,
                dimensions=[_completed_dimension(item, mapped.report_line_count) for item in response.dimensions],
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


def _verify_report_copies(
    root: Path,
    coordinator: AnnotationPacketCoordinator,
    assignment: BlindedAnnotationAssignment,
) -> None:
    assignment_by_id = {item.item_id: item for item in assignment.items}
    for item in coordinator.items:
        copied = _resolve_inside(root, item.copied_report_path, "blinded report")
        payload = _read_limited(copied, MAX_PACKET_FILE_BYTES, "blinded report")
        if _sha256(payload) != item.copied_report_sha256 or item.copied_report_sha256 != item.report_sha256:
            raise EvaluationInputError(f"blinded report fingerprint changed: {item.item_id}")
        line_count = _line_count(payload, f"blinded report '{item.item_id}'")
        assignment_item = assignment_by_id[item.item_id]
        expected_assignment_path = item.copied_report_path.removeprefix(f"{ANNOTATOR_DIR}/")
        if (
            assignment_item.report_path != expected_assignment_path
            or line_count != item.report_line_count
            or assignment_item.report_line_count != line_count
        ):
            raise EvaluationInputError(f"blinded report metadata changed: {item.item_id}")


def _verify_coordinator_inventory(
    dataset: LoadedDatasetManifest,
    coordinator: AnnotationPacketCoordinator,
) -> None:
    expected = {
        (group.group_id, report.report_id): report.report_sha256
        for group in dataset.manifest.groups
        if group.split in {DatasetSplit.VALIDATION, DatasetSplit.TEST}
        for report in group.reports
    }
    actual = {(item.group_id, item.report_id): item.report_sha256 for item in coordinator.items}
    if len(actual) != len(coordinator.items) or actual != expected:
        raise EvaluationInputError("coordinator inventory must contain every validation/test report exactly once")


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


def _completed_dimension(item: DraftDimensionResponse, line_count: int) -> DimensionAnnotation:
    if item.status is None or not item.rationale.strip():
        raise EvaluationInputError(f"annotation dimension '{item.dimension}' is incomplete")
    if any(line < 1 or line > line_count for line in item.evidence_lines):
        raise EvaluationInputError(f"annotation evidence line is outside blinded report for '{item.dimension}'")
    try:
        return DimensionAnnotation(
            dimension=item.dimension,
            status=item.status,
            score=item.score,
            rationale=item.rationale,
            evidence_lines=item.evidence_lines,
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


def _line_count(payload: bytes, label: str) -> int:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvaluationInputError(f"{label} must be UTF-8 text") from exc
    line_count = len(text.splitlines())
    if line_count < 1:
        raise EvaluationInputError(f"{label} must contain at least one line")
    return line_count


def _write_json(path: Path, model: StrictModel) -> None:
    path.write_bytes((model.model_dump_json(indent=2) + "\n").encode("utf-8"))


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()
