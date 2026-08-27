"""Deterministic extraction and comparison of common experiment settings."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .loaders import LoadedBundle, LoadedSource
from .models import (
    CompareReproductionResult,
    DeterministicSettingCheck,
    DifferenceSeverity,
    EvidenceCitation,
    EvidenceSupport,
    SettingCheckStatus,
    SettingDifference,
    SourceReference,
    SourceType,
    ToolWarning,
)


@dataclass(frozen=True)
class SettingRule:
    name: str
    aliases: tuple[str, ...]
    patterns: tuple[str, ...]
    value_kind: str
    severity: DifferenceSeverity
    likely_effect: str


@dataclass(frozen=True)
class SettingObservation:
    raw_value: str
    normalized_value: str
    citation: EvidenceCitation


SETTING_RULES = (
    SettingRule(
        name="epochs",
        aliases=("epoch", "epochs", "num_epoch", "num_epochs", "training_epochs"),
        patterns=(
            r"\b(?:num(?:ber)?[\s_-]*of[\s_-]*)?(?:training[\s_-]*)?epochs?\s*(?:=|:|is|of)?\s*(\d+)\b",
            r"(?<![\w.])(\d+)\s+(?:training\s+)?epochs?\b",
        ),
        value_kind="integer",
        severity=DifferenceSeverity.CRITICAL,
        likely_effect=(
            "A different training budget can make the reported and reproduced metrics not directly comparable."
        ),
    ),
    SettingRule(
        name="learning_rate",
        aliases=("learning_rate", "learningrate", "lr"),
        patterns=(r"\b(?:learning[\s_-]*rate|lr)\s*(?:=|:|is|of)?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\b",),
        value_kind="number",
        severity=DifferenceSeverity.MATERIAL,
        likely_effect="A learning-rate mismatch can change convergence speed and final model quality.",
    ),
    SettingRule(
        name="batch_size",
        aliases=("batch_size", "batchsize", "train_batch_size"),
        patterns=(r"\b(?:training[\s_-]*)?batch[\s_-]*size\s*(?:=|:|is|of)?\s*(\d+)\b",),
        value_kind="integer",
        severity=DifferenceSeverity.MATERIAL,
        likely_effect="A batch-size mismatch can alter optimization dynamics and effective regularization.",
    ),
    SettingRule(
        name="optimizer",
        aliases=("optimizer", "optimiser", "optim"),
        patterns=(r"\b(?:optimizer|optimiser|optim)\s*(?:=|:|is)?\s*([a-z][a-z0-9_.+-]*)\b",),
        value_kind="identifier",
        severity=DifferenceSeverity.CRITICAL,
        likely_effect="A different optimizer changes the training algorithm and weakens direct comparability.",
    ),
    SettingRule(
        name="weight_decay",
        aliases=("weight_decay", "weightdecay", "wd"),
        patterns=(r"\b(?:weight[\s_-]*decay|wd)\s*(?:=|:|is|of)?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\b",),
        value_kind="number",
        severity=DifferenceSeverity.MATERIAL,
        likely_effect="A weight-decay mismatch changes regularization and may affect generalization.",
    ),
    SettingRule(
        name="scheduler",
        aliases=("scheduler", "lr_scheduler", "learning_rate_scheduler"),
        patterns=(r"\b(?:learning[\s_-]*rate[\s_-]*)?(?:lr[\s_-]*)?scheduler\s*(?:=|:|is)?\s*([a-z][a-z0-9_.+-]*)\b",),
        value_kind="identifier",
        severity=DifferenceSeverity.MATERIAL,
        likely_effect="A scheduler mismatch changes the optimization trajectory and effective learning-rate budget.",
    ),
    SettingRule(
        name="seed",
        aliases=("seed", "random_seed", "random_state"),
        patterns=(r"\b(?:random[\s_-]*)?(?:seed|state)\s*(?:=|:|is)?\s*(\d+)\b",),
        value_kind="integer",
        severity=DifferenceSeverity.MINOR,
        likely_effect=(
            "A different explicit seed may change an individual run; repeated-seed protocols should be reviewed "
            "before treating this as a comparability failure."
        ),
    ),
)

_RULE_BY_NAME = {rule.name: rule for rule in SETTING_RULES}
_RULE_BY_ALIAS = {alias: rule for rule in SETTING_RULES for alias in rule.aliases}


def build_setting_checks(
    paper_bundle: LoadedBundle,
    reproduction_bundle: LoadedBundle,
) -> list[DeterministicSettingCheck]:
    """Extract common settings locally and compare normalized values."""

    paper = _extract_bundle_settings(paper_bundle)
    reproduction = _extract_bundle_settings(reproduction_bundle)
    checks: list[DeterministicSettingCheck] = []
    for rule in SETTING_RULES:
        paper_observations = paper.get(rule.name, [])
        reproduction_observations = reproduction.get(rule.name, [])
        if not paper_observations and not reproduction_observations:
            continue
        paper_values = _display_values(paper_observations)
        reproduction_values = _display_values(reproduction_observations)
        paper_normalized = {observation.normalized_value for observation in paper_observations}
        reproduction_normalized = {observation.normalized_value for observation in reproduction_observations}
        if not paper_observations:
            status = SettingCheckStatus.MISSING_IN_PAPER
        elif not reproduction_observations:
            status = SettingCheckStatus.MISSING_IN_REPRODUCTION
        elif len(paper_normalized) > 1 or len(reproduction_normalized) > 1:
            status = SettingCheckStatus.AMBIGUOUS
        elif paper_normalized == reproduction_normalized:
            status = SettingCheckStatus.MATCH
        else:
            status = SettingCheckStatus.MISMATCH
        checks.append(
            DeterministicSettingCheck(
                setting=rule.name,
                paper_values=paper_values,
                reproduction_values=reproduction_values,
                status=status,
                paper_citations=_deduplicate_citations(paper_observations),
                reproduction_citations=_deduplicate_citations(reproduction_observations),
            )
        )
    return checks


def reconcile_setting_differences(
    result: CompareReproductionResult,
    checks: list[DeterministicSettingCheck],
) -> None:
    """Make locally checkable settings authoritative over model-proposed differences."""

    result.deterministic_setting_checks = checks
    checks_by_name = {check.setting: check for check in checks}
    retained_model_differences: list[SettingDifference] = []
    removed_model_settings: set[str] = set()
    for difference in result.setting_differences:
        canonical = canonical_setting_name(difference.setting)
        check = checks_by_name.get(canonical) if canonical else None
        if check is not None and check.status in {
            SettingCheckStatus.MATCH,
            SettingCheckStatus.MISMATCH,
            SettingCheckStatus.AMBIGUOUS,
        }:
            removed_model_settings.add(check.setting)
            continue
        retained_model_differences.append(difference)

    deterministic_differences: list[SettingDifference] = []
    for check in checks:
        if check.status is SettingCheckStatus.MISMATCH:
            rule = _RULE_BY_NAME[check.setting]
            deterministic_differences.append(
                SettingDifference(
                    setting=check.setting,
                    paper_value=", ".join(check.paper_values),
                    reproduction_value=", ".join(check.reproduction_values),
                    severity=rule.severity,
                    likely_effect=rule.likely_effect,
                    citations=[*check.paper_citations, *check.reproduction_citations],
                )
            )
            result.warnings.append(
                ToolWarning(
                    code="DETERMINISTIC_SETTING_MISMATCH",
                    message=(
                        f"Local extraction found a {check.setting} mismatch: "
                        f"paper={check.paper_values}, reproduction={check.reproduction_values}."
                    ),
                    source_references=_references_for_check(check),
                )
            )
        elif check.status is SettingCheckStatus.AMBIGUOUS:
            result.warnings.append(
                ToolWarning(
                    code="AMBIGUOUS_EXPERIMENT_SETTING",
                    message=(
                        f"Multiple {check.setting} values prevent a deterministic setting comparison: "
                        f"paper={check.paper_values}, reproduction={check.reproduction_values}."
                    ),
                    source_references=_references_for_check(check),
                )
            )
            question = f"Which {check.setting} value belongs to the exact paper and reproduction run being compared?"
            if question not in result.unresolved_questions:
                result.unresolved_questions.append(question)

    if removed_model_settings:
        result.warnings.append(
            ToolWarning(
                code="SETTING_DIFFERENCES_RECALCULATED",
                message=(
                    "Model-proposed differences were replaced by deterministic checks for: "
                    + ", ".join(sorted(removed_model_settings))
                ),
            )
        )
    result.setting_differences = [*retained_model_differences, *deterministic_differences]


def canonical_setting_name(raw_name: str) -> str | None:
    normalized = _normalize_key(raw_name)
    rule = _RULE_BY_ALIAS.get(normalized)
    return rule.name if rule else None


def _extract_bundle_settings(bundle: LoadedBundle) -> dict[str, list[SettingObservation]]:
    observations: dict[str, list[SettingObservation]] = defaultdict(list)
    for source in bundle.sources:
        if source.source_type in {SourceType.CSV, SourceType.JSON, SourceType.JSONL}:
            source_observations = _extract_structured_source(source)
        else:
            source_observations = _extract_text_source(source)
            if source.structured_summary:
                _merge_observations(source_observations, _extract_structured_mapping(source))
        for setting, values in source_observations.items():
            observations[setting].extend(values)
    return {setting: _deduplicate_observations(values) for setting, values in observations.items()}


def _merge_observations(
    target: dict[str, list[SettingObservation]],
    additions: dict[str, list[SettingObservation]],
) -> None:
    for setting, values in additions.items():
        target[setting].extend(values)


def _extract_text_source(source: LoadedSource) -> dict[str, list[SettingObservation]]:
    extracted: dict[str, list[SettingObservation]] = defaultdict(list)
    for segment in source.segments:
        for rule in SETTING_RULES:
            for pattern in rule.patterns:
                for match in re.finditer(pattern, segment.text, flags=re.IGNORECASE):
                    raw_value = match.group(1)
                    normalized = _normalize_value(rule, raw_value)
                    if normalized is None:
                        continue
                    extracted[rule.name].append(
                        SettingObservation(
                            raw_value=raw_value,
                            normalized_value=normalized,
                            citation=_citation(
                                reference=segment.reference,
                                locator=segment.locator,
                                value=raw_value,
                                setting=rule.name,
                            ),
                        )
                    )
    return extracted


def _extract_structured_source(source: LoadedSource) -> dict[str, list[SettingObservation]]:
    extracted: dict[str, list[SettingObservation]] = defaultdict(list)
    try:
        payload = json.loads(source.excerpt)
    except json.JSONDecodeError:
        return extracted
    if not source.segments:
        return extracted
    reference = source.segments[0].reference
    locator = source.segments[0].locator
    for key, value in _walk_scalar_items(payload):
        rule = _RULE_BY_ALIAS.get(_normalize_key(key))
        if rule is None:
            continue
        normalized = _normalize_value(rule, str(value))
        if normalized is None:
            continue
        extracted[rule.name].append(
            SettingObservation(
                raw_value=str(value),
                normalized_value=normalized,
                citation=_citation(
                    reference=reference,
                    locator=locator,
                    value=str(value),
                    setting=rule.name,
                ),
            )
        )
    return extracted


def _extract_structured_mapping(source: LoadedSource) -> dict[str, list[SettingObservation]]:
    """Extract known settings from YAML/log nested summaries when available."""

    extracted: dict[str, list[SettingObservation]] = defaultdict(list)
    if not source.structured_summary or not source.segments:
        return extracted
    flattened = source.structured_summary.get("flattened_scalars", {})
    if not isinstance(flattened, dict):
        return extracted
    reference = source.segments[0].reference
    locator = source.segments[0].locator
    for key, value in flattened.items():
        rule = _RULE_BY_ALIAS.get(_normalize_key(str(key).split(".")[-1]))
        if rule is None:
            continue
        normalized = _normalize_value(rule, str(value))
        if normalized is None:
            continue
        extracted[rule.name].append(
            SettingObservation(
                raw_value=str(value),
                normalized_value=normalized,
                citation=_citation(
                    reference=reference,
                    locator=locator,
                    value=str(value),
                    setting=rule.name,
                ),
            )
        )
    return extracted


def _walk_scalar_items(value: Any) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, (str, int, float)) and not isinstance(child, bool):
                items.append((str(key), child))
            else:
                items.extend(_walk_scalar_items(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(_walk_scalar_items(child))
    return items


def _normalize_value(rule: SettingRule, raw_value: str) -> str | None:
    rendered = raw_value.strip().strip("\"'")
    if rule.value_kind in {"integer", "number"}:
        try:
            numeric = Decimal(rendered)
        except InvalidOperation:
            return None
        if not numeric.is_finite():
            return None
        if rule.value_kind == "integer" and numeric != numeric.to_integral_value():
            return None
        return format(numeric.normalize(), "f")
    return re.sub(r"[^a-z0-9]+", "", rendered.casefold())


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")


def _display_values(observations: list[SettingObservation]) -> list[str]:
    displayed: dict[str, str] = {}
    for observation in observations:
        displayed.setdefault(observation.normalized_value, observation.raw_value)
    return [displayed[key] for key in sorted(displayed)]


def _deduplicate_observations(observations: list[SettingObservation]) -> list[SettingObservation]:
    deduplicated: list[SettingObservation] = []
    seen: set[tuple[str, str, str]] = set()
    for observation in observations:
        key = (
            observation.normalized_value,
            observation.citation.source_id,
            observation.citation.locator,
        )
        if key not in seen:
            seen.add(key)
            deduplicated.append(observation)
    return deduplicated


def _deduplicate_citations(observations: list[SettingObservation]) -> list[EvidenceCitation]:
    citations: list[EvidenceCitation] = []
    seen: set[tuple[str, str, str | None]] = set()
    for observation in observations:
        citation = observation.citation
        key = (citation.source_id, citation.locator, citation.quote_or_value)
        if key not in seen:
            seen.add(key)
            citations.append(citation)
    return citations


def _citation(
    *,
    reference: SourceReference,
    locator: str,
    value: str,
    setting: str,
) -> EvidenceCitation:
    return EvidenceCitation(
        source_id=reference.source_id,
        support=EvidenceSupport.MENTIONS,
        locator=locator,
        quote_or_value=value,
        rationale=f"Local extraction found the {setting} value in this source segment.",
        source_reference=reference,
    )


def _references_for_check(check: DeterministicSettingCheck) -> list[SourceReference]:
    references: list[SourceReference] = []
    seen: set[tuple[str, str]] = set()
    for citation in [*check.paper_citations, *check.reproduction_citations]:
        if citation.source_reference is None:
            continue
        key = (citation.source_reference.source_id, citation.source_reference.content_hash)
        if key not in seen:
            seen.add(key)
            references.append(citation.source_reference)
    return references
