"""Deterministic construction and validation of claim-evidence-result graphs."""

from __future__ import annotations

from collections.abc import Iterable

from .errors import EvidenceGraphValidationError
from .models import (
    BuildEvidenceGraphResult,
    CompareReproductionResult,
    DomainProfileName,
    EvidenceCitation,
    EvidenceGraphEdge,
    EvidenceGraphEdgeType,
    EvidenceGraphMetrics,
    EvidenceGraphNode,
    EvidenceGraphNodeType,
    EvidenceKind,
    ExtractClaimsResult,
    GraphProperty,
    MetricComparison,
    MetricComparisonStatus,
    ReliabilityScoreResult,
    SourceReference,
    ToolWarning,
)

_CLAIM_RELATIONS = {
    EvidenceGraphEdgeType.SUPPORTS,
    EvidenceGraphEdgeType.PARTIALLY_SUPPORTS,
    EvidenceGraphEdgeType.CONTRADICTS,
}

_ALLOWED_EDGE_ENDPOINTS: dict[
    EvidenceGraphEdgeType,
    set[tuple[EvidenceGraphNodeType, EvidenceGraphNodeType]],
] = {
    EvidenceGraphEdgeType.REPORTED_BY: {
        (EvidenceGraphNodeType.CLAIM, EvidenceGraphNodeType.ARTIFACT),
        (EvidenceGraphNodeType.EXPERIMENT, EvidenceGraphNodeType.ARTIFACT),
        (EvidenceGraphNodeType.REPORTED_RESULT, EvidenceGraphNodeType.ARTIFACT),
    },
    EvidenceGraphEdgeType.MEASURED_BY: {
        (EvidenceGraphNodeType.REPORTED_RESULT, EvidenceGraphNodeType.METRIC),
        (EvidenceGraphNodeType.REPRODUCTION_RESULT, EvidenceGraphNodeType.METRIC),
    },
    EvidenceGraphEdgeType.SUPPORTS: {
        (EvidenceGraphNodeType.ASSESSMENT, EvidenceGraphNodeType.CLAIM),
        (EvidenceGraphNodeType.REPRODUCTION_RESULT, EvidenceGraphNodeType.CLAIM),
    },
    EvidenceGraphEdgeType.PARTIALLY_SUPPORTS: {
        (EvidenceGraphNodeType.ASSESSMENT, EvidenceGraphNodeType.CLAIM),
        (EvidenceGraphNodeType.REPRODUCTION_RESULT, EvidenceGraphNodeType.CLAIM),
    },
    EvidenceGraphEdgeType.CONTRADICTS: {
        (EvidenceGraphNodeType.ASSESSMENT, EvidenceGraphNodeType.CLAIM),
        (EvidenceGraphNodeType.REPRODUCTION_RESULT, EvidenceGraphNodeType.CLAIM),
    },
    EvidenceGraphEdgeType.DERIVED_FROM: {
        (EvidenceGraphNodeType.REPRODUCTION_RESULT, EvidenceGraphNodeType.ARTIFACT),
        (EvidenceGraphNodeType.REPRODUCTION_RESULT, EvidenceGraphNodeType.REPRODUCTION_RUN),
        (EvidenceGraphNodeType.REPRODUCTION_RUN, EvidenceGraphNodeType.ARTIFACT),
        (EvidenceGraphNodeType.ASSESSMENT, EvidenceGraphNodeType.REPRODUCTION_RESULT),
        (EvidenceGraphNodeType.ASSESSMENT, EvidenceGraphNodeType.REPORTED_RESULT),
        (EvidenceGraphNodeType.DOMAIN_PROFILE, EvidenceGraphNodeType.ARTIFACT),
        (EvidenceGraphNodeType.DOMAIN_FINDING, EvidenceGraphNodeType.ARTIFACT),
    },
    EvidenceGraphEdgeType.DEPENDS_ON: {
        (EvidenceGraphNodeType.ASSESSMENT, EvidenceGraphNodeType.ASSESSMENT),
        (EvidenceGraphNodeType.ASSESSMENT, EvidenceGraphNodeType.CLAIM),
        (EvidenceGraphNodeType.ASSESSMENT, EvidenceGraphNodeType.REPRODUCTION_RESULT),
        (EvidenceGraphNodeType.CLAIM, EvidenceGraphNodeType.ASSUMPTION),
        (EvidenceGraphNodeType.DOMAIN_FINDING, EvidenceGraphNodeType.DOMAIN_PROFILE),
    },
    EvidenceGraphEdgeType.INVALIDATED_BY: {
        (EvidenceGraphNodeType.ASSUMPTION, EvidenceGraphNodeType.PROJECT_CONTEXT),
        (EvidenceGraphNodeType.ASSUMPTION, EvidenceGraphNodeType.EVIDENCE_GAP),
    },
    EvidenceGraphEdgeType.MISSING_FOR: {
        (EvidenceGraphNodeType.EVIDENCE_GAP, EvidenceGraphNodeType.CLAIM),
        (EvidenceGraphNodeType.EVIDENCE_GAP, EvidenceGraphNodeType.ASSUMPTION),
        (EvidenceGraphNodeType.EVIDENCE_GAP, EvidenceGraphNodeType.EXPERIMENT),
        (EvidenceGraphNodeType.EVIDENCE_GAP, EvidenceGraphNodeType.METRIC),
    },
    EvidenceGraphEdgeType.TRANSFERRED_TO: {
        (EvidenceGraphNodeType.CLAIM, EvidenceGraphNodeType.PROJECT_CONTEXT),
        (EvidenceGraphNodeType.ASSUMPTION, EvidenceGraphNodeType.PROJECT_CONTEXT),
        (EvidenceGraphNodeType.EXPERIMENT, EvidenceGraphNodeType.PROJECT_CONTEXT),
        (EvidenceGraphNodeType.METRIC, EvidenceGraphNodeType.PROJECT_CONTEXT),
    },
}


def build_graph(
    *,
    run_id: str,
    claims: ExtractClaimsResult,
    comparison: CompareReproductionResult,
    score: ReliabilityScoreResult,
) -> BuildEvidenceGraphResult:
    """Build a graph from already validated analysis artifacts without another Hy3 call."""

    nodes: list[EvidenceGraphNode] = []
    edges: list[EvidenceGraphEdge] = []
    warnings: list[ToolWarning] = []
    sources = _deduplicate_references([*claims.sources, *comparison.sources, *score.sources])
    source_nodes: dict[str, str] = {}

    for index, source in enumerate(sources, start=1):
        node_id = f"artifact:{index}"
        source_nodes[source.source_id] = node_id
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                node_type=EvidenceGraphNodeType.ARTIFACT,
                label=source.source_path,
                evidence_kind=EvidenceKind.OBSERVED,
                source_references=[source],
                properties={
                    "source_id": source.source_id,
                    "source_type": source.source_type.value,
                    "content_hash": source.content_hash,
                },
            )
        )

    reproduction_sources = [source for source in sources if source.source_id.startswith("repro_")]
    reproduction_run_node_id = "reproduction-run:1" if reproduction_sources else None
    if reproduction_run_node_id is not None:
        nodes.append(
            EvidenceGraphNode(
                node_id=reproduction_run_node_id,
                node_type=EvidenceGraphNodeType.REPRODUCTION_RUN,
                label="Reproduction evidence run",
                evidence_kind=EvidenceKind.OBSERVED,
                source_references=reproduction_sources,
                properties={"comparison_run_id": comparison.run_id},
            )
        )
        _connect_to_sources(
            edges,
            source_node_id=reproduction_run_node_id,
            references=reproduction_sources,
            source_nodes=source_nodes,
            edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
            evidence_kind=EvidenceKind.OBSERVED,
            rationale="The reproduction run is represented by this supplied result artifact.",
        )

    claim_nodes: dict[str, str] = {}
    for index, claim in enumerate(claims.core_claims, start=1):
        node_id = f"claim:{index}"
        references = _references_from_citations(claim.citations)
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                node_type=EvidenceGraphNodeType.CLAIM,
                label=claim.statement,
                evidence_kind=EvidenceKind.OBSERVED if references else EvidenceKind.UNKNOWN,
                source_references=references,
                properties={
                    "claim_id": claim.claim_id,
                    "claim_type": claim.claim_type.value,
                    "reported_value": claim.reported_value,
                },
            )
        )
        if claim.claim_id in claim_nodes:
            warnings.append(
                ToolWarning(
                    code="DUPLICATE_CLAIM_ID",
                    message=f"Only the first graph node is addressable for duplicated claim ID: {claim.claim_id}",
                    source_references=references,
                )
            )
        else:
            claim_nodes[claim.claim_id] = node_id
        _connect_to_sources(
            edges,
            source_node_id=node_id,
            references=references,
            source_nodes=source_nodes,
            edge_type=EvidenceGraphEdgeType.REPORTED_BY,
            evidence_kind=EvidenceKind.OBSERVED,
            rationale="The paper source reports this claim.",
        )

    for index, setting in enumerate(claims.experiment_settings, start=1):
        node_id = f"experiment:{index}"
        references = _references_from_citations(setting.citations)
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                node_type=EvidenceGraphNodeType.EXPERIMENT,
                label=f"{setting.name}: {setting.value or 'unknown'}",
                evidence_kind=(EvidenceKind.OBSERVED if setting.disclosed and references else EvidenceKind.UNKNOWN),
                source_references=references,
                properties={
                    "name": setting.name,
                    "value": setting.value,
                    "disclosed": setting.disclosed,
                },
            )
        )
        _connect_to_sources(
            edges,
            source_node_id=node_id,
            references=references,
            source_nodes=source_nodes,
            edge_type=EvidenceGraphEdgeType.REPORTED_BY,
            evidence_kind=EvidenceKind.OBSERVED,
            rationale="The paper source reports this experiment setting.",
        )

    for index, detail in enumerate(claims.missing_details, start=1):
        references = _references_from_citations(detail.citations)
        nodes.append(
            EvidenceGraphNode(
                node_id=f"evidence-gap:{index}",
                node_type=EvidenceGraphNodeType.EVIDENCE_GAP,
                label=detail.item,
                evidence_kind=EvidenceKind.INFERRED if references else EvidenceKind.UNKNOWN,
                source_references=references,
                properties={
                    "impact": detail.impact,
                    "severity": detail.severity.value,
                },
            )
        )

    activation = claims.domain_profile_activation
    if activation is not None and activation.effective_profile is DomainProfileName.ISAC_PHY:
        profile_node_id = "domain-profile:1"
        nodes.append(
            EvidenceGraphNode(
                node_id=profile_node_id,
                node_type=EvidenceGraphNodeType.DOMAIN_PROFILE,
                label=f"Domain profile: {activation.effective_profile.value}",
                evidence_kind=(EvidenceKind.INFERRED if activation.source_references else EvidenceKind.UNKNOWN),
                source_references=activation.source_references,
                properties={
                    "requested_profile": activation.requested_profile.value,
                    "detected_profile": activation.detected_profile.value,
                    "effective_profile": activation.effective_profile.value,
                    "profile_version": activation.profile_version,
                    "activation_source": activation.activation_source.value,
                    "confidence": activation.confidence,
                },
            )
        )
        _connect_to_sources(
            edges,
            source_node_id=profile_node_id,
            references=activation.source_references,
            source_nodes=source_nodes,
            edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The profile activation detector inspected these supplied paper sources.",
        )

        if claims.isac_analysis is not None:
            for index, finding in enumerate(claims.isac_analysis.findings, start=1):
                finding_node_id = f"domain-finding:{index}"
                references = _references_from_citations(finding.citations)
                nodes.append(
                    EvidenceGraphNode(
                        node_id=finding_node_id,
                        node_type=EvidenceGraphNodeType.DOMAIN_FINDING,
                        label=f"{finding.rule_id}: {finding.summary}",
                        evidence_kind=finding.evidence_kind,
                        source_references=references,
                        properties={
                            "rule_id": finding.rule_id,
                            "status": finding.status.value,
                            "review_required": finding.review_required,
                            "affects_score": finding.affects_score,
                            "missing_evidence": "; ".join(finding.missing_evidence),
                        },
                    )
                )
                _append_edge(
                    edges,
                    edge_type=EvidenceGraphEdgeType.DEPENDS_ON,
                    source_node_id=finding_node_id,
                    target_node_id=profile_node_id,
                    evidence_kind=EvidenceKind.INFERRED,
                    rationale="This domain finding is defined by the active, versioned ISAC profile.",
                    source_references=references,
                )
                _connect_to_sources(
                    edges,
                    source_node_id=finding_node_id,
                    references=references,
                    source_nodes=source_nodes,
                    edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
                    evidence_kind=finding.evidence_kind,
                    rationale="The current paper source supports this domain finding.",
                )

    reproduction_result_nodes: list[str] = []
    metric_nodes_by_mapping: dict[tuple[str | None, str | None, str], str] = {}
    group_result_nodes_by_mapping: dict[tuple[str, str, str], list[str]] = {}
    for index, metric in enumerate(comparison.metric_comparisons, start=1):
        metric_node_id = f"metric:{index}"
        metric_nodes_by_mapping.setdefault(
            (metric.reproduction_source_id, metric.reproduction_column, metric.metric),
            metric_node_id,
        )
        metric_references = _references_from_citations(metric.citations)
        nodes.append(
            EvidenceGraphNode(
                node_id=metric_node_id,
                node_type=EvidenceGraphNodeType.METRIC,
                label=metric.metric,
                evidence_kind=EvidenceKind.INFERRED,
                source_references=metric_references,
                properties={
                    "canonical_metric": metric.canonical_metric,
                    "unit": metric.unit,
                    "paper_scale": metric.paper_scale.value,
                    "reproduction_scale": metric.reproduction_scale.value,
                    "normalized_scale": metric.normalized_scale.value,
                    "scale_conversion": metric.scale_conversion,
                    "higher_is_better": metric.higher_is_better,
                    "severity": metric.severity.value,
                    "computation_status": metric.computation_status.value,
                },
            )
        )

        paper_references = [reference for reference in metric_references if reference.source_id.startswith("paper_")]
        if metric.paper_value is not None:
            reported_node_id = f"reported-result:{index}"
            nodes.append(
                EvidenceGraphNode(
                    node_id=reported_node_id,
                    node_type=EvidenceGraphNodeType.REPORTED_RESULT,
                    label=f"Reported {metric.metric}",
                    evidence_kind=EvidenceKind.OBSERVED if paper_references else EvidenceKind.UNKNOWN,
                    source_references=paper_references,
                    properties={
                        "value": metric.paper_value,
                        "normalized_value": metric.normalized_paper_value,
                        "unit": metric.unit,
                        "paper_scale": metric.paper_scale.value,
                        "normalized_scale": metric.normalized_scale.value,
                        "scale_conversion": metric.scale_conversion,
                    },
                )
            )
            _append_edge(
                edges,
                edge_type=EvidenceGraphEdgeType.MEASURED_BY,
                source_node_id=reported_node_id,
                target_node_id=metric_node_id,
                evidence_kind=EvidenceKind.OBSERVED,
                rationale="The paper reports this value for the metric.",
                source_references=paper_references,
            )
            _connect_to_sources(
                edges,
                source_node_id=reported_node_id,
                references=paper_references,
                source_nodes=source_nodes,
                edge_type=EvidenceGraphEdgeType.REPORTED_BY,
                evidence_kind=EvidenceKind.OBSERVED,
                rationale="The reported value comes from this paper source.",
            )

        if metric.computation_status is MetricComparisonStatus.COMPUTED:
            reproduction_node_id = f"reproduction-result:{index}"
            reproduction_references = _reproduction_references(metric, comparison.sources)
            nodes.append(
                EvidenceGraphNode(
                    node_id=reproduction_node_id,
                    node_type=EvidenceGraphNodeType.REPRODUCTION_RESULT,
                    label=f"Reproduced {metric.metric}",
                    evidence_kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
                    source_references=reproduction_references,
                    properties={
                        "canonical_metric": metric.canonical_metric,
                        "value": metric.reproduced_value,
                        "stddev": metric.reproduced_stddev,
                        "sample_count": metric.sample_count,
                        "absolute_delta": metric.absolute_delta,
                        "relative_delta_percent": metric.relative_delta_percent,
                        "unit": metric.unit,
                        "paper_scale": metric.paper_scale.value,
                        "reproduction_scale": metric.reproduction_scale.value,
                        "normalized_scale": metric.normalized_scale.value,
                        "scale_conversion": metric.scale_conversion,
                        **_data_quality_properties(metric),
                    },
                )
            )
            reproduction_result_nodes.append(reproduction_node_id)
            _append_edge(
                edges,
                edge_type=EvidenceGraphEdgeType.MEASURED_BY,
                source_node_id=reproduction_node_id,
                target_node_id=metric_node_id,
                evidence_kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
                rationale="Python calculated the reproduction aggregate for this metric.",
                source_references=reproduction_references,
            )
            if reproduction_run_node_id is not None:
                _append_edge(
                    edges,
                    edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
                    source_node_id=reproduction_node_id,
                    target_node_id=reproduction_run_node_id,
                    evidence_kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
                    rationale="The locally calculated result aggregates this reproduction evidence run.",
                    source_references=reproduction_references,
                )
            _connect_to_sources(
                edges,
                source_node_id=reproduction_node_id,
                references=reproduction_references,
                source_nodes=source_nodes,
                edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
                evidence_kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
                rationale="The aggregate was calculated from this reproduction artifact.",
            )

    for index, metric in enumerate(comparison.group_metric_comparisons, start=1):
        if metric.computation_status is not MetricComparisonStatus.COMPUTED:
            continue
        metric_node_id = metric_nodes_by_mapping.get(
            (metric.reproduction_source_id, metric.reproduction_column, metric.metric)
        )
        if metric_node_id is None:
            continue
        rendered_group = ", ".join(f"{key}={value}" for key, value in metric.group.items())
        reproduction_node_id = f"group-reproduction-result:{index}"
        reproduction_references = _reproduction_references(metric, comparison.sources)
        nodes.append(
            EvidenceGraphNode(
                node_id=reproduction_node_id,
                node_type=EvidenceGraphNodeType.REPRODUCTION_RESULT,
                label=f"Reproduced {metric.metric} [{rendered_group}]",
                evidence_kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
                source_references=reproduction_references,
                properties={
                    "group": rendered_group,
                    **{f"group_{key}": value for key, value in metric.group.items()},
                    "canonical_metric": metric.canonical_metric,
                    "value": metric.reproduced_value,
                    "stddev": metric.reproduced_stddev,
                    "sample_count": metric.sample_count,
                    "absolute_delta": metric.absolute_delta,
                    "relative_delta_percent": metric.relative_delta_percent,
                    "unit": metric.unit,
                    "paper_scale": metric.paper_scale.value,
                    "reproduction_scale": metric.reproduction_scale.value,
                    "normalized_scale": metric.normalized_scale.value,
                    "scale_conversion": metric.scale_conversion,
                    **_data_quality_properties(metric),
                },
            )
        )
        reproduction_result_nodes.append(reproduction_node_id)
        mapping_key = (
            metric.reproduction_source_id,
            metric.reproduction_column,
            metric.metric,
        )
        group_result_nodes_by_mapping.setdefault(mapping_key, []).append(reproduction_node_id)
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.MEASURED_BY,
            source_node_id=reproduction_node_id,
            target_node_id=metric_node_id,
            evidence_kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
            rationale="Python calculated this group-scoped reproduction aggregate for the metric.",
            source_references=reproduction_references,
        )
        if reproduction_run_node_id is not None:
            _append_edge(
                edges,
                edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
                source_node_id=reproduction_node_id,
                target_node_id=reproduction_run_node_id,
                evidence_kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
                rationale="The group-scoped result was derived from this reproduction evidence run.",
                source_references=reproduction_references,
            )
        _connect_to_sources(
            edges,
            source_node_id=reproduction_node_id,
            references=reproduction_references,
            source_nodes=source_nodes,
            edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
            evidence_kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
            rationale="The group-scoped aggregate was calculated from this reproduction artifact.",
        )

    stability_node_ids: list[str] = []
    for index, stability in enumerate(comparison.group_stability_summaries, start=1):
        mapping_key = (
            stability.reproduction_source_id,
            stability.reproduction_column,
            stability.metric,
        )
        result_node_ids = group_result_nodes_by_mapping.get(mapping_key, [])
        if len(result_node_ids) < 2:
            continue
        stability_node_id = f"assessment:group-stability:{index}"
        stability_node_ids.append(stability_node_id)
        source_references = [
            source for source in comparison.sources if source.source_id == stability.reproduction_source_id
        ]
        minimum_group = ", ".join(f"{key}={value}" for key, value in stability.minimum_group.items())
        maximum_group = ", ".join(f"{key}={value}" for key, value in stability.maximum_group.items())
        max_delta_group = (
            ", ".join(f"{key}={value}" for key, value in stability.max_delta_group.items())
            if stability.max_delta_group
            else None
        )
        nodes.append(
            EvidenceGraphNode(
                node_id=stability_node_id,
                node_type=EvidenceGraphNodeType.ASSESSMENT,
                label=f"Cross-group stability: {stability.metric}",
                evidence_kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
                source_references=source_references,
                properties={
                    "group_by": ", ".join(stability.group_by),
                    "group_count": stability.group_count,
                    "group_mean": stability.group_mean,
                    "group_mean_stddev": stability.group_mean_stddev,
                    "minimum_group": minimum_group,
                    "minimum_value": stability.minimum_value,
                    "maximum_group": maximum_group,
                    "maximum_value": stability.maximum_value,
                    "value_range": stability.value_range,
                    "range_percent_of_reported": stability.range_percent_of_reported,
                    "max_absolute_paper_delta": stability.max_absolute_paper_delta,
                    "max_delta_group": max_delta_group,
                },
            )
        )
        for result_node_id in result_node_ids:
            _append_edge(
                edges,
                edge_type=EvidenceGraphEdgeType.DEPENDS_ON,
                source_node_id=stability_node_id,
                target_node_id=result_node_id,
                evidence_kind=EvidenceKind.DETERMINISTICALLY_DERIVED,
                rationale="The cross-group stability summary is calculated from this group-scoped result.",
                source_references=source_references,
            )

    comparison_references = _comparison_references(comparison)
    comparison_node_id = "assessment:comparison"
    nodes.append(
        EvidenceGraphNode(
            node_id=comparison_node_id,
            node_type=EvidenceGraphNodeType.ASSESSMENT,
            label="Reproduction comparison",
            evidence_kind=EvidenceKind.INFERRED,
            source_references=comparison_references,
            properties={"conclusion_stability": comparison.conclusion_stability},
        )
    )
    for result_node_id in reproduction_result_nodes:
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.DEPENDS_ON,
            source_node_id=comparison_node_id,
            target_node_id=result_node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The semantic comparison depends on this locally calculated reproduction result.",
            source_references=comparison_references,
        )
    for stability_node_id in stability_node_ids:
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.DEPENDS_ON,
            source_node_id=comparison_node_id,
            target_node_id=stability_node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The semantic comparison considers the deterministic cross-group stability summary.",
            source_references=comparison_references,
        )

    _connect_claim_assessments(
        edges=edges,
        assessment_node_id=comparison_node_id,
        claim_ids=comparison.supported_claim_ids,
        claim_nodes=claim_nodes,
        edge_type=EvidenceGraphEdgeType.SUPPORTS,
        references=comparison_references,
        warnings=warnings,
    )
    _connect_claim_assessments(
        edges=edges,
        assessment_node_id=comparison_node_id,
        claim_ids=comparison.partially_supported_claim_ids,
        claim_nodes=claim_nodes,
        edge_type=EvidenceGraphEdgeType.PARTIALLY_SUPPORTS,
        references=comparison_references,
        warnings=warnings,
    )
    _connect_claim_assessments(
        edges=edges,
        assessment_node_id=comparison_node_id,
        claim_ids=comparison.contradicted_claim_ids,
        claim_nodes=claim_nodes,
        edge_type=EvidenceGraphEdgeType.CONTRADICTS,
        references=comparison_references,
        warnings=warnings,
    )

    score_references = _score_references(score)
    score_node_id = "assessment:reliability"
    nodes.append(
        EvidenceGraphNode(
            node_id=score_node_id,
            node_type=EvidenceGraphNodeType.ASSESSMENT,
            label="Reliability rubric assessment",
            evidence_kind=EvidenceKind.INFERRED,
            source_references=score_references,
            properties={
                "overall_score": score.overall_score,
                "reliability_band": score.reliability_band.value,
                "conclusion_confidence": score.conclusion_confidence,
                "rubric_coverage": score.rubric_coverage,
            },
        )
    )
    _append_edge(
        edges,
        edge_type=EvidenceGraphEdgeType.DEPENDS_ON,
        source_node_id=score_node_id,
        target_node_id=comparison_node_id,
        evidence_kind=EvidenceKind.INFERRED,
        rationale="The reliability assessment uses the reproduction comparison as evidence.",
        source_references=score_references,
    )

    metrics = calculate_graph_metrics(nodes=nodes, edges=edges, sources=sources)
    result = BuildEvidenceGraphResult(
        run_id=run_id,
        summary=(
            f"Built a validated graph with {len(nodes)} nodes, {len(edges)} edges, "
            f"and {metrics.orphan_claim_count} orphan claims."
        ),
        source_run_ids=[claims.run_id, comparison.run_id, score.run_id],
        sources=sources,
        warnings=warnings,
        nodes=nodes,
        edges=edges,
        metrics=metrics,
    )
    validate_evidence_graph(result)
    result.graph_validated = True
    return result


def validate_evidence_graph(graph: BuildEvidenceGraphResult) -> None:
    """Reject malformed, stale, or internally inconsistent graph structures."""

    nodes_by_id = {node.node_id: node for node in graph.nodes}
    if len(nodes_by_id) != len(graph.nodes):
        raise EvidenceGraphValidationError("Evidence graph contains duplicate node IDs.")

    edge_ids = {edge.edge_id for edge in graph.edges}
    if len(edge_ids) != len(graph.edges):
        raise EvidenceGraphValidationError("Evidence graph contains duplicate edge IDs.")

    source_keys = {(source.source_id, source.content_hash) for source in graph.sources}
    source_ids = {source.source_id for source in graph.sources}
    if len(source_ids) != len(graph.sources):
        raise EvidenceGraphValidationError("Evidence graph contains ambiguous source IDs.")

    for node in graph.nodes:
        _validate_references(node.source_references, source_keys, f"node {node.node_id}")
        if node.evidence_kind is EvidenceKind.DETERMINISTICALLY_DERIVED and not node.source_references:
            raise EvidenceGraphValidationError(
                f"Deterministically derived node has no source reference: {node.node_id}"
            )

    for edge in graph.edges:
        source_node = nodes_by_id.get(edge.source_node_id)
        target_node = nodes_by_id.get(edge.target_node_id)
        if source_node is None or target_node is None:
            raise EvidenceGraphValidationError(f"Evidence graph edge has a dangling endpoint: {edge.edge_id}")
        allowed = _ALLOWED_EDGE_ENDPOINTS.get(edge.edge_type, set())
        if (source_node.node_type, target_node.node_type) not in allowed:
            raise EvidenceGraphValidationError(
                f"Illegal {edge.edge_type.value} endpoints on edge {edge.edge_id}: "
                f"{source_node.node_type.value} -> {target_node.node_type.value}"
            )
        _validate_references(edge.source_references, source_keys, f"edge {edge.edge_id}")

    expected_metrics = calculate_graph_metrics(nodes=graph.nodes, edges=graph.edges, sources=graph.sources)
    if graph.metrics != expected_metrics:
        raise EvidenceGraphValidationError("Evidence graph metrics do not match its nodes and edges.")


def calculate_graph_metrics(
    *,
    nodes: list[EvidenceGraphNode],
    edges: list[EvidenceGraphEdge],
    sources: list[SourceReference],
) -> EvidenceGraphMetrics:
    nodes_by_id = {node.node_id: node for node in nodes}
    claim_nodes = [node for node in nodes if node.node_type is EvidenceGraphNodeType.CLAIM]
    relation_edges = [edge for edge in edges if edge.edge_type in _CLAIM_RELATIONS]
    related_claim_ids = {edge.target_node_id for edge in relation_edges}
    evidenced_claims = {
        node.node_id for node in claim_nodes if node.source_references or node.node_id in related_claim_ids
    }
    source_evidenced_claims = {node.node_id for node in claim_nodes if node.source_references}
    reproduction_result_ids = {
        node.node_id for node in nodes if node.node_type is EvidenceGraphNodeType.REPRODUCTION_RESULT
    }
    reproduction_dependent_assessments = {
        edge.source_node_id
        for edge in edges
        if edge.edge_type is EvidenceGraphEdgeType.DEPENDS_ON
        and edge.target_node_id in reproduction_result_ids
        and nodes_by_id.get(edge.source_node_id) is not None
        and nodes_by_id[edge.source_node_id].node_type is EvidenceGraphNodeType.ASSESSMENT
    }
    reproduction_assessed_claims = {
        edge.target_node_id for edge in relation_edges if edge.source_node_id in reproduction_dependent_assessments
    }
    contradicted_claims = {
        edge.target_node_id for edge in relation_edges if edge.edge_type is EvidenceGraphEdgeType.CONTRADICTS
    }
    supported_claims = {
        edge.target_node_id for edge in relation_edges if edge.edge_type is EvidenceGraphEdgeType.SUPPORTS
    }
    partially_supported_claims = {
        edge.target_node_id for edge in relation_edges if edge.edge_type is EvidenceGraphEdgeType.PARTIALLY_SUPPORTS
    }
    assessed_claims = {edge.target_node_id for edge in relation_edges}
    orphan_claims = [
        node for node in claim_nodes if not node.source_references and node.node_id not in related_claim_ids
    ]

    experiment_nodes = [node for node in nodes if node.node_type is EvidenceGraphNodeType.EXPERIMENT]
    disclosed_settings = sum(node.properties.get("disclosed") is True for node in experiment_nodes)

    source_keys = {(source.source_id, source.content_hash) for source in sources}
    graph_references = [reference for item in [*nodes, *edges] for reference in item.source_references]
    closed_references = sum(
        (reference.source_id, reference.content_hash) in source_keys for reference in graph_references
    )
    invalidated_assumptions = sum(
        edge.edge_type is EvidenceGraphEdgeType.INVALIDATED_BY
        and nodes_by_id[edge.source_node_id].node_type is EvidenceGraphNodeType.ASSUMPTION
        for edge in edges
        if edge.source_node_id in nodes_by_id
    )

    return EvidenceGraphMetrics(
        claim_evidence_coverage=_ratio(len(evidenced_claims), len(claim_nodes)),
        claim_source_coverage=_ratio(len(source_evidenced_claims), len(claim_nodes)),
        reproduction_assessment_coverage=_ratio(len(reproduction_assessed_claims), len(claim_nodes)),
        contradiction_ratio=_ratio(len(contradicted_claims), len(assessed_claims)),
        orphan_claim_count=len(orphan_claims),
        source_closure_ratio=_ratio(closed_references, len(graph_references)),
        experiment_setting_coverage=_ratio(disclosed_settings, len(experiment_nodes)),
        reproduction_support_ratio=_ratio(len(supported_claims), len(assessed_claims)),
        reproduction_partial_support_ratio=_ratio(len(partially_supported_claims), len(assessed_claims)),
        invalidated_assumption_count=invalidated_assumptions,
    )


def _connect_to_sources(
    edges: list[EvidenceGraphEdge],
    *,
    source_node_id: str,
    references: list[SourceReference],
    source_nodes: dict[str, str],
    edge_type: EvidenceGraphEdgeType,
    evidence_kind: EvidenceKind,
    rationale: str,
) -> None:
    seen_source_ids: set[str] = set()
    for reference in references:
        if reference.source_id in seen_source_ids or reference.source_id not in source_nodes:
            continue
        seen_source_ids.add(reference.source_id)
        _append_edge(
            edges,
            edge_type=edge_type,
            source_node_id=source_node_id,
            target_node_id=source_nodes[reference.source_id],
            evidence_kind=evidence_kind,
            rationale=rationale,
            source_references=[reference],
        )


def _connect_claim_assessments(
    *,
    edges: list[EvidenceGraphEdge],
    assessment_node_id: str,
    claim_ids: list[str],
    claim_nodes: dict[str, str],
    edge_type: EvidenceGraphEdgeType,
    references: list[SourceReference],
    warnings: list[ToolWarning],
) -> None:
    for claim_id in dict.fromkeys(claim_ids):
        claim_node_id = claim_nodes.get(claim_id)
        if claim_node_id is None:
            warnings.append(
                ToolWarning(
                    code="UNKNOWN_GRAPH_CLAIM_ID",
                    message=f"Skipped {edge_type.value} relation to unknown claim ID: {claim_id}",
                    source_references=references,
                )
            )
            continue
        _append_edge(
            edges,
            edge_type=edge_type,
            source_node_id=assessment_node_id,
            target_node_id=claim_node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale=f"The reproduction comparison classifies this claim as {edge_type.value}.",
            source_references=references,
        )


def _append_edge(
    edges: list[EvidenceGraphEdge],
    *,
    edge_type: EvidenceGraphEdgeType,
    source_node_id: str,
    target_node_id: str,
    evidence_kind: EvidenceKind,
    rationale: str,
    source_references: list[SourceReference],
) -> None:
    edges.append(
        EvidenceGraphEdge(
            edge_id=f"edge:{len(edges) + 1}",
            edge_type=edge_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            evidence_kind=evidence_kind,
            rationale=rationale,
            source_references=_deduplicate_references(source_references),
        )
    )


def _references_from_citations(citations: Iterable[EvidenceCitation]) -> list[SourceReference]:
    return _deduplicate_references(
        [citation.source_reference for citation in citations if citation.source_reference is not None]
    )


def _comparison_references(comparison: CompareReproductionResult) -> list[SourceReference]:
    citations = [
        citation
        for item in [*comparison.metric_comparisons, *comparison.setting_differences]
        for citation in item.citations
    ]
    return _references_from_citations(citations)


def _score_references(score: ReliabilityScoreResult) -> list[SourceReference]:
    return _references_from_citations(citation for dimension in score.dimensions for citation in dimension.citations)


def _reproduction_references(metric: object, sources: list[SourceReference]) -> list[SourceReference]:
    source_id = getattr(metric, "reproduction_source_id", None)
    column = getattr(metric, "reproduction_column", None)
    return [source.model_copy(update={"column": column}) for source in sources if source.source_id == source_id]


def _data_quality_properties(metric: MetricComparison) -> dict[str, GraphProperty]:
    quality = metric.data_quality
    if quality is None:
        return {}
    return {
        "data_total_count": quality.total_count,
        "data_valid_numeric_count": quality.valid_numeric_count,
        "data_missing_count": quality.missing_count,
        "data_non_numeric_count": quality.non_numeric_count,
        "data_non_finite_count": quality.non_finite_count,
        "data_valid_ratio": quality.valid_ratio,
    }


def _deduplicate_references(references: Iterable[SourceReference]) -> list[SourceReference]:
    result: list[SourceReference] = []
    seen: set[tuple[object, ...]] = set()
    for reference in references:
        key = (
            reference.source_id,
            reference.content_hash,
            reference.page,
            reference.line_start,
            reference.line_end,
            reference.row_start,
            reference.row_end,
            reference.column,
        )
        if key not in seen:
            seen.add(key)
            result.append(reference)
    return result


def _validate_references(
    references: list[SourceReference],
    source_keys: set[tuple[str, str]],
    label: str,
) -> None:
    for reference in references:
        if (reference.source_id, reference.content_hash) not in source_keys:
            raise EvidenceGraphValidationError(f"Evidence graph {label} references an unknown source.")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
