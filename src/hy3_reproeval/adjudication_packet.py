"""Blind third-reviewer packets for resolving queued human disagreements."""

from __future__ import annotations

import secrets
from collections import defaultdict
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import __version__
from .agreement import AdjudicationItem, AdjudicationReason, analyze_annotation_agreement
from .annotation_packet import (
    ANNOTATOR_DIR,
    ASSIGNMENT_NAME,
    COORDINATOR_NAME,
    REPORTS_DIR,
    RESPONSES_NAME,
    SOURCES_DIR,
    AssignmentRubricDimension,
    BlindedAssignmentSource,
    CoordinatorSource,
    DraftAnnotatorProfile,
    DraftDimensionResponse,
    _completed_dimension,
    _file_sha256,
    _load_model,
    _numbered_text,
    _prepare_empty_output,
    _read_limited,
    _resolve_case_file,
    _resolve_inside,
    _safe_suffix,
    _sha256,
    _write_json,
)
from .annotations import (
    AnnotationBundle,
    AnnotationRound,
    AnnotationSource,
    AnnotatorProfile,
    DimensionAnnotation,
    ReportAnnotation,
    allowed_annotation_error_codes,
    load_validated_annotation_bundles,
    validate_annotation_bundles,
)
from .dataset import DatasetSplit, LoadedDatasetManifest, load_dataset_manifest, validate_dataset_manifest
from .errors import EvaluationInputError
from .evaluator import _rubric_sha256
from .freeze import verify_dataset_freeze
from .models import DimensionId, DimensionStatus, ErrorCode, StrictModel
from .rubric import load_public_rubric
from .validators import LoadedEvaluationCase, load_evaluation_case

GUIDE_NAME = "README_CN.md"


class DisputedDimension(StrictModel):
    dimension: DimensionId
    reasons: list[AdjudicationReason] = Field(min_length=1)


class AnonymousSourceEvidence(StrictModel):
    source_id: str = Field(pattern=r"^source-[0-9]{3}$")
    evidence_lines: list[int] = Field(min_length=1, max_length=16)


class AnonymousDimensionAssessment(StrictModel):
    dimension: DimensionId
    status: DimensionStatus
    score: int | None = Field(default=None, ge=0, le=4)
    rationale: str = Field(min_length=1, max_length=2000)
    evidence_lines: list[int] = Field(default_factory=list, max_length=16)
    source_evidence: list[AnonymousSourceEvidence] = Field(default_factory=list, max_length=8)
    error_codes: list[ErrorCode] = Field(default_factory=list)


class AnonymousParentAssessment(StrictModel):
    assessment_id: str = Field(pattern=r"^parent-[0-9]{3}$")
    dimensions: list[AnonymousDimensionAssessment] = Field(min_length=1, max_length=7)


class AdjudicationAssignmentItem(StrictModel):
    item_id: str = Field(pattern=r"^item-[0-9]{3}$")
    report_path: str = Field(pattern=r"^reports/item-[0-9]{3}\.[A-Za-z0-9]+$")
    report_line_count: int = Field(ge=1)
    sources: list[BlindedAssignmentSource] = Field(min_length=1)
    disputed_dimensions: list[DisputedDimension] = Field(min_length=1, max_length=7)
    parent_assessments: list[AnonymousParentAssessment] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_dispute_inventory(self) -> AdjudicationAssignmentItem:
        disputed = [item.dimension for item in self.disputed_dimensions]
        if len(disputed) != len(set(disputed)):
            raise ValueError("adjudication disputed dimensions must be unique")
        aliases = [item.assessment_id for item in self.parent_assessments]
        if len(aliases) != len(set(aliases)):
            raise ValueError("anonymous parent assessment IDs must be unique")
        if any({item.dimension for item in parent.dimensions} != set(disputed) for parent in self.parent_assessments):
            raise ValueError("each anonymous parent assessment must cover every disputed dimension")
        return self


class BlindedAdjudicationAssignment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    assignment_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    annotation_bundle_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    adjudicator_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    dataset_id: str
    dataset_version: str
    dataset_freeze_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    instructions: list[str] = Field(min_length=1)
    rubric: list[AssignmentRubricDimension] = Field(min_length=7, max_length=7)
    items: list[AdjudicationAssignmentItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> BlindedAdjudicationAssignment:
        if {item.dimension for item in self.rubric} != set(DimensionId):
            raise ValueError("adjudication assignment Rubric must contain every public dimension")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("adjudication assignment item IDs must be unique")
        return self


class AdjudicationDraftItemResponse(StrictModel):
    item_id: str = Field(pattern=r"^item-[0-9]{3}$")
    dimensions: list[DraftDimensionResponse] = Field(min_length=1, max_length=7)

    @model_validator(mode="after")
    def validate_dimensions(self) -> AdjudicationDraftItemResponse:
        dimensions = [item.dimension for item in self.dimensions]
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("adjudication response dimensions must be unique")
        return self


class DraftAdjudicationResponses(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    assignment_id: str
    annotation_bundle_id: str
    adjudicator_id: str
    annotation_date: str | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    annotator_profile: DraftAnnotatorProfile
    responses: list[AdjudicationDraftItemResponse] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_items(self) -> DraftAdjudicationResponses:
        item_ids = [item.item_id for item in self.responses]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("adjudication response item IDs must be unique")
        return self


class AdjudicationCoordinatorParent(StrictModel):
    assessment_id: str = Field(pattern=r"^parent-[0-9]{3}$")
    annotation_bundle_id: str
    annotation_bundle_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    annotator_id: str


class AdjudicationCoordinatorItem(StrictModel):
    item_id: str = Field(pattern=r"^item-[0-9]{3}$")
    group_id: str
    report_id: str
    report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    copied_report_path: str = Field(pattern=r"^annotator/reports/item-[0-9]{3}\.[A-Za-z0-9]+$")
    copied_report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    report_line_count: int = Field(ge=1)
    sources: list[CoordinatorSource] = Field(min_length=1)
    disputed_dimensions: list[DisputedDimension] = Field(min_length=1, max_length=7)


class AdjudicationPacketCoordinator(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    assignment_id: str
    annotation_bundle_id: str
    adjudicator_id: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    assignment_path: Literal["annotator/assignment.json"] = "annotator/assignment.json"
    assignment_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    guide_path: Literal["annotator/README_CN.md"] = "annotator/README_CN.md"
    guide_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    responses_path: Literal["annotator/responses.json"] = "annotator/responses.json"
    parent_bundles: list[AdjudicationCoordinatorParent] = Field(min_length=2)
    item_count: int = Field(ge=1)
    items: list[AdjudicationCoordinatorItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> AdjudicationPacketCoordinator:
        if self.item_count != len(self.items):
            raise ValueError("adjudication coordinator item_count does not match inventory")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("adjudication coordinator item IDs must be unique")
        if len({item.report_id for item in self.items}) != len(self.items):
            raise ValueError("adjudication coordinator report IDs must be unique")
        parent_ids = [item.annotation_bundle_id for item in self.parent_bundles]
        aliases = [item.assessment_id for item in self.parent_bundles]
        if len(parent_ids) != len(set(parent_ids)) or len(aliases) != len(set(aliases)):
            raise ValueError("adjudication coordinator parent identities must be unique")
        return self


class AdjudicationPacketResult(StrictModel):
    output_root: str
    assignment_id: str
    adjudicator_id: str
    disputed_report_count: int = Field(ge=1)
    disputed_dimension_count: int = Field(ge=1)
    annotator_directory: str
    coordinator_manifest: str


def prepare_adjudication_packet(
    dataset_path: str | Path,
    dataset_freeze_path: str | Path,
    bundle_paths: list[str | Path],
    output_dir: str | Path,
    *,
    assignment_id: str,
    adjudicator_id: str,
    annotation_bundle_id: str,
) -> AdjudicationPacketResult:
    """Create a blind packet containing only disputes from two independent human Bundles."""

    dataset, freeze, rubric, rubric_sha256, bundles, bundle_hashes = _load_two_parents(
        dataset_path, dataset_freeze_path, bundle_paths
    )
    agreement = analyze_annotation_agreement(
        dataset_path,
        bundle_paths,
        dataset_freeze_path=dataset_freeze_path,
    )
    if not agreement.agreement_ready:
        raise EvaluationInputError("adjudication packet requires benchmark-ready independent annotations")
    if not agreement.adjudication_items:
        raise EvaluationInputError("independent annotations contain no queued disputes")
    if adjudicator_id in {bundle.annotator.annotator_id for bundle in bundles}:
        raise EvaluationInputError("adjudicator must be distinct from both parent annotators")

    output_root = _prepare_empty_output(output_dir)
    annotator_root = output_root / ANNOTATOR_DIR
    (annotator_root / REPORTS_DIR).mkdir(parents=True)
    (annotator_root / SOURCES_DIR).mkdir()

    randomized_parents = sorted(bundles, key=lambda item: item.annotation_bundle_id)
    secrets.SystemRandom().shuffle(randomized_parents)
    alias_by_annotator = {
        bundle.annotator.annotator_id: f"parent-{number:03d}"
        for number, bundle in enumerate(randomized_parents, start=1)
    }
    parent_annotations = {
        bundle.annotator.annotator_id: {item.report_id: item for item in bundle.annotations} for bundle in bundles
    }
    disputes_by_report = _group_disputes(agreement.adjudication_items)
    report_inventory = _dataset_report_inventory(dataset)
    report_ids = sorted(disputes_by_report)
    secrets.SystemRandom().shuffle(report_ids)

    assignment_items: list[AdjudicationAssignmentItem] = []
    coordinator_items: list[AdjudicationCoordinatorItem] = []
    response_items: list[AdjudicationDraftItemResponse] = []
    for number, report_id in enumerate(report_ids, start=1):
        group_id, report_sha256, loaded = report_inventory[report_id]
        item_id = f"item-{number:03d}"
        report_payload = _read_limited(loaded.report_path, 16 * 1024 * 1024, "adjudication report")
        if _sha256(report_payload) != report_sha256:
            raise EvaluationInputError(f"adjudication source report hash changed: {report_id}")
        numbered_report, report_line_count = _numbered_text(report_payload, f"adjudication report '{report_id}'")
        report_suffix = _safe_suffix(loaded.report_path)
        relative_report = f"{REPORTS_DIR}/{item_id}{report_suffix}"
        (annotator_root / relative_report).write_bytes(numbered_report)

        assignment_sources: list[BlindedAssignmentSource] = []
        coordinator_sources: list[CoordinatorSource] = []
        neutral_by_artifact: dict[str, str] = {}
        for source_number, artifact in enumerate(
            sorted(loaded.case.artifacts, key=lambda item: item.artifact_id), start=1
        ):
            source_id = f"source-{source_number:03d}"
            neutral_by_artifact[artifact.artifact_id] = source_id
            source_path = _resolve_case_file(loaded.root, artifact.path, "adjudication source material")
            source_payload = _read_limited(source_path, 16 * 1024 * 1024, "adjudication source material")
            source_sha256 = _sha256(source_payload)
            if source_sha256 != artifact.sha256.upper():
                raise EvaluationInputError(f"adjudication source material hash changed: {artifact.artifact_id}")
            numbered_source, source_line_count = _numbered_text(
                source_payload, f"adjudication source material '{artifact.artifact_id}'"
            )
            source_suffix = _safe_suffix(source_path)
            relative_source = f"{SOURCES_DIR}/{item_id}-{source_id}{source_suffix}"
            (annotator_root / relative_source).write_bytes(numbered_source)
            copied_source_sha256 = _sha256(numbered_source)
            assignment_sources.append(
                BlindedAssignmentSource(
                    source_id=source_id,
                    source_path=relative_source,
                    source_sha256=source_sha256,
                    numbered_source_sha256=copied_source_sha256,
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
                    copied_source_sha256=copied_source_sha256,
                    source_line_count=source_line_count,
                )
            )

        disputed = disputes_by_report[report_id]
        parent_assessments = _anonymous_parent_assessments(
            randomized_parents,
            parent_annotations,
            report_id,
            disputed,
            alias_by_annotator,
            neutral_by_artifact,
        )
        assignment_items.append(
            AdjudicationAssignmentItem(
                item_id=item_id,
                report_path=relative_report,
                report_line_count=report_line_count,
                sources=assignment_sources,
                disputed_dimensions=disputed,
                parent_assessments=parent_assessments,
            )
        )
        coordinator_items.append(
            AdjudicationCoordinatorItem(
                item_id=item_id,
                group_id=group_id,
                report_id=report_id,
                report_sha256=report_sha256,
                copied_report_path=f"{ANNOTATOR_DIR}/{relative_report}",
                copied_report_sha256=_sha256(numbered_report),
                report_line_count=report_line_count,
                sources=coordinator_sources,
                disputed_dimensions=disputed,
            )
        )
        response_items.append(
            AdjudicationDraftItemResponse(
                item_id=item_id,
                dimensions=[DraftDimensionResponse(dimension=item.dimension) for item in disputed],
            )
        )

    assignment = BlindedAdjudicationAssignment(
        assignment_id=assignment_id,
        annotation_bundle_id=annotation_bundle_id,
        adjudicator_id=adjudicator_id,
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        dataset_freeze_sha256=freeze.freeze_sha256,
        rubric_version=rubric.rubric_version,
        rubric_sha256=rubric_sha256,
        instructions=[
            "Resolve only the listed disputed dimensions using the report, source material, Rubric, "
            "and two anonymous parent assessments.",
            "Do not seek quality tiers, mutation labels, system scores, or the identities of the parent reviewers.",
            "Parent assessments are evidence traces, not votes; make and justify your own final decision.",
            "Every displayed line uses an L000001-style identifier; cite report lines and source lines where required.",
            "Set independent_annotation to false because adjudication intentionally exposes "
            "anonymous parent assessments.",
            "Complete every requested response dimension, profile declaration, and annotation_date before return.",
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
    responses = DraftAdjudicationResponses(
        assignment_id=assignment_id,
        annotation_bundle_id=annotation_bundle_id,
        adjudicator_id=adjudicator_id,
        annotator_profile=DraftAnnotatorProfile(),
        responses=response_items,
    )
    assignment_path = annotator_root / ASSIGNMENT_NAME
    guide_path = annotator_root / GUIDE_NAME
    _write_json(assignment_path, assignment)
    _write_json(annotator_root / RESPONSES_NAME, responses)
    guide_path.write_bytes(_adjudicator_guide())
    coordinator = AdjudicationPacketCoordinator(
        engine_version=__version__,
        assignment_id=assignment_id,
        annotation_bundle_id=annotation_bundle_id,
        adjudicator_id=adjudicator_id,
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        dataset_manifest_sha256=dataset.manifest_sha256,
        dataset_freeze_sha256=freeze.freeze_sha256,
        rubric_version=rubric.rubric_version,
        rubric_sha256=rubric_sha256,
        assignment_sha256=_file_sha256(assignment_path),
        guide_sha256=_file_sha256(guide_path),
        parent_bundles=[
            AdjudicationCoordinatorParent(
                assessment_id=alias_by_annotator[bundle.annotator.annotator_id],
                annotation_bundle_id=bundle.annotation_bundle_id,
                annotation_bundle_sha256=bundle_hashes[bundle.annotation_bundle_id],
                annotator_id=bundle.annotator.annotator_id,
            )
            for bundle in randomized_parents
        ],
        item_count=len(coordinator_items),
        items=coordinator_items,
    )
    _write_json(output_root / COORDINATOR_NAME, coordinator)
    return AdjudicationPacketResult(
        output_root=output_root.as_posix(),
        assignment_id=assignment_id,
        adjudicator_id=adjudicator_id,
        disputed_report_count=len(coordinator_items),
        disputed_dimension_count=sum(len(item.disputed_dimensions) for item in coordinator_items),
        annotator_directory=annotator_root.as_posix(),
        coordinator_manifest=(output_root / COORDINATOR_NAME).as_posix(),
    )


def finalize_adjudication_packet(
    dataset_path: str | Path,
    dataset_freeze_path: str | Path,
    bundle_paths: list[str | Path],
    packet_dir: str | Path,
    output_path: str | Path,
) -> AnnotationBundle:
    """Verify one completed adjudication packet and emit a parent-bound human Bundle."""

    dataset, freeze, rubric, rubric_sha256, bundles, bundle_hashes = _load_two_parents(
        dataset_path, dataset_freeze_path, bundle_paths
    )
    agreement = analyze_annotation_agreement(
        dataset_path,
        bundle_paths,
        dataset_freeze_path=dataset_freeze_path,
    )
    root = Path(packet_dir).expanduser().resolve()
    coordinator = _load_model(root / COORDINATOR_NAME, AdjudicationPacketCoordinator, "adjudication coordinator")
    assignment_path = _resolve_inside(root, coordinator.assignment_path, "adjudication assignment")
    guide_path = _resolve_inside(root, coordinator.guide_path, "adjudicator guide")
    responses_path = _resolve_inside(root, coordinator.responses_path, "adjudication responses")
    assignment = _load_model(assignment_path, BlindedAdjudicationAssignment, "blinded adjudication assignment")
    responses = _load_model(responses_path, DraftAdjudicationResponses, "adjudication responses")

    expected_identity = (
        dataset.manifest.dataset_id,
        dataset.manifest.dataset_version,
        dataset.manifest_sha256,
        freeze.freeze_sha256,
        rubric.rubric_version,
        rubric_sha256,
    )
    actual_identity = (
        coordinator.dataset_id,
        coordinator.dataset_version,
        coordinator.dataset_manifest_sha256,
        coordinator.dataset_freeze_sha256,
        coordinator.rubric_version,
        coordinator.rubric_sha256,
    )
    if actual_identity != expected_identity:
        raise EvaluationInputError("adjudication packet uses a different Dataset, Freeze, or Rubric")
    assignment_identity = (
        assignment.dataset_id,
        assignment.dataset_version,
        assignment.dataset_freeze_sha256,
        assignment.rubric_version,
        assignment.rubric_sha256,
    )
    if assignment_identity != (
        dataset.manifest.dataset_id,
        dataset.manifest.dataset_version,
        freeze.freeze_sha256,
        rubric.rubric_version,
        rubric_sha256,
    ):
        raise EvaluationInputError("adjudication assignment uses a different Dataset, Freeze, or Rubric")
    expected_parents = {
        bundle.annotation_bundle_id: (bundle_hashes[bundle.annotation_bundle_id], bundle.annotator.annotator_id)
        for bundle in bundles
    }
    actual_parents = {
        parent.annotation_bundle_id: (parent.annotation_bundle_sha256, parent.annotator_id)
        for parent in coordinator.parent_bundles
    }
    if actual_parents != expected_parents:
        raise EvaluationInputError("adjudication parent Bundle identity or fingerprint changed")
    if coordinator.adjudicator_id in {bundle.annotator.annotator_id for bundle in bundles}:
        raise EvaluationInputError("adjudicator must be distinct from both parent annotators")
    if _file_sha256(assignment_path) != coordinator.assignment_sha256:
        raise EvaluationInputError("blinded adjudication assignment fingerprint changed")
    if guide_path.read_bytes() != _adjudicator_guide() or _file_sha256(guide_path) != coordinator.guide_sha256:
        raise EvaluationInputError("adjudicator guide fingerprint changed")
    shared = (coordinator.assignment_id, coordinator.annotation_bundle_id, coordinator.adjudicator_id)
    if shared != (assignment.assignment_id, assignment.annotation_bundle_id, assignment.adjudicator_id):
        raise EvaluationInputError("adjudication assignment identity does not match coordinator")
    if shared != (responses.assignment_id, responses.annotation_bundle_id, responses.adjudicator_id):
        raise EvaluationInputError("adjudication response identity does not match coordinator")

    expected_disputes = _group_disputes(agreement.adjudication_items)
    if not expected_disputes:
        raise EvaluationInputError("parent annotations no longer contain queued disputes")
    coordinator_by_report = {item.report_id: item for item in coordinator.items}
    if set(coordinator_by_report) != set(expected_disputes):
        raise EvaluationInputError("adjudication coordinator dispute inventory changed")
    for report_id, item in coordinator_by_report.items():
        if item.disputed_dimensions != expected_disputes[report_id]:
            raise EvaluationInputError(f"adjudication dispute inventory changed: {report_id}")

    loaded_by_item = _verify_adjudication_inventory(dataset, coordinator)
    _verify_adjudication_copies(root, coordinator, assignment, loaded_by_item)
    _verify_parent_assessments(assignment, coordinator, bundles)
    assignment_ids = [item.item_id for item in assignment.items]
    coordinator_ids = [item.item_id for item in coordinator.items]
    response_ids = [item.item_id for item in responses.responses]
    if assignment_ids != coordinator_ids or set(response_ids) != set(coordinator_ids):
        raise EvaluationInputError("adjudication packet item inventories do not match")
    profile = _completed_adjudicator_profile(responses)
    if responses.annotation_date is None:
        raise EvaluationInputError("adjudication responses must declare annotation_date")

    responses_by_id = {item.item_id: item for item in responses.responses}
    annotations: list[ReportAnnotation] = []
    for mapped in coordinator.items:
        response = responses_by_id[mapped.item_id]
        disputed_dimensions = [item.dimension for item in mapped.disputed_dimensions]
        if {item.dimension for item in response.dimensions} != set(disputed_dimensions):
            raise EvaluationInputError(f"adjudication response dimensions changed: {mapped.item_id}")
        response_by_dimension = {item.dimension: item for item in response.dimensions}
        source_inventory = {
            source.source_id: (source.artifact_id, source.source_line_count) for source in mapped.sources
        }
        dimensions: list[DimensionAnnotation] = []
        for dimension in DimensionId:
            if dimension in response_by_dimension:
                dimensions.append(
                    _completed_dimension(response_by_dimension[dimension], mapped.report_line_count, source_inventory)
                )
            else:
                dimensions.append(
                    DimensionAnnotation(
                        dimension=dimension,
                        status=DimensionStatus.INSUFFICIENT_EVIDENCE,
                        rationale="Not part of this adjudication assignment; consensus uses the independent labels.",
                    )
                )
        annotations.append(
            ReportAnnotation(
                group_id=mapped.group_id,
                report_id=mapped.report_id,
                report_sha256=mapped.report_sha256,
                dimensions=dimensions,
            )
        )

    parent_ids = sorted(expected_parents)
    bundle = AnnotationBundle(
        annotation_bundle_id=coordinator.annotation_bundle_id,
        annotation_source=AnnotationSource.HUMAN,
        annotation_round=AnnotationRound.ADJUDICATION,
        annotation_date=responses.annotation_date,
        dataset_id=coordinator.dataset_id,
        dataset_version=coordinator.dataset_version,
        dataset_manifest_sha256=coordinator.dataset_manifest_sha256,
        dataset_freeze_sha256=coordinator.dataset_freeze_sha256,
        rubric_version=coordinator.rubric_version,
        rubric_sha256=coordinator.rubric_sha256,
        annotator=profile,
        parent_annotation_bundle_ids=parent_ids,
        parent_annotation_bundle_sha256={parent_id: expected_parents[parent_id][0] for parent_id in parent_ids},
        annotations=annotations,
    )
    target = Path(output_path).expanduser().resolve()
    if target.exists():
        raise EvaluationInputError(f"adjudication Bundle output already exists: {target.as_posix()}")
    if not target.parent.is_dir():
        raise EvaluationInputError(f"adjudication Bundle parent directory does not exist: {target.parent.as_posix()}")
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    try:
        _write_json(temporary, bundle)
        validate_annotation_bundles(
            dataset_path,
            [*bundle_paths, temporary],
            dataset_freeze_path=dataset_freeze_path,
        )
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return bundle


def _load_two_parents(
    dataset_path: str | Path,
    dataset_freeze_path: str | Path,
    bundle_paths: list[str | Path],
) -> tuple[LoadedDatasetManifest, object, object, str, list[AnnotationBundle], dict[str, str]]:
    if len(bundle_paths) != 2:
        raise EvaluationInputError("adjudication packets require exactly two parent Bundles")
    validate_dataset_manifest(dataset_path)
    dataset = load_dataset_manifest(dataset_path)
    freeze = verify_dataset_freeze(dataset_freeze_path, dataset_path)
    rubric = load_public_rubric()
    rubric_sha256 = _rubric_sha256(rubric)
    validation = validate_annotation_bundles(
        dataset_path,
        bundle_paths,
        dataset_freeze_path=dataset_freeze_path,
    )
    bundles = load_validated_annotation_bundles(bundle_paths, validation)
    if any(
        bundle.annotation_source is not AnnotationSource.HUMAN
        or bundle.annotation_round is not AnnotationRound.INDEPENDENT
        for bundle in bundles
    ):
        raise EvaluationInputError("adjudication parents must be independent human Bundles")
    hashes = {item.annotation_bundle_id: item.annotation_bundle_sha256 for item in validation.bundles}
    return dataset, freeze, rubric, rubric_sha256, bundles, hashes


def _group_disputes(items: list[AdjudicationItem]) -> dict[str, list[DisputedDimension]]:
    grouped: dict[str, dict[DimensionId, set[AdjudicationReason]]] = defaultdict(lambda: defaultdict(set))
    for item in items:
        grouped[item.report_id][item.dimension].add(item.reason)
    return {
        report_id: [
            DisputedDimension(dimension=dimension, reasons=sorted(reasons, key=lambda reason: reason.value))
            for dimension, reasons in sorted(dimensions.items(), key=lambda item: item[0].value)
        ]
        for report_id, dimensions in sorted(grouped.items())
    }


def _dataset_report_inventory(
    dataset: LoadedDatasetManifest,
) -> dict[str, tuple[str, str, LoadedEvaluationCase]]:
    return {
        report.report_id: (
            group.group_id,
            report.report_sha256,
            load_evaluation_case(dataset.resolve(report.case_path, "evaluation case")),
        )
        for group in dataset.manifest.groups
        if group.split in {DatasetSplit.VALIDATION, DatasetSplit.TEST}
        for report in group.reports
    }


def _anonymous_parent_assessments(
    parents: list[AnnotationBundle],
    annotations: dict[str, dict[str, ReportAnnotation]],
    report_id: str,
    disputes: list[DisputedDimension],
    alias_by_annotator: dict[str, str],
    neutral_by_artifact: dict[str, str],
) -> list[AnonymousParentAssessment]:
    disputed_dimensions = [item.dimension for item in disputes]
    results: list[AnonymousParentAssessment] = []
    for parent in parents:
        annotator_id = parent.annotator.annotator_id
        report = annotations[annotator_id][report_id]
        by_dimension = {item.dimension: item for item in report.dimensions}
        results.append(
            AnonymousParentAssessment(
                assessment_id=alias_by_annotator[annotator_id],
                dimensions=[
                    _anonymous_dimension(by_dimension[dimension], neutral_by_artifact)
                    for dimension in disputed_dimensions
                ],
            )
        )
    return results


def _anonymous_dimension(
    annotation: DimensionAnnotation,
    neutral_by_artifact: dict[str, str],
) -> AnonymousDimensionAssessment:
    try:
        source_evidence = [
            AnonymousSourceEvidence(
                source_id=neutral_by_artifact[reference.source_id],
                evidence_lines=reference.evidence_lines,
            )
            for reference in annotation.source_evidence
        ]
    except KeyError as exc:  # pragma: no cover - parent validation should reject unknown sources
        raise EvaluationInputError(f"parent annotation references unknown source: {exc.args[0]}") from exc
    return AnonymousDimensionAssessment(
        dimension=annotation.dimension,
        status=annotation.status,
        score=annotation.score,
        rationale=annotation.rationale,
        evidence_lines=annotation.evidence_lines,
        source_evidence=source_evidence,
        error_codes=annotation.error_codes,
    )


def _verify_adjudication_inventory(
    dataset: LoadedDatasetManifest,
    coordinator: AdjudicationPacketCoordinator,
) -> dict[str, LoadedEvaluationCase]:
    inventory = _dataset_report_inventory(dataset)
    loaded: dict[str, LoadedEvaluationCase] = {}
    for item in coordinator.items:
        expected = inventory.get(item.report_id)
        if expected is None:
            raise EvaluationInputError(f"adjudication coordinator references unknown report: {item.report_id}")
        group_id, report_sha256, evaluation_case = expected
        if item.group_id != group_id or item.report_sha256 != report_sha256:
            raise EvaluationInputError(f"adjudication coordinator report fingerprint changed: {item.item_id}")
        artifacts = sorted(evaluation_case.case.artifacts, key=lambda artifact: artifact.artifact_id)
        if len(artifacts) != len(item.sources):
            raise EvaluationInputError(f"adjudication coordinator source inventory changed: {item.item_id}")
        for source_number, (source, artifact) in enumerate(zip(item.sources, artifacts, strict=True), start=1):
            if (
                source.source_id != f"source-{source_number:03d}"
                or source.artifact_id != artifact.artifact_id
                or source.artifact_path != artifact.path
                or source.source_sha256 != artifact.sha256.upper()
            ):
                raise EvaluationInputError(f"adjudication coordinator source inventory changed: {item.item_id}")
        loaded[item.item_id] = evaluation_case
    return loaded


def _verify_adjudication_copies(
    root: Path,
    coordinator: AdjudicationPacketCoordinator,
    assignment: BlindedAdjudicationAssignment,
    loaded_by_item: dict[str, LoadedEvaluationCase],
) -> None:
    assignment_by_id = {item.item_id: item for item in assignment.items}
    if set(assignment_by_id) != {item.item_id for item in coordinator.items}:
        raise EvaluationInputError("adjudication assignment inventory changed")
    for item in coordinator.items:
        assigned = assignment_by_id[item.item_id]
        loaded = loaded_by_item[item.item_id]
        source_report = _read_limited(loaded.report_path, 16 * 1024 * 1024, "adjudication report")
        expected_report, line_count = _numbered_text(source_report, f"adjudication report '{item.report_id}'")
        copied_report = _read_limited(
            _resolve_inside(root, item.copied_report_path, "blinded adjudication report"),
            16 * 1024 * 1024,
            "blinded adjudication report",
        )
        if (
            copied_report != expected_report
            or _sha256(copied_report) != item.copied_report_sha256
            or assigned.report_line_count != line_count
            or item.report_line_count != line_count
            or assigned.report_path != item.copied_report_path.removeprefix(f"{ANNOTATOR_DIR}/")
        ):
            raise EvaluationInputError(f"blinded adjudication report fingerprint changed: {item.item_id}")
        assigned_sources = {source.source_id: source for source in assigned.sources}
        if set(assigned_sources) != {source.source_id for source in item.sources}:
            raise EvaluationInputError(f"blinded adjudication source inventory changed: {item.item_id}")
        for source in item.sources:
            original_path = _resolve_case_file(loaded.root, source.artifact_path, "adjudication source material")
            original = _read_limited(original_path, 16 * 1024 * 1024, "adjudication source material")
            expected_source, source_line_count = _numbered_text(
                original, f"adjudication source material '{source.artifact_id}'"
            )
            copied = _read_limited(
                _resolve_inside(root, source.copied_source_path, "blinded adjudication source"),
                16 * 1024 * 1024,
                "blinded adjudication source",
            )
            assigned_source = assigned_sources[source.source_id]
            if (
                _sha256(original) != source.source_sha256
                or copied != expected_source
                or _sha256(copied) != source.copied_source_sha256
                or source.source_line_count != source_line_count
                or assigned_source.source_path != source.copied_source_path.removeprefix(f"{ANNOTATOR_DIR}/")
                or assigned_source.source_sha256 != source.source_sha256
                or assigned_source.numbered_source_sha256 != source.copied_source_sha256
                or assigned_source.source_line_count != source_line_count
            ):
                raise EvaluationInputError(f"blinded adjudication source fingerprint changed: {item.item_id}")


def _verify_parent_assessments(
    assignment: BlindedAdjudicationAssignment,
    coordinator: AdjudicationPacketCoordinator,
    bundles: list[AnnotationBundle],
) -> None:
    parent_by_id = {bundle.annotation_bundle_id: bundle for bundle in bundles}
    ordered_parents = [parent_by_id[parent.annotation_bundle_id] for parent in coordinator.parent_bundles]
    aliases = {parent.annotator_id: parent.assessment_id for parent in coordinator.parent_bundles}
    parent_annotations = {
        bundle.annotator.annotator_id: {item.report_id: item for item in bundle.annotations} for bundle in bundles
    }
    coordinator_by_item = {item.item_id: item for item in coordinator.items}
    for assigned in assignment.items:
        mapped = coordinator_by_item[assigned.item_id]
        neutral_by_artifact = {source.artifact_id: source.source_id for source in mapped.sources}
        expected = _anonymous_parent_assessments(
            ordered_parents,
            parent_annotations,
            mapped.report_id,
            mapped.disputed_dimensions,
            aliases,
            neutral_by_artifact,
        )
        if assigned.disputed_dimensions != mapped.disputed_dimensions or assigned.parent_assessments != expected:
            raise EvaluationInputError(f"anonymous parent assessment changed: {assigned.item_id}")


def _completed_adjudicator_profile(responses: DraftAdjudicationResponses) -> AnnotatorProfile:
    draft = responses.annotator_profile
    declarations = (
        draft.independent_annotation,
        draft.blind_to_system_scores,
        draft.rubric_training_completed,
        draft.conflict_of_interest_disclosed,
        draft.conflict_of_interest_present,
    )
    if not draft.expertise_description.strip() or any(value is None for value in declarations):
        raise EvaluationInputError("adjudication responses must complete every annotator profile field")
    if (
        draft.independent_annotation
        or not draft.blind_to_system_scores
        or not draft.rubric_training_completed
        or not draft.conflict_of_interest_disclosed
        or draft.conflict_of_interest_present
    ):
        raise EvaluationInputError(
            "adjudication requires a parent-aware, trained, system-score-blind, conflict-free declaration"
        )
    return AnnotatorProfile(
        annotator_id=responses.adjudicator_id,
        expertise_description=draft.expertise_description,
        independent_annotation=False,
        blind_to_system_scores=True,
        rubric_training_completed=True,
        conflict_of_interest_disclosed=True,
        conflict_of_interest_present=False,
    )


def _adjudicator_guide() -> bytes:
    return files("hy3_reproeval.data").joinpath("adjudicator_guide_cn.md").read_bytes()
