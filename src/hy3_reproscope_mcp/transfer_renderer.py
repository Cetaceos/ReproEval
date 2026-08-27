"""Deterministic Markdown rendering for technology-transfer assessments."""

from __future__ import annotations

from collections.abc import Iterable

from .models import ArtifactAuditEntry, EvidenceCitation, SourceReference, ToolWarning
from .transfer_models import BuildTransferGraphResult, SolutionProfileResult, TransferAssessmentResult


def render_transfer_markdown_report(
    *,
    title: str,
    profile: SolutionProfileResult,
    assessment: TransferAssessmentResult,
    artifact_inventory: list[ArtifactAuditEntry],
    graph: BuildTransferGraphResult | None = None,
) -> str:
    lines = [
        f"# {_inline(title)}",
        "",
        "## Decision summary",
        "",
        assessment.summary,
        "",
        "| Transfer score | Feasibility band | Confidence | Evidence coverage | Rubric coverage |",
        "| ---: | --- | ---: | ---: | ---: |",
        (
            f"| {_score(assessment.overall_score)} | {assessment.feasibility_band.value} | "
            f"{assessment.conclusion_confidence:.2f} | {assessment.evidence_coverage:.2f} | "
            f"{assessment.rubric_coverage:.2f} |"
        ),
        "",
        f"**Target context:** {_inline(assessment.target_context_summary)}",
        "",
        (
            "This is a conditional evidence assessment. It does not predict point performance in the target "
            "environment, and license or provenance signals are not legal advice."
        ),
        "",
        "## Source solution profile",
        "",
        profile.summary,
        "",
        "### Objectives",
        "",
        "| ID | Objective | Success criteria | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    if profile.objectives:
        for objective in profile.objectives:
            lines.append(
                f"| {_cell(objective.objective_id)} | {_cell(objective.statement)} | "
                f"{_cell('; '.join(objective.success_criteria))} | {_cell(_citations(objective.citations))} |"
            )
    else:
        lines.append("| - | No objectives were supported by the supplied evidence. | - | - |")

    lines.extend(
        [
            "",
            "### Components and dependencies",
            "",
            "| Component | Responsibility | Interfaces | Evidence |",
            "| --- | --- | --- | --- |",
        ]
    )
    if profile.components:
        for component in profile.components:
            lines.append(
                f"| {_cell(component.component_id)}: {_cell(component.name)} | "
                f"{_cell(component.responsibility)} | {_cell('; '.join(component.interfaces))} | "
                f"{_cell(_citations(component.citations))} |"
            )
    else:
        lines.append("| - | No components were extracted. | - | - |")
    if profile.dependencies:
        lines.extend(
            [
                "",
                "| Dependency | Type | Required condition | Replaceable | Evidence |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for dependency in profile.dependencies:
            replaceable = "unknown" if dependency.replaceable is None else ("yes" if dependency.replaceable else "no")
            lines.append(
                f"| {_cell(dependency.dependency_id)}: {_cell(dependency.name)} | "
                f"{_cell(dependency.dependency_type)} | {_cell(dependency.required_condition)} | {replaceable} | "
                f"{_cell(_citations(dependency.citations))} |"
            )

    lines.extend(
        [
            "",
            "## Transfer rubric",
            "",
            "| Dimension | Weight | Status | Score | Rationale | Evidence gaps | Evidence |",
            "| --- | ---: | --- | ---: | --- | --- | --- |",
        ]
    )
    for dimension in assessment.dimensions:
        lines.append(
            f"| {_cell(dimension.name.value)} | {dimension.weight:.0%} | "
            f"{_cell(dimension.assessment_status.value)} | {_score(dimension.score, suffix=False)} | "
            f"{_cell(dimension.rationale)} | {_cell('; '.join(dimension.evidence_gaps))} | "
            f"{_cell(_citations(dimension.citations))} |"
        )

    lines.extend(
        [
            "",
            "## Assumption compatibility",
            "",
            "| Assumption | Compatibility | Target condition | Rationale | Evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if assessment.assumption_assessments:
        for item in assessment.assumption_assessments:
            lines.append(
                f"| {_cell(item.assumption_id)} | {_cell(item.compatibility.value)} | "
                f"{_cell(item.target_condition)} | {_cell(item.rationale)} | "
                f"{_cell(_citations(item.citations))} |"
            )
    else:
        lines.append("| - | unknown | - | No assumptions were assessed. | - |")

    lines.extend(
        [
            "",
            "## Dependency and resource feasibility",
            "",
            "| Dependency | Status | Target condition | Required action | Rationale | Evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if assessment.dependency_assessments:
        for item in assessment.dependency_assessments:
            lines.append(
                f"| {_cell(item.dependency_id)} | {_cell(item.status.value)} | "
                f"{_cell(item.target_condition)} | {_cell(item.required_action)} | {_cell(item.rationale)} | "
                f"{_cell(_citations(item.citations))} |"
            )
    else:
        lines.append("| - | unknown | - | - | No dependencies were assessed. | - |")
    lines.extend(
        [
            "",
            "| Resource | Status | Target condition | Required action | Rationale | Evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if assessment.resource_assessments:
        for item in assessment.resource_assessments:
            lines.append(
                f"| {_cell(item.resource_id)} | {_cell(item.status.value)} | "
                f"{_cell(item.target_condition)} | {_cell(item.required_action)} | {_cell(item.rationale)} | "
                f"{_cell(_citations(item.citations))} |"
            )
    else:
        lines.append("| - | unknown | - | - | No resource requirements were assessed. | - |")

    lines.extend(
        [
            "",
            "## Reuse and adaptation",
            "",
            "| Component | Reuse level | Required changes | Rationale | Evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if assessment.component_assessments:
        for item in assessment.component_assessments:
            lines.append(
                f"| {_cell(item.component_id)} | {_cell(item.reuse_level.value)} | "
                f"{_cell('; '.join(item.required_changes))} | {_cell(item.rationale)} | "
                f"{_cell(_citations(item.citations))} |"
            )
    else:
        lines.append("| - | unknown | - | No components were assessed. | - |")
    lines.extend(["", "### Transferable strengths", "", *_bullets(assessment.transferable_strengths)])
    lines.extend(["", "### Required adaptations", ""])
    if assessment.required_adaptations:
        for item in assessment.required_adaptations:
            components = ", ".join(item.affected_component_ids) or "unspecified"
            lines.append(
                f"- **{_inline(item.adaptation_id)}** ({item.estimated_effort.value}; {components}): "
                f"{_inline(item.change)}. Reason: {_inline(item.reason)} {_citations(item.citations)}".rstrip()
            )
    else:
        lines.append("- None supported by the supplied evidence.")

    lines.extend(["", "## Risks", ""])
    if assessment.risks:
        for risk in assessment.risks:
            lines.append(
                f"- **{_inline(risk.risk_id)}** ({risk.level.value}, {_inline(risk.category)}): "
                f"{_inline(risk.description)} Mitigation: {_inline(risk.mitigation)} "
                f"{_citations(risk.citations)}".rstrip()
            )
    else:
        lines.append("- No risks were returned; this does not establish risk absence.")

    lines.extend(["", "## Validation plan", ""])
    if assessment.validation_plan:
        for step in assessment.validation_plan:
            criteria = "; ".join(step.success_criteria) or "not specified"
            prerequisites = "; ".join(step.prerequisites) or "none recorded"
            lines.append(
                f"1. **{_inline(step.step_id)}: {_inline(step.objective)}:** {_inline(step.method)} "
                f"Success criteria: {_inline(criteria)}. Prerequisites: {_inline(prerequisites)}. "
                f"{_citations(step.citations)}".rstrip()
            )
    else:
        lines.append("No evidence-grounded validation steps were produced.")

    if graph is not None:
        metrics = graph.metrics
        lines.extend(
            [
                "",
                "## Transfer evidence graph",
                "",
                graph.summary,
                "",
                "| Nodes | Edges | Profile evidence | Assumptions assessed | Components assessed | "
                "Dependencies assessed | Resources assessed | Invalidated conditions | Transferred components | "
                "High risks | Validation steps | Source closure |",
                "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                (
                    f"| {len(graph.nodes)} | {len(graph.edges)} | "
                    f"{metrics.profile_entity_evidence_coverage:.2f} | "
                    f"{metrics.assumption_assessment_coverage:.2f} | "
                    f"{metrics.component_assessment_coverage:.2f} | "
                    f"{metrics.dependency_assessment_coverage:.2f} | "
                    f"{metrics.resource_assessment_coverage:.2f} | "
                    f"{metrics.invalidated_condition_count} | "
                    f"{metrics.transferred_component_count} | {metrics.high_risk_count} | "
                    f"{metrics.validation_step_count} | {metrics.source_closure_ratio:.2f} |"
                ),
                "",
                (
                    "Graph relations are constructed and validated locally from the supplied profile and assessment. "
                    "Inferred transfer relations remain conditional evidence, not measured target performance."
                ),
                "",
                f"Graph validation marker: `graph_validated={str(graph.graph_validated).lower()}`.",
            ]
        )

    _append_source_inventory(lines, assessment.sources)
    _append_audit_trail(lines, profile, assessment, artifact_inventory)
    _append_warnings(lines, [*profile.warnings, *assessment.warnings])
    return "\n".join(lines)


def _append_source_inventory(lines: list[str], sources: list[SourceReference]) -> None:
    lines.extend(
        [
            "",
            "## Source inventory",
            "",
            "| Source | Path | Type | SHA-256 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for source in sources:
        lines.append(
            f"| {_cell(source.source_id)} | {_cell(source.source_path)} | {_cell(source.source_type.value)} | "
            f"`{source.content_hash}` |"
        )
    if not sources:
        lines.append("| - | - | - | No source lineage recorded. |")


def _append_audit_trail(
    lines: list[str],
    profile: SolutionProfileResult,
    assessment: TransferAssessmentResult,
    artifacts: list[ArtifactAuditEntry],
) -> None:
    lines.extend(
        [
            "",
            "## Audit trail",
            "",
            f"Source runs: `{profile.run_id}`, `{assessment.run_id}`. "
            "Rubric aggregation and the feasibility band are calculated deterministically by ReproScope.",
            "",
            "| Role | Run | Path | Schema | File SHA-256 | Payload SHA-256 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for artifact in artifacts:
        lines.append(
            f"| {_cell(artifact.role)} | {_cell(artifact.run_id)} | {_cell(artifact.relative_path)} | "
            f"{_cell(artifact.schema_version)} | `{artifact.content_hash}` | "
            f"{f'`{artifact.payload_hash}`' if artifact.payload_hash else '-'} |"
        )


def _append_warnings(lines: list[str], warnings: list[ToolWarning]) -> None:
    if not warnings:
        return
    lines.extend(["", "Warnings:"])
    for warning in warnings:
        lines.append(f"- `{warning.code}`: {_inline(warning.message)}")


def _citations(citations: Iterable[EvidenceCitation]) -> str:
    return ", ".join(f"[{citation.source_id}@{citation.locator}]" for citation in citations) or "-"


def _score(value: float | None, *, suffix: bool = True) -> str:
    if value is None:
        return "not assessed"
    rendered = f"{value:.2f}"
    return f"{rendered}/100" if suffix else rendered


def _cell(value: object | None) -> str:
    if value is None or value == "":
        return "-"
    return _inline(str(value))


def _inline(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _bullets(items: list[str]) -> list[str]:
    return [f"- {_inline(item)}" for item in items] or ["- None recorded."]
