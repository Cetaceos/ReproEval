"""Deterministic validators for registered report facts and evidence."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .errors import EvaluationInputError
from .models import (
    DimensionId,
    ErrorCode,
    EvaluationCase,
    EvidenceLocation,
    FindingSeverity,
)

MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024

_CITATION_PATTERN = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_.:-]*)@([^\]\r\n]+)\]")
_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_NUMBER_PATTERN = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_SLUG_PATTERN = re.compile(r"[^A-Za-z0-9_.:-]+")


@dataclass(frozen=True, slots=True)
class LoadedEvaluationCase:
    case: EvaluationCase
    manifest_path: Path
    root: Path
    report_path: Path
    report_text: str
    manifest_sha256: str
    report_sha256: str


@dataclass(frozen=True, slots=True)
class RawCheck:
    check_id: str
    validator: str
    passed: bool
    message: str
    dimensions: tuple[DimensionId, ...]
    error_code: ErrorCode
    severity_on_failure: FindingSeverity = FindingSeverity.ERROR
    evidence: tuple[EvidenceLocation, ...] = ()
    hard_cap_eligible: bool = True


def load_evaluation_case(path: str | Path) -> LoadedEvaluationCase:
    manifest_path = Path(path).expanduser().resolve()
    manifest_bytes = _read_limited(manifest_path, MAX_MANIFEST_BYTES, "evaluation manifest")
    try:
        case = EvaluationCase.model_validate_json(manifest_bytes)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid evaluation manifest: {exc}") from exc

    root = manifest_path.parent.resolve()
    report_path = _resolve_registered_path(root, case.report_path, "report")
    report_bytes = _read_limited(report_path, MAX_REPORT_BYTES, "report")
    try:
        report_text = report_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvaluationInputError("report must be UTF-8 text") from exc
    return LoadedEvaluationCase(
        case=case,
        manifest_path=manifest_path,
        root=root,
        report_path=report_path,
        report_text=report_text,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest().upper(),
        report_sha256=hashlib.sha256(report_bytes).hexdigest().upper(),
    )


def run_deterministic_validators(loaded: LoadedEvaluationCase) -> list[RawCheck]:
    lines = loaded.report_text.splitlines()
    checks: list[RawCheck] = []
    checks.extend(_validate_citations(loaded, lines))
    checks.extend(_validate_claims(loaded, lines))
    checks.extend(_validate_numbers(loaded, lines))
    checks.extend(_validate_sections(loaded, lines))
    checks.extend(_validate_uncertainty(loaded))
    checks.extend(_validate_artifacts(loaded))
    return checks


def _validate_citations(loaded: LoadedEvaluationCase, lines: list[str]) -> list[RawCheck]:
    registered = {source.source_id: set(source.locators) for source in loaded.case.sources}
    checks: list[RawCheck] = []
    citation_index = 0
    for line_number, line in enumerate(lines, start=1):
        for match in _CITATION_PATTERN.finditer(line):
            citation_index += 1
            source_id, locator = match.group(1), match.group(2).strip()
            location = _location(loaded, line_number, line)
            if source_id not in registered:
                checks.append(
                    RawCheck(
                        check_id=f"citation-{citation_index:03d}-source",
                        validator="citation_registry",
                        passed=False,
                        message=f"Citation references unregistered source '{source_id}'.",
                        dimensions=(DimensionId.EVIDENCE_TRACEABILITY,),
                        error_code=ErrorCode.FABRICATED_CITATION,
                        severity_on_failure=FindingSeverity.CRITICAL,
                        evidence=(location,),
                    )
                )
                continue
            locator_valid = locator in registered[source_id]
            checks.append(
                RawCheck(
                    check_id=f"citation-{citation_index:03d}-locator",
                    validator="citation_registry",
                    passed=locator_valid,
                    message=(
                        f"Citation [{source_id}@{locator}] has a registered locator."
                        if locator_valid
                        else f"Citation [{source_id}@{locator}] uses an unregistered locator."
                    ),
                    dimensions=(DimensionId.EVIDENCE_TRACEABILITY,),
                    error_code=ErrorCode.CITATION_MISMATCH,
                    severity_on_failure=FindingSeverity.CRITICAL,
                    evidence=(location,),
                )
            )
    return checks


def _validate_claims(loaded: LoadedEvaluationCase, lines: list[str]) -> list[RawCheck]:
    checks: list[RawCheck] = []
    for expectation in loaded.case.claims:
        match = _find_line(lines, expectation.marker)
        claim_slug = _slug(expectation.claim_id)
        if match is None:
            checks.append(
                RawCheck(
                    check_id=f"claim-{claim_slug}-presence",
                    validator="claim_presence",
                    passed=False,
                    message=f"Required claim marker '{expectation.marker}' is absent.",
                    dimensions=(DimensionId.CONTENT_COMPLETENESS,),
                    error_code=ErrorCode.SETTING_OMISSION,
                    hard_cap_eligible=False,
                )
            )
            for source_id in expectation.required_source_ids:
                checks.append(
                    RawCheck(
                        check_id=f"claim-{claim_slug}-support-{_slug(source_id)}",
                        validator="claim_support",
                        passed=False,
                        message=f"Absent claim '{expectation.claim_id}' cannot be supported by '{source_id}'.",
                        dimensions=(DimensionId.FACTUAL_ACCURACY, DimensionId.EVIDENCE_TRACEABILITY),
                        error_code=ErrorCode.UNSUPPORTED_CLAIM,
                        severity_on_failure=FindingSeverity.CRITICAL,
                    )
                )
            continue

        line_number, line = match
        location = _location(loaded, line_number, line)
        checks.append(
            RawCheck(
                check_id=f"claim-{claim_slug}-presence",
                validator="claim_presence",
                passed=True,
                message=f"Required claim '{expectation.claim_id}' is present.",
                dimensions=(DimensionId.CONTENT_COMPLETENESS,),
                error_code=ErrorCode.SETTING_OMISSION,
                evidence=(location,),
                hard_cap_eligible=False,
            )
        )
        cited_sources = {match.group(1) for match in _CITATION_PATTERN.finditer(line)}
        for source_id in expectation.required_source_ids:
            supported = source_id in cited_sources
            checks.append(
                RawCheck(
                    check_id=f"claim-{claim_slug}-support-{_slug(source_id)}",
                    validator="claim_support",
                    passed=supported,
                    message=(
                        f"Claim '{expectation.claim_id}' cites required source '{source_id}'."
                        if supported
                        else f"Claim '{expectation.claim_id}' does not cite required source '{source_id}' on its line."
                    ),
                    dimensions=(DimensionId.FACTUAL_ACCURACY, DimensionId.EVIDENCE_TRACEABILITY),
                    error_code=ErrorCode.UNSUPPORTED_CLAIM,
                    severity_on_failure=FindingSeverity.CRITICAL,
                    evidence=(location,),
                )
            )
    return checks


def _validate_numbers(loaded: LoadedEvaluationCase, lines: list[str]) -> list[RawCheck]:
    checks: list[RawCheck] = []
    for expectation in loaded.case.numeric_expectations:
        match = _find_line(lines, expectation.label)
        fact_slug = _slug(expectation.fact_id)
        if match is None:
            checks.append(
                RawCheck(
                    check_id=f"numeric-{fact_slug}-value",
                    validator="numeric_consistency",
                    passed=False,
                    message=f"Numeric label '{expectation.label}' is absent.",
                    dimensions=(DimensionId.NUMERICAL_CONSISTENCY,),
                    error_code=ErrorCode.NUMERIC_ERROR,
                    severity_on_failure=_numeric_severity(expectation.critical),
                    hard_cap_eligible=expectation.critical,
                )
            )
            continue

        line_number, line = match
        location = _location(loaded, line_number, line)
        tail_index = line.casefold().find(expectation.label.casefold()) + len(expectation.label)
        number_match = _NUMBER_PATTERN.search(line[tail_index:])
        if number_match is None:
            checks.append(
                RawCheck(
                    check_id=f"numeric-{fact_slug}-value",
                    validator="numeric_consistency",
                    passed=False,
                    message=f"No numeric value follows label '{expectation.label}'.",
                    dimensions=(DimensionId.NUMERICAL_CONSISTENCY,),
                    error_code=ErrorCode.NUMERIC_ERROR,
                    severity_on_failure=_numeric_severity(expectation.critical),
                    evidence=(location,),
                    hard_cap_eligible=expectation.critical,
                )
            )
            continue
        try:
            actual = Decimal(number_match.group(0))
        except InvalidOperation as exc:  # pragma: no cover - guarded by the number pattern
            raise EvaluationInputError(f"unable to parse numeric value for {expectation.fact_id}") from exc
        delta = abs(actual - expectation.expected)
        value_valid = delta <= expectation.absolute_tolerance
        checks.append(
            RawCheck(
                check_id=f"numeric-{fact_slug}-value",
                validator="numeric_consistency",
                passed=value_valid,
                message=(
                    f"Value {actual} is within tolerance of {expectation.expected}."
                    if value_valid
                    else (
                        f"Value {actual} differs from {expectation.expected} by {delta}, exceeding tolerance "
                        f"{expectation.absolute_tolerance}."
                    )
                ),
                dimensions=(DimensionId.NUMERICAL_CONSISTENCY,),
                error_code=ErrorCode.NUMERIC_ERROR,
                severity_on_failure=_numeric_severity(expectation.critical),
                evidence=(location,),
                hard_cap_eligible=expectation.critical,
            )
        )
        if expectation.unit is not None:
            unit_valid = expectation.unit.casefold() in line[tail_index:].casefold()
            checks.append(
                RawCheck(
                    check_id=f"numeric-{fact_slug}-unit",
                    validator="unit_consistency",
                    passed=unit_valid,
                    message=(
                        f"Expected unit '{expectation.unit}' is present."
                        if unit_valid
                        else f"Expected unit '{expectation.unit}' is absent from the numeric statement."
                    ),
                    dimensions=(DimensionId.NUMERICAL_CONSISTENCY,),
                    error_code=ErrorCode.UNIT_ERROR,
                    severity_on_failure=FindingSeverity.ERROR,
                    evidence=(location,),
                )
            )
    return checks


def _validate_sections(loaded: LoadedEvaluationCase, lines: list[str]) -> list[RawCheck]:
    headings = {
        _normalize_heading(match.group(1)): line_number
        for line_number, line in enumerate(lines, start=1)
        if (match := _HEADING_PATTERN.match(line))
    }
    checks: list[RawCheck] = []
    for expectation in loaded.case.required_sections:
        normalized = _normalize_heading(expectation.heading)
        line_number = headings.get(normalized)
        checks.append(
            RawCheck(
                check_id=f"section-{_slug(expectation.section_id)}",
                validator="required_sections",
                passed=line_number is not None,
                message=(
                    f"Required section '{expectation.heading}' is present."
                    if line_number is not None
                    else f"Required section '{expectation.heading}' is absent."
                ),
                dimensions=(DimensionId.CONTENT_COMPLETENESS,),
                error_code=ErrorCode.FORMAT_VIOLATION,
                evidence=((_location(loaded, line_number, lines[line_number - 1]),) if line_number is not None else ()),
                hard_cap_eligible=False,
            )
        )
    return checks


def _validate_uncertainty(loaded: LoadedEvaluationCase) -> list[RawCheck]:
    expectation = loaded.case.uncertainty
    if expectation is None or not expectation.required:
        return []
    report_folded = loaded.report_text.casefold()
    matched = next((phrase for phrase in expectation.accepted_phrases if phrase.casefold() in report_folded), None)
    return [
        RawCheck(
            check_id="uncertainty-disclosure",
            validator="uncertainty_disclosure",
            passed=matched is not None,
            message=(
                f"Uncertainty is disclosed using registered phrase '{matched}'."
                if matched is not None
                else "No registered uncertainty or limitation phrase is present."
            ),
            dimensions=(DimensionId.UNCERTAINTY_HANDLING,),
            error_code=ErrorCode.OVERCONFIDENCE,
            severity_on_failure=FindingSeverity.CRITICAL,
        )
    ]


def _validate_artifacts(loaded: LoadedEvaluationCase) -> list[RawCheck]:
    checks: list[RawCheck] = []
    for expectation in loaded.case.artifacts:
        artifact_path = _resolve_registered_path(loaded.root, expectation.path, "artifact")
        if not artifact_path.is_file():
            checks.append(
                RawCheck(
                    check_id=f"artifact-{_slug(expectation.artifact_id)}-sha256",
                    validator="artifact_lineage",
                    passed=False,
                    message=f"Registered artifact '{expectation.artifact_id}' is missing.",
                    dimensions=(DimensionId.EVIDENCE_TRACEABILITY,),
                    error_code=ErrorCode.ARTIFACT_LINEAGE_ERROR,
                    severity_on_failure=FindingSeverity.CRITICAL,
                    evidence=(EvidenceLocation(path=_relative(artifact_path, loaded.root)),),
                )
            )
            continue
        artifact_bytes = _read_limited(artifact_path, MAX_ARTIFACT_BYTES, "artifact")
        actual = hashlib.sha256(artifact_bytes).hexdigest().upper()
        expected = expectation.sha256.upper()
        matches = actual == expected
        checks.append(
            RawCheck(
                check_id=f"artifact-{_slug(expectation.artifact_id)}-sha256",
                validator="artifact_lineage",
                passed=matches,
                message=(
                    f"Artifact '{expectation.artifact_id}' matches its registered SHA-256."
                    if matches
                    else f"Artifact '{expectation.artifact_id}' SHA-256 does not match its registration."
                ),
                dimensions=(DimensionId.EVIDENCE_TRACEABILITY,),
                error_code=ErrorCode.ARTIFACT_LINEAGE_ERROR,
                severity_on_failure=FindingSeverity.CRITICAL,
                evidence=(EvidenceLocation(path=_relative(artifact_path, loaded.root)),),
            )
        )
    return checks


def _read_limited(path: Path, maximum_bytes: int, label: str) -> bytes:
    if not path.is_file():
        raise EvaluationInputError(f"{label} does not exist or is not a file: {path.as_posix()}")
    size = path.stat().st_size
    if size > maximum_bytes:
        raise EvaluationInputError(f"{label} exceeds {maximum_bytes} bytes: {path.as_posix()}")
    return path.read_bytes()


def _resolve_registered_path(root: Path, raw_path: str, label: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise EvaluationInputError(f"{label} path must be relative to the manifest directory")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise EvaluationInputError(f"{label} path escapes the manifest directory: {raw_path}")
    return resolved


def _find_line(lines: list[str], marker: str) -> tuple[int, str] | None:
    marker_folded = marker.casefold()
    return next(
        ((line_number, line) for line_number, line in enumerate(lines, start=1) if marker_folded in line.casefold()),
        None,
    )


def _location(loaded: LoadedEvaluationCase, line_number: int, line: str) -> EvidenceLocation:
    return EvidenceLocation(
        path=_relative(loaded.report_path, loaded.root),
        line=line_number,
        excerpt=line.strip()[:240],
    )


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _normalize_heading(value: str) -> str:
    return " ".join(value.casefold().split())


def _slug(value: str) -> str:
    return _SLUG_PATTERN.sub("-", value).strip("-") or "item"


def _numeric_severity(critical: bool) -> FindingSeverity:
    return FindingSeverity.CRITICAL if critical else FindingSeverity.ERROR
