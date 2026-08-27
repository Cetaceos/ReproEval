"""Artifact lineage checks based on immutable source content hashes."""

from __future__ import annotations

from collections.abc import Iterable

from .errors import ArtifactLineageError
from .models import (
    BuildEvidenceGraphResult,
    CompareReproductionResult,
    ExtractClaimsResult,
    ParentArtifactReference,
    ReliabilityScoreResult,
    SourceReference,
    ToolResultBase,
)
from .transfer_models import BuildTransferGraphResult, SolutionProfileResult, TransferAssessmentResult


def validate_score_context(
    *,
    paper_sources: list[SourceReference],
    reproduction_sources: list[SourceReference],
    claims: ExtractClaimsResult | None,
    comparison: CompareReproductionResult | None,
    group_filters: dict[str, str],
    claims_artifact: ParentArtifactReference | None = None,
    comparison_artifact: ParentArtifactReference | None = None,
) -> None:
    """Ensure optional prior artifacts describe the currently loaded source bytes."""

    if claims is not None:
        _require_role_match("claim artifact", claims.sources, paper_sources, "paper")
    if comparison is not None:
        if not reproduction_sources:
            raise ArtifactLineageError(
                "A comparison artifact requires matching reproduction_paths when scoring.",
                hint="Pass the original reproduction files or omit comparison_artifact_path.",
            )
        _require_role_match("comparison artifact", comparison.sources, paper_sources, "paper")
        _require_role_match("comparison artifact", comparison.sources, reproduction_sources, "repro")
        if comparison.group_filters != group_filters:
            raise ArtifactLineageError(
                "The comparison artifact uses different experiment group filters from the score request.",
                hint="Pass exactly the same group_filters to comparison and scoring.",
            )
        if claims is not None:
            _require_comparison_claim_run(comparison, claims)
            if claims_artifact is not None:
                require_exact_parent(comparison, claims_artifact)
    if comparison_artifact is not None and comparison is None:
        raise ArtifactLineageError("A comparison artifact reference was supplied without comparison content.")


def validate_comparison_context(
    *,
    paper_sources: list[SourceReference],
    claims: ExtractClaimsResult,
) -> None:
    """Ensure an optional claim artifact describes the paper currently being compared."""

    _require_role_match("claim artifact", claims.sources, paper_sources, "paper")


def validate_report_lineage(
    claims: ExtractClaimsResult,
    comparison: CompareReproductionResult,
    score: ReliabilityScoreResult,
    *,
    claims_artifact: ParentArtifactReference | None = None,
    comparison_artifact: ParentArtifactReference | None = None,
) -> None:
    """Reject reports assembled from unrelated or stale analysis artifacts."""

    _require_role_match("comparison artifact", comparison.sources, claims.sources, "paper")
    _require_role_match("score artifact", score.sources, claims.sources, "paper")
    _require_role_match("score artifact", score.sources, comparison.sources, "repro")
    if comparison.group_filters != score.group_filters:
        raise ArtifactLineageError(
            "The comparison and score artifacts use different experiment group filters.",
            hint="Re-run comparison and scoring with exactly the same group_filters.",
        )
    _require_comparison_claim_run(comparison, claims)
    if claims_artifact is not None and comparison_artifact is not None:
        require_exact_parent(comparison, claims_artifact)
        require_exact_parent(score, claims_artifact)
        require_exact_parent(score, comparison_artifact)


def _require_comparison_claim_run(
    comparison: CompareReproductionResult,
    claims: ExtractClaimsResult,
) -> None:
    if comparison.claims_run_id is not None and comparison.claims_run_id != claims.run_id:
        raise ArtifactLineageError(
            "The comparison artifact references a different claim-analysis run.",
            hint="Use the extract_claims artifact that was passed to reproscope_compare_results.",
        )


def validate_graph_artifact_lineage(
    graph: BuildEvidenceGraphResult,
    claims: ExtractClaimsResult,
    comparison: CompareReproductionResult,
    score: ReliabilityScoreResult,
    *,
    claims_artifact: ParentArtifactReference | None = None,
    comparison_artifact: ParentArtifactReference | None = None,
    score_artifact: ParentArtifactReference | None = None,
) -> None:
    """Ensure a graph was built from the exact artifacts supplied to report rendering."""

    expected_run_ids = [claims.run_id, comparison.run_id, score.run_id]
    if graph.source_run_ids != expected_run_ids:
        raise ArtifactLineageError(
            "The evidence graph was not built from the supplied analysis artifacts.",
            hint="Rebuild the evidence graph from the current claim, comparison, and score artifacts.",
        )
    _require_role_match("evidence graph artifact", graph.sources, claims.sources, "paper")
    _require_role_match("evidence graph artifact", graph.sources, comparison.sources, "repro")
    for artifact in (claims_artifact, comparison_artifact, score_artifact):
        if artifact is not None:
            require_exact_parent(graph, artifact)


def validate_transfer_context(
    *,
    solution_sources: list[SourceReference],
    profile: SolutionProfileResult,
) -> None:
    """Ensure a solution profile describes the source solution bytes being assessed."""

    _require_role_match("solution profile artifact", profile.sources, solution_sources, "solution")


def validate_transfer_report_lineage(
    profile: SolutionProfileResult,
    assessment: TransferAssessmentResult,
    *,
    profile_artifact: ParentArtifactReference,
) -> None:
    """Reject transfer reports assembled from unrelated profile and assessment runs."""

    _require_role_match("transfer assessment artifact", assessment.sources, profile.sources, "solution")
    _require_role_present("transfer assessment artifact", assessment.sources, "target")
    if assessment.solution_profile_run_id != profile.run_id:
        raise ArtifactLineageError(
            "The transfer assessment references a different solution-profile run.",
            hint="Use the solution_profile.json artifact passed to reproscope_assess_transfer.",
        )
    require_exact_parent(assessment, profile_artifact)


def validate_transfer_graph_artifact_lineage(
    graph: BuildTransferGraphResult,
    profile: SolutionProfileResult,
    assessment: TransferAssessmentResult,
    *,
    profile_artifact: ParentArtifactReference,
    assessment_artifact: ParentArtifactReference,
) -> None:
    """Ensure a transfer graph was built from the exact supplied upstream artifacts."""

    if graph.source_run_ids != [profile.run_id, assessment.run_id]:
        raise ArtifactLineageError(
            "The transfer graph was not built from the supplied profile and assessment artifacts.",
            hint="Rebuild the transfer graph from the current solution profile and transfer assessment.",
        )
    _require_role_match("transfer graph artifact", graph.sources, profile.sources, "solution")
    _require_role_present("transfer graph artifact", graph.sources, "target")
    require_exact_parent(graph, profile_artifact)
    require_exact_parent(graph, assessment_artifact)


def require_exact_parent(
    child: ToolResultBase,
    expected: ParentArtifactReference,
) -> None:
    """Require one child lineage entry to match the exact supplied parent bytes."""

    candidates = [parent for parent in child.parent_artifacts if parent.role == expected.role]
    if len(candidates) != 1:
        raise ArtifactLineageError(
            f"The {child.run_id} artifact does not declare exactly one {expected.role} parent artifact.",
            hint="Re-run the child tool with the exact upstream artifact used in this workflow.",
        )
    actual = candidates[0]
    compared_fields = (
        "run_id",
        "artifact_type",
        "relative_path",
        "content_hash",
        "payload_hash",
        "schema_version",
    )
    if any(getattr(actual, field) != getattr(expected, field) for field in compared_fields):
        raise ArtifactLineageError(
            f"The {child.run_id} artifact does not reference the exact supplied {expected.role} artifact.",
            hint="Do not combine artifacts from different runs, even when their original sources are identical.",
        )


def merge_sources(*groups: Iterable[SourceReference]) -> list[SourceReference]:
    """Merge source inventories while preserving first-seen order."""

    merged: list[SourceReference] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for source in group:
            key = (source.source_id, source.content_hash)
            if key not in seen:
                seen.add(key)
                merged.append(source)
    return merged


def _require_role_match(
    artifact_label: str,
    actual: list[SourceReference],
    expected: list[SourceReference],
    role: str,
) -> None:
    actual_hashes = _role_hashes(actual, role)
    expected_hashes = _role_hashes(expected, role)
    if not actual_hashes:
        raise ArtifactLineageError(
            f"The {artifact_label} has no {role} source lineage.",
            hint="Re-run the upstream tool with the current ReproScope version.",
        )
    if actual_hashes != expected_hashes:
        raise ArtifactLineageError(
            f"The {artifact_label} does not match the current {role} source content.",
            hint="Use artifacts generated from exactly the same input files, or re-run the upstream tools.",
        )


def _require_role_present(
    artifact_label: str,
    sources: list[SourceReference],
    role: str,
) -> None:
    if not _role_hashes(sources, role):
        raise ArtifactLineageError(
            f"The {artifact_label} has no {role} source lineage.",
            hint="Re-run the upstream tool with the required input files.",
        )


def _role_hashes(sources: Iterable[SourceReference], role: str) -> tuple[tuple[str, str], ...]:
    prefix = f"{role}_"
    return tuple(
        sorted((source.source_id, source.content_hash) for source in sources if source.source_id.startswith(prefix))
    )
