"""Deterministic construction and validation of technology-transfer evidence graphs."""

from __future__ import annotations

from collections.abc import Iterable

from .errors import EvidenceGraphValidationError
from .models import (
    EvidenceCitation,
    EvidenceGraphEdge,
    EvidenceGraphEdgeType,
    EvidenceGraphNode,
    EvidenceGraphNodeType,
    EvidenceKind,
    SourceReference,
)
from .transfer_models import (
    AssumptionCompatibility,
    BuildTransferGraphResult,
    ComponentReuseLevel,
    SolutionProfileResult,
    TransferAssessmentResult,
    TransferConditionStatus,
    TransferGraphMetrics,
    TransferRiskLevel,
)

_PROFILE_ENTITY_TYPES = {
    EvidenceGraphNodeType.OBJECTIVE,
    EvidenceGraphNodeType.COMPONENT,
    EvidenceGraphNodeType.DEPENDENCY,
    EvidenceGraphNodeType.ASSUMPTION,
    EvidenceGraphNodeType.RESOURCE,
}

_ALLOWED_EDGE_ENDPOINTS: dict[
    EvidenceGraphEdgeType,
    set[tuple[EvidenceGraphNodeType, EvidenceGraphNodeType]],
] = {
    EvidenceGraphEdgeType.REPORTED_BY: {
        (node_type, EvidenceGraphNodeType.ARTIFACT)
        for node_type in {
            *_PROFILE_ENTITY_TYPES,
            EvidenceGraphNodeType.PROJECT_CONTEXT,
            EvidenceGraphNodeType.EVIDENCE_GAP,
        }
    },
    EvidenceGraphEdgeType.DERIVED_FROM: {
        (node_type, EvidenceGraphNodeType.ARTIFACT)
        for node_type in {
            EvidenceGraphNodeType.ASSESSMENT,
            EvidenceGraphNodeType.ADAPTATION,
            EvidenceGraphNodeType.RISK,
            EvidenceGraphNodeType.VALIDATION_STEP,
        }
    }
    | {
        (EvidenceGraphNodeType.RISK, EvidenceGraphNodeType.ASSESSMENT),
        (EvidenceGraphNodeType.ADAPTATION, EvidenceGraphNodeType.ASSESSMENT),
        (EvidenceGraphNodeType.VALIDATION_STEP, EvidenceGraphNodeType.ASSESSMENT),
    },
    EvidenceGraphEdgeType.DEPENDS_ON: {
        (EvidenceGraphNodeType.ASSESSMENT, node_type) for node_type in _PROFILE_ENTITY_TYPES
    },
    EvidenceGraphEdgeType.INVALIDATED_BY: {
        (EvidenceGraphNodeType.ASSUMPTION, EvidenceGraphNodeType.PROJECT_CONTEXT),
        (EvidenceGraphNodeType.DEPENDENCY, EvidenceGraphNodeType.PROJECT_CONTEXT),
        (EvidenceGraphNodeType.RESOURCE, EvidenceGraphNodeType.PROJECT_CONTEXT),
    },
    EvidenceGraphEdgeType.COMPATIBLE_WITH: {
        (EvidenceGraphNodeType.ASSUMPTION, EvidenceGraphNodeType.PROJECT_CONTEXT),
        (EvidenceGraphNodeType.DEPENDENCY, EvidenceGraphNodeType.PROJECT_CONTEXT),
        (EvidenceGraphNodeType.RESOURCE, EvidenceGraphNodeType.PROJECT_CONTEXT),
    },
    EvidenceGraphEdgeType.TRANSFERRED_TO: {
        (EvidenceGraphNodeType.COMPONENT, EvidenceGraphNodeType.PROJECT_CONTEXT),
        (EvidenceGraphNodeType.ADAPTATION, EvidenceGraphNodeType.PROJECT_CONTEXT),
    },
    EvidenceGraphEdgeType.ADAPTED_FOR: {
        (EvidenceGraphNodeType.ADAPTATION, EvidenceGraphNodeType.COMPONENT),
    },
    EvidenceGraphEdgeType.VALIDATED_BY: {
        (EvidenceGraphNodeType.ASSESSMENT, EvidenceGraphNodeType.VALIDATION_STEP),
    },
    EvidenceGraphEdgeType.MISSING_FOR: {
        (EvidenceGraphNodeType.EVIDENCE_GAP, EvidenceGraphNodeType.ASSESSMENT),
    },
}


def build_transfer_graph(
    *,
    run_id: str,
    profile: SolutionProfileResult,
    assessment: TransferAssessmentResult,
) -> BuildTransferGraphResult:
    """Build a transfer graph from validated profile and assessment artifacts."""

    nodes: list[EvidenceGraphNode] = []
    edges: list[EvidenceGraphEdge] = []
    sources = _deduplicate_references([*profile.sources, *assessment.sources])
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

    target_references = [source for source in sources if source.source_id.startswith("target_")]
    context_node_id = "project-context:1"
    nodes.append(
        EvidenceGraphNode(
            node_id=context_node_id,
            node_type=EvidenceGraphNodeType.PROJECT_CONTEXT,
            label=assessment.target_context_summary,
            evidence_kind=EvidenceKind.OBSERVED if target_references else EvidenceKind.UNKNOWN,
            source_references=target_references,
            properties={"assessment_run_id": assessment.run_id},
        )
    )
    _connect_to_sources(
        edges,
        source_node_id=context_node_id,
        references=target_references,
        source_nodes=source_nodes,
        edge_type=EvidenceGraphEdgeType.REPORTED_BY,
        evidence_kind=EvidenceKind.OBSERVED,
        rationale="The supplied target-context source describes this project context.",
    )

    objective_nodes = _add_profile_nodes(
        nodes,
        edges,
        items=profile.objectives,
        node_type=EvidenceGraphNodeType.OBJECTIVE,
        id_attribute="objective_id",
        label_attribute="statement",
        source_nodes=source_nodes,
    )
    component_nodes = _add_profile_nodes(
        nodes,
        edges,
        items=profile.components,
        node_type=EvidenceGraphNodeType.COMPONENT,
        id_attribute="component_id",
        label_attribute="name",
        source_nodes=source_nodes,
    )
    dependency_nodes = _add_profile_nodes(
        nodes,
        edges,
        items=profile.dependencies,
        node_type=EvidenceGraphNodeType.DEPENDENCY,
        id_attribute="dependency_id",
        label_attribute="name",
        source_nodes=source_nodes,
    )
    assumption_nodes = _add_profile_nodes(
        nodes,
        edges,
        items=profile.assumptions,
        node_type=EvidenceGraphNodeType.ASSUMPTION,
        id_attribute="assumption_id",
        label_attribute="statement",
        source_nodes=source_nodes,
    )
    resource_nodes = _add_profile_nodes(
        nodes,
        edges,
        items=profile.resource_requirements,
        node_type=EvidenceGraphNodeType.RESOURCE,
        id_attribute="resource_id",
        label_attribute="requirement",
        source_nodes=source_nodes,
    )

    assessment_references = _assessment_references(assessment)
    assessment_node_id = "assessment:transfer"
    nodes.append(
        EvidenceGraphNode(
            node_id=assessment_node_id,
            node_type=EvidenceGraphNodeType.ASSESSMENT,
            label="Technology-transfer assessment",
            evidence_kind=EvidenceKind.INFERRED,
            source_references=assessment_references,
            properties={
                "overall_score": assessment.overall_score,
                "feasibility_band": assessment.feasibility_band.value,
                "conclusion_confidence": assessment.conclusion_confidence,
                "rubric_coverage": assessment.rubric_coverage,
            },
        )
    )
    _connect_to_sources(
        edges,
        source_node_id=assessment_node_id,
        references=assessment_references,
        source_nodes=source_nodes,
        edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
        evidence_kind=EvidenceKind.INFERRED,
        rationale="The transfer assessment is inferred from these supplied sources.",
    )

    for node_id in objective_nodes.values():
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.DEPENDS_ON,
            source_node_id=assessment_node_id,
            target_node_id=node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The transfer decision depends on the source solution objective.",
            source_references=assessment_references,
        )
    _connect_assumption_assessments(
        edges,
        assessment,
        assessment_node_id,
        context_node_id,
        assumption_nodes,
    )
    _connect_component_assessments(
        edges,
        assessment,
        assessment_node_id,
        context_node_id,
        component_nodes,
    )
    _connect_condition_assessments(
        edges,
        assessment_node_id=assessment_node_id,
        context_node_id=context_node_id,
        assessments=assessment.dependency_assessments,
        node_ids=dependency_nodes,
        id_attribute="dependency_id",
    )
    _connect_condition_assessments(
        edges,
        assessment_node_id=assessment_node_id,
        context_node_id=context_node_id,
        assessments=assessment.resource_assessments,
        node_ids=resource_nodes,
        id_attribute="resource_id",
    )

    for index, gap in enumerate(profile.evidence_gaps, start=1):
        references = _references_from_citations(gap.citations)
        node_id = f"evidence-gap:{index}"
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                node_type=EvidenceGraphNodeType.EVIDENCE_GAP,
                label=gap.item,
                evidence_kind=EvidenceKind.INFERRED if references else EvidenceKind.UNKNOWN,
                source_references=references,
                properties={"impact": gap.impact, "severity": gap.severity.value},
            )
        )
        _connect_to_sources(
            edges,
            source_node_id=node_id,
            references=references,
            source_nodes=source_nodes,
            edge_type=EvidenceGraphEdgeType.REPORTED_BY,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The source material supports this evidence-gap finding.",
        )
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.MISSING_FOR,
            source_node_id=node_id,
            target_node_id=assessment_node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="This evidence gap limits the transfer assessment.",
            source_references=references,
        )

    for index, adaptation in enumerate(assessment.required_adaptations, start=1):
        references = _references_from_citations(adaptation.citations)
        node_id = f"adaptation:{index}"
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                node_type=EvidenceGraphNodeType.ADAPTATION,
                label=adaptation.change,
                evidence_kind=EvidenceKind.INFERRED,
                source_references=references,
                properties={
                    "adaptation_id": adaptation.adaptation_id,
                    "estimated_effort": adaptation.estimated_effort.value,
                },
            )
        )
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
            source_node_id=node_id,
            target_node_id=assessment_node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The required adaptation is derived from the transfer assessment.",
            source_references=references,
        )
        _connect_to_sources(
            edges,
            source_node_id=node_id,
            references=references,
            source_nodes=source_nodes,
            edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The required adaptation is grounded in these source conditions.",
        )
        for component_id in adaptation.affected_component_ids:
            component_node_id = component_nodes.get(component_id)
            if component_node_id is not None:
                _append_edge(
                    edges,
                    edge_type=EvidenceGraphEdgeType.ADAPTED_FOR,
                    source_node_id=node_id,
                    target_node_id=component_node_id,
                    evidence_kind=EvidenceKind.INFERRED,
                    rationale="This adaptation modifies the referenced source component.",
                    source_references=references,
                )
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.TRANSFERRED_TO,
            source_node_id=node_id,
            target_node_id=context_node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="This adaptation is required for the target project context.",
            source_references=references,
        )

    for index, risk in enumerate(assessment.risks, start=1):
        references = _references_from_citations(risk.citations)
        node_id = f"risk:{index}"
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                node_type=EvidenceGraphNodeType.RISK,
                label=risk.description,
                evidence_kind=EvidenceKind.INFERRED,
                source_references=references,
                properties={
                    "risk_id": risk.risk_id,
                    "category": risk.category,
                    "level": risk.level.value,
                    "mitigation": risk.mitigation,
                },
            )
        )
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
            source_node_id=node_id,
            target_node_id=assessment_node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="This risk is derived from the transfer assessment.",
            source_references=references,
        )
        _connect_to_sources(
            edges,
            source_node_id=node_id,
            references=references,
            source_nodes=source_nodes,
            edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="This risk is grounded in the supplied source and target conditions.",
        )

    for index, step in enumerate(assessment.validation_plan, start=1):
        references = _references_from_citations(step.citations)
        node_id = f"validation-step:{index}"
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                node_type=EvidenceGraphNodeType.VALIDATION_STEP,
                label=step.objective,
                evidence_kind=EvidenceKind.INFERRED,
                source_references=references,
                properties={
                    "step_id": step.step_id,
                    "method": step.method,
                    "success_criteria": "; ".join(step.success_criteria),
                },
            )
        )
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.VALIDATED_BY,
            source_node_id=assessment_node_id,
            target_node_id=node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="This validation step tests the conditional transfer assessment.",
            source_references=references,
        )
        _connect_to_sources(
            edges,
            source_node_id=node_id,
            references=references,
            source_nodes=source_nodes,
            edge_type=EvidenceGraphEdgeType.DERIVED_FROM,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The validation step reflects these target requirements.",
        )

    metrics = calculate_transfer_graph_metrics(nodes=nodes, edges=edges, sources=sources)
    result = BuildTransferGraphResult(
        run_id=run_id,
        summary=(
            f"Built a validated transfer graph with {len(nodes)} nodes, {len(edges)} edges, "
            f"{metrics.invalidated_condition_count} invalidated conditions, and "
            f"{metrics.transferred_component_count} transferred components."
        ),
        source_run_ids=[profile.run_id, assessment.run_id],
        sources=sources,
        nodes=nodes,
        edges=edges,
        metrics=metrics,
    )
    validate_transfer_graph(result)
    result.graph_validated = True
    return result


def validate_transfer_graph(graph: BuildTransferGraphResult) -> None:
    """Reject malformed or internally inconsistent transfer graph structures."""

    nodes_by_id = {node.node_id: node for node in graph.nodes}
    if len(nodes_by_id) != len(graph.nodes):
        raise EvidenceGraphValidationError("Transfer graph contains duplicate node IDs.")
    edge_ids = {edge.edge_id for edge in graph.edges}
    if len(edge_ids) != len(graph.edges):
        raise EvidenceGraphValidationError("Transfer graph contains duplicate edge IDs.")

    source_keys = {(source.source_id, source.content_hash) for source in graph.sources}
    source_ids = {source.source_id for source in graph.sources}
    if len(source_ids) != len(graph.sources):
        raise EvidenceGraphValidationError("Transfer graph contains ambiguous source IDs.")

    for node in graph.nodes:
        _validate_references(node.source_references, source_keys, f"node {node.node_id}")
    for edge in graph.edges:
        source_node = nodes_by_id.get(edge.source_node_id)
        target_node = nodes_by_id.get(edge.target_node_id)
        if source_node is None or target_node is None:
            raise EvidenceGraphValidationError(f"Transfer graph edge has a dangling endpoint: {edge.edge_id}")
        allowed = _ALLOWED_EDGE_ENDPOINTS.get(edge.edge_type, set())
        if (source_node.node_type, target_node.node_type) not in allowed:
            raise EvidenceGraphValidationError(
                f"Illegal {edge.edge_type.value} endpoints on transfer edge {edge.edge_id}: "
                f"{source_node.node_type.value} -> {target_node.node_type.value}"
            )
        _validate_references(edge.source_references, source_keys, f"edge {edge.edge_id}")

    expected_metrics = calculate_transfer_graph_metrics(
        nodes=graph.nodes,
        edges=graph.edges,
        sources=graph.sources,
    )
    if graph.metrics != expected_metrics:
        raise EvidenceGraphValidationError("Transfer graph metrics do not match its nodes and edges.")


def require_validated_transfer_graph(graph: BuildTransferGraphResult) -> None:
    """Validate a persisted graph and require its explicit completion marker.

    ``validate_transfer_graph`` checks structure and deterministic metrics.  The
    separate marker is written only after graph construction succeeds, so a
    structurally valid but hand-edited or incomplete artifact must not be
    presented as a validated graph by downstream reports.
    """

    validate_transfer_graph(graph)
    if graph.graph_validated is not True:
        raise EvidenceGraphValidationError(
            "Transfer graph artifact is not marked graph_validated=true; regenerate it with "
            "reproscope_build_transfer_graph."
        )


def calculate_transfer_graph_metrics(
    *,
    nodes: list[EvidenceGraphNode],
    edges: list[EvidenceGraphEdge],
    sources: list[SourceReference],
) -> TransferGraphMetrics:
    nodes_by_id = {node.node_id: node for node in nodes}
    profile_nodes = [node for node in nodes if node.node_type in _PROFILE_ENTITY_TYPES]
    evidenced_profile_nodes = [node for node in profile_nodes if node.source_references]
    assessment_edges = [
        edge
        for edge in edges
        if edge.edge_type is EvidenceGraphEdgeType.DEPENDS_ON
        and nodes_by_id.get(edge.source_node_id) is not None
        and nodes_by_id[edge.source_node_id].node_type is EvidenceGraphNodeType.ASSESSMENT
    ]
    assessed_targets = {edge.target_node_id for edge in assessment_edges}

    source_keys = {(source.source_id, source.content_hash) for source in sources}
    graph_references = [reference for item in [*nodes, *edges] for reference in item.source_references]
    closed_references = sum(
        (reference.source_id, reference.content_hash) in source_keys for reference in graph_references
    )

    def coverage(node_type: EvidenceGraphNodeType) -> float:
        typed = [node for node in profile_nodes if node.node_type is node_type]
        assessed = [node for node in typed if node.node_id in assessed_targets]
        return _ratio(len(assessed), len(typed))

    invalidated = sum(edge.edge_type is EvidenceGraphEdgeType.INVALIDATED_BY for edge in edges)
    transferred_components = {
        edge.source_node_id
        for edge in edges
        if edge.edge_type is EvidenceGraphEdgeType.TRANSFERRED_TO
        and nodes_by_id.get(edge.source_node_id) is not None
        and nodes_by_id[edge.source_node_id].node_type is EvidenceGraphNodeType.COMPONENT
    }
    high_risks = [
        node
        for node in nodes
        if node.node_type is EvidenceGraphNodeType.RISK and node.properties.get("level") == TransferRiskLevel.HIGH.value
    ]
    validation_steps = [node for node in nodes if node.node_type is EvidenceGraphNodeType.VALIDATION_STEP]
    return TransferGraphMetrics(
        source_closure_ratio=_ratio(closed_references, len(graph_references)),
        profile_entity_evidence_coverage=_ratio(len(evidenced_profile_nodes), len(profile_nodes)),
        assumption_assessment_coverage=coverage(EvidenceGraphNodeType.ASSUMPTION),
        component_assessment_coverage=coverage(EvidenceGraphNodeType.COMPONENT),
        dependency_assessment_coverage=coverage(EvidenceGraphNodeType.DEPENDENCY),
        resource_assessment_coverage=coverage(EvidenceGraphNodeType.RESOURCE),
        invalidated_condition_count=invalidated,
        transferred_component_count=len(transferred_components),
        high_risk_count=len(high_risks),
        validation_step_count=len(validation_steps),
    )


def _add_profile_nodes(
    nodes: list[EvidenceGraphNode],
    edges: list[EvidenceGraphEdge],
    *,
    items: list[object],
    node_type: EvidenceGraphNodeType,
    id_attribute: str,
    label_attribute: str,
    source_nodes: dict[str, str],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for index, item in enumerate(items, start=1):
        item_id = str(getattr(item, id_attribute))
        references = _references_from_citations(item.citations)
        node_id = f"{node_type.value}:{index}"
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                node_type=node_type,
                label=str(getattr(item, label_attribute)),
                evidence_kind=EvidenceKind.OBSERVED if references else EvidenceKind.UNKNOWN,
                source_references=references,
                properties={id_attribute: item_id},
            )
        )
        result[item_id] = node_id
        _connect_to_sources(
            edges,
            source_node_id=node_id,
            references=references,
            source_nodes=source_nodes,
            edge_type=EvidenceGraphEdgeType.REPORTED_BY,
            evidence_kind=EvidenceKind.OBSERVED,
            rationale=f"The source solution reports this {node_type.value}.",
        )
    return result


def _connect_assumption_assessments(
    edges: list[EvidenceGraphEdge],
    assessment: TransferAssessmentResult,
    assessment_node_id: str,
    context_node_id: str,
    node_ids: dict[str, str],
) -> None:
    for item in assessment.assumption_assessments:
        node_id = node_ids.get(item.assumption_id)
        if node_id is None:
            continue
        references = _references_from_citations(item.citations)
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.DEPENDS_ON,
            source_node_id=assessment_node_id,
            target_node_id=node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The transfer assessment evaluates this source assumption.",
            source_references=references,
        )
        if item.compatibility is AssumptionCompatibility.INCOMPATIBLE:
            relation = EvidenceGraphEdgeType.INVALIDATED_BY
        elif item.compatibility is AssumptionCompatibility.COMPATIBLE:
            relation = EvidenceGraphEdgeType.COMPATIBLE_WITH
        else:
            continue
        _append_edge(
            edges,
            edge_type=relation,
            source_node_id=node_id,
            target_node_id=context_node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale=f"The target context makes this assumption {item.compatibility.value}.",
            source_references=references,
        )


def _connect_component_assessments(
    edges: list[EvidenceGraphEdge],
    assessment: TransferAssessmentResult,
    assessment_node_id: str,
    context_node_id: str,
    node_ids: dict[str, str],
) -> None:
    for item in assessment.component_assessments:
        node_id = node_ids.get(item.component_id)
        if node_id is None:
            continue
        references = _references_from_citations(item.citations)
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.DEPENDS_ON,
            source_node_id=assessment_node_id,
            target_node_id=node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The transfer assessment evaluates this source component.",
            source_references=references,
        )
        if item.reuse_level in {ComponentReuseLevel.DIRECT, ComponentReuseLevel.ADAPT}:
            _append_edge(
                edges,
                edge_type=EvidenceGraphEdgeType.TRANSFERRED_TO,
                source_node_id=node_id,
                target_node_id=context_node_id,
                evidence_kind=EvidenceKind.INFERRED,
                rationale=f"The component is transferred with reuse level {item.reuse_level.value}.",
                source_references=references,
            )


def _connect_condition_assessments(
    edges: list[EvidenceGraphEdge],
    *,
    assessment_node_id: str,
    context_node_id: str,
    assessments: list[object],
    node_ids: dict[str, str],
    id_attribute: str,
) -> None:
    for item in assessments:
        node_id = node_ids.get(str(getattr(item, id_attribute)))
        if node_id is None:
            continue
        references = _references_from_citations(item.citations)
        _append_edge(
            edges,
            edge_type=EvidenceGraphEdgeType.DEPENDS_ON,
            source_node_id=assessment_node_id,
            target_node_id=node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale="The transfer assessment evaluates this source condition.",
            source_references=references,
        )
        status = item.status
        if status is TransferConditionStatus.UNSATISFIED:
            relation = EvidenceGraphEdgeType.INVALIDATED_BY
        elif status in {TransferConditionStatus.SATISFIED, TransferConditionStatus.CONDITIONAL}:
            relation = EvidenceGraphEdgeType.COMPATIBLE_WITH
        else:
            continue
        _append_edge(
            edges,
            edge_type=relation,
            source_node_id=node_id,
            target_node_id=context_node_id,
            evidence_kind=EvidenceKind.INFERRED,
            rationale=f"The target-context condition is {status.value}.",
            source_references=references,
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
            edge_id=f"transfer-edge:{len(edges) + 1}",
            edge_type=edge_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            evidence_kind=evidence_kind,
            rationale=rationale,
            source_references=_deduplicate_references(source_references),
        )
    )


def _assessment_references(assessment: TransferAssessmentResult) -> list[SourceReference]:
    groups = (
        assessment.dimensions,
        assessment.assumption_assessments,
        assessment.component_assessments,
        assessment.dependency_assessments,
        assessment.resource_assessments,
        assessment.required_adaptations,
        assessment.risks,
        assessment.validation_plan,
    )
    return _references_from_citations(citation for group in groups for item in group for citation in item.citations)


def _references_from_citations(citations: Iterable[EvidenceCitation]) -> list[SourceReference]:
    return _deduplicate_references(
        [citation.source_reference for citation in citations if citation.source_reference is not None]
    )


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
            raise EvidenceGraphValidationError(f"Transfer graph {label} references an unknown source.")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
