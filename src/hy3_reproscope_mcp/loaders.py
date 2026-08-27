"""Deterministic local file loaders for ReproScope tools."""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .config import Settings
from .errors import GroupFilterError, ParseError, TotalInputTooLargeError, UnsupportedFileTypeError
from .models import SourceReference, SourceType, ToolWarning
from .security import detect_prompt_injection, prompt_injection_handling
from .workspace import Workspace, make_relative_path, sha256_bytes

try:  # PyYAML is an optional runtime for structured YAML support.
    import yaml
except ImportError:  # pragma: no cover - exercised in minimal installations.
    yaml = None  # type: ignore[assignment]

SOURCE_TYPE_BY_SUFFIX = {
    ".pdf": SourceType.PDF,
    ".md": SourceType.MARKDOWN,
    ".markdown": SourceType.MARKDOWN,
    ".txt": SourceType.TEXT,
    ".csv": SourceType.CSV,
    ".json": SourceType.JSON,
    ".jsonl": SourceType.JSONL,
    ".yaml": SourceType.YAML,
    ".yml": SourceType.YAML,
    ".log": SourceType.LOG,
}

SEGMENT_LINE_LIMIT = 20
MAX_GROUP_VALUES = 20
MAX_STRUCTURED_DEPTH = 16
MAX_STRUCTURED_NODES = 10_000
MAX_LOG_EVENTS = 500
GROUP_COLUMN_ALIASES = {
    "approach",
    "condition",
    "data_set",
    "data_split",
    "dataset",
    "dataset_name",
    "method",
    "method_name",
    "model",
    "model_name",
    "scenario",
    "split",
    "subset",
    "test_scenario",
}
GROUP_COLUMN_CANONICAL = {
    "data_set": "dataset",
    "dataset": "dataset",
    "dataset_name": "dataset",
    "data_split": "split",
    "split": "split",
    "subset": "split",
    "condition": "scenario",
    "scenario": "scenario",
    "test_scenario": "scenario",
    "approach": "method",
    "method": "method",
    "method_name": "method",
    "model": "method",
    "model_name": "method",
}
MISSING_GROUP_VALUE = "<missing>"
OMITTED_GROUP_VALUES = "<additional values omitted>"


@dataclass(frozen=True)
class LoadedSegment:
    """Prompt-sized evidence with a stable, source-local locator."""

    locator: str
    text: str
    reference: SourceReference

    def to_prompt_dict(self) -> dict[str, str]:
        return {"locator": self.locator, "text": self.text}


@dataclass(frozen=True)
class LoadedSource:
    source_id: str
    source_type: SourceType
    source_path: str
    content_hash: str
    excerpt: str
    full_char_count: int
    truncated: bool
    reference: SourceReference
    segments: tuple[LoadedSegment, ...]
    numeric_stats: dict[str, dict[str, float | int]]
    group_values: dict[str, tuple[str, ...]]
    applied_group_filters: dict[str, str]
    structured_summary: dict[str, Any] = field(default_factory=dict)
    prompt_injection_signals: tuple[str, ...] = ()

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "source_path": self.source_path,
            "content_hash": self.content_hash,
            "full_char_count": self.full_char_count,
            "truncated": self.truncated,
            "segments": [segment.to_prompt_dict() for segment in self.segments],
            "group_values": {column: list(values) for column, values in self.group_values.items()},
            "applied_group_filters": self.applied_group_filters,
            "aggregation_safe": not self.ambiguous_group_columns,
            "structured_summary": self.structured_summary,
            "prompt_injection": prompt_injection_handling(self.prompt_injection_signals),
        }

    @property
    def ambiguous_group_columns(self) -> tuple[str, ...]:
        return tuple(column for column, values in self.group_values.items() if len(values) > 1)


@dataclass(frozen=True)
class LoadedBundle:
    sources: list[LoadedSource]
    warnings: list[ToolWarning]

    def prompt_sources(self) -> list[dict[str, Any]]:
        return [source.to_prompt_dict() for source in self.sources]

    def valid_locators(self) -> dict[str, set[str]]:
        return {source.source_id: {segment.locator for segment in source.segments} for source in self.sources}

    def source_references(self) -> list[SourceReference]:
        return [source.reference for source in self.sources]

    def citation_references(self) -> dict[str, dict[str, SourceReference]]:
        return {
            source.source_id: {segment.locator: segment.reference for segment in source.segments}
            for source in self.sources
        }


def load_sources(
    paths: list[str],
    *,
    role: str,
    settings: Settings,
    source_id_prefix: str,
    group_filters: dict[str, str] | None = None,
    prompt_injection_policy: str | None = None,
) -> LoadedBundle:
    workspace = Workspace(settings)
    sources: list[LoadedSource] = []
    warnings: list[ToolWarning] = []
    total_chars = 0
    normalized_filters = normalize_group_filters(group_filters or {})
    injection_policy = prompt_injection_policy or settings.reproscope_prompt_injection_policy
    if injection_policy not in {"warn", "reject"}:
        raise ValueError("prompt_injection_policy must be 'warn' or 'reject'")
    matched_filter_keys: set[str] = set()

    for index, raw_path in enumerate(paths, start=1):
        source_id = f"{source_id_prefix}_{index}"
        resolved_path, raw_content = workspace.read_bytes(raw_path)
        source_type = _source_type_for_path(resolved_path)
        text, numeric_stats, group_values, applied_group_filters, structured_summary = _extract_text(
            resolved_path,
            raw_content,
            source_type,
            normalized_filters,
        )
        matched_filter_keys.update(applied_group_filters)
        excerpt, truncated = _truncate(text, settings.reproscope_max_source_chars)
        total_chars += len(excerpt)
        if total_chars > settings.reproscope_max_total_chars:
            raise TotalInputTooLargeError(
                "Loaded source excerpts exceed REPROSCOPE_MAX_TOTAL_CHARS.",
                hint="Reduce the number of files or increase REPROSCOPE_MAX_TOTAL_CHARS.",
            )

        content_hash = sha256_bytes(raw_content)
        source_path = make_relative_path(resolved_path, workspace.allowed_roots)
        reference = _reference_for_source(
            source_id=source_id,
            source_path=source_path,
            source_type=source_type,
            content_hash=content_hash,
            excerpt=excerpt,
        )
        segments = _segments_for_source(
            source_id=source_id,
            source_path=source_path,
            source_type=source_type,
            content_hash=content_hash,
            excerpt=excerpt,
        )
        # Detect against both the complete raw UTF-8 input and the derived
        # prompt text. Structured CSV summaries intentionally cap sample rows,
        # so checking only ``text`` could miss an instruction-like value in a
        # later raw row when reject mode is enabled.
        raw_security_text = _decode_security_text(raw_content)
        prompt_injection_signals = tuple(
            dict.fromkeys(
                [
                    *detect_prompt_injection(raw_security_text),
                    *detect_prompt_injection(text),
                ]
            )
        )
        if prompt_injection_signals and injection_policy == "reject":
            signal_text = ", ".join(prompt_injection_signals)
            raise ParseError(
                f"Rejected possible prompt injection in {role} source {source_path} ({signal_text}).",
                hint=(
                    "Treat the source as untrusted quoted data, remove the instruction-like content, or explicitly "
                    "set REPROSCOPE_PROMPT_INJECTION_POLICY=warn after manual review."
                ),
            )
        sources.append(
            LoadedSource(
                source_id=source_id,
                source_type=source_type,
                source_path=source_path,
                content_hash=content_hash,
                excerpt=excerpt,
                full_char_count=len(text),
                truncated=truncated,
                reference=reference,
                segments=segments,
                numeric_stats=numeric_stats,
                group_values=group_values,
                applied_group_filters=applied_group_filters,
                structured_summary=structured_summary,
                prompt_injection_signals=prompt_injection_signals,
            )
        )
        if truncated:
            warnings.append(
                ToolWarning(
                    code="SOURCE_TRUNCATED",
                    message=f"{role} source was truncated for prompt size: {source_path}",
                    source_references=[reference],
                )
            )
        if prompt_injection_signals:
            warnings.append(
                ToolWarning(
                    code="PROMPT_INJECTION_SUSPECTED",
                    message=(
                        f"Possible instruction-like content was detected in untrusted {role} source "
                        f"{source_path}; source text remains quoted data and is not actionable."
                    ),
                    source_references=[reference],
                )
            )
        ambiguous_group_columns = tuple(column for column, values in group_values.items() if len(values) > 1)
        if ambiguous_group_columns:
            rendered_groups = "; ".join(f"{column}={list(group_values[column])}" for column in ambiguous_group_columns)
            warnings.append(
                ToolWarning(
                    code="MIXED_EXPERIMENT_GROUPS",
                    message=(
                        f"{role} source contains multiple experiment groups; whole-column metric aggregation "
                        f"is unsafe: {source_path} ({rendered_groups})"
                    ),
                    source_references=[reference],
                )
            )
        if applied_group_filters:
            rendered_filters = ", ".join(f"{key}={value}" for key, value in applied_group_filters.items())
            warnings.append(
                ToolWarning(
                    code="GROUP_FILTER_APPLIED",
                    message=f"Applied experiment group filters to {source_path}: {rendered_filters}",
                    source_references=[reference],
                )
            )

    unmatched_filters = sorted(set(normalized_filters) - matched_filter_keys)
    if unmatched_filters:
        raise GroupFilterError(
            "Group filter columns were not found in any structured input source: " + ", ".join(unmatched_filters),
            hint="Use a dataset, split, scenario, method, model, or equivalent column present in CSV/JSON/JSONL.",
        )
    return LoadedBundle(sources=sources, warnings=warnings)


def normalize_group_filters(group_filters: dict[str, str]) -> dict[str, str]:
    """Normalize and validate user-supplied experiment group filters."""

    normalized: dict[str, str] = {}
    for raw_key, raw_value in group_filters.items():
        key = _normalize_column_name(raw_key)
        value = str(raw_value).strip()
        if key not in GROUP_COLUMN_ALIASES:
            raise GroupFilterError(
                f"Unsupported group filter column: {raw_key}",
                hint="Use dataset, split, scenario, method, model, or an equivalent documented alias.",
            )
        if not value:
            raise GroupFilterError(f"Group filter value cannot be empty: {raw_key}")
        existing = normalized.get(key)
        if existing is not None and existing.casefold() != value.casefold():
            raise GroupFilterError(f"Conflicting values were supplied for group filter: {raw_key}")
        normalized[key] = value
    return normalized


def normalize_group_by(group_by: list[str]) -> list[str]:
    """Normalize group dimensions to stable dataset/split/scenario/method names."""

    normalized: list[str] = []
    for raw_column in group_by:
        key = _normalize_column_name(raw_column)
        if key not in GROUP_COLUMN_ALIASES:
            raise GroupFilterError(
                f"Unsupported group-by column: {raw_column}",
                hint="Use dataset, split, scenario, method, model, or an equivalent documented alias.",
            )
        canonical = canonical_group_dimension(key)
        if canonical in normalized:
            raise GroupFilterError(f"Duplicate group-by dimension: {raw_column}")
        normalized.append(canonical)
    return normalized


def canonical_group_dimension(column: str) -> str:
    """Return the stable dimension represented by a supported group-column alias."""

    key = _normalize_column_name(column)
    return GROUP_COLUMN_CANONICAL.get(key, key)


def source_group_values(
    source: LoadedSource,
    group_by: list[str],
) -> dict[str, tuple[str, ...]]:
    """Resolve canonical group dimensions against one source's actual columns."""

    resolved: dict[str, tuple[str, ...]] = {}
    for dimension in group_by:
        matches = [
            (column, values)
            for column, values in source.group_values.items()
            if GROUP_COLUMN_CANONICAL.get(_normalize_column_name(column)) == dimension
        ]
        if len(matches) > 1:
            raise GroupFilterError(
                f"Group-by dimension matches multiple columns in {source.source_path}: {dimension}",
                hint="Remove duplicate alias columns from the structured result file.",
            )
        if matches:
            resolved[dimension] = matches[0][1]
    return resolved


def _source_type_for_path(path: Path) -> SourceType:
    suffix = path.suffix.lower()
    source_type = SOURCE_TYPE_BY_SUFFIX.get(suffix)
    if source_type is None:
        raise UnsupportedFileTypeError(
            f"Unsupported file type: {path.name}",
            hint="Use PDF, markdown, text, CSV, JSON, JSONL, YAML, or log files.",
        )
    return source_type


def _extract_text(
    path: Path,
    content: bytes,
    source_type: SourceType,
    group_filters: dict[str, str],
) -> tuple[
    str,
    dict[str, dict[str, float | int]],
    dict[str, tuple[str, ...]],
    dict[str, str],
    dict[str, Any],
]:
    if source_type is SourceType.PDF:
        return _extract_pdf(path, content), {}, {}, {}, {}
    if source_type is SourceType.CSV:
        text, numeric_stats, group_values, filters = _extract_csv(path, content, group_filters)
        return text, numeric_stats, group_values, filters, {}
    if source_type is SourceType.JSON:
        text, numeric_stats, group_values, filters = _extract_json(path, content, group_filters)
        return text, numeric_stats, group_values, filters, _structured_json_summary(text)
    if source_type is SourceType.JSONL:
        text, numeric_stats, group_values, filters = _extract_jsonl(path, content, group_filters)
        return text, numeric_stats, group_values, filters, _structured_json_summary(text)
    text = _decode_text(path, content)
    if source_type is SourceType.YAML:
        return (*_extract_yaml(path, text, group_filters),)
    if source_type is SourceType.LOG:
        return text, {}, {}, {}, _extract_log_summary(text)
    return text, {}, {}, {}, {}


def _extract_pdf(path: Path, content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [f"[PAGE {index}]\n{page.extract_text() or ''}" for index, page in enumerate(reader.pages, start=1)]
    except Exception as exc:
        raise ParseError(
            f"Could not parse PDF file: {path.name}",
            hint="Check that the PDF is readable and not encrypted.",
        ) from exc

    extracted = "\n\n".join(pages).strip()
    if not extracted or all(not page.split("\n", maxsplit=1)[-1].strip() for page in pages):
        raise ParseError(
            f"PDF contains no extractable text: {path.name}",
            hint="Run OCR first, then provide the OCR PDF or exported markdown/text.",
        )
    return extracted


def _decode_text(path: Path, content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError(
            f"Could not decode file as UTF-8: {path.name}",
            hint="Convert the file to UTF-8 before loading it.",
        ) from exc


def _decode_security_text(content: bytes) -> str:
    """Decode raw input for safety scanning without changing loader semantics."""

    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        # The normal loader reports a parse error for non-UTF-8 text. This
        # helper is deliberately non-raising so binary/PDF bytes never turn a
        # safety check into a second, misleading parse failure.
        return ""


def _extract_yaml(
    path: Path,
    text: str,
    group_filters: dict[str, str],
) -> tuple[str, dict[str, dict[str, float | int]], dict[str, tuple[str, ...]], dict[str, str], dict[str, Any]]:
    """Parse YAML with a safe loader while retaining the original evidence text.

    YAML is a configuration/evidence format, not an executable input.  The
    safe loader rejects Python object tags and this local loader additionally
    rejects aliases so an alias expansion cannot amplify the bounded input.
    Structured data is returned as a bounded prompt summary; line segments
    still reference the original text for citation accuracy.
    """

    if yaml is None:
        # Keep the minimal wheel deterministic: without PyYAML we may retain
        # plain YAML as quoted text, but aliases and Python object tags are
        # rejected instead of being passed through as if fully parsed.
        if re.search(r"(?:^|\s)[*&][A-Za-z0-9_.-]+|!!python(?:/|\s)", text, flags=re.I | re.M):
            raise ParseError(
                f"Could not parse YAML file: {path.name}",
                hint="Install the optional YAML parser or remove aliases and custom Python tags.",
            )
        return (
            text,
            {},
            {},
            {},
            {
                "parser": "unavailable",
                "parse_status": "raw_text_only",
                "bounded": True,
                "reason": "PyYAML is not installed; YAML was retained as unparsed UTF-8 text.",
            },
        )

    try:
        documents = list(yaml.load_all(text, Loader=_NoAliasSafeLoader))
    except Exception as exc:
        raise ParseError(
            f"Could not parse YAML file: {path.name}",
            hint="Use YAML 1.2-compatible mappings/lists without aliases or custom Python tags.",
        ) from exc

    bounded_documents = [_bound_structured_value(document) for document in documents]
    payload: Any = bounded_documents[0] if len(bounded_documents) == 1 else {"documents": bounded_documents}

    rows = _tabular_records(payload)
    original_row_count = len(rows)
    columns = _record_columns(rows)
    rows, applied_filters = _apply_group_filters(path, rows, columns, group_filters)
    numeric_stats = _numeric_stats(rows, columns) if rows else {}
    group_values = _group_values(rows, columns)
    if applied_filters:
        payload = _replace_tabular_records(payload, rows)
    summary = {
        "parser": "yaml.safe_load_all",
        "parse_status": "parsed",
        "bounded": True,
        "max_depth": MAX_STRUCTURED_DEPTH,
        "max_nodes": MAX_STRUCTURED_NODES,
        "document_count": len(documents),
        "payload": payload,
        "original_row_count": original_row_count,
        "row_count": len(rows),
        "numeric_stats": numeric_stats,
        "group_values": group_values,
        "applied_group_filters": applied_filters,
        "aggregation_safe": not _ambiguous_group_columns(group_values),
        "flattened_scalars": _flatten_scalar_values(payload),
    }
    return text, numeric_stats, group_values, applied_filters, summary


if yaml is not None:

    class _NoAliasSafeLoader(yaml.SafeLoader):  # type: ignore[misc, valid-type]
        """SafeLoader variant that rejects aliases and custom object tags."""

        def compose_node(self, parent: Any, index: Any) -> Any:
            if self.check_event(yaml.events.AliasEvent):
                raise yaml.YAMLError("YAML aliases are not accepted by the bounded loader")
            node_count = getattr(self, "_reproscope_node_count", 0) + 1
            if node_count > MAX_STRUCTURED_NODES:
                raise yaml.YAMLError("YAML node limit exceeded")
            self._reproscope_node_count = node_count
            depth = getattr(self, "_reproscope_depth", 0) + 1
            if depth > MAX_STRUCTURED_DEPTH:
                raise yaml.YAMLError("YAML nesting depth limit exceeded")
            self._reproscope_depth = depth
            try:
                return super().compose_node(parent, index)
            finally:
                self._reproscope_depth = depth - 1

else:
    _NoAliasSafeLoader = None  # type: ignore[assignment,misc]


def _extract_log_summary(text: str) -> dict[str, Any]:
    """Extract bounded key/value events from common training/service logs."""

    events: list[dict[str, Any]] = []
    flattened: dict[str, str | int | float | bool] = {}
    line_count = len(text.splitlines())
    events_truncated = False
    key_value_pattern = re.compile(
        r"(?P<key>[A-Za-z_][A-Za-z0-9_.-]{0,80})\s*(?:=|:)\s*(?P<value>\"[^\"]*\"|'[^']*'|[^,\s]+)"
    )
    for line_number, line in enumerate(text.splitlines(), start=1):
        if len(events) >= MAX_LOG_EVENTS:
            events_truncated = True
            break
        fields: dict[str, Any] = {}
        for match in key_value_pattern.finditer(line):
            key = match.group("key")
            value = _coerce_log_scalar(match.group("value"))
            fields[key] = value
            flattened[key] = value
        if fields:
            events.append({"line": line_number, "fields": fields})
    return {
        "parser": "key_value_log_v1",
        "parse_status": "parsed",
        "bounded": True,
        "max_events": MAX_LOG_EVENTS,
        "line_count": line_count,
        "parsed_line_count": len(events),
        "events_truncated": events_truncated,
        "events": events,
        "flattened_scalars": flattened,
    }


def _coerce_log_scalar(raw_value: str) -> str | int | float | bool:
    rendered = raw_value.strip().strip("\"'")
    lowered = rendered.casefold()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        numeric = float(rendered)
    except ValueError:
        return rendered
    if math.isfinite(numeric) and numeric.is_integer() and "." not in rendered:
        return int(numeric)
    return numeric if math.isfinite(numeric) else rendered


def _structured_json_summary(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return {
        "parser": "json",
        "parse_status": "parsed",
        "bounded": True,
        "max_depth": MAX_STRUCTURED_DEPTH,
        "max_nodes": MAX_STRUCTURED_NODES,
        "flattened_scalars": _flatten_scalar_values(payload),
    }


def _flatten_scalar_values(
    value: Any, *, prefix: str = "", _depth: int = 0
) -> dict[str, str | int | float | bool | None]:
    """Flatten bounded nested configuration values for deterministic extraction."""

    if _depth > MAX_STRUCTURED_DEPTH:
        return {}
    flattened: dict[str, str | int | float | bool | None] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            name = str(key)
            path = f"{prefix}.{name}" if prefix else name
            if isinstance(child, (str, int, float, bool)) or child is None:
                flattened[path] = child
            else:
                flattened.update(_flatten_scalar_values(child, prefix=path, _depth=_depth + 1))
    elif isinstance(value, list):
        for index, child in enumerate(value[:MAX_STRUCTURED_NODES]):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            if isinstance(child, (str, int, float, bool)) or child is None:
                flattened[path] = child
            else:
                flattened.update(_flatten_scalar_values(child, prefix=path, _depth=_depth + 1))
    return dict(list(flattened.items())[:MAX_STRUCTURED_NODES])


def _bound_structured_value(value: Any, *, _depth: int = 0, _counter: list[int] | None = None) -> Any:
    """Copy YAML values with deterministic depth/node bounds."""

    counter = _counter if _counter is not None else [0]
    counter[0] += 1
    if counter[0] > MAX_STRUCTURED_NODES:
        return "<structured value omitted: node limit exceeded>"
    if _depth > MAX_STRUCTURED_DEPTH:
        return "<structured value omitted: depth limit exceeded>"
    if isinstance(value, dict):
        return {
            str(key): _bound_structured_value(child, _depth=_depth + 1, _counter=counter)
            for key, child in list(value.items())[:MAX_STRUCTURED_NODES]
        }
    if isinstance(value, list):
        return [
            _bound_structured_value(child, _depth=_depth + 1, _counter=counter)
            for child in value[:MAX_STRUCTURED_NODES]
        ]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _extract_json(
    path: Path,
    content: bytes,
    group_filters: dict[str, str],
) -> tuple[str, dict[str, dict[str, float | int]], dict[str, tuple[str, ...]], dict[str, str]]:
    text = _decode_text(path, content)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Could not parse JSON file: {path.name}") from exc
    rows = _tabular_records(payload)
    original_row_count = len(rows)
    columns = _record_columns(rows)
    rows, applied_filters = _apply_group_filters(path, rows, columns, group_filters)
    numeric_stats = _numeric_stats(rows, columns) if rows else {}
    group_values = _group_values(rows, columns)
    rendered = {
        "payload": _replace_tabular_records(payload, rows) if applied_filters else payload,
        "original_row_count": original_row_count,
        "row_count": len(rows),
        "numeric_stats": numeric_stats,
        "group_values": group_values,
        "applied_group_filters": applied_filters,
        "aggregation_safe": not _ambiguous_group_columns(group_values),
    }
    return (
        json.dumps(rendered, ensure_ascii=False, indent=2, sort_keys=True),
        numeric_stats,
        group_values,
        applied_filters,
    )


def _extract_jsonl(
    path: Path,
    content: bytes,
    group_filters: dict[str, str],
) -> tuple[str, dict[str, dict[str, float | int]], dict[str, tuple[str, ...]], dict[str, str]]:
    text = _decode_text(path, content)
    records: list[Any] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ParseError(f"Could not parse JSONL at line {line_number}: {path.name}") from exc
    rows = [record for record in records if isinstance(record, dict)]
    columns = _record_columns(rows)
    original_row_count = len(rows)
    rows, applied_filters = _apply_group_filters(path, rows, columns, group_filters)
    numeric_stats = _numeric_stats(rows, columns) if rows else {}
    group_values = _group_values(rows, columns)
    payload = {
        "jsonl_records": rows if applied_filters else records,
        "original_row_count": original_row_count,
        "row_count": len(rows),
        "numeric_stats": numeric_stats,
        "group_values": group_values,
        "applied_group_filters": applied_filters,
        "aggregation_safe": not _ambiguous_group_columns(group_values),
    }
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        numeric_stats,
        group_values,
        applied_filters,
    )


def _extract_csv(
    path: Path,
    content: bytes,
    group_filters: dict[str, str],
) -> tuple[str, dict[str, dict[str, float | int]], dict[str, tuple[str, ...]], dict[str, str]]:
    text = _decode_text(path, content)
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if reader.fieldnames is None:
        raise ParseError(f"CSV file has no header row: {path.name}")

    original_row_count = len(rows)
    rows, applied_filters = _apply_group_filters(path, rows, reader.fieldnames, group_filters)
    numeric_stats = _numeric_stats(rows, reader.fieldnames)
    group_values = _group_values(rows, reader.fieldnames)
    payload = {
        "columns": reader.fieldnames,
        "original_row_count": original_row_count,
        "row_count": len(rows),
        "sample_rows": rows[:30],
        "numeric_stats": numeric_stats,
        "group_values": group_values,
        "applied_group_filters": applied_filters,
        "aggregation_safe": not _ambiguous_group_columns(group_values),
    }
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        numeric_stats,
        group_values,
        applied_filters,
    )


def _apply_group_filters(
    path: Path,
    rows: list[dict[str, Any]],
    columns: list[str],
    group_filters: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    resolved_filters: list[tuple[str, str, str]] = []
    for filter_key, expected_value in group_filters.items():
        column = _resolve_filter_column(path, columns, filter_key)
        if column is not None:
            resolved_filters.append((filter_key, column, expected_value))
    if not resolved_filters:
        return rows, {}

    filtered_rows = [
        row
        for row in rows
        if all(_group_value_matches(row.get(column), expected) for _, column, expected in resolved_filters)
    ]
    if not filtered_rows:
        rendered_filters = ", ".join(f"{key}={value}" for key, _, value in resolved_filters)
        raise GroupFilterError(
            f"Group filters selected no rows in {path.name}: {rendered_filters}",
            hint="Inspect the source group_values and use an exact available value.",
        )
    return filtered_rows, {key: value for key, _, value in resolved_filters}


def _resolve_filter_column(path: Path, columns: list[str], filter_key: str) -> str | None:
    normalized_columns: dict[str, list[str]] = {}
    for column in columns:
        normalized_columns.setdefault(_normalize_column_name(column), []).append(column)

    exact_matches = normalized_columns.get(filter_key, [])
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise GroupFilterError(f"Group filter column is ambiguous in {path.name}: {filter_key}")

    canonical_key = GROUP_COLUMN_CANONICAL[filter_key]
    canonical_matches = [
        column
        for normalized_column, matching_columns in normalized_columns.items()
        if GROUP_COLUMN_CANONICAL.get(normalized_column) == canonical_key
        for column in matching_columns
    ]
    if len(canonical_matches) == 1:
        return canonical_matches[0]
    if len(canonical_matches) > 1:
        raise GroupFilterError(
            f"Group filter alias matches multiple columns in {path.name}: {filter_key}",
            hint="Use the exact column name to disambiguate the filter.",
        )
    return None


def _group_value_matches(raw_value: Any, expected: str) -> bool:
    if expected == MISSING_GROUP_VALUE:
        return raw_value is None or (isinstance(raw_value, str) and not raw_value.strip())
    if raw_value is None or isinstance(raw_value, (dict, list)):
        return False
    return str(raw_value).strip().casefold() == expected.casefold()


def _numeric_stats(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> dict[str, dict[str, float | int]]:
    stats: dict[str, dict[str, float | int]] = {}
    for column in columns:
        values: list[float] = []
        missing_count = 0
        non_numeric_count = 0
        ignored_non_finite = 0
        for row in rows:
            raw_value = row.get(column)
            if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
                missing_count += 1
                continue
            if isinstance(raw_value, bool):
                non_numeric_count += 1
                continue
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError):
                non_numeric_count += 1
                continue
            if not math.isfinite(numeric_value):
                ignored_non_finite += 1
                continue
            values.append(numeric_value)
        if values:
            stats[column] = {
                "total_count": len(rows),
                "count": len(values),
                "missing_count": missing_count,
                "non_numeric_count": non_numeric_count,
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
                "stddev": statistics.stdev(values) if len(values) > 1 else 0.0,
                "ignored_non_finite": ignored_non_finite,
                "valid_ratio": len(values) / len(rows),
            }
    return stats


def _group_values(
    rows: list[dict[str, Any]],
    columns: list[str],
) -> dict[str, tuple[str, ...]]:
    groups: dict[str, tuple[str, ...]] = {}
    for column in columns:
        if _normalize_column_name(column) not in GROUP_COLUMN_ALIASES:
            continue
        values: dict[str, str] = {}
        missing = False
        omitted = False
        for row in rows:
            raw_value = row.get(column)
            if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
                missing = True
                continue
            if isinstance(raw_value, (dict, list)):
                continue
            rendered_value = str(raw_value).strip()
            normalized_value = rendered_value.casefold()
            if normalized_value in values:
                continue
            if len(values) < MAX_GROUP_VALUES:
                values[normalized_value] = rendered_value
            else:
                omitted = True
        if values:
            if missing:
                if len(values) < MAX_GROUP_VALUES:
                    values[MISSING_GROUP_VALUE.casefold()] = MISSING_GROUP_VALUE
                else:
                    omitted = True
            rendered_values = set(values.values())
            if omitted:
                rendered_values.add(OMITTED_GROUP_VALUES)
            groups[column] = tuple(sorted(rendered_values))
    return groups


def _normalize_column_name(column: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", column.strip().lower()).strip("_")


def _ambiguous_group_columns(group_values: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    return tuple(column for column, values in group_values.items() if len(values) > 1)


def _tabular_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list) and all(isinstance(record, dict) for record in payload):
        return payload
    if isinstance(payload, dict):
        for key in ("records", "results", "runs", "metrics"):
            candidate = payload.get(key)
            if isinstance(candidate, list) and all(isinstance(record, dict) for record in candidate):
                return candidate
    return []


def _replace_tabular_records(payload: Any, rows: list[dict[str, Any]]) -> Any:
    if isinstance(payload, list):
        return rows
    if isinstance(payload, dict):
        filtered_payload = dict(payload)
        for key in ("records", "results", "runs", "metrics"):
            candidate = payload.get(key)
            if isinstance(candidate, list) and all(isinstance(record, dict) for record in candidate):
                filtered_payload[key] = rows
                return filtered_payload
    return rows


def _record_columns(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({str(column) for row in rows for column in row})


def _segments_for_source(
    *,
    source_id: str,
    source_path: str,
    source_type: SourceType,
    content_hash: str,
    excerpt: str,
) -> tuple[LoadedSegment, ...]:
    if source_type is SourceType.PDF:
        segments = _pdf_segments(
            source_id=source_id,
            source_path=source_path,
            source_type=source_type,
            content_hash=content_hash,
            excerpt=excerpt,
        )
    else:
        segments = _line_segments(
            source_id=source_id,
            source_path=source_path,
            source_type=source_type,
            content_hash=content_hash,
            text=excerpt,
        )
    return tuple(segments)


def _line_segments(
    *,
    source_id: str,
    source_path: str,
    source_type: SourceType,
    content_hash: str,
    text: str,
    page: int | None = None,
) -> list[LoadedSegment]:
    lines = text.splitlines() or [""]
    segments: list[LoadedSegment] = []
    for offset in range(0, len(lines), SEGMENT_LINE_LIMIT):
        start = offset + 1
        end = min(offset + SEGMENT_LINE_LIMIT, len(lines))
        segment_text = "\n".join(lines[offset:end])
        if page is None:
            locator = f"L{start}" if start == end else f"L{start}-L{end}"
        elif len(lines) <= SEGMENT_LINE_LIMIT:
            locator = f"P{page}"
        else:
            locator = f"P{page}:L{start}-L{end}"
        reference = SourceReference(
            source_id=source_id,
            source_path=source_path,
            source_type=source_type,
            content_hash=content_hash,
            page=page,
            line_start=start,
            line_end=end,
            excerpt=segment_text[:1000],
        )
        segments.append(LoadedSegment(locator=locator, text=segment_text, reference=reference))
    return segments


def _pdf_segments(
    *,
    source_id: str,
    source_path: str,
    source_type: SourceType,
    content_hash: str,
    excerpt: str,
) -> list[LoadedSegment]:
    matches = list(re.finditer(r"\[PAGE (\d+)\]\n", excerpt))
    segments: list[LoadedSegment] = []
    for index, match in enumerate(matches):
        page = int(match.group(1))
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(excerpt)
        page_text = excerpt[content_start:content_end].strip()
        segments.extend(
            _line_segments(
                source_id=source_id,
                source_path=source_path,
                source_type=source_type,
                content_hash=content_hash,
                text=page_text,
                page=page,
            )
        )
    return segments


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n[TRUNCATED]", True


def _reference_for_source(
    *,
    source_id: str,
    source_path: str,
    source_type: SourceType,
    content_hash: str,
    excerpt: str,
) -> SourceReference:
    line_count = max(1, excerpt.count("\n") + 1)
    return SourceReference(
        source_id=source_id,
        source_path=source_path,
        source_type=source_type,
        content_hash=content_hash,
        line_start=1,
        line_end=line_count,
        excerpt=excerpt[:1000],
    )
