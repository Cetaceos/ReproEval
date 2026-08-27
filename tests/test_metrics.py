from __future__ import annotations

import pytest

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.loaders import load_sources
from hy3_reproscope_mcp.metrics import compute_metric_differences
from hy3_reproscope_mcp.models import CompareReproductionResult, MetricComparison


def test_zero_paper_value_keeps_relative_delta_and_severity_unknown(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("accuracy\n0.2\n0.4\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = CompareReproductionResult(
        run_id="compare_test",
        summary="Zero-valued paper baseline.",
        metric_comparisons=[
            MetricComparison(
                metric="accuracy",
                reproduction_source_id="repro_1",
                reproduction_column="accuracy",
                paper_value=0,
                severity="critical",
                conclusion="The model-proposed severity must be replaced.",
            )
        ],
        conclusion_stability="Relative change is undefined.",
    )

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.reproduced_value == pytest.approx(0.3)
    assert comparison.absolute_delta == pytest.approx(0.3)
    assert comparison.relative_delta_percent is None
    assert comparison.severity.value == "unknown"
    assert comparison.computation_status.value == "computed"
    assert any(warning.code == "RELATIVE_DELTA_UNDEFINED" for warning in result.warnings)


def test_metric_comparison_discloses_excluded_values(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text(
        "run,accuracy\n1,0.8\n2,\n3,not-a-number\n4,Infinity\n5,0.9\n",
        encoding="utf-8",
    )
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="accuracy", column="accuracy", paper_value=0.9)

    compute_metric_differences(result, bundle)

    quality = result.metric_comparisons[0].data_quality
    assert quality is not None
    assert quality.total_count == 5
    assert quality.valid_numeric_count == 2
    assert quality.missing_count == 1
    assert quality.non_numeric_count == 1
    assert quality.non_finite_count == 1
    assert quality.valid_ratio == pytest.approx(0.4)
    warning = next(warning for warning in result.warnings if warning.code == "METRIC_VALUES_EXCLUDED")
    assert "valid=2/5" in warning.message
    assert "missing=1" in warning.message
    assert "non_numeric=1" in warning.message
    assert "non_finite=1" in warning.message


def test_unmatched_metric_does_not_keep_model_proposed_severity(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("accuracy\n0.8\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = CompareReproductionResult(
        run_id="compare_test",
        summary="Missing mapped column.",
        metric_comparisons=[
            MetricComparison(
                metric="f1",
                reproduction_source_id="repro_1",
                reproduction_column="missing_column",
                paper_value=0.7,
                severity="critical",
                conclusion="The mapping is unresolved.",
            )
        ],
        conclusion_stability="Insufficient evidence.",
    )

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.severity.value == "unknown"
    assert comparison.computation_status.value == "unmatched_reproduction_metric"


@pytest.mark.parametrize("group_column", ["dataset", "split", "scenario", "method"])
def test_mixed_experiment_groups_block_whole_column_aggregation(tmp_path, group_column) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text(
        f"{group_column},accuracy\nGroup-A,0.8\nGroup-B,0.9\n",
        encoding="utf-8",
    )
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = CompareReproductionResult(
        run_id="compare_test",
        summary="The model proposed an unsafe global comparison.",
        metric_comparisons=[
            MetricComparison(
                metric="accuracy",
                reproduction_source_id="repro_1",
                reproduction_column="accuracy",
                paper_value=0.85,
                reproduced_value=0.85,
                reproduced_stddev=0.07,
                sample_count=2,
                absolute_delta=0,
                relative_delta_percent=0,
                severity="none",
                conclusion="The global average appears to match.",
            )
        ],
        conclusion_stability="The conclusion depends on unsafe aggregation.",
    )

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.reproduced_value is None
    assert comparison.reproduced_stddev is None
    assert comparison.sample_count is None
    assert comparison.absolute_delta is None
    assert comparison.relative_delta_percent is None
    assert comparison.severity.value == "unknown"
    assert comparison.computation_status.value == "ambiguous_reproduction_group"
    assert "multiple experiment groups" in comparison.conclusion
    assert any(warning.code == "UNSAFE_METRIC_AGGREGATION_BLOCKED" for warning in result.warnings)
    assert any("Filter each reproduction result file" in question for question in result.unresolved_questions)


def _comparison_result(
    *,
    metric: str,
    column: str,
    paper_value: float,
    unit: str | None = None,
) -> CompareReproductionResult:
    return CompareReproductionResult(
        run_id="compare_test",
        summary="Scale contract test.",
        metric_comparisons=[
            MetricComparison(
                metric=metric,
                reproduction_source_id="repro_1",
                reproduction_column=column,
                paper_value=paper_value,
                unit=unit,
                severity="critical",
                conclusion="The model-proposed comparison must be validated locally.",
            )
        ],
        conclusion_stability="Depends on deterministic scale validation.",
    )


def test_percentage_paper_value_is_converted_to_fraction_scale(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("accuracy\n0.87\n0.89\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="accuracy", column="accuracy", paper_value=91, unit="%")

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.canonical_metric == "accuracy"
    assert comparison.paper_scale.value == "percentage"
    assert comparison.reproduction_scale.value == "fraction"
    assert comparison.normalized_scale.value == "fraction"
    assert comparison.normalized_paper_value == pytest.approx(0.91)
    assert comparison.scale_conversion == "percentage_to_fraction"
    assert comparison.reproduced_value == pytest.approx(0.88)
    assert comparison.absolute_delta == pytest.approx(-0.03)
    assert comparison.relative_delta_percent == pytest.approx(-3.2967)
    assert comparison.computation_status.value == "computed"
    assert any(warning.code == "METRIC_SCALE_CONVERTED" for warning in result.warnings)


def test_fraction_paper_value_is_converted_to_percentage_scale(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("accuracy_percent\n87\n89\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="accuracy", column="accuracy_percent", paper_value=0.91, unit="fraction")

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.normalized_paper_value == pytest.approx(91)
    assert comparison.reproduced_value == pytest.approx(88)
    assert comparison.scale_conversion == "fraction_to_percentage"
    assert comparison.absolute_delta == pytest.approx(-3)
    assert comparison.relative_delta_percent == pytest.approx(-3.2967)


def test_linear_metric_uses_relative_delta_on_matching_scale(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("latency_ms\n14.2\n14.4\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="latency", column="latency_ms", paper_value=14, unit="ms")

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.canonical_metric == "latency"
    assert comparison.normalized_scale.value == "linear"
    assert comparison.normalized_paper_value == pytest.approx(14)
    assert comparison.reproduced_value == pytest.approx(14.3)
    assert comparison.relative_delta_percent == pytest.approx(2.1429)
    assert comparison.severity.value == "material"


def test_linear_time_units_are_converted_when_both_sides_are_explicit(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("latency_ms\n1000\n1200\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="latency", column="latency_ms", paper_value=1.05, unit="s")

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.reproduced_value == pytest.approx(1.1)
    assert comparison.reproduced_stddev == pytest.approx(0.1414213562)
    assert comparison.normalized_paper_value == pytest.approx(1.05)
    assert comparison.absolute_delta == pytest.approx(0.05)
    assert comparison.relative_delta_percent == pytest.approx(4.7619)
    assert comparison.scale_conversion == "ms_to_s"
    assert any(warning.code == "METRIC_UNIT_CONVERTED" for warning in result.warnings)
    assert not any(warning.code == "METRIC_SCALE_CONVERTED" for warning in result.warnings)


@pytest.mark.parametrize(
    ("column", "paper_unit"),
    [("latency", "s"), ("latency_ms", None)],
)
def test_linear_metric_with_one_sided_unit_is_withheld(tmp_path, column: str, paper_unit: str | None) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text(f"{column}\n14\n16\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="latency", column=column, paper_value=1.0, unit=paper_unit)

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.computation_status.value == "unresolved_metric_unit"
    assert comparison.reproduced_value == pytest.approx(15)
    assert comparison.absolute_delta is None
    assert comparison.relative_delta_percent is None
    assert comparison.severity.value == "unknown"
    assert any(warning.code == "METRIC_UNIT_UNRESOLVED" for warning in result.warnings)


def test_unsupported_explicit_metric_unit_is_withheld(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("latency\n14\n16\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="latency", column="latency", paper_value=14, unit="ticks")

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.computation_status.value == "unresolved_metric_unit"
    assert comparison.absolute_delta is None
    assert any(warning.code == "METRIC_UNIT_UNRESOLVED" for warning in result.warnings)


@pytest.mark.parametrize(
    ("metric", "column", "paper_value", "expected_reproduced", "expected_delta", "expected_conversion"),
    [
        ("throughput_mbps", "throughput_kbps", 1.05, 1.1, 0.05, "kbps_to_mbps"),
        (
            "spectral_efficiency_mbps_hz",
            "spectral_efficiency_kbps_hz",
            1.05,
            1.1,
            0.05,
            "kbps_hz_to_mbps_hz",
        ),
    ],
)
def test_metric_name_units_are_converted_symmetrically(
    tmp_path,
    metric: str,
    column: str,
    paper_value: float,
    expected_reproduced: float,
    expected_delta: float,
    expected_conversion: str,
) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text(f"{column}\n1000\n1200\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric=metric, column=column, paper_value=paper_value)

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.reproduced_value == pytest.approx(expected_reproduced)
    assert comparison.absolute_delta == pytest.approx(expected_delta)
    assert comparison.scale_conversion == expected_conversion
    assert any(warning.code == "METRIC_UNIT_CONVERTED" for warning in result.warnings)


def test_db_metric_only_computes_absolute_delta(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("snr_db\n9\n11\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="snr", column="snr_db", paper_value=9, unit="dB")

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.normalized_scale.value == "decibel"
    assert comparison.reproduced_value == pytest.approx(10)
    assert comparison.absolute_delta == pytest.approx(1)
    assert comparison.relative_delta_percent is None
    assert comparison.severity.value == "unknown"
    assert comparison.computation_status.value == "computed"
    assert any(warning.code == "DB_RELATIVE_DELTA_UNDEFINED" for warning in result.warnings)


def test_linear_db_mismatch_is_not_automatically_converted(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("snr_linear\n9\n11\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="snr", column="snr_linear", paper_value=9, unit="dB")

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.computation_status.value == "incompatible_metric_scale"
    assert comparison.absolute_delta is None
    assert comparison.relative_delta_percent is None
    assert comparison.severity.value == "unknown"
    assert any(warning.code == "METRIC_SCALE_INCOMPATIBLE" for warning in result.warnings)


def test_registered_metric_alias_mismatch_blocks_comparison(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("latency_ms\n14.2\n14.4\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="accuracy", column="latency_ms", paper_value=0.9)

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.computation_status.value == "metric_alias_mismatch"
    assert comparison.reproduced_value is None
    assert comparison.severity.value == "unknown"
    assert any(warning.code == "METRIC_ALIAS_MISMATCH" for warning in result.warnings)


def test_unknown_metric_scale_blocks_delta_calculation(tmp_path) -> None:
    result_path = tmp_path / "results.csv"
    result_path.write_text("custom_score\n2\n3\n", encoding="utf-8")
    bundle = load_sources(
        [str(result_path)],
        role="reproduction",
        settings=Settings(REPROSCOPE_ALLOWED_ROOTS=str(tmp_path)),
        source_id_prefix="repro",
    )
    result = _comparison_result(metric="custom score", column="custom_score", paper_value=2.5)

    compute_metric_differences(result, bundle)

    comparison = result.metric_comparisons[0]
    assert comparison.reproduced_value == pytest.approx(2.5)
    assert comparison.computation_status.value == "unresolved_metric_scale"
    assert comparison.absolute_delta is None
    assert comparison.severity.value == "unknown"
    assert any(warning.code == "METRIC_SCALE_UNRESOLVED" for warning in result.warnings)
