from __future__ import annotations

import pytest

from hy3_reproscope_mcp.metric_registry import (
    canonical_metric_name,
    has_metric_unit_contract,
    normalize_paper_value,
    resolve_metric_unit,
    resolve_scale,
    scale_from_name,
    scale_from_unit,
    scales_are_compatible,
)
from hy3_reproscope_mcp.models import MetricScale


@pytest.mark.parametrize(
    ("name", "canonical"),
    [
        ("accuracy", "accuracy"),
        ("test accuracy", "accuracy"),
        ("accuracy_percent", "accuracy"),
        ("F1-score", "f1"),
        ("bit error rate", "ber"),
        ("latency_ms", "latency"),
        ("latency_seconds", "latency"),
        ("throughput_gbps", "throughput"),
        ("SNR (dB)", "snr"),
        ("unknown score", None),
    ],
)
def test_metric_alias_registry_canonicalizes_known_names(name, canonical) -> None:
    assert canonical_metric_name(name) == canonical


@pytest.mark.parametrize(
    ("value", "scale"),
    [
        ("%", MetricScale.PERCENTAGE),
        ("percentage", MetricScale.PERCENTAGE),
        ("fraction", MetricScale.FRACTION),
        ("dB", MetricScale.DECIBEL),
        ("ms", MetricScale.LINEAR),
        ("unknown", MetricScale.UNKNOWN),
    ],
)
def test_unit_scale_resolution(value, scale) -> None:
    assert scale_from_unit(value) is scale


@pytest.mark.parametrize(
    ("name", "scale"),
    [
        ("accuracy_pct", MetricScale.PERCENTAGE),
        ("accuracy_fraction", MetricScale.FRACTION),
        ("snr_db", MetricScale.DECIBEL),
        ("snr_linear", MetricScale.LINEAR),
        ("latency_ms", MetricScale.LINEAR),
    ],
)
def test_column_name_scale_resolution(name, scale) -> None:
    assert scale_from_name(name) is scale


def test_bounded_metric_values_resolve_fraction_and_percentage() -> None:
    fraction = resolve_scale(
        metric_name="accuracy",
        unit=None,
        minimum=0.8,
        maximum=0.9,
    )
    percentage = resolve_scale(
        metric_name="accuracy",
        unit=None,
        minimum=80,
        maximum=90,
    )

    assert fraction.scale is MetricScale.FRACTION
    assert percentage.scale is MetricScale.PERCENTAGE


def test_only_fraction_percentage_have_automatic_cross_scale_conversion() -> None:
    converted, conversion = normalize_paper_value(
        91,
        paper_scale=MetricScale.PERCENTAGE,
        reproduction_scale=MetricScale.FRACTION,
    )

    assert converted == pytest.approx(0.91)
    assert conversion == "percentage_to_fraction"
    assert scales_are_compatible(MetricScale.FRACTION, MetricScale.PERCENTAGE)
    assert not scales_are_compatible(MetricScale.LINEAR, MetricScale.DECIBEL)


def test_metric_unit_registry_resolves_explicit_and_column_units() -> None:
    paper = resolve_metric_unit("latency", "s")
    reproduction = resolve_metric_unit("latency_ms", None, infer_from_name=True)
    inferred_paper = resolve_metric_unit("latency_ms", None, infer_from_name=True)
    throughput = resolve_metric_unit("throughput", "Mbps")

    assert paper is not None
    assert paper.canonical_unit == "s"
    assert paper.factor_to_canonical == 1
    assert reproduction is not None
    assert reproduction.factor_to_canonical == pytest.approx(1e-3)
    assert reproduction.source == "name"
    assert inferred_paper is not None
    assert inferred_paper.input_unit == "ms"
    assert throughput is not None
    assert throughput.canonical_unit == "bps"
    assert throughput.factor_to_canonical == pytest.approx(1e6)


def test_metric_unit_contract_is_limited_to_registered_linear_metrics() -> None:
    assert has_metric_unit_contract("latency")
    assert has_metric_unit_contract("throughput_mbps")
    assert has_metric_unit_contract("spectral_efficiency_mbps_hz")
    assert not has_metric_unit_contract("accuracy")
    assert not has_metric_unit_contract("snr")
