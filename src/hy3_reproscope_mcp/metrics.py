"""Deterministic reproduction metric aggregation and delta classification."""

from __future__ import annotations

import statistics
from itertools import product

from .config import Settings
from .errors import GroupFilterError
from .loaders import (
    OMITTED_GROUP_VALUES,
    LoadedBundle,
    canonical_group_dimension,
    load_sources,
    source_group_values,
)
from .metric_registry import (
    canonical_metric_name,
    has_metric_unit_contract,
    normalize_paper_value,
    resolve_metric_unit,
    resolve_scale,
    scales_are_compatible,
)
from .models import (
    CompareReproductionResult,
    DifferenceSeverity,
    GroupMetricComparison,
    GroupMetricStabilitySummary,
    MetricComparisonStatus,
    MetricDataQuality,
    MetricScale,
    ToolWarning,
)

NO_DIFFERENCE_MAX_PERCENT = 0.5
MINOR_DIFFERENCE_MAX_PERCENT = 2.0
MATERIAL_DIFFERENCE_MAX_PERCENT = 5.0
MAX_GROUP_COMBINATIONS = 100


def compute_metric_differences(
    result: CompareReproductionResult,
    reproduction_bundle: LoadedBundle,
) -> None:
    """Replace model-proposed aggregates with values computed from loaded tabular data."""

    unresolved_mappings: list[str] = []
    undefined_relative: list[str] = []
    undefined_db_relative: list[str] = []
    unsafe_aggregations: list[str] = []
    alias_mismatches: list[str] = []
    unresolved_scales: list[str] = []
    unresolved_units: list[str] = []
    incompatible_scales: list[str] = []
    scale_conversions: list[str] = []
    unit_conversions: list[str] = []
    excluded_values: list[str] = []
    computed = False
    sources_by_id = {source.source_id: source for source in reproduction_bundle.sources}
    for comparison in result.metric_comparisons:
        suggested_paper_scale = comparison.paper_scale
        comparison.reproduced_value = None
        comparison.reproduced_stddev = None
        comparison.sample_count = None
        comparison.data_quality = None
        comparison.normalized_paper_value = None
        comparison.absolute_delta = None
        comparison.relative_delta_percent = None
        comparison.severity = DifferenceSeverity.UNKNOWN
        comparison.canonical_metric = None
        comparison.paper_scale = MetricScale.UNKNOWN
        comparison.reproduction_scale = MetricScale.UNKNOWN
        comparison.normalized_scale = MetricScale.UNKNOWN
        comparison.scale_conversion = None
        source = sources_by_id.get(comparison.reproduction_source_id or "")
        if source and source.ambiguous_group_columns:
            comparison.computation_status = MetricComparisonStatus.AMBIGUOUS_REPRODUCTION_GROUP
            comparison.conclusion = (
                "Local aggregation was not performed because the mapped source contains multiple experiment groups."
            )
            group_description = ", ".join(
                f"{column}={list(source.group_values[column])}" for column in source.ambiguous_group_columns
            )
            unsafe_aggregations.append(f"{comparison.metric} ({source.source_id}: {group_description})")
            continue
        reproduction_column = comparison.reproduction_column or ""
        stats = source.numeric_stats.get(reproduction_column) if source else None
        if not stats:
            comparison.computation_status = MetricComparisonStatus.UNMATCHED_REPRODUCTION_METRIC
            unresolved_mappings.append(comparison.metric)
            continue

        paper_metric = canonical_metric_name(comparison.metric)
        reproduction_metric = canonical_metric_name(reproduction_column)
        if paper_metric and reproduction_metric and paper_metric != reproduction_metric:
            comparison.computation_status = MetricComparisonStatus.METRIC_ALIAS_MISMATCH
            comparison.conclusion = (
                "Local comparison was not performed because the paper metric and reproduction column map to "
                "different registered metrics."
            )
            alias_mismatches.append(f"{comparison.metric}->{reproduction_column}")
            continue
        comparison.canonical_metric = paper_metric or reproduction_metric
        comparison.reproduced_value = float(stats["mean"])
        comparison.reproduced_stddev = float(stats["stddev"])
        comparison.sample_count = int(stats["count"])
        comparison.data_quality = _metric_data_quality(stats)
        excluded_count = (
            comparison.data_quality.missing_count
            + comparison.data_quality.non_numeric_count
            + comparison.data_quality.non_finite_count
        )
        if excluded_count:
            excluded_values.append(
                f"{comparison.metric} ({source.source_id}.{reproduction_column}: "
                f"valid={comparison.data_quality.valid_numeric_count}/{comparison.data_quality.total_count}, "
                f"missing={comparison.data_quality.missing_count}, "
                f"non_numeric={comparison.data_quality.non_numeric_count}, "
                f"non_finite={comparison.data_quality.non_finite_count})"
            )
        reproduction_resolution = resolve_scale(
            metric_name=reproduction_column,
            unit=None,
            minimum=float(stats["min"]),
            maximum=float(stats["max"]),
        )
        comparison.reproduction_scale = reproduction_resolution.scale
        if comparison.paper_value is None:
            comparison.computation_status = MetricComparisonStatus.MISSING_PAPER_VALUE
            comparison.normalized_scale = comparison.reproduction_scale
            unresolved_mappings.append(comparison.metric)
            continue

        paper_resolution = resolve_scale(
            metric_name=comparison.metric,
            unit=comparison.unit,
            minimum=comparison.paper_value,
            maximum=comparison.paper_value,
            suggested=suggested_paper_scale,
        )
        comparison.paper_scale = paper_resolution.scale
        if comparison.paper_scale is MetricScale.UNKNOWN or comparison.reproduction_scale is MetricScale.UNKNOWN:
            comparison.computation_status = MetricComparisonStatus.UNRESOLVED_METRIC_SCALE
            comparison.conclusion = (
                "Local comparison was not performed because the paper or reproduction metric scale is unresolved."
            )
            unresolved_scales.append(
                f"{comparison.metric} (paper={comparison.paper_scale.value}, "
                f"reproduction={comparison.reproduction_scale.value})"
            )
            continue
        if not scales_are_compatible(comparison.paper_scale, comparison.reproduction_scale):
            comparison.computation_status = MetricComparisonStatus.INCOMPATIBLE_METRIC_SCALE
            comparison.conclusion = (
                "Local comparison was not performed because the paper and reproduction metric scales are not "
                "safely convertible."
            )
            incompatible_scales.append(
                f"{comparison.metric} ({comparison.paper_scale.value}->{comparison.reproduction_scale.value})"
            )
            continue

        # A metric-name suffix (for example ``latency_ms``) is an explicit unit
        # declaration just like a separate ``unit`` field.  Treat both sides
        # symmetrically so safe conversion does not depend on which side used
        # the structured field.
        paper_unit = resolve_metric_unit(comparison.metric, comparison.unit, infer_from_name=True)
        reproduction_unit = resolve_metric_unit(reproduction_column, None, infer_from_name=True)
        if has_metric_unit_contract(comparison.metric) or has_metric_unit_contract(reproduction_column):
            paper_unit_declared = bool(comparison.unit) or paper_unit is not None
            reproduction_unit_declared = reproduction_unit is not None
            if (
                paper_unit_declared != reproduction_unit_declared
                or (paper_unit_declared and paper_unit is None)
                or (reproduction_unit_declared and reproduction_unit is None)
            ):
                comparison.computation_status = MetricComparisonStatus.UNRESOLVED_METRIC_UNIT
                comparison.conclusion = (
                    "Local comparison was not performed because both sides must provide a supported, explicit "
                    "unit for this metric-specific conversion contract."
                )
                paper_unit_label = comparison.unit or (paper_unit.input_unit if paper_unit else "missing")
                reproduction_unit_label = reproduction_unit.input_unit if reproduction_unit else "missing"
                unresolved_units.append(
                    f"{comparison.metric} (paper={paper_unit_label}, reproduction={reproduction_unit_label})"
                )
                continue
        unit_conversion: str | None = None
        if (
            paper_unit
            and reproduction_unit
            and paper_unit.canonical_unit == reproduction_unit.canonical_unit
            and paper_unit.factor_to_canonical != reproduction_unit.factor_to_canonical
        ):
            conversion_factor = reproduction_unit.factor_to_canonical / paper_unit.factor_to_canonical
            comparison.reproduced_value *= conversion_factor
            if comparison.reproduced_stddev is not None:
                comparison.reproduced_stddev *= conversion_factor
            unit_conversion = f"{reproduction_unit.input_unit}_to_{paper_unit.input_unit}"
            unit_conversions.append(f"{comparison.metric} ({unit_conversion})")

        comparison.normalized_paper_value, scale_conversion = normalize_paper_value(
            comparison.paper_value,
            paper_scale=comparison.paper_scale,
            reproduction_scale=comparison.reproduction_scale,
        )
        comparison.scale_conversion = scale_conversion
        if unit_conversion:
            comparison.scale_conversion = (
                f"{comparison.scale_conversion};{unit_conversion}" if comparison.scale_conversion else unit_conversion
            )
        comparison.normalized_scale = comparison.reproduction_scale
        if scale_conversion:
            scale_conversions.append(f"{comparison.metric} ({scale_conversion})")

        delta = comparison.reproduced_value - comparison.normalized_paper_value
        comparison.absolute_delta = round(delta, 6)
        if comparison.normalized_scale is MetricScale.DECIBEL:
            undefined_db_relative.append(comparison.metric)
        elif comparison.normalized_paper_value != 0:
            comparison.relative_delta_percent = round(delta / abs(comparison.normalized_paper_value) * 100, 4)
            comparison.severity = delta_severity(abs(comparison.relative_delta_percent))
        else:
            undefined_relative.append(comparison.metric)
        comparison.computation_status = MetricComparisonStatus.COMPUTED
        computed = True

    if computed:
        result.warnings.append(
            ToolWarning(
                code="METRIC_VALUES_RECALCULATED",
                message="Reproduction means, standard deviations, sample counts, and deltas were computed locally.",
            )
        )
    if undefined_relative:
        result.warnings.append(
            ToolWarning(
                code="RELATIVE_DELTA_UNDEFINED",
                message=(
                    "Relative deltas and severity are unknown because the paper value is zero: "
                    + ", ".join(sorted(set(undefined_relative)))
                ),
            )
        )
    if undefined_db_relative:
        result.warnings.append(
            ToolWarning(
                code="DB_RELATIVE_DELTA_UNDEFINED",
                message=(
                    "Only absolute dB deltas were computed; relative percentages and severity are undefined: "
                    + ", ".join(sorted(set(undefined_db_relative)))
                ),
            )
        )
    if unsafe_aggregations:
        message = (
            "Whole-column metric aggregation was blocked because the mapped source contains multiple dataset, "
            "split, scenario, or method groups: " + "; ".join(sorted(set(unsafe_aggregations)))
        )
        result.warnings.append(
            ToolWarning(
                code="UNSAFE_METRIC_AGGREGATION_BLOCKED",
                message=message,
            )
        )
        result.unresolved_questions.append(
            "Filter each reproduction result file to one dataset/split/scenario/method group before comparison."
        )
    if alias_mismatches:
        result.warnings.append(
            ToolWarning(
                code="METRIC_ALIAS_MISMATCH",
                message=(
                    "Registered paper metrics do not match the mapped reproduction columns: "
                    + ", ".join(sorted(set(alias_mismatches)))
                ),
            )
        )
    if unresolved_scales:
        result.warnings.append(
            ToolWarning(
                code="METRIC_SCALE_UNRESOLVED",
                message="Could not determine compatible metric scales: " + "; ".join(sorted(set(unresolved_scales))),
            )
        )
    if unresolved_units:
        result.warnings.append(
            ToolWarning(
                code="METRIC_UNIT_UNRESOLVED",
                message=(
                    "Metric comparison was withheld because a metric-specific unit was missing or unsupported: "
                    + "; ".join(sorted(set(unresolved_units)))
                ),
            )
        )
    if incompatible_scales:
        result.warnings.append(
            ToolWarning(
                code="METRIC_SCALE_INCOMPATIBLE",
                message=(
                    "Automatic linear/dB conversion is disabled because the transformation is metric-dependent: "
                    + ", ".join(sorted(set(incompatible_scales)))
                ),
            )
        )
    if scale_conversions:
        result.warnings.append(
            ToolWarning(
                code="METRIC_SCALE_CONVERTED",
                message=(
                    "Paper values were deterministically converted to the reproduction scale: "
                    + ", ".join(sorted(set(scale_conversions)))
                ),
            )
        )
    if unit_conversions:
        result.warnings.append(
            ToolWarning(
                code="METRIC_UNIT_CONVERTED",
                message=(
                    "Metric values were deterministically converted between compatible units: "
                    + ", ".join(sorted(set(unit_conversions)))
                ),
            )
        )
    if excluded_values:
        result.warnings.append(
            ToolWarning(
                code="METRIC_VALUES_EXCLUDED",
                message=(
                    "Some mapped result-column values were excluded from deterministic statistics: "
                    + "; ".join(sorted(set(excluded_values)))
                ),
            )
        )
    if unresolved_mappings:
        result.warnings.append(
            ToolWarning(
                code="METRIC_MAPPING_UNRESOLVED",
                message=("Could not deterministically compute metrics: " + ", ".join(sorted(set(unresolved_mappings)))),
            )
        )


def validate_group_analysis_request(
    reproduction_bundle: LoadedBundle,
    *,
    group_by: list[str],
    group_filters: dict[str, str],
) -> None:
    """Reject missing, redundant, truncated, or unbounded group-analysis requests."""

    if not group_by:
        return
    filtered_dimensions = {canonical_group_dimension(column) for column in group_filters}
    overlap = sorted(set(group_by) & filtered_dimensions)
    if overlap:
        raise GroupFilterError(
            "group_by repeats dimensions already fixed by group_filters: " + ", ".join(overlap),
            hint="Remove the repeated group_by dimensions or the corresponding filters.",
        )

    found_dimensions: set[str] = set()
    candidate_count = 0
    for source in reproduction_bundle.sources:
        values_by_dimension = source_group_values(source, group_by)
        found_dimensions.update(values_by_dimension)
        if any(OMITTED_GROUP_VALUES in values for values in values_by_dimension.values()):
            raise GroupFilterError(
                f"Group analysis exceeds the discoverable value limit in {source.source_path}.",
                hint="Apply group_filters first or reduce the number of distinct group values.",
            )
        if len(values_by_dimension) == len(group_by):
            combinations = 1
            for values in values_by_dimension.values():
                combinations *= len(values)
            candidate_count += combinations

    missing = [dimension for dimension in group_by if dimension not in found_dimensions]
    if missing:
        raise GroupFilterError(
            "Group-by dimensions were not found in any structured input source: " + ", ".join(missing),
            hint="Use dimensions listed in the source group_values inventory.",
        )
    if candidate_count == 0:
        raise GroupFilterError(
            "No structured input source contains every requested group-by dimension.",
            hint="Request fewer dimensions or analyze the sources separately.",
        )
    if candidate_count > MAX_GROUP_COMBINATIONS:
        raise GroupFilterError(
            f"Group analysis would inspect {candidate_count} candidate combinations; the limit is "
            f"{MAX_GROUP_COMBINATIONS}.",
            hint="Apply group_filters or request fewer group_by dimensions.",
        )


def compute_group_metric_comparisons(
    result: CompareReproductionResult,
    *,
    reproduction_paths: list[str],
    reproduction_bundle: LoadedBundle,
    group_by: list[str],
    settings: Settings,
) -> None:
    """Compute mapped reproduction metrics independently for each requested group."""

    result.group_metric_comparisons = []
    if not group_by:
        return

    source_inputs = {
        source.source_id: (raw_path, source)
        for raw_path, source in zip(reproduction_paths, reproduction_bundle.sources, strict=True)
    }
    skipped_sources: set[str] = set()
    for comparison in result.metric_comparisons:
        source_input = source_inputs.get(comparison.reproduction_source_id or "")
        if source_input is None:
            continue
        raw_path, source = source_input
        values_by_dimension = source_group_values(source, group_by)
        if len(values_by_dimension) != len(group_by):
            skipped_sources.add(source.source_id)
            continue
        ordered_values = [values_by_dimension[dimension] for dimension in group_by]
        for values in product(*ordered_values):
            group = dict(zip(group_by, values, strict=True))
            filters = {**source.applied_group_filters, **group}
            try:
                filtered_bundle = load_sources(
                    [raw_path],
                    role="reproduction group",
                    settings=settings,
                    source_id_prefix="group_repro",
                    group_filters=filters,
                )
            except GroupFilterError:
                continue
            candidate = comparison.model_copy(
                deep=True,
                update={"reproduction_source_id": "group_repro_1"},
            )
            temporary = CompareReproductionResult(
                run_id=result.run_id,
                summary=result.summary,
                conclusion_stability=result.conclusion_stability,
                metric_comparisons=[candidate],
            )
            compute_metric_differences(temporary, filtered_bundle)
            computed = temporary.metric_comparisons[0]
            if computed.computation_status is MetricComparisonStatus.COMPUTED:
                rendered_group = ", ".join(f"{key}={value}" for key, value in group.items())
                computed.conclusion = f"Locally recalculated for experiment group: {rendered_group}."
            result.group_metric_comparisons.append(
                GroupMetricComparison.model_validate(
                    {
                        **computed.model_dump(mode="json"),
                        "group": group,
                        "reproduction_source_id": source.source_id,
                    }
                )
            )

    if result.group_metric_comparisons:
        result.warnings.append(
            ToolWarning(
                code="GROUP_METRIC_COMPARISONS_COMPUTED",
                message=(
                    f"Computed {len(result.group_metric_comparisons)} group-scoped metric comparisons locally; "
                    "global computation continues to follow the existing aggregation-safety rules."
                ),
            )
        )
        excluded_groups = [
            comparison
            for comparison in result.group_metric_comparisons
            if comparison.data_quality is not None and comparison.data_quality.valid_ratio < 1
        ]
        if excluded_groups:
            rendered = []
            for comparison in excluded_groups:
                quality = comparison.data_quality
                if quality is None:  # pragma: no cover - narrowed by the comprehension
                    continue
                group = ", ".join(f"{key}={value}" for key, value in comparison.group.items())
                rendered.append(
                    f"{comparison.metric} [{group}] "
                    f"(valid={quality.valid_numeric_count}/{quality.total_count}, "
                    f"missing={quality.missing_count}, non_numeric={quality.non_numeric_count}, "
                    f"non_finite={quality.non_finite_count})"
                )
            result.warnings.append(
                ToolWarning(
                    code="GROUP_METRIC_VALUES_EXCLUDED",
                    message=(
                        "Some group-scoped result-column values were excluded from deterministic statistics: "
                        + "; ".join(rendered)
                    ),
                )
            )
        manual_filter_question = (
            "Filter each reproduction result file to one dataset/split/scenario/method group before comparison."
        )
        if manual_filter_question in result.unresolved_questions:
            result.unresolved_questions.remove(manual_filter_question)
        result.unresolved_questions.append(
            "Review group_metric_comparisons; global aggregation remains intentionally blocked for mixed sources."
        )
    if skipped_sources:
        result.warnings.append(
            ToolWarning(
                code="GROUP_BY_DIMENSION_MISSING_FOR_SOURCE",
                message=(
                    "No group-scoped metrics were computed for sources missing one or more requested dimensions: "
                    + ", ".join(sorted(skipped_sources))
                ),
            )
        )
    _compute_group_stability_summaries(result)


def _metric_data_quality(stats: dict[str, float | int]) -> MetricDataQuality:
    return MetricDataQuality(
        total_count=int(stats["total_count"]),
        valid_numeric_count=int(stats["count"]),
        missing_count=int(stats["missing_count"]),
        non_numeric_count=int(stats["non_numeric_count"]),
        non_finite_count=int(stats["ignored_non_finite"]),
        valid_ratio=float(stats["valid_ratio"]),
    )


def _compute_group_stability_summaries(result: CompareReproductionResult) -> None:
    grouped: dict[tuple[str, str, str], list[GroupMetricComparison]] = {}
    for comparison in result.group_metric_comparisons:
        if (
            comparison.computation_status is not MetricComparisonStatus.COMPUTED
            or comparison.reproduced_value is None
            or comparison.reproduction_source_id is None
            or comparison.reproduction_column is None
        ):
            continue
        key = (
            comparison.reproduction_source_id,
            comparison.reproduction_column,
            comparison.metric,
        )
        grouped.setdefault(key, []).append(comparison)

    result.group_stability_summaries = []
    for (source_id, column, metric), comparisons in grouped.items():
        if len(comparisons) < 2:
            continue
        values = [comparison.reproduced_value for comparison in comparisons]
        minimum = min(comparisons, key=lambda comparison: comparison.reproduced_value or 0)
        maximum = max(comparisons, key=lambda comparison: comparison.reproduced_value or 0)
        normalized_paper_value = next(
            (
                comparison.normalized_paper_value
                for comparison in comparisons
                if comparison.normalized_paper_value is not None
            ),
            None,
        )
        normalized_scale = comparisons[0].normalized_scale
        value_range = maximum.reproduced_value - minimum.reproduced_value
        range_percent = None
        if normalized_paper_value not in {None, 0} and normalized_scale is not MetricScale.DECIBEL:
            range_percent = round(value_range / abs(normalized_paper_value) * 100, 4)
        delta_candidates = [comparison for comparison in comparisons if comparison.absolute_delta is not None]
        max_delta = (
            max(delta_candidates, key=lambda comparison: abs(comparison.absolute_delta or 0))
            if delta_candidates
            else None
        )
        result.group_stability_summaries.append(
            GroupMetricStabilitySummary(
                metric=metric,
                canonical_metric=comparisons[0].canonical_metric,
                reproduction_source_id=source_id,
                reproduction_column=column,
                group_by=list(result.group_by),
                group_count=len(comparisons),
                group_mean=round(statistics.fmean(values), 6),
                group_mean_stddev=round(statistics.stdev(values), 6),
                minimum_group=minimum.group,
                minimum_value=minimum.reproduced_value,
                maximum_group=maximum.group,
                maximum_value=maximum.reproduced_value,
                value_range=round(value_range, 6),
                normalized_paper_value=normalized_paper_value,
                normalized_scale=normalized_scale,
                range_percent_of_reported=range_percent,
                max_absolute_paper_delta=(
                    round(abs(max_delta.absolute_delta), 6)
                    if max_delta is not None and max_delta.absolute_delta is not None
                    else None
                ),
                max_delta_group=max_delta.group if max_delta is not None else None,
            )
        )
    if result.group_stability_summaries:
        result.warnings.append(
            ToolWarning(
                code="GROUP_STABILITY_SUMMARIES_COMPUTED",
                message=(
                    f"Computed {len(result.group_stability_summaries)} descriptive cross-group stability summaries "
                    "without converting them into reliability scores."
                ),
            )
        )


def delta_severity(relative_delta_percent: float) -> DifferenceSeverity:
    """Classify an absolute relative difference using documented fixed thresholds."""

    if relative_delta_percent <= NO_DIFFERENCE_MAX_PERCENT:
        return DifferenceSeverity.NONE
    if relative_delta_percent <= MINOR_DIFFERENCE_MAX_PERCENT:
        return DifferenceSeverity.MINOR
    if relative_delta_percent <= MATERIAL_DIFFERENCE_MAX_PERCENT:
        return DifferenceSeverity.MATERIAL
    return DifferenceSeverity.CRITICAL
