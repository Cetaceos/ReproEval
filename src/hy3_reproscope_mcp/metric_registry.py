"""Deterministic metric aliases and conservative unit/scale resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import MetricScale


@dataclass(frozen=True)
class MetricSpec:
    canonical_name: str
    aliases: tuple[str, ...]
    bounded_proportion: bool = False
    default_scale: MetricScale = MetricScale.UNKNOWN


@dataclass(frozen=True)
class ScaleResolution:
    scale: MetricScale
    source: str


@dataclass(frozen=True)
class MetricUnitResolution:
    """A conservative metric-specific unit conversion to one canonical unit."""

    canonical_metric: str
    input_unit: str
    canonical_unit: str
    factor_to_canonical: float
    source: str


METRIC_SPECS = (
    MetricSpec(
        canonical_name="accuracy",
        aliases=(
            "accuracy",
            "acc",
            "test_accuracy",
            "validation_accuracy",
            "val_accuracy",
            "top1",
            "top_1",
            "top1_accuracy",
            "top_1_accuracy",
        ),
        bounded_proportion=True,
    ),
    MetricSpec(
        canonical_name="precision",
        aliases=("precision", "positive_predictive_value", "ppv"),
        bounded_proportion=True,
    ),
    MetricSpec(
        canonical_name="recall",
        aliases=("recall", "sensitivity", "true_positive_rate", "tpr"),
        bounded_proportion=True,
    ),
    MetricSpec(
        canonical_name="f1",
        aliases=("f1", "f1_score", "f_score"),
        bounded_proportion=True,
    ),
    MetricSpec(
        canonical_name="auroc",
        aliases=("auroc", "roc_auc", "auc_roc"),
        bounded_proportion=True,
    ),
    MetricSpec(
        canonical_name="error_rate",
        aliases=("error_rate", "classification_error", "test_error"),
        bounded_proportion=True,
    ),
    MetricSpec(
        canonical_name="ber",
        aliases=("ber", "bit_error_rate", "bit_error_ratio"),
        bounded_proportion=True,
    ),
    MetricSpec(
        canonical_name="bler",
        aliases=("bler", "block_error_rate", "block_error_ratio"),
        bounded_proportion=True,
    ),
    MetricSpec(
        canonical_name="success_rate",
        aliases=("success_rate", "success_ratio"),
        bounded_proportion=True,
    ),
    MetricSpec(
        canonical_name="latency",
        aliases=(
            "latency",
            "latency_ms",
            "latency_s",
            "latency_seconds",
            "latency_milliseconds",
            "inference_latency",
            "runtime_ms",
            "runtime_s",
            "runtime_seconds",
        ),
        default_scale=MetricScale.LINEAR,
    ),
    MetricSpec(
        canonical_name="throughput",
        aliases=(
            "throughput",
            "throughput_bps",
            "throughput_kbps",
            "throughput_mbps",
            "throughput_gbps",
            "data_rate",
        ),
        default_scale=MetricScale.LINEAR,
    ),
    MetricSpec(
        canonical_name="spectral_efficiency",
        aliases=(
            "spectral_efficiency",
            "spectral_efficiency_bps_hz",
            "spectral_efficiency_kbps_hz",
            "spectral_efficiency_mbps_hz",
            "spectral_efficiency_gbps_hz",
        ),
        default_scale=MetricScale.LINEAR,
    ),
    MetricSpec(
        canonical_name="snr",
        aliases=("snr", "snr_db", "signal_to_noise_ratio"),
    ),
    MetricSpec(
        canonical_name="eb_n0",
        aliases=("eb_n0", "eb_n0_db", "ebno", "ebno_db"),
    ),
    MetricSpec(
        canonical_name="loss",
        aliases=("loss", "test_loss", "validation_loss", "val_loss"),
        default_scale=MetricScale.LINEAR,
    ),
)

_SPEC_BY_ALIAS = {alias: spec for spec in METRIC_SPECS for alias in (spec.canonical_name, *spec.aliases)}


def metric_spec(name: str | None) -> MetricSpec | None:
    if not name:
        return None
    normalized = _normalize_name(name)
    direct = _SPEC_BY_ALIAS.get(normalized)
    if direct:
        return direct
    for suffix in ("_percent", "_percentage", "_pct", "_fraction", "_proportion", "_linear", "_db", "_dbm", "_dbw"):
        if normalized.endswith(suffix):
            return _SPEC_BY_ALIAS.get(normalized[: -len(suffix)])
    return None


def canonical_metric_name(name: str | None) -> str | None:
    spec = metric_spec(name)
    return spec.canonical_name if spec else None


def has_metric_unit_contract(name: str | None) -> bool:
    """Return whether a known metric has a metric-specific unit registry."""

    canonical = canonical_metric_name(name)
    return canonical in _UNIT_DEFINITIONS if canonical is not None else False


def metric_registry_payload() -> list[dict[str, object]]:
    return [
        {
            "canonical_name": spec.canonical_name,
            "aliases": list(spec.aliases),
            "bounded_proportion": spec.bounded_proportion,
            "default_scale": spec.default_scale.value,
        }
        for spec in METRIC_SPECS
    ]


def resolve_scale(
    *,
    metric_name: str | None,
    unit: str | None,
    minimum: float | None,
    maximum: float | None,
    suggested: MetricScale = MetricScale.UNKNOWN,
) -> ScaleResolution:
    unit_scale = scale_from_unit(unit)
    if unit_scale is not MetricScale.UNKNOWN:
        return ScaleResolution(unit_scale, "unit")

    name_scale = scale_from_name(metric_name)
    if name_scale is not MetricScale.UNKNOWN:
        return ScaleResolution(name_scale, "name")

    spec = metric_spec(metric_name)
    if spec and spec.bounded_proportion:
        inferred = _bounded_scale(minimum, maximum)
        if inferred is not MetricScale.UNKNOWN:
            return ScaleResolution(inferred, "bounded_values")

    if spec and spec.default_scale is not MetricScale.UNKNOWN:
        return ScaleResolution(spec.default_scale, "registry")

    if suggested is not MetricScale.UNKNOWN:
        return ScaleResolution(suggested, "model")

    return ScaleResolution(MetricScale.UNKNOWN, "unresolved")


def scale_from_unit(unit: str | None) -> MetricScale:
    if not unit:
        return MetricScale.UNKNOWN
    normalized = _normalize_unit(unit)
    if normalized in {"%", "percent", "percentage", "pct"}:
        return MetricScale.PERCENTAGE
    if normalized in {"fraction", "proportion", "ratio", "unitless_fraction"}:
        return MetricScale.FRACTION
    if normalized in {"db", "dbm", "dbw"}:
        return MetricScale.DECIBEL
    if normalized in {
        "s",
        "sec",
        "second",
        "seconds",
        "ms",
        "us",
        "ns",
        "bps",
        "kbps",
        "mbps",
        "gbps",
        "hz",
        "khz",
        "mhz",
        "ghz",
        "w",
        "mw",
        "bps/hz",
    }:
        return MetricScale.LINEAR
    return MetricScale.UNKNOWN


def scale_from_name(name: str | None) -> MetricScale:
    if not name:
        return MetricScale.UNKNOWN
    normalized = _normalize_name(name)
    if normalized.endswith(("_percent", "_percentage", "_pct")):
        return MetricScale.PERCENTAGE
    if normalized.endswith(("_fraction", "_proportion")):
        return MetricScale.FRACTION
    if normalized.endswith("_linear"):
        return MetricScale.LINEAR
    if normalized.endswith(("_db", "_dbm", "_dbw")):
        return MetricScale.DECIBEL
    if normalized.endswith(
        (
            "_ms",
            "_seconds",
            "_bps",
            "_kbps",
            "_mbps",
            "_gbps",
            "_hz",
            "_khz",
            "_mhz",
            "_ghz",
            "_watts",
        )
    ):
        return MetricScale.LINEAR
    return MetricScale.UNKNOWN


def resolve_metric_unit(
    metric_name: str | None,
    unit: str | None,
    *,
    infer_from_name: bool = False,
) -> MetricUnitResolution | None:
    """Resolve only metric-specific linear units with an unambiguous base."""

    canonical = canonical_metric_name(metric_name)
    if canonical is None:
        return None
    candidate = _normalize_unit(unit) if unit else ""
    source = "unit"
    if not candidate and infer_from_name:
        candidate = _unit_suffix(metric_name)
        source = "name"
    if not candidate:
        return None
    unit_key = candidate.replace("/", "_")
    definition = _UNIT_DEFINITIONS.get(canonical, {}).get(unit_key)
    if definition is None:
        return None
    canonical_unit, factor = definition
    return MetricUnitResolution(
        canonical_metric=canonical,
        input_unit=candidate,
        canonical_unit=canonical_unit,
        factor_to_canonical=factor,
        source=source,
    )


def normalize_paper_value(
    value: float,
    *,
    paper_scale: MetricScale,
    reproduction_scale: MetricScale,
) -> tuple[float, str | None]:
    if paper_scale is reproduction_scale:
        return value, None
    if paper_scale is MetricScale.PERCENTAGE and reproduction_scale is MetricScale.FRACTION:
        return value / 100, "percentage_to_fraction"
    if paper_scale is MetricScale.FRACTION and reproduction_scale is MetricScale.PERCENTAGE:
        return value * 100, "fraction_to_percentage"
    raise ValueError(f"Cannot safely convert {paper_scale.value} to {reproduction_scale.value}")


def scales_are_compatible(paper_scale: MetricScale, reproduction_scale: MetricScale) -> bool:
    if paper_scale is reproduction_scale:
        return True
    return {paper_scale, reproduction_scale} == {MetricScale.FRACTION, MetricScale.PERCENTAGE}


def _bounded_scale(minimum: float | None, maximum: float | None) -> MetricScale:
    if minimum is None or maximum is None or minimum < 0:
        return MetricScale.UNKNOWN
    if maximum <= 1:
        return MetricScale.FRACTION
    if maximum <= 100:
        return MetricScale.PERCENTAGE
    return MetricScale.UNKNOWN


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _normalize_unit(value: str) -> str:
    normalized = value.strip().lower().replace("μ", "u").replace("µ", "u")
    return re.sub(r"\s+", "", normalized)


def _unit_suffix(value: str | None) -> str:
    if not value:
        return ""
    normalized = _normalize_name(value)
    for suffix in (
        "_milliseconds",
        "_microseconds",
        "_nanoseconds",
        "_seconds",
        "_millis",
        "_micros",
        "_nanos",
        "_ms",
        "_us",
        "_ns",
        "_kbps_hz",
        "_mbps_hz",
        "_gbps_hz",
        "_bps_hz",
        "_kbps",
        "_mbps",
        "_gbps",
        "_bps",
    ):
        if normalized.endswith(suffix):
            return suffix[1:]
    return ""


_UNIT_DEFINITIONS: dict[str, dict[str, tuple[str, float]]] = {
    "latency": {
        "s": ("s", 1.0),
        "sec": ("s", 1.0),
        "second": ("s", 1.0),
        "seconds": ("s", 1.0),
        "ms": ("s", 1e-3),
        "millisecond": ("s", 1e-3),
        "milliseconds": ("s", 1e-3),
        "us": ("s", 1e-6),
        "microsecond": ("s", 1e-6),
        "microseconds": ("s", 1e-6),
        "ns": ("s", 1e-9),
        "nanosecond": ("s", 1e-9),
        "nanoseconds": ("s", 1e-9),
    },
    "throughput": {
        "bps": ("bps", 1.0),
        "kbps": ("bps", 1e3),
        "mbps": ("bps", 1e6),
        "gbps": ("bps", 1e9),
    },
    "spectral_efficiency": {
        "bps_hz": ("bps/Hz", 1.0),
        "kbps_hz": ("bps/Hz", 1e3),
        "mbps_hz": ("bps/Hz", 1e6),
        "gbps_hz": ("bps/Hz", 1e9),
    },
}
