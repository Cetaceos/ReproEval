"""Explicitly labelled, offline calibration helpers for the ISAC profile.

The calibration layer is deliberately separate from MCP Tool execution. It evaluates
already recorded predictions against an Evidence Card and never changes a Tool result,
the generic reliability score, or the profile activation threshold.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...models import DomainFindingStatus, DomainProfileName, EvidenceCitation, EvidenceSupport, ExtractClaimsResult
from .constants import ISAC_DEFAULT_ACTIVATION_THRESHOLD, ISAC_PROFILE_VERSION


class ISACCaseSplit(StrEnum):
    """Evaluation split used for an ISAC Evidence Card."""

    DEVELOPMENT = "development"
    CALIBRATION = "calibration"
    HELD_OUT = "held_out"
    NEGATIVE = "negative"
    DEMO = "demo"


class ISACCitation(BaseModel):
    """The auditable part of one citation label or prediction."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    target_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    support: EvidenceSupport
    locator: str = Field(min_length=1, max_length=200)


class ISACAnnotationProtocol(BaseModel):
    """De-identified provenance required for a human-labelled benchmark.

    The protocol is metadata supplied by the annotation team; it is not proof
    that the labels are correct.  The strict loader checks the metadata and
    source manifest before permitting calibration/held-out evaluation.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    dataset_id: str = Field(min_length=1)
    annotation_schema_version: str = Field(min_length=1)
    minimum_independent_annotators: int = Field(ge=2)
    annotator_ids: list[str] = Field(min_length=2)
    adjudicator_id: str = Field(min_length=1)
    adjudication_record_id: str = Field(min_length=1)
    adjudication_required: Literal[True] = True
    adjudication_completed: Literal[True] = True
    split_frozen: Literal[True] = True
    source_material_policy: str = Field(min_length=1)
    split_policy: str = Field(min_length=1)
    # A keyed, de-identified manifest.  Values are SHA-256 digests of the
    # source bundles; no local path, URL, or author identity is retained.
    source_manifest: dict[str, str] = Field(min_length=1)
    agreement_metric: str = Field(min_length=1)
    agreement_value: float = Field(ge=-1, le=1)
    agreement_case_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_protocol(self) -> ISACAnnotationProtocol:
        if len(set(self.annotator_ids)) != len(self.annotator_ids):
            raise ValueError("annotation_protocol.annotator_ids must be unique")
        if any(not value.strip() for value in self.annotator_ids):
            raise ValueError("annotation_protocol.annotator_ids must not contain blank IDs")
        if self.minimum_independent_annotators > len(self.annotator_ids):
            raise ValueError("annotation_protocol.minimum_independent_annotators exceeds the number of annotator_ids")
        for case_id, digest in self.source_manifest.items():
            if not case_id.strip():
                raise ValueError("annotation_protocol.source_manifest contains a blank case ID")
            if not _is_sha256(digest):
                raise ValueError(f"annotation_protocol.source_manifest has an invalid SHA-256 for {case_id!r}")
        if "deident" not in self.source_material_policy.casefold():
            raise ValueError("annotation_protocol.source_material_policy must identify de-identified source material")
        return self


class ISACEvidenceCard(BaseModel):
    """Human-provided ground truth for one bounded ISAC case."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    case_id: str = Field(min_length=1)
    split: ISACCaseSplit
    # Cases from the same paper, repository, scene, or author-created variant
    # must share a group_id and stay in one split.  Omitting it keeps legacy
    # fixtures valid by treating each case as its own group.
    group_id: str | None = Field(default=None, min_length=1)
    # Optional SHA-256 of the de-identified source bundle.  It provides a second
    # leakage guard when a paper has multiple case IDs or aliases.
    content_hash: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    expected_isac: bool
    expected_risk_rule_ids: list[str] = Field(default_factory=list)
    expected_citations: list[ISACCitation] = Field(default_factory=list)
    expected_unsupported_assertion_ids: list[str] = Field(default_factory=list)
    expected_abstention: bool | None = None
    annotation_source: Literal["expert", "reviewed", "synthetic"] = "synthetic"
    notes: str | None = None

    @model_validator(mode="after")
    def validate_labels(self) -> ISACEvidenceCard:
        if self.group_id is None:
            self.group_id = self.case_id
        if self.content_hash is not None and not _is_sha256(self.content_hash):
            raise ValueError("content_hash must be a lowercase SHA-256 hex digest")
        if len(set(self.expected_risk_rule_ids)) != len(self.expected_risk_rule_ids):
            raise ValueError("expected_risk_rule_ids must be unique")
        for rule_id in self.expected_risk_rule_ids:
            if not _is_rule_id(rule_id):
                raise ValueError(f"expected_risk_rule_ids contains an invalid rule ID: {rule_id}")
        _validate_unique_citations(self.expected_citations, field_name="expected_citations")
        _validate_unique_strings(
            self.expected_unsupported_assertion_ids,
            field_name="expected_unsupported_assertion_ids",
        )
        if self.expected_abstention is None:
            self.expected_abstention = not self.expected_isac
        return self


class ISACPrediction(BaseModel):
    """One recorded detector/profile prediction for an Evidence Card."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    case_id: str = Field(min_length=1)
    detected: bool
    # The confidence is optional for old artifacts, but required when selecting
    # a threshold from calibration data.  Keeping it with the prediction makes
    # threshold selection auditable and independent of a live detector call.
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk_rule_ids: list[str] = Field(default_factory=list)
    citations: list[ISACCitation] = Field(default_factory=list)
    assertion_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None

    @model_validator(mode="after")
    def validate_prediction(self) -> ISACPrediction:
        if len(set(self.risk_rule_ids)) != len(self.risk_rule_ids):
            raise ValueError("risk_rule_ids must be unique")
        for rule_id in self.risk_rule_ids:
            if not _is_rule_id(rule_id):
                raise ValueError(f"risk_rule_ids contains an invalid rule ID: {rule_id}")
        _validate_unique_citations(self.citations, field_name="citations")
        _validate_unique_strings(self.assertion_ids, field_name="assertion_ids")
        return self


class ISACCalibrationCase(BaseModel):
    """A labelled case plus one or more predictions for stability checks."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    label: ISACEvidenceCard
    predictions: list[ISACPrediction] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_ids(self) -> ISACCalibrationCase:
        if any(prediction.case_id != self.label.case_id for prediction in self.predictions):
            raise ValueError("all prediction case_id values must match the Evidence Card")
        run_ids = [prediction.run_id for prediction in self.predictions if prediction.run_id is not None]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("predictions must not contain duplicate run_id values")
        return self


class ISACBinaryMetrics(BaseModel):
    """Confusion counts and derived metrics for profile activation."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    case_count: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    f1: float | None = Field(default=None, ge=0, le=1)
    false_activation_rate: float | None = Field(default=None, ge=0, le=1)


class ISACSetMetrics(BaseModel):
    """Set-level precision/recall for risk-rule predictions."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    expected_count: int = Field(ge=0)
    predicted_count: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    f1: float | None = Field(default=None, ge=0, le=1)


class ISACRuleMetrics(BaseModel):
    """Per-rule binary metrics for an explicitly labelled risk rule."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    case_count: int = Field(ge=0)
    expected_positive: int = Field(ge=0)
    predicted_positive: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float | None = Field(default=None, ge=0, le=1)
    recall: float | None = Field(default=None, ge=0, le=1)
    f1: float | None = Field(default=None, ge=0, le=1)


class ISACAssertionMetrics(BaseModel):
    """Unsupported-assertion and explicit-abstention metrics."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    expected_unsupported_count: int = Field(ge=0)
    predicted_assertion_count: int = Field(ge=0)
    unsupported_assertion_count: int = Field(ge=0)
    correct_abstention_count: int = Field(ge=0)
    unsupported_assertion_rate: float | None = Field(default=None, ge=0, le=1)
    correct_abstention_rate: float | None = Field(default=None, ge=0, le=1)


class ISACCalibrationMetrics(BaseModel):
    """Metrics for one split or the complete labelled collection."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    activation: ISACBinaryMetrics
    risk_rules: ISACSetMetrics
    risk_rule_by_id: dict[str, ISACRuleMetrics] = Field(default_factory=dict)
    citations: ISACSetMetrics
    unsupported_assertions: ISACAssertionMetrics
    correct_abstention_rate: float | None = Field(default=None, ge=0, le=1)
    abstention_case_count: int = Field(ge=0)
    stability_case_count: int = Field(ge=0)
    inter_run_stability: float | None = Field(default=None, ge=0, le=1)
    citation_case_count: int = Field(default=0, ge=0)
    citation_exact_match_count: int = Field(default=0, ge=0)
    # Exact citation-set accuracy over cases that contain a citation label or
    # prediction.  Precision/recall/F1 remain available under ``citations``.
    citation_accuracy: float | None = Field(default=None, ge=0, le=1)
    # Explicit names used in reports and downstream analysis.  They mirror the
    # fields on ``unsupported_assertions`` but avoid ambiguity around UAR/CAR.
    uar: float | None = Field(default=None, ge=0, le=1)
    car: float | None = Field(default=None, ge=0, le=1)


class ISACThresholdSelection(BaseModel):
    """Threshold selected using calibration cases only.

    A selection is not a benchmark result.  The held-out split must be evaluated
    later with this frozen value; it is intentionally absent from the selection
    inputs to prevent leakage.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    source_split: Literal[ISACCaseSplit.CALIBRATION.value] = ISACCaseSplit.CALIBRATION.value
    selected_threshold: float = Field(ge=0, le=1)
    max_false_activation_rate: float = Field(ge=0, le=1)
    calibration_case_count: int = Field(ge=1)
    candidate_thresholds: list[float] = Field(min_length=1)
    metrics: ISACBinaryMetrics


class ISACCalibrationReport(BaseModel):
    """Descriptive calibration report; it is not a domain benchmark claim."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    evaluation_kind: Literal["descriptive_calibration"] = "descriptive_calibration"
    profile_version: str = Field(min_length=1)
    annotation_sources: list[str] = Field(min_length=1)
    overall: ISACCalibrationMetrics
    by_split: dict[str, ISACCalibrationMetrics] = Field(default_factory=dict)
    threshold_selection: ISACThresholdSelection | None = None
    # Stable digests make it possible to compare a report with a later rerun
    # without archiving the de-identified labels in the public repository.
    label_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    prediction_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    warnings: list[str] = Field(default_factory=list)


def prediction_from_claims_result(
    result: ExtractClaimsResult,
    *,
    case_id: str | None = None,
    run_id: str | None = None,
) -> ISACPrediction:
    """Adapt a normalized claims artifact into the calibration representation."""

    activation = result.domain_profile_activation
    detected = activation is not None and activation.effective_profile is DomainProfileName.ISAC_PHY
    risk_rule_ids = []
    citations: list[ISACCitation] = []
    assertion_ids: list[str] = []
    if result.isac_analysis is not None:
        analysis = result.isac_analysis
        if analysis.system_type.value != "unknown" or analysis.classification_citations:
            classification_id = "classification:system_type"
            _append_unique_string(assertion_ids, classification_id)
            _append_unique_citations(
                citations,
                _citations_for_target(classification_id, analysis.classification_citations),
            )
        for metric in analysis.metrics:
            target_id = f"metric:{metric.canonical_name}"
            _append_unique_string(assertion_ids, target_id)
            _append_unique_citations(citations, _citations_for_target(target_id, metric.citations))
        for assumption in analysis.assumptions:
            target_id = f"assumption:{assumption.name}"
            _append_unique_string(assertion_ids, target_id)
            _append_unique_citations(citations, _citations_for_target(target_id, assumption.citations))
        for finding in analysis.findings:
            if finding.status is not DomainFindingStatus.UNKNOWN:
                _append_unique_string(assertion_ids, finding.rule_id)
            if finding.status is DomainFindingStatus.RISK:
                _append_unique_string(risk_rule_ids, finding.rule_id)
            _append_unique_citations(citations, _citations_for_target(finding.rule_id, finding.citations))
    return ISACPrediction(
        case_id=case_id or result.run_id,
        detected=detected,
        confidence=(activation.confidence if activation is not None else None),
        risk_rule_ids=risk_rule_ids,
        citations=citations,
        assertion_ids=assertion_ids,
        run_id=run_id or result.run_id,
    )


def evaluate_isac_calibration(
    cases: Sequence[ISACCalibrationCase],
    *,
    profile_version: str = ISAC_PROFILE_VERSION,
) -> ISACCalibrationReport:
    """Evaluate explicit labels without learning or changing detector behavior."""

    if not cases:
        raise ValueError("at least one ISAC calibration case is required")
    case_ids = [case.label.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("ISAC calibration case IDs must be unique")
    validate_calibration_splits(cases)

    overall = _metrics(cases)
    by_split = {
        split.value: _metrics([case for case in cases if case.label.split is split])
        for split in ISACCaseSplit
        if any(case.label.split is split for case in cases)
    }
    warnings: list[str] = []
    present_splits = {case.label.split for case in cases}
    if ISACCaseSplit.CALIBRATION not in present_splits:
        warnings.append("No calibration split is present; threshold tuning is not supported by this report.")
    if ISACCaseSplit.HELD_OUT not in present_splits:
        warnings.append("No held_out split is present; generalization is not assessed.")
    if ISACCaseSplit.NEGATIVE not in present_splits:
        warnings.append("No negative split is present; false activation rate is incomplete.")
    if overall.stability_case_count == 0:
        warnings.append("No case has multiple predictions; inter-run stability is not assessed.")
    if overall.citations.expected_count == 0:
        warnings.append("No citation labels are present; citation accuracy is not assessed.")
    if overall.unsupported_assertions.expected_unsupported_count == 0:
        warnings.append("No unsupported assertion labels are present; UAR/CAR are not assessed.")
    if not any(case.label.annotation_source in {"expert", "reviewed"} for case in cases):
        warnings.append("No human-reviewed annotation is present; metrics are engineering regression evidence only.")

    return ISACCalibrationReport(
        profile_version=profile_version,
        annotation_sources=sorted({case.label.annotation_source for case in cases}),
        overall=overall,
        by_split=by_split,
        label_fingerprint=_cases_fingerprint(cases, include_predictions=False),
        prediction_fingerprint=_cases_fingerprint(cases, include_predictions=True),
        warnings=warnings,
    )


def _metrics(cases: Sequence[ISACCalibrationCase]) -> ISACCalibrationMetrics:
    activation_counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    expected_risks: set[tuple[str, str]] = set()
    predicted_risks: set[tuple[str, str]] = set()
    expected_citations: set[tuple[str, str, str, str, str]] = set()
    predicted_citations: set[tuple[str, str, str, str, str]] = set()
    expected_unsupported: set[tuple[str, str]] = set()
    predicted_assertions: set[tuple[str, str]] = set()
    abstention_count = 0
    correct_abstentions = 0
    stability_cases = 0
    stable_cases = 0
    citation_case_count = 0
    citation_exact_match_count = 0

    for case in cases:
        label = case.label
        primary = case.predictions[0]
        if label.expected_isac and primary.detected:
            activation_counts["tp"] += 1
        elif label.expected_isac:
            activation_counts["fn"] += 1
        elif primary.detected:
            activation_counts["fp"] += 1
        else:
            activation_counts["tn"] += 1

        expected_risks.update((label.case_id, rule_id) for rule_id in label.expected_risk_rule_ids)
        predicted_risks.update((label.case_id, rule_id) for rule_id in primary.risk_rule_ids)
        expected_citations.update((label.case_id, *_citation_key(citation)) for citation in label.expected_citations)
        predicted_citations.update((label.case_id, *_citation_key(citation)) for citation in primary.citations)
        expected_case_citations = {_citation_key(citation) for citation in label.expected_citations}
        predicted_case_citations = {_citation_key(citation) for citation in primary.citations}
        if expected_case_citations or predicted_case_citations:
            citation_case_count += 1
            citation_exact_match_count += int(expected_case_citations == predicted_case_citations)
        expected_unsupported.update(
            (label.case_id, assertion_id) for assertion_id in label.expected_unsupported_assertion_ids
        )
        predicted_assertions.update((label.case_id, assertion_id) for assertion_id in primary.assertion_ids)
        if label.expected_abstention:
            abstention_count += 1
            if not primary.detected:
                correct_abstentions += 1

        if len(case.predictions) > 1:
            stability_cases += 1
            signatures = {
                (
                    prediction.detected,
                    tuple(sorted(prediction.risk_rule_ids)),
                    tuple(sorted(prediction.assertion_ids)),
                    tuple(sorted(_citation_key(citation) for citation in prediction.citations)),
                )
                for prediction in case.predictions
            }
            stable_cases += int(len(signatures) == 1)

    true_positive_risks = expected_risks & predicted_risks
    false_positive_risks = predicted_risks - expected_risks
    false_negative_risks = expected_risks - predicted_risks
    activation = ISACBinaryMetrics(
        case_count=len(cases),
        true_positive=activation_counts["tp"],
        false_positive=activation_counts["fp"],
        true_negative=activation_counts["tn"],
        false_negative=activation_counts["fn"],
        precision=_ratio(activation_counts["tp"], activation_counts["tp"] + activation_counts["fp"]),
        recall=_ratio(activation_counts["tp"], activation_counts["tp"] + activation_counts["fn"]),
        f1=_f1(
            activation_counts["tp"],
            activation_counts["tp"] + activation_counts["fp"],
            activation_counts["tp"] + activation_counts["fn"],
        ),
        false_activation_rate=_ratio(activation_counts["fp"], activation_counts["fp"] + activation_counts["tn"]),
    )
    risk_rules = ISACSetMetrics(
        expected_count=len(expected_risks),
        predicted_count=len(predicted_risks),
        true_positive=len(true_positive_risks),
        false_positive=len(false_positive_risks),
        false_negative=len(false_negative_risks),
        precision=_ratio(len(true_positive_risks), len(true_positive_risks) + len(false_positive_risks)),
        recall=_ratio(len(true_positive_risks), len(true_positive_risks) + len(false_negative_risks)),
        f1=_f1(
            len(true_positive_risks),
            len(true_positive_risks) + len(false_positive_risks),
            len(true_positive_risks) + len(false_negative_risks),
        ),
    )
    risk_rule_ids = sorted({rule_id for _, rule_id in expected_risks | predicted_risks})
    risk_rule_by_id: dict[str, ISACRuleMetrics] = {}
    for rule_id in risk_rule_ids:
        expected_cases = {case_id for case_id, candidate in expected_risks if candidate == rule_id}
        predicted_cases = {case_id for case_id, candidate in predicted_risks if candidate == rule_id}
        true_positive_count = len(expected_cases & predicted_cases)
        false_positive_count = len(predicted_cases - expected_cases)
        false_negative_count = len(expected_cases - predicted_cases)
        risk_rule_by_id[rule_id] = ISACRuleMetrics(
            case_count=len(cases),
            expected_positive=len(expected_cases),
            predicted_positive=len(predicted_cases),
            true_positive=true_positive_count,
            false_positive=false_positive_count,
            false_negative=false_negative_count,
            precision=_ratio(true_positive_count, true_positive_count + false_positive_count),
            recall=_ratio(true_positive_count, true_positive_count + false_negative_count),
            f1=_f1(
                true_positive_count,
                true_positive_count + false_positive_count,
                true_positive_count + false_negative_count,
            ),
        )
    citation_true_positives = expected_citations & predicted_citations
    citation_false_positives = predicted_citations - expected_citations
    citation_false_negatives = expected_citations - predicted_citations
    citations = ISACSetMetrics(
        expected_count=len(expected_citations),
        predicted_count=len(predicted_citations),
        true_positive=len(citation_true_positives),
        false_positive=len(citation_false_positives),
        false_negative=len(citation_false_negatives),
        precision=_ratio(len(citation_true_positives), len(citation_true_positives) + len(citation_false_positives)),
        recall=_ratio(len(citation_true_positives), len(citation_true_positives) + len(citation_false_negatives)),
        f1=_f1(
            len(citation_true_positives),
            len(citation_true_positives) + len(citation_false_positives),
            len(citation_true_positives) + len(citation_false_negatives),
        ),
    )
    unsupported_assertions = expected_unsupported & predicted_assertions
    correctly_abstained = expected_unsupported - predicted_assertions
    unsupported_metrics = ISACAssertionMetrics(
        expected_unsupported_count=len(expected_unsupported),
        predicted_assertion_count=len(predicted_assertions),
        unsupported_assertion_count=len(unsupported_assertions),
        correct_abstention_count=len(correctly_abstained),
        unsupported_assertion_rate=_ratio(len(unsupported_assertions), len(predicted_assertions)),
        correct_abstention_rate=_ratio(len(correctly_abstained), len(expected_unsupported)),
    )
    return ISACCalibrationMetrics(
        activation=activation,
        risk_rules=risk_rules,
        risk_rule_by_id=risk_rule_by_id,
        citations=citations,
        unsupported_assertions=unsupported_metrics,
        correct_abstention_rate=_ratio(correct_abstentions, abstention_count),
        abstention_case_count=abstention_count,
        stability_case_count=stability_cases,
        inter_run_stability=_ratio(stable_cases, stability_cases),
        citation_case_count=citation_case_count,
        citation_exact_match_count=citation_exact_match_count,
        citation_accuracy=_ratio(citation_exact_match_count, citation_case_count),
        uar=unsupported_metrics.unsupported_assertion_rate,
        car=unsupported_metrics.correct_abstention_rate,
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _cases_fingerprint(
    cases: Sequence[ISACCalibrationCase],
    *,
    include_predictions: bool,
) -> str:
    """Return a deterministic digest for the evaluated labels/predictions.

    Sorting by case ID keeps the digest independent of JSON list ordering.  A
    label-only digest allows a held-out result to be compared across threshold
    runs while the prediction digest changes whenever a prediction changes.
    """

    normalized: list[dict[str, object]] = []
    for case in sorted(cases, key=lambda item: item.label.case_id):
        item: dict[str, object] = {"label": case.label.model_dump(mode="json")}
        if include_predictions:
            item["predictions"] = [prediction.model_dump(mode="json") for prediction in case.predictions]
        normalized.append(item)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _f1(true_positive: int, predicted_total: int, expected_total: int) -> float | None:
    precision = _ratio(true_positive, predicted_total)
    recall = _ratio(true_positive, expected_total)
    if precision is None or recall is None or precision + recall == 0:
        return None
    return round(2 * precision * recall / (precision + recall), 6)


def _activation_metrics(
    cases: Sequence[ISACCalibrationCase],
    *,
    threshold: float | None = None,
) -> ISACBinaryMetrics:
    """Compute activation metrics using recorded booleans or confidence scores."""

    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for case in cases:
        prediction = case.predictions[0]
        detected = prediction.detected
        if threshold is not None:
            if prediction.confidence is None:
                raise ValueError(
                    f"case {case.label.case_id!r} has no confidence; threshold selection requires recorded confidence"
                )
            detected = prediction.confidence >= threshold
        if case.label.expected_isac and detected:
            counts["tp"] += 1
        elif case.label.expected_isac:
            counts["fn"] += 1
        elif detected:
            counts["fp"] += 1
        else:
            counts["tn"] += 1
    return ISACBinaryMetrics(
        case_count=len(cases),
        true_positive=counts["tp"],
        false_positive=counts["fp"],
        true_negative=counts["tn"],
        false_negative=counts["fn"],
        precision=_ratio(counts["tp"], counts["tp"] + counts["fp"]),
        recall=_ratio(counts["tp"], counts["tp"] + counts["fn"]),
        f1=_f1(counts["tp"], counts["tp"] + counts["fp"], counts["tp"] + counts["fn"]),
        false_activation_rate=_ratio(counts["fp"], counts["fp"] + counts["tn"]),
    )


def select_activation_threshold(
    cases: Sequence[ISACCalibrationCase],
    *,
    candidate_thresholds: Sequence[float] | None = None,
    max_false_activation_rate: float = 0.05,
) -> ISACThresholdSelection:
    """Select an activation threshold from the calibration split only.

    Held-out and negative cases are deliberately excluded from tuning.  The
    caller should apply the returned threshold to a frozen model/prediction and
    then evaluate ``held_out`` separately.
    """

    if not 0 <= max_false_activation_rate <= 1:
        raise ValueError("max_false_activation_rate must be between 0 and 1")
    validate_calibration_splits(cases)
    calibration_cases = [case for case in cases if case.label.split is ISACCaseSplit.CALIBRATION]
    if not calibration_cases:
        raise ValueError("at least one calibration split case is required for threshold selection")
    if not any(case.label.expected_isac for case in calibration_cases):
        raise ValueError("calibration split must include at least one positive case")
    if not any(not case.label.expected_isac for case in calibration_cases):
        raise ValueError("calibration split must include at least one negative case")
    if any(case.predictions[0].confidence is None for case in calibration_cases):
        missing = [case.label.case_id for case in calibration_cases if case.predictions[0].confidence is None]
        raise ValueError("threshold selection requires confidence for every calibration case: " + ", ".join(missing))

    values = candidate_thresholds or [
        ISAC_DEFAULT_ACTIVATION_THRESHOLD,
        *[case.predictions[0].confidence for case in calibration_cases if case.predictions[0].confidence is not None],
    ]
    normalized = sorted({round(float(value), 6) for value in values})
    if not normalized or any(not 0 <= value <= 1 for value in normalized):
        raise ValueError("candidate_thresholds must contain values between 0 and 1")
    scored = [(threshold, _activation_metrics(calibration_cases, threshold=threshold)) for threshold in normalized]
    feasible = [
        (threshold, metrics)
        for threshold, metrics in scored
        if metrics.false_activation_rate is not None and metrics.false_activation_rate <= max_false_activation_rate
    ]
    if not feasible:
        raise ValueError("no candidate threshold satisfies max_false_activation_rate on calibration cases")
    selected_threshold, selected_metrics = max(
        feasible,
        key=lambda item: (
            item[1].f1 if item[1].f1 is not None else -1,
            item[1].recall if item[1].recall is not None else -1,
            item[1].precision if item[1].precision is not None else -1,
            item[0],
        ),
    )
    return ISACThresholdSelection(
        selected_threshold=selected_threshold,
        max_false_activation_rate=max_false_activation_rate,
        calibration_case_count=len(calibration_cases),
        candidate_thresholds=normalized,
        metrics=selected_metrics,
    )


def apply_activation_threshold(
    cases: Sequence[ISACCalibrationCase],
    threshold: float,
) -> list[ISACCalibrationCase]:
    """Return copied predictions re-evaluated at a frozen confidence threshold."""

    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    validate_calibration_splits(cases)
    updated: list[ISACCalibrationCase] = []
    for case in cases:
        predictions: list[ISACPrediction] = []
        for prediction in case.predictions:
            if prediction.confidence is None:
                raise ValueError(f"case {case.label.case_id!r} has no confidence; cannot apply an activation threshold")
            predictions.append(prediction.model_copy(update={"detected": prediction.confidence >= threshold}))
        updated.append(case.model_copy(update={"predictions": predictions}))
    return updated


def _citation_key(citation: ISACCitation) -> tuple[str, str, str, str]:
    return (citation.target_id, citation.source_id, citation.support.value, citation.locator)


def _citations_for_target(target_id: str, citations: Sequence[EvidenceCitation]) -> list[ISACCitation]:
    return [
        ISACCitation(
            target_id=target_id,
            source_id=citation.source_id,
            support=citation.support,
            locator=citation.locator,
        )
        for citation in citations
    ]


def _validate_unique_citations(citations: Sequence[ISACCitation], *, field_name: str) -> None:
    keys = [_citation_key(citation) for citation in citations]
    if len(set(keys)) != len(keys):
        raise ValueError(f"{field_name} must not contain duplicate citation records")


def _validate_unique_strings(values: Sequence[str], *, field_name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must be unique")
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} must not contain blank IDs")


def _is_rule_id(value: str) -> bool:
    return len(value) == 9 and value.startswith("ISAC-R") and value[-3:].isdigit()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def validate_calibration_splits(cases: Sequence[ISACCalibrationCase]) -> None:
    """Reject source/group overlap between calibration and held-out splits.

    Split names alone do not prevent leakage: one paper can yield many cases.
    ``group_id`` and ``content_hash`` are therefore checked independently.  A
    missing value is represented by the stable case ID and remains backwards
    compatible with older fixtures.
    """

    groups: dict[str, set[ISACCaseSplit]] = {}
    hashes: dict[str, set[ISACCaseSplit]] = {}
    for case in cases:
        split = case.label.split
        group_key = case.label.group_id or case.label.case_id
        groups.setdefault(group_key, set()).add(split)
        if case.label.content_hash:
            hashes.setdefault(case.label.content_hash, set()).add(split)
    for key, splits in groups.items():
        if len(splits) > 1:
            raise ValueError(f"calibration split leakage: group_id {key!r} occurs in multiple splits")
    for digest, splits in hashes.items():
        if len(splits) > 1:
            raise ValueError(f"calibration split leakage: content_hash {digest!r} occurs in multiple splits")


def load_calibration_cases(
    payload: Mapping[str, object],
    *,
    expected_profile_version: str = ISAC_PROFILE_VERSION,
) -> list[ISACCalibrationCase]:
    """Validate a versioned JSON fixture payload and return its labelled cases."""

    profile_version = payload.get("profile_version")
    if not isinstance(profile_version, str) or not profile_version.strip():
        raise ValueError("ISAC calibration fixture must contain a non-empty profile_version")
    if profile_version != expected_profile_version:
        raise ValueError(
            f"ISAC calibration fixture profile_version {profile_version!r} does not match "
            f"expected profile {expected_profile_version!r}."
        )
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("ISAC calibration fixture must contain a cases list")
    annotation_policy = payload.get("annotation_policy")
    allowed_policies = {"synthetic", "expert", "reviewed", "mixed", "external_human_required"}
    if annotation_policy is not None and annotation_policy not in allowed_policies:
        raise ValueError(f"unsupported annotation_policy: {annotation_policy!r}")
    cases = [ISACCalibrationCase.model_validate(case) for case in raw_cases]
    case_ids = [case.label.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("ISAC calibration fixture case IDs must be unique")
    validate_calibration_splits(cases)
    if annotation_policy == "expert" and any(case.label.annotation_source != "expert" for case in cases):
        raise ValueError("annotation_policy='expert' requires every case to have annotation_source='expert'")
    if annotation_policy == "reviewed" and any(
        case.label.annotation_source not in {"expert", "reviewed"} for case in cases
    ):
        raise ValueError("annotation_policy='reviewed' cannot include synthetic cases")
    return cases


def load_expert_calibration_cases(
    payload: Mapping[str, object],
    *,
    expected_profile_version: str = ISAC_PROFILE_VERSION,
    require_provenance: bool = False,
) -> list[ISACCalibrationCase]:
    """Load a human-annotation fixture and reject synthetic labels.

    This is the import boundary for a real calibration/held-out dataset.  The
    repository intentionally does not fabricate expert labels; callers supply a
    JSON payload exported by their annotation process and retain its provenance.
    """

    annotation_policy = payload.get("annotation_policy")
    if annotation_policy not in {"expert", "reviewed", "mixed"}:
        raise ValueError("human annotation fixture must declare annotation_policy as 'expert', 'reviewed', or 'mixed'")
    cases = load_calibration_cases(payload, expected_profile_version=expected_profile_version)
    if not cases:
        raise ValueError("human annotation fixture must contain at least one labelled case")
    if any(case.label.annotation_source == "synthetic" for case in cases):
        raise ValueError("human annotation fixture cannot contain synthetic labels")
    required_splits = {ISACCaseSplit.CALIBRATION, ISACCaseSplit.HELD_OUT}
    present_splits = {case.label.split for case in cases}
    missing = required_splits - present_splits
    if missing:
        missing_names = ", ".join(sorted(split.value for split in missing))
        raise ValueError("human annotation fixture is missing required split(s): " + missing_names)
    if require_provenance:
        _validate_human_annotation_protocol(payload, cases)
    return cases


def _validate_human_annotation_protocol(
    payload: Mapping[str, object],
    cases: Sequence[ISACCalibrationCase],
) -> None:
    """Require provenance metadata before a fixture is accepted as benchmark input."""

    protocol = payload.get("annotation_protocol")
    if not isinstance(protocol, Mapping):
        raise ValueError("human annotation fixture requires annotation_protocol provenance metadata")
    try:
        validated = ISACAnnotationProtocol.model_validate(protocol)
    except ValueError as exc:
        # Keep the public error actionable while preserving Pydantic's field
        # details for callers that need to repair an external annotation file.
        raise ValueError(f"invalid annotation_protocol: {exc}") from exc

    case_ids = {case.label.case_id for case in cases}
    manifest_ids = set(validated.source_manifest)
    if manifest_ids != case_ids:
        missing = sorted(case_ids - manifest_ids)
        extra = sorted(manifest_ids - case_ids)
        details: list[str] = []
        if missing:
            details.append("missing case IDs: " + ", ".join(missing))
        if extra:
            details.append("unknown case IDs: " + ", ".join(extra))
        raise ValueError("annotation_protocol.source_manifest does not match cases (" + "; ".join(details) + ")")

    missing_hashes = [case.label.case_id for case in cases if case.label.content_hash is None]
    if missing_hashes:
        raise ValueError(
            "human benchmark cases require content_hash for every source bundle: " + ", ".join(missing_hashes)
        )
    mismatches = [
        case.label.case_id for case in cases if case.label.content_hash != validated.source_manifest[case.label.case_id]
    ]
    if mismatches:
        raise ValueError("annotation_protocol.source_manifest hash mismatch for case(s): " + ", ".join(mismatches))


def _append_unique_string(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _append_unique_citations(values: list[ISACCitation], citations: Sequence[ISACCitation]) -> None:
    existing = {_citation_key(citation) for citation in values}
    for citation in citations:
        key = _citation_key(citation)
        if key not in existing:
            values.append(citation)
            existing.add(key)
