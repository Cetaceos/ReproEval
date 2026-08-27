"""Deterministic Markdown report rendering for completed ReproScope runs."""

from __future__ import annotations

from collections.abc import Iterable

from .models import (
    ArtifactAuditEntry,
    BuildEvidenceGraphResult,
    CompareReproductionResult,
    EvidenceCitation,
    ExtractClaimsResult,
    ReliabilityScoreResult,
)


def render_markdown_report(
    *,
    title: str,
    claims: ExtractClaimsResult,
    comparison: CompareReproductionResult,
    score: ReliabilityScoreResult,
    graph: BuildEvidenceGraphResult | None = None,
    artifact_inventory: list[ArtifactAuditEntry],
) -> str:
    lines = [
        f"# {_inline(title)}",
        "",
        "## Executive summary",
        "",
        score.summary,
        "",
        "| Overall score | Reliability band | Confidence | Evidence coverage | Rubric coverage | Assessment scope |",
        "| ---: | --- | ---: | ---: | ---: | --- |",
        (
            f"| {_score(score.overall_score)} | {score.reliability_band.value} | "
            f"{score.conclusion_confidence:.2f} | {score.evidence_coverage:.2f} | "
            f"{score.rubric_coverage:.2f} | {score.assessment_scope.value} |"
        ),
        "",
        "## Core claims",
        "",
        claims.summary,
        "",
        "| Claim | Type | Reported value | Statement | Evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    if claims.core_claims:
        for claim in claims.core_claims:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(claim.claim_id),
                        _cell(claim.claim_type.value),
                        _cell(claim.reported_value),
                        _cell(claim.statement),
                        _cell(_citations(claim.citations)),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | No core claims were extracted. | - |")

    lines.extend(
        [
            "",
            "## Reported experiment settings",
            "",
            "| Setting | Value | Disclosed | Evidence |",
            "| --- | --- | --- | --- |",
        ]
    )
    if claims.experiment_settings:
        for setting in claims.experiment_settings:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(setting.name),
                        _cell(setting.value),
                        "yes" if setting.disclosed else "no",
                        _cell(_citations(setting.citations)),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | no | No experiment settings were extracted. |")
    if claims.evidence_quality_notes:
        lines.extend(["", "Evidence quality notes:", *_bullets(claims.evidence_quality_notes)])

    _append_isac_profile(lines, claims)

    lines.extend(
        [
            "",
            "## Reproduction comparison",
            "",
            comparison.summary,
            "",
            "| Metric | Paper reported | Unit | Paper normalized | Reproduced mean | Scale | Conversion | Std. dev. | "
            "n | Absolute delta | Relative delta | Severity | Status | Evidence |",
            "| --- | ---: | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    if comparison.metric_comparisons:
        for metric in comparison.metric_comparisons:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(metric.metric),
                        _number(metric.paper_value),
                        _cell(metric.unit),
                        _number(metric.normalized_paper_value),
                        _number(metric.reproduced_value),
                        _cell(metric.normalized_scale.value),
                        _cell(metric.scale_conversion),
                        _number(metric.reproduced_stddev),
                        _cell(metric.sample_count),
                        _number(metric.absolute_delta),
                        _percent(metric.relative_delta_percent),
                        _cell(metric.severity.value),
                        _cell(metric.computation_status.value),
                        _cell(_citations(metric.citations)),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | unknown | - | - | - | - | - | unknown | unmatched | - |")
    if comparison.group_metric_comparisons:
        lines.extend(
            [
                "",
                "### Per-group metric comparisons",
                "",
                f"Group dimensions: `{', '.join(comparison.group_by)}`.",
                "",
                "| Group | Metric | Reproduced mean | Std. dev. | n | Absolute delta | Relative delta | "
                "Severity | Status |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for metric in comparison.group_metric_comparisons:
            rendered_group = ", ".join(f"{key}={value}" for key, value in metric.group.items())
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(rendered_group),
                        _cell(metric.metric),
                        _number(metric.reproduced_value),
                        _number(metric.reproduced_stddev),
                        _cell(metric.sample_count),
                        _number(metric.absolute_delta),
                        _percent(metric.relative_delta_percent),
                        _cell(metric.severity.value),
                        _cell(metric.computation_status.value),
                    ]
                )
                + " |"
            )
    if comparison.group_stability_summaries:
        lines.extend(
            [
                "",
                "### Cross-group stability",
                "",
                "| Metric | Groups | Group mean | Group-mean std. dev. | Minimum group | Minimum | Maximum group | "
                "Maximum | Range | Range / reported | Largest paper delta | Delta group |",
                "| --- | ---: | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for stability in comparison.group_stability_summaries:
            minimum_group = ", ".join(f"{key}={value}" for key, value in stability.minimum_group.items())
            maximum_group = ", ".join(f"{key}={value}" for key, value in stability.maximum_group.items())
            max_delta_group = (
                ", ".join(f"{key}={value}" for key, value in stability.max_delta_group.items())
                if stability.max_delta_group
                else None
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(stability.metric),
                        _cell(stability.group_count),
                        _number(stability.group_mean),
                        _number(stability.group_mean_stddev),
                        _cell(minimum_group),
                        _number(stability.minimum_value),
                        _cell(maximum_group),
                        _number(stability.maximum_value),
                        _number(stability.value_range),
                        _percent(stability.range_percent_of_reported),
                        _number(stability.max_absolute_paper_delta),
                        _cell(max_delta_group),
                    ]
                )
                + " |"
            )
    quality_rows = [("global", metric) for metric in comparison.metric_comparisons if metric.data_quality is not None]
    quality_rows.extend(
        (
            ", ".join(f"{key}={value}" for key, value in metric.group.items()),
            metric,
        )
        for metric in comparison.group_metric_comparisons
        if metric.data_quality is not None
    )
    if quality_rows:
        lines.extend(
            [
                "",
                "### Metric data quality",
                "",
                "| Scope | Metric | Source column | Rows | Valid numeric | Missing | Non-numeric | Non-finite | "
                "Valid ratio |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for scope, metric in quality_rows:
            quality = metric.data_quality
            if quality is None:  # pragma: no cover - narrowed while constructing quality_rows
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(scope),
                        _cell(metric.metric),
                        _cell(metric.reproduction_column),
                        _cell(quality.total_count),
                        _cell(quality.valid_numeric_count),
                        _cell(quality.missing_count),
                        _cell(quality.non_numeric_count),
                        _cell(quality.non_finite_count),
                        _percent(quality.valid_ratio * 100),
                    ]
                )
                + " |"
            )
    diagnostics = comparison.claim_relation_diagnostics
    lines.extend(
        [
            "",
            "### Claim relationship coverage",
            "",
            "| Total claims | Fully supported | Partially supported | Contradicted | Unassessed | Coverage |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
            (
                f"| {diagnostics.total_claim_count} | {diagnostics.fully_supported_count} | "
                f"{diagnostics.partially_supported_count} | {diagnostics.contradicted_count} | "
                f"{diagnostics.unassessed_claim_count} | "
                f"{_percent(_ratio_percent(diagnostics.claim_relation_coverage))} |"
            ),
        ]
    )
    if diagnostics.unassessed_claim_ids:
        lines.extend(
            [
                "",
                "**Unassessed claims:** "
                + ", ".join(f"`{_inline(claim_id)}`" for claim_id in diagnostics.unassessed_claim_ids),
            ]
        )
    lines.extend(
        [
            "",
            "Coverage reports how many extracted Claims received one locally validated three-way relation. "
            "It does not measure whether a relation is correct and does not modify the reliability score.",
        ]
    )
    lines.extend(["", f"**Conclusion stability:** {_inline(comparison.conclusion_stability)}"])

    lines.extend(["", "### Experimental setting differences", ""])
    if comparison.setting_differences:
        lines.extend(
            [
                "| Setting | Paper | Reproduction | Severity | Likely effect | Evidence |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for difference in comparison.setting_differences:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(difference.setting),
                        _cell(difference.paper_value),
                        _cell(difference.reproduction_value),
                        _cell(difference.severity.value),
                        _cell(difference.likely_effect),
                        _cell(_citations(difference.citations)),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No setting differences were identified from the supplied evidence.")

    lines.extend(["", "### Deterministic setting checks", ""])
    if comparison.deterministic_setting_checks:
        lines.extend(
            [
                "| Setting | Paper values | Reproduction values | Status | Evidence |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for check in comparison.deterministic_setting_checks:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(check.setting),
                        _cell(", ".join(check.paper_values)),
                        _cell(", ".join(check.reproduction_values)),
                        _cell(check.status.value),
                        _cell(_citations([*check.paper_citations, *check.reproduction_citations])),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No supported experiment settings were found on both sides.")
    if comparison.unresolved_questions:
        lines.extend(["", "### Unresolved questions", "", *_bullets(comparison.unresolved_questions)])

    if graph is not None:
        metrics = graph.metrics
        lines.extend(
            [
                "",
                "## Claim-Evidence-Result graph",
                "",
                graph.summary,
                "",
                "| Nodes | Edges | Claim evidence coverage | Claim source coverage | Reproduction-assessed claims | "
                "Contradiction ratio | Orphan claims | Source closure | Setting coverage | Full support | "
                "Partial support |",
                "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                (
                    f"| {len(graph.nodes)} | {len(graph.edges)} | {metrics.claim_evidence_coverage:.2f} | "
                    f"{metrics.claim_source_coverage:.2f} | {metrics.reproduction_assessment_coverage:.2f} | "
                    f"{metrics.contradiction_ratio:.2f} | {metrics.orphan_claim_count} | "
                    f"{metrics.source_closure_ratio:.2f} | {metrics.experiment_setting_coverage:.2f} | "
                    f"{metrics.reproduction_support_ratio:.2f} | "
                    f"{metrics.reproduction_partial_support_ratio:.2f} |"
                ),
                "",
                (
                    "Claim source coverage counts direct Claim citations. Reproduction-assessed claims count Claim "
                    "relations from an assessment that directly depends on a locally recalculated reproduction "
                    "result; this does not prove that the supplied reproduction is independent. Graph relations and "
                    "coverage metrics are validated locally, but inferred relations do not become observations "
                    "merely because they appear in the graph."
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Reliability rubric",
            "",
            "| Dimension | Weight | Status | Score | Rationale | Evidence gaps | Evidence |",
            "| --- | ---: | --- | ---: | --- | --- | --- |",
        ]
    )
    for dimension in score.dimensions:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(dimension.name.value),
                    f"{dimension.weight:.0%}",
                    _cell(dimension.assessment_status.value),
                    _score(dimension.score, suffix=False),
                    _cell(dimension.rationale),
                    _cell("; ".join(dimension.evidence_gaps)),
                    _cell(_citations(dimension.citations)),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Verdicts",
            "",
            f"**Reproduction:** {score.reproduction_verdict}",
            "",
            f"**Experimental rigor:** {score.experimental_rigor_verdict}",
            "",
            "### Major strengths",
            "",
            *_bullets(score.major_strengths),
            "",
            "### Major risks",
            "",
            *_bullets(score.major_risks),
            "",
            "### Recommended checks",
            "",
            *_bullets(score.recommended_checks),
            "",
            "## Missing reproduction details",
            "",
        ]
    )
    if claims.missing_details:
        for detail in claims.missing_details:
            lines.append(
                f"- **{_inline(detail.item)}** ({detail.severity.value}): {_inline(detail.impact)} "
                f"{_citations(detail.citations)}".rstrip()
            )
    else:
        lines.append("- No missing details were extracted.")

    all_warnings = [*claims.warnings, *comparison.warnings, *score.warnings]
    lines.extend(["", "## Source inventory", ""])
    lines.extend(
        [
            "| Source | Path | Type | SHA-256 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for source in score.sources:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(source.source_id),
                    _cell(source.source_path),
                    _cell(source.source_type.value),
                    f"`{source.content_hash}`",
                ]
            )
            + " |"
        )
    if not score.sources:
        lines.append("| - | - | - | No source lineage recorded. |")

    lines.extend(["", "## Audit trail", ""])
    lines.append(
        f"Source runs: `{claims.run_id}`, `{comparison.run_id}`, `{score.run_id}`. "
        "Metric aggregates and the final weighted score are calculated deterministically by ReproScope."
    )
    lines.extend(
        [
            "",
            "### Upstream artifact inventory",
            "",
            "| Role | Run | Path | Type | Schema | File SHA-256 | Payload SHA-256 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for artifact in artifact_inventory:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(artifact.role),
                    _cell(artifact.run_id),
                    _cell(artifact.relative_path),
                    _cell(artifact.artifact_type),
                    _cell(artifact.schema_version),
                    f"`{artifact.content_hash}`",
                    f"`{artifact.payload_hash}`" if artifact.payload_hash else "-",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "### Direct parent lineage",
            "",
            "| Child role | Child run | Parent role | Parent run | Parent path | Parent file SHA-256 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    parent_count = 0
    for artifact in artifact_inventory:
        for parent in artifact.direct_parents:
            parent_count += 1
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(artifact.role),
                        _cell(artifact.run_id),
                        _cell(parent.role),
                        _cell(parent.run_id),
                        _cell(parent.relative_path),
                        f"`{parent.content_hash}`",
                    ]
                )
                + " |"
            )
    if parent_count == 0:
        lines.append("| - | - | - | - | - | No direct parent artifacts recorded. |")

    if comparison.group_filters:
        rendered_filters = ", ".join(f"{key}={value}" for key, value in comparison.group_filters.items())
        lines.append(f"Experiment group filters: `{_inline(rendered_filters)}`.")
    if all_warnings:
        lines.extend(["", "Warnings:"])
        for warning in all_warnings:
            lines.append(f"- `{warning.code}`: {_inline(warning.message)}")
    return "\n".join(lines)


def _append_isac_profile(lines: list[str], claims: ExtractClaimsResult) -> None:
    activation = claims.domain_profile_activation
    analysis = claims.isac_analysis
    if activation is None or analysis is None:
        return

    lines.extend(
        [
            "",
            "## ISAC physical-layer audit",
            "",
            (
                f"Profile `{activation.effective_profile.value}` version `{activation.profile_version}` was "
                f"activated by `{activation.activation_source.value}` with detector confidence "
                f"`{activation.confidence:.2f}`. Domain findings are advisory and do not affect the generic score."
            ),
            "",
            "| System type | Sensing topology | Waveform | Research method | Evidence level | Evidence |",
            "| --- | --- | --- | --- | --- | --- |",
            (
                "| "
                + " | ".join(
                    [
                        _cell(analysis.system_type.value),
                        _cell(", ".join(item.value for item in analysis.sensing_topologies)),
                        _cell(", ".join(item.value for item in analysis.waveforms)),
                        _cell(", ".join(item.value for item in analysis.research_methods)),
                        _cell(analysis.evidence_level.value),
                        _cell(_citations(analysis.classification_citations)),
                    ]
                )
                + " |"
            ),
            "",
            "### ISAC metrics",
            "",
            (
                "| Canonical metric | Reported name | Value | Unit | Scale | Present context | "
                "Missing context | Evidence |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if analysis.metrics:
        for metric in analysis.metrics:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(metric.canonical_name),
                        _cell(metric.reported_name),
                        _cell(metric.reported_value),
                        _cell(metric.unit),
                        _cell(metric.scale.value),
                        _cell(", ".join(metric.required_context_present)),
                        _cell(", ".join(metric.missing_required_context)),
                        _cell(_citations(metric.citations)),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | unknown | - | No registered ISAC metrics were extracted. | - |")

    lines.extend(
        [
            "",
            "### ISAC assumptions",
            "",
            "| Assumption | Value | Evidence kind | Evidence |",
            "| --- | --- | --- | --- |",
        ]
    )
    if analysis.assumptions:
        for assumption in analysis.assumptions:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(assumption.name),
                        _cell(assumption.value),
                        _cell(assumption.evidence_kind.value),
                        _cell(_citations(assumption.citations)),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | unknown | No registered ISAC assumptions were extracted. |")

    lines.extend(
        [
            "",
            "### ISAC risk findings",
            "",
            "| Rule | Status | Finding | Evidence kind | Missing evidence | Review | Evidence |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for finding in analysis.findings:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(finding.rule_id),
                    _cell(finding.status.value),
                    _cell(f"{finding.summary} {finding.rationale}"),
                    _cell(finding.evidence_kind.value),
                    _cell("; ".join(finding.missing_evidence)),
                    "yes" if finding.review_required else "no",
                    _cell(_citations(finding.citations)),
                ]
            )
            + " |"
        )
    if analysis.limitations:
        lines.extend(["", "Profile limitations:", *_bullets(analysis.limitations)])


def _citations(citations: Iterable[EvidenceCitation]) -> str:
    return ", ".join(f"[{citation.source_id}@{citation.locator}]" for citation in citations) or "-"


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.6g}"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.4g}%"


def _ratio_percent(value: float | None) -> float | None:
    return None if value is None else value * 100


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
