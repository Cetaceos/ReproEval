"""Deterministic SVG figures derived from a verified public result bundle."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
from pathlib import Path
from statistics import fmean
from typing import Any, Literal

from pydantic import Field, model_validator

from . import __version__
from .errors import EvaluationInputError
from .models import StrictModel
from .results_export import (
    EXPORT_MANIFEST_NAME,
    MAX_EXPORT_MANIFEST_BYTES,
    MAX_EXPORTED_RESULT_BYTES,
    ResultsExportManifest,
    verify_results_export,
)

FIGURE_MANIFEST_NAME = "figure_manifest.json"
MAX_FIGURE_BYTES = 2 * 1024 * 1024
FigurePath = Literal["dimension_stability.svg", "score_by_tier.svg"]

REPORT_COLUMNS = [
    "report_id",
    "group_id",
    "split",
    "quality_tier",
    "mean_score",
    "score_stddev",
    "score_range",
    "score_coverage",
    "quality_band_flip",
    "ranking_eligibility_flip",
    "evaluation_status_flip",
]
DIMENSION_COLUMNS = [
    "dimension",
    "report_count",
    "fully_assessed_report_count",
    "fully_assessed_report_coverage",
    "mean_report_score_stddev",
    "maximum_report_score_stddev",
    "report_status_flip_count",
]


class ResultsFigures(StrictModel):
    output_root: str
    dataset_id: str
    source_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    files: list[str]


class ResultsFigureFile(StrictModel):
    path: FigurePath
    bytes: int = Field(ge=1, le=MAX_FIGURE_BYTES)
    sha256: str = Field(pattern=r"^[A-F0-9]{64}$")


class ResultsFigureManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    dataset_id: str
    dataset_version: str
    source_export_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    figures: list[ResultsFigureFile] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_inventory(self) -> ResultsFigureManifest:
        paths = [item.path for item in self.figures]
        expected = ["dimension_stability.svg", "score_by_tier.svg"]
        if paths != expected:
            raise ValueError("figure outputs must contain the canonical sorted inventory")
        return self


class ResultsFiguresVerification(StrictModel):
    output_root: str
    dataset_id: str
    dataset_version: str
    engine_version: str
    source_export_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    file_count: Literal[3] = 3
    manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    valid: Literal[True] = True


def render_results_figures(bundle_dir: str | Path, output_dir: str | Path) -> ResultsFigures:
    """Verify one result bundle and render a closed, deterministic SVG figure bundle."""

    source_requested = Path(bundle_dir).expanduser()
    if source_requested.is_symlink():
        raise EvaluationInputError("results export bundle must not be a symbolic link")
    source_root = source_requested.resolve()
    source_verification = verify_results_export(source_root)
    source_manifest_payload = _read_limited(
        source_root / EXPORT_MANIFEST_NAME,
        MAX_EXPORT_MANIFEST_BYTES,
        "results export manifest",
    )
    try:
        source_manifest = ResultsExportManifest.model_validate_json(source_manifest_payload)
    except ValueError as exc:  # pragma: no cover - already verified above
        raise EvaluationInputError(f"invalid results export manifest: {exc}") from exc

    report_rows = _load_report_rows(source_root / "report_stability.csv")
    dimension_rows = _load_dimension_rows(source_root / "dimension_stability.csv")
    output_requested = Path(output_dir).expanduser()
    if output_requested.is_symlink():
        raise EvaluationInputError("figure output path must not be a symbolic link")
    output_root = output_requested.resolve()
    if output_root.exists() and (not output_root.is_dir() or output_root.is_symlink()):
        raise EvaluationInputError("figure output path must be a real directory")
    if output_root.exists() and any(output_root.iterdir()):
        raise EvaluationInputError("figure output directory must be absent or empty")
    if not output_root.parent.is_dir() or output_root.parent.is_symlink():
        raise EvaluationInputError(f"figure output parent is not a real directory: {output_root.parent.as_posix()}")
    output_root.mkdir(exist_ok=True)

    payloads = {
        "score_by_tier.svg": _render_score_by_tier(report_rows).encode("utf-8"),
        "dimension_stability.svg": _render_dimension_stability(dimension_rows).encode("utf-8"),
    }
    for name, payload in payloads.items():
        if len(payload) > MAX_FIGURE_BYTES:
            raise EvaluationInputError(f"rendered figure exceeds {MAX_FIGURE_BYTES} bytes: {name}")
        (output_root / name).write_bytes(payload)
    manifest = ResultsFigureManifest(
        engine_version=__version__,
        dataset_id=source_manifest.dataset_id,
        dataset_version=source_manifest.dataset_version,
        source_export_manifest_sha256=source_verification.manifest_sha256,
        figures=[
            ResultsFigureFile(path=name, bytes=len(payload), sha256=_sha256(payload))
            for name, payload in sorted(payloads.items())
        ],
    )
    (output_root / FIGURE_MANIFEST_NAME).write_bytes(_json_bytes(manifest.model_dump(mode="json")))
    return ResultsFigures(
        output_root=output_root.as_posix(),
        dataset_id=manifest.dataset_id,
        source_manifest_sha256=manifest.source_export_manifest_sha256,
        files=[*sorted(payloads), FIGURE_MANIFEST_NAME],
    )


def verify_results_figures(
    figure_dir: str | Path,
    *,
    source_bundle: str | Path | None = None,
) -> ResultsFiguresVerification:
    """Verify a figure bundle and optionally rebind it to its source result bundle."""

    output_requested = Path(figure_dir).expanduser()
    if output_requested.is_symlink():
        raise EvaluationInputError("figure bundle must not be a symbolic link")
    output_root = output_requested.resolve()
    if not output_root.is_dir() or output_root.is_symlink():
        raise EvaluationInputError(f"figure bundle is not a real directory: {output_root.as_posix()}")
    manifest_payload = _read_limited(
        output_root / FIGURE_MANIFEST_NAME,
        MAX_EXPORT_MANIFEST_BYTES,
        "figure manifest",
    )
    try:
        manifest = ResultsFigureManifest.model_validate_json(manifest_payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid figure manifest: {exc}") from exc
    expected_paths = {FIGURE_MANIFEST_NAME, *(item.path for item in manifest.figures)}
    entries = list(output_root.iterdir())
    if {entry.name for entry in entries} != expected_paths or any(
        not entry.is_file() or entry.is_symlink() for entry in entries
    ):
        raise EvaluationInputError("figure bundle does not match the closed manifest inventory")
    for item in manifest.figures:
        payload = _read_limited(output_root / item.path, MAX_FIGURE_BYTES, f"figure '{item.path}'")
        if len(payload) != item.bytes or _sha256(payload) != item.sha256:
            raise EvaluationInputError(f"figure fingerprint changed: {item.path}")
    if source_bundle is not None:
        source = verify_results_export(source_bundle)
        if source.dataset_id != manifest.dataset_id or source.dataset_version != manifest.dataset_version:
            raise EvaluationInputError("figure bundle Dataset identity does not match the source result bundle")
        if source.manifest_sha256 != manifest.source_export_manifest_sha256:
            raise EvaluationInputError("figure bundle is not bound to the supplied source result bundle")
    return ResultsFiguresVerification(
        output_root=output_root.as_posix(),
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        engine_version=manifest.engine_version,
        source_export_manifest_sha256=manifest.source_export_manifest_sha256,
        manifest_sha256=_sha256(manifest_payload),
    )


def _load_report_rows(path: Path) -> list[dict[str, str]]:
    rows = _read_csv(path, REPORT_COLUMNS, "report stability CSV")
    seen: set[str] = set()
    for row in rows:
        report_id = row["report_id"].strip()
        if not report_id or report_id in seen:
            raise EvaluationInputError("report stability CSV contains an empty or duplicate report_id")
        seen.add(report_id)
        if not row["group_id"].strip() or row["split"] not in {"development", "validation", "test"}:
            raise EvaluationInputError(f"report stability CSV has invalid identity fields: {report_id}")
        if row["quality_tier"] not in {"high", "medium", "low", "adversarial"}:
            raise EvaluationInputError(f"report stability CSV has an invalid quality tier: {report_id}")
        _optional_float(row["mean_score"], 0.0, 100.0, f"mean_score for {report_id}")
        _optional_float(row["score_stddev"], 0.0, 100.0, f"score_stddev for {report_id}")
        _optional_float(row["score_range"], 0.0, 100.0, f"score_range for {report_id}")
        _required_float(row["score_coverage"], 0.0, 1.0, f"score_coverage for {report_id}")
        for column in ("quality_band_flip", "ranking_eligibility_flip", "evaluation_status_flip"):
            if row[column] not in {"True", "False"}:
                raise EvaluationInputError(f"report stability CSV has an invalid {column}: {report_id}")
    if not rows:
        raise EvaluationInputError("report stability CSV contains no rows")
    return rows


def _load_dimension_rows(path: Path) -> list[dict[str, str]]:
    rows = _read_csv(path, DIMENSION_COLUMNS, "dimension stability CSV")
    seen: set[str] = set()
    for row in rows:
        dimension = row["dimension"].strip()
        if not dimension or dimension in seen:
            raise EvaluationInputError("dimension stability CSV contains an empty or duplicate dimension")
        seen.add(dimension)
        report_count = _required_int(row["report_count"], f"report_count for {dimension}")
        assessed = _required_int(row["fully_assessed_report_count"], f"fully_assessed_report_count for {dimension}")
        if assessed > report_count:
            raise EvaluationInputError(f"fully assessed count exceeds report count for {dimension}")
        _required_float(
            row["fully_assessed_report_coverage"],
            0.0,
            1.0,
            f"fully_assessed_report_coverage for {dimension}",
        )
        mean_value = _optional_float(
            row["mean_report_score_stddev"], 0.0, 100.0, f"mean_report_score_stddev for {dimension}"
        )
        maximum_value = _optional_float(
            row["maximum_report_score_stddev"],
            0.0,
            100.0,
            f"maximum_report_score_stddev for {dimension}",
        )
        if mean_value is not None and maximum_value is not None and mean_value > maximum_value:
            raise EvaluationInputError(f"mean standard deviation exceeds maximum for {dimension}")
        _required_int(row["report_status_flip_count"], f"report_status_flip_count for {dimension}")
    if not rows:
        raise EvaluationInputError("dimension stability CSV contains no rows")
    return rows


def _render_score_by_tier(rows: list[dict[str, str]]) -> str:
    tier_values: dict[str, list[float]] = {"high": [], "medium": [], "low": []}
    for row in rows:
        score = _optional_float(row["mean_score"], 0.0, 100.0, "mean_score")
        if row["quality_tier"] in tier_values and score is not None:
            tier_values[row["quality_tier"]].append(score)
    if any(not tier_values[tier] for tier in tier_values):
        raise EvaluationInputError("score figure requires scored high, medium, and low reports")
    means = {tier: fmean(values) for tier, values in tier_values.items()}
    colors = {"high": "#16805C", "medium": "#D18A00", "low": "#C4443E"}
    labels = {"high": "High", "medium": "Medium", "low": "Low"}
    width, height = 960, 470
    plot_x, plot_width = 210, 650
    lines = _svg_header(width, height, "Mean report score by registered quality tier")
    lines.extend(
        [
            '<text x="48" y="55" class="title">Mean report score by quality tier</text>',
            '<text x="48" y="82" class="subtitle">Verified aggregate results; 0-100 scale</text>',
        ]
    )
    for tick in range(0, 101, 20):
        x = plot_x + plot_width * tick / 100
        lines.append(f'<line x1="{x:.1f}" y1="110" x2="{x:.1f}" y2="365" class="grid"/>')
        lines.append(f'<text x="{x:.1f}" y="395" text-anchor="middle" class="axis">{tick}</text>')
    for index, tier in enumerate(("high", "medium", "low")):
        y = 135 + index * 82
        value = means[tier]
        bar_width = plot_width * value / 100
        lines.append(f'<text x="185" y="{y + 29}" text-anchor="end" class="label">{labels[tier]}</text>')
        lines.append(f'<rect x="{plot_x}" y="{y}" width="{plot_width}" height="40" rx="4" fill="#EEF1F4"/>')
        lines.append(f'<rect x="{plot_x}" y="{y}" width="{bar_width:.1f}" height="40" rx="4" fill="{colors[tier]}"/>')
        lines.append(
            f'<text x="{min(plot_x + bar_width + 10, 900):.1f}" y="{y + 27}" class="value">'
            f"{value:.1f} (n={len(tier_values[tier])})</text>"
        )
    lines.append('<text x="535" y="438" text-anchor="middle" class="axis-label">Mean total score</text>')
    return _finish_svg(lines)


def _render_dimension_stability(rows: list[dict[str, str]]) -> str:
    values: list[tuple[str, float, float]] = []
    for row in rows:
        mean_value = _optional_float(row["mean_report_score_stddev"], 0.0, 100.0, "dimension mean stddev")
        maximum_value = _optional_float(row["maximum_report_score_stddev"], 0.0, 100.0, "dimension maximum stddev")
        values.append((row["dimension"], mean_value or 0.0, maximum_value or 0.0))
    scale_max = max(1.0, math.ceil(max(item[2] for item in values) * 10) / 10)
    width = 960
    height = 220 + len(values) * 52
    plot_x, plot_width = 300, 570
    plot_top = 125
    lines = _svg_header(width, height, "Repeated-run score stability by evaluation dimension")
    lines.extend(
        [
            '<text x="48" y="55" class="title">Dimension-level repeated-run stability</text>',
            '<text x="48" y="82" class="subtitle">Lower standard deviation indicates higher stability</text>',
            '<rect x="650" y="49" width="14" height="14" rx="2" fill="#2E6F9E"/>',
            '<text x="672" y="61" class="legend">Mean</text>',
            '<rect x="755" y="49" width="14" height="14" rx="2" fill="#D45B45"/>',
            '<text x="777" y="61" class="legend">Maximum</text>',
        ]
    )
    for tick_index in range(6):
        value = scale_max * tick_index / 5
        x = plot_x + plot_width * tick_index / 5
        lines.append(
            f'<line x1="{x:.1f}" y1="{plot_top - 10}" x2="{x:.1f}" y2="{plot_top + len(values) * 52}" class="grid"/>'
        )
        lines.append(
            f'<text x="{x:.1f}" y="{plot_top + len(values) * 52 + 25}" text-anchor="middle" class="axis">'
            f"{value:.2g}</text>"
        )
    for index, (dimension, mean_value, maximum_value) in enumerate(values):
        y = plot_top + index * 52
        escaped = html.escape(dimension.replace("_", " "))
        max_width = plot_width * maximum_value / scale_max
        mean_width = plot_width * mean_value / scale_max
        lines.append(f'<text x="280" y="{y + 23}" text-anchor="end" class="dimension">{escaped}</text>')
        lines.append(f'<rect x="{plot_x}" y="{y + 5}" width="{max_width:.1f}" height="25" rx="3" fill="#D45B45"/>')
        lines.append(f'<rect x="{plot_x}" y="{y + 11}" width="{mean_width:.1f}" height="13" rx="2" fill="#2E6F9E"/>')
        lines.append(
            f'<text x="{min(plot_x + max_width + 8, 900):.1f}" y="{y + 23}" class="value-small">'
            f"{mean_value:.3f} / {maximum_value:.3f}</text>"
        )
    lines.append(
        f'<text x="{plot_x + plot_width / 2:.1f}" y="{height - 28}" text-anchor="middle" class="axis-label">'
        "Report score standard deviation (mean / maximum)</text>"
    )
    return _finish_svg(lines)


def _svg_header(width: int, height: int, description: str) -> list[str]:
    escaped_description = html.escape(description)
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
        'aria-labelledby="title description">',
        f'<title id="title">{escaped_description}</title>',
        f'<desc id="description">{escaped_description}</desc>',
        "<style>",
        "text { font-family: Arial, Helvetica, sans-serif; fill: #17212B; }",
        ".title { font-size: 25px; font-weight: 700; }",
        ".subtitle { font-size: 14px; fill: #55616E; }",
        ".label { font-size: 16px; font-weight: 700; }",
        ".dimension { font-size: 13px; }",
        ".value { font-size: 14px; font-weight: 700; }",
        ".value-small { font-size: 12px; font-weight: 700; }",
        ".axis { font-size: 12px; fill: #5F6B76; }",
        ".axis-label { font-size: 14px; font-weight: 700; }",
        ".legend { font-size: 13px; }",
        ".grid { stroke: #D9DEE4; stroke-width: 1; }",
        "</style>",
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
    ]


def _finish_svg(lines: list[str]) -> str:
    return "\n".join([*lines, "</svg>", ""])


def _read_csv(path: Path, expected_columns: list[str], label: str) -> list[dict[str, str]]:
    payload = _read_limited(path, MAX_EXPORTED_RESULT_BYTES, label)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvaluationInputError(f"{label} must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != expected_columns:
        raise EvaluationInputError(f"{label} does not use the canonical columns")
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise EvaluationInputError(f"{label} contains malformed rows")
    return rows


def _required_float(value: str, minimum: float, maximum: float, label: str) -> float:
    parsed = _optional_float(value, minimum, maximum, label)
    if parsed is None:
        raise EvaluationInputError(f"{label} is required")
    return parsed


def _optional_float(value: str, minimum: float, maximum: float, label: str) -> float | None:
    if value == "":
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise EvaluationInputError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise EvaluationInputError(f"{label} must be between {minimum} and {maximum}")
    return parsed


def _required_int(value: str, label: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise EvaluationInputError(f"{label} must be an integer") from exc
    if parsed < 0:
        raise EvaluationInputError(f"{label} must not be negative")
    return parsed


def _read_limited(path: Path, maximum_bytes: int, label: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise EvaluationInputError(f"{label} does not exist as a regular file: {path.as_posix()}")
    if path.stat().st_size > maximum_bytes:
        raise EvaluationInputError(f"{label} exceeds {maximum_bytes} bytes")
    return path.read_bytes()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
