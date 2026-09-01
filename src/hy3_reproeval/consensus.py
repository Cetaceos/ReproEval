"""Fail-closed aggregation of independent and adjudicated human annotations."""

from __future__ import annotations

import statistics
from collections import defaultdict
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import __version__
from .agreement import AdjudicationItem, AnnotationAgreementResult, analyze_annotation_agreement
from .annotations import (
    AnnotationBundle,
    AnnotationRound,
    DimensionAnnotation,
    ReportAnnotation,
    is_benchmark_eligible,
    load_validated_annotation_bundles,
)
from .dataset import DatasetSplit, load_dataset_manifest
from .errors import EvaluationInputError
from .models import DimensionId, DimensionStatus, ErrorCode, StrictModel
from .rubric import RubricDefinition, load_public_rubric


class ConsensusSource(StrEnum):
    INDEPENDENT_AGGREGATE = "independent_aggregate"
    ADJUDICATION = "adjudication"


class ConsensusDimension(StrictModel):
    dimension: DimensionId
    status: DimensionStatus
    score: float | None = Field(default=None, ge=0, le=4)
    error_codes: list[ErrorCode]
    source: ConsensusSource
    independent_bundle_ids: list[str] = Field(min_length=2)
    adjudication_bundle_id: str | None = None

    @model_validator(mode="after")
    def validate_consensus_source(self) -> ConsensusDimension:
        if self.status is DimensionStatus.ASSESSED and self.score is None:
            raise ValueError("assessed consensus dimension requires a score")
        if self.status is DimensionStatus.INSUFFICIENT_EVIDENCE and self.score is not None:
            raise ValueError("insufficient consensus dimension cannot define a score")
        if self.source is ConsensusSource.ADJUDICATION and self.adjudication_bundle_id is None:
            raise ValueError("adjudicated consensus dimension requires an adjudication Bundle ID")
        if self.source is ConsensusSource.INDEPENDENT_AGGREGATE and self.adjudication_bundle_id is not None:
            raise ValueError("independent aggregate cannot define an adjudication Bundle ID")
        return self


class ConsensusReport(StrictModel):
    group_id: str
    report_id: str
    split: DatasetSplit
    report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    assessed_weight: float = Field(ge=0, le=1)
    human_score: float | None = Field(default=None, ge=0, le=100)
    dimensions: list[ConsensusDimension] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def require_all_dimensions(self) -> ConsensusReport:
        dimensions = [item.dimension for item in self.dimensions]
        if set(dimensions) != set(DimensionId) or len(dimensions) != len(set(dimensions)):
            raise ValueError("consensus report must contain every Rubric dimension exactly once")
        return self


class UnresolvedAdjudicationItem(StrictModel):
    report_id: str
    dimension: DimensionId
    reasons: list[str] = Field(min_length=1)
    required_parent_bundle_ids: list[str] = Field(min_length=2)


class AnnotationConsensusResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_sha256: str | None = Field(default=None, pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    agreement: AnnotationAgreementResult
    consensus_ready: bool
    target_report_count: int = Field(ge=0)
    consensus_report_count: int = Field(ge=0)
    adjudication_required_item_count: int = Field(ge=0)
    adjudication_resolved_item_count: int = Field(ge=0)
    unresolved_adjudication_item_count: int = Field(ge=0)
    used_adjudication_bundle_ids: list[str]
    unresolved_adjudication_items: list[UnresolvedAdjudicationItem]
    reports: list[ConsensusReport]
    warnings: list[str] = Field(default_factory=list)


def finalize_annotation_consensus(
    dataset_path: str | Path,
    bundle_paths: list[str | Path],
    *,
    dataset_freeze_path: str | Path | None = None,
) -> AnnotationConsensusResult:
    """Resolve queued disagreements only through explicitly parent-bound adjudication Bundles."""

    agreement = analyze_annotation_agreement(
        dataset_path,
        bundle_paths,
        dataset_freeze_path=dataset_freeze_path,
    )
    bundles = load_validated_annotation_bundles(bundle_paths, agreement.annotation_validation)
    dataset = load_dataset_manifest(dataset_path)
    rubric = load_public_rubric()
    inventory = {
        report.report_id: (group.group_id, group.split, report.report_sha256)
        for group in dataset.manifest.groups
        for report in group.reports
    }
    independent = [bundle for bundle in bundles if bundle.annotation_round is AnnotationRound.INDEPENDENT]
    adjudications = [bundle for bundle in bundles if bundle.annotation_round is AnnotationRound.ADJUDICATION]
    independent_bundle_by_annotator = {
        bundle.annotator.annotator_id: bundle.annotation_bundle_id for bundle in independent
    }
    eligible_by_report: dict[str, dict[str, tuple[str, ReportAnnotation]]] = defaultdict(dict)
    for bundle in independent:
        for annotation in bundle.annotations:
            split = inventory[annotation.report_id][1]
            if is_benchmark_eligible(bundle, split):
                eligible_by_report[annotation.report_id][bundle.annotator.annotator_id] = (
                    bundle.annotation_bundle_id,
                    annotation,
                )

    disputes = _disputes_by_dimension(agreement.adjudication_items)
    _reject_adjudication_for_non_disputed_reports(adjudications, disputes)
    used_adjudications: set[str] = set()
    unresolved: list[UnresolvedAdjudicationItem] = []
    reports: list[ConsensusReport] = []
    target_reports = {
        report_id
        for report_id, (_, split, _) in inventory.items()
        if split in {DatasetSplit.VALIDATION, DatasetSplit.TEST}
    }
    for report_id in sorted(target_reports):
        annotations_by_annotator = eligible_by_report.get(report_id, {})
        if len(annotations_by_annotator) < 2:
            continue
        independent_bundle_ids = sorted(bundle_id for bundle_id, _ in annotations_by_annotator.values())
        dimensions_by_annotator = {
            annotator_id: _dimensions_by_id(annotation)
            for annotator_id, (_, annotation) in annotations_by_annotator.items()
        }
        consensus_dimensions: list[ConsensusDimension] = []
        report_unresolved = False
        for dimension in DimensionId:
            key = (report_id, dimension)
            dimension_disputes = disputes.get(key, [])
            annotations = [items[dimension] for items in dimensions_by_annotator.values()]
            if dimension_disputes:
                required_parent_ids = sorted(
                    {
                        independent_bundle_by_annotator[annotator_id]
                        for item in dimension_disputes
                        for annotator_id in (item.annotator_a, item.annotator_b)
                    }
                )
                candidate = _select_adjudication(
                    adjudications,
                    report_id,
                    dimension,
                    required_parent_ids,
                )
                if candidate is None:
                    unresolved.append(
                        UnresolvedAdjudicationItem(
                            report_id=report_id,
                            dimension=dimension,
                            reasons=sorted({item.reason.value for item in dimension_disputes}),
                            required_parent_bundle_ids=required_parent_ids,
                        )
                    )
                    report_unresolved = True
                    continue
                used_adjudications.add(candidate.annotation_bundle_id)
                adjudicated = _dimensions_by_id(_report_annotation(candidate, report_id))[dimension]
                consensus_dimensions.append(
                    _consensus_from_adjudication(adjudicated, independent_bundle_ids, candidate.annotation_bundle_id)
                )
            else:
                consensus_dimensions.append(_aggregate_independent(dimension, annotations, independent_bundle_ids))
        if not report_unresolved:
            assessed_weight, human_score = _consensus_score(consensus_dimensions, rubric)
            group_id, split, report_sha256 = inventory[report_id]
            reports.append(
                ConsensusReport(
                    group_id=group_id,
                    report_id=report_id,
                    split=split,
                    report_sha256=report_sha256,
                    assessed_weight=assessed_weight,
                    human_score=human_score,
                    dimensions=consensus_dimensions,
                )
            )

    unused_adjudications = sorted(
        bundle.annotation_bundle_id for bundle in adjudications if bundle.annotation_bundle_id not in used_adjudications
    )
    if unused_adjudications:
        raise EvaluationInputError(
            "adjudication Bundles do not resolve a queued disagreement: " + ", ".join(unused_adjudications)
        )
    consensus_ready = (
        agreement.agreement_ready and not unresolved and bool(target_reports) and len(reports) == len(target_reports)
    )
    warnings = list(agreement.warnings)
    if unresolved:
        warnings.append(f"{len(unresolved)} disputed dimensions remain unresolved.")
    if not consensus_ready:
        warnings.append("Human consensus is not ready for benchmark use.")
    return AnnotationConsensusResult(
        engine_version=__version__,
        dataset_id=agreement.dataset_id,
        dataset_version=agreement.dataset_version,
        dataset_manifest_sha256=agreement.dataset_manifest_sha256,
        dataset_freeze_sha256=agreement.dataset_freeze_sha256,
        rubric_version=agreement.rubric_version,
        rubric_sha256=agreement.rubric_sha256,
        agreement=agreement,
        consensus_ready=consensus_ready,
        target_report_count=len(target_reports),
        consensus_report_count=len(reports),
        adjudication_required_item_count=len(disputes),
        adjudication_resolved_item_count=len(disputes) - len(unresolved),
        unresolved_adjudication_item_count=len(unresolved),
        used_adjudication_bundle_ids=sorted(used_adjudications),
        unresolved_adjudication_items=unresolved,
        reports=reports,
        warnings=warnings,
    )


def _disputes_by_dimension(
    items: list[AdjudicationItem],
) -> dict[tuple[str, DimensionId], list[AdjudicationItem]]:
    grouped: dict[tuple[str, DimensionId], list[AdjudicationItem]] = defaultdict(list)
    for item in items:
        grouped[(item.report_id, item.dimension)].append(item)
    return grouped


def _reject_adjudication_for_non_disputed_reports(
    adjudications: list[AnnotationBundle],
    disputes: dict[tuple[str, DimensionId], list[AdjudicationItem]],
) -> None:
    disputed_reports = {report_id for report_id, _ in disputes}
    for bundle in adjudications:
        extra = sorted(
            annotation.report_id for annotation in bundle.annotations if annotation.report_id not in disputed_reports
        )
        if extra:
            raise EvaluationInputError(
                f"adjudication Bundle '{bundle.annotation_bundle_id}' includes reports without queued disputes: "
                + ", ".join(extra)
            )


def _select_adjudication(
    adjudications: list[AnnotationBundle],
    report_id: str,
    dimension: DimensionId,
    required_parent_ids: list[str],
) -> AnnotationBundle | None:
    candidates = [
        bundle
        for bundle in adjudications
        if set(required_parent_ids).issubset(bundle.parent_annotation_bundle_ids)
        and any(annotation.report_id == report_id for annotation in bundle.annotations)
    ]
    if len(candidates) > 1:
        names = ", ".join(sorted(bundle.annotation_bundle_id for bundle in candidates))
        raise EvaluationInputError(
            f"multiple adjudication Bundles resolve report '{report_id}' dimension '{dimension.value}': {names}"
        )
    return candidates[0] if candidates else None


def _report_annotation(bundle: AnnotationBundle, report_id: str) -> ReportAnnotation:
    return next(annotation for annotation in bundle.annotations if annotation.report_id == report_id)


def _dimensions_by_id(annotation: ReportAnnotation) -> dict[DimensionId, DimensionAnnotation]:
    return {item.dimension: item for item in annotation.dimensions}


def _consensus_from_adjudication(
    annotation: DimensionAnnotation,
    independent_bundle_ids: list[str],
    adjudication_bundle_id: str,
) -> ConsensusDimension:
    return ConsensusDimension(
        dimension=annotation.dimension,
        status=annotation.status,
        score=float(annotation.score) if annotation.score is not None else None,
        error_codes=sorted(annotation.error_codes, key=lambda item: item.value),
        source=ConsensusSource.ADJUDICATION,
        independent_bundle_ids=independent_bundle_ids,
        adjudication_bundle_id=adjudication_bundle_id,
    )


def _aggregate_independent(
    dimension: DimensionId,
    annotations: list[DimensionAnnotation],
    independent_bundle_ids: list[str],
) -> ConsensusDimension:
    statuses = {annotation.status for annotation in annotations}
    error_sets = {tuple(sorted(annotation.error_codes, key=lambda item: item.value)) for annotation in annotations}
    if len(statuses) != 1 or len(error_sets) != 1:
        raise EvaluationInputError("unresolved annotation disagreement reached independent aggregation")
    status = next(iter(statuses))
    scores = [float(annotation.score) for annotation in annotations if annotation.score is not None]
    return ConsensusDimension(
        dimension=dimension,
        status=status,
        score=round(statistics.fmean(scores), 6) if scores else None,
        error_codes=list(next(iter(error_sets))),
        source=ConsensusSource.INDEPENDENT_AGGREGATE,
        independent_bundle_ids=independent_bundle_ids,
    )


def _consensus_score(
    dimensions: list[ConsensusDimension],
    rubric: RubricDefinition,
) -> tuple[float, float | None]:
    assessed = [item for item in dimensions if item.status is DimensionStatus.ASSESSED]
    assessed_weight = sum(rubric.dimension(item.dimension).weight for item in assessed)
    if assessed_weight < rubric.minimum_assessed_weight:
        return round(assessed_weight, 6), None
    weighted = sum(
        (float(item.score) / 4.0) * rubric.dimension(item.dimension).weight
        for item in assessed
        if item.score is not None
    )
    score = (weighted / assessed_weight) * 100.0
    hard_caps = [
        rubric.hard_caps[error] for item in assessed for error in item.error_codes if error in rubric.hard_caps
    ]
    if hard_caps:
        score = min(score, *hard_caps)
    return round(assessed_weight, 6), round(score, 6)
