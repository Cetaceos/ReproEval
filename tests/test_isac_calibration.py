from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hy3_reproscope_mcp.models import ExtractClaimsResult
from hy3_reproscope_mcp.profiles.isac_phy import (
    ISACAnnotationProtocol,
    ISACCalibrationCase,
    ISACCaseSplit,
    ISACEvidenceCard,
    ISACPrediction,
    apply_activation_threshold,
    evaluate_isac_calibration,
    load_calibration_cases,
    load_expert_calibration_cases,
    prediction_from_claims_result,
    select_activation_threshold,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_calibration_fixture_reports_descriptive_metrics() -> None:
    payload = json.loads((PROJECT_ROOT / "evals" / "synthetic_isac_calibration.json").read_text(encoding="utf-8"))
    report = evaluate_isac_calibration(load_calibration_cases(payload))

    assert report.evaluation_kind == "descriptive_calibration"
    assert report.annotation_sources == ["synthetic"]
    assert report.overall.activation.precision == 1
    assert report.overall.activation.recall == 1
    assert report.overall.activation.false_activation_rate == 0
    assert report.overall.risk_rules.precision == 1
    assert report.overall.risk_rules.recall == 1
    assert report.overall.citations.precision == 1
    assert report.overall.citations.recall == 1
    assert report.overall.citation_accuracy == 1
    assert report.overall.uar == 0
    assert report.overall.car == 1
    assert report.overall.risk_rule_by_id["ISAC-R001"].precision == 1
    assert report.overall.risk_rule_by_id["ISAC-R002"].recall == 1
    assert report.overall.unsupported_assertions.unsupported_assertion_rate == 0
    assert report.overall.unsupported_assertions.correct_abstention_rate == 1
    assert report.overall.correct_abstention_rate == 1
    assert report.overall.inter_run_stability == 1
    assert report.overall.stability_case_count == 2
    assert len(report.label_fingerprint or "") == 64
    assert len(report.prediction_fingerprint or "") == 64
    assert not any("not assessed" in warning for warning in report.warnings)


def test_checked_in_calibration_case_schema_matches_model() -> None:
    checked_in_schema = json.loads(
        (PROJECT_ROOT / "evals" / "isac_calibration_case.schema.json").read_text(encoding="utf-8")
    )
    assert checked_in_schema == ISACCalibrationCase.model_json_schema()


def test_calibration_metrics_keep_false_activation_and_risk_errors_separate() -> None:
    cases = [
        ISACCalibrationCase(
            label=ISACEvidenceCard(
                case_id="positive",
                split=ISACCaseSplit.CALIBRATION,
                expected_isac=True,
                expected_risk_rule_ids=["ISAC-R001"],
                expected_citations=[
                    {"target_id": "ISAC-R001", "source_id": "paper_1", "support": "mentions", "locator": "L1"}
                ],
                expected_unsupported_assertion_ids=["ISAC-R001"],
            ),
            predictions=[
                ISACPrediction(
                    case_id="positive",
                    detected=False,
                    risk_rule_ids=["ISAC-R999"],
                    citations=[
                        {"target_id": "ISAC-R001", "source_id": "paper_1", "support": "mentions", "locator": "L2"}
                    ],
                    assertion_ids=["ISAC-R001"],
                )
            ],
        ),
        ISACCalibrationCase(
            label=ISACEvidenceCard(
                case_id="negative",
                split=ISACCaseSplit.NEGATIVE,
                expected_isac=False,
            ),
            predictions=[ISACPrediction(case_id="negative", detected=True)],
        ),
    ]

    report = evaluate_isac_calibration(cases)
    assert report.overall.activation.true_positive == 0
    assert report.overall.activation.false_positive == 1
    assert report.overall.activation.false_negative == 1
    assert report.overall.activation.false_activation_rate == 1
    assert report.overall.risk_rules.true_positive == 0
    assert report.overall.risk_rules.false_positive == 1
    assert report.overall.risk_rules.false_negative == 1
    assert report.overall.citations.true_positive == 0
    assert report.overall.citations.false_positive == 1
    assert report.overall.citations.false_negative == 1
    assert report.overall.unsupported_assertions.unsupported_assertion_rate == 1
    assert report.overall.unsupported_assertions.correct_abstention_rate == 0
    assert report.overall.correct_abstention_rate == 0
    assert any("held_out" in warning for warning in report.warnings)


def test_calibration_rejects_duplicate_rule_labels() -> None:
    with pytest.raises(ValidationError, match="expected_risk_rule_ids"):
        ISACEvidenceCard(
            case_id="duplicate",
            split="development",
            expected_isac=True,
            expected_risk_rule_ids=["ISAC-R001", "ISAC-R001"],
        )


def test_calibration_rejects_duplicate_citations() -> None:
    with pytest.raises(ValidationError, match="expected_citations"):
        ISACEvidenceCard(
            case_id="duplicate-citation",
            split="development",
            expected_isac=True,
            expected_citations=[
                {"target_id": "ISAC-R001", "source_id": "paper_1", "support": "mentions", "locator": "L1"},
                {"target_id": "ISAC-R001", "source_id": "paper_1", "support": "mentions", "locator": "L1"},
            ],
        )


def test_prediction_adapter_uses_only_normalized_risk_findings() -> None:
    result = ExtractClaimsResult.model_validate(
        {
            "run_id": "claims-run",
            "summary": "ISAC result",
            "domain_profile_activation": {
                "effective_profile": "isac_phy",
                "profile_version": "1.0.0",
            },
            "isac_analysis": {
                "findings": [
                    {
                        "rule_id": "ISAC-R001",
                        "status": "risk",
                        "summary": "Risk",
                        "rationale": "Evidence",
                        "citations": [
                            {
                                "source_id": "paper_1",
                                "support": "mentions",
                                "locator": "L1",
                                "rationale": "The source supports the rule.",
                            }
                        ],
                    },
                    {
                        "rule_id": "ISAC-R002",
                        "status": "unknown",
                        "summary": "Unknown",
                        "rationale": "No evidence",
                    },
                ]
            },
        }
    )

    prediction = prediction_from_claims_result(result, case_id="labelled-case", run_id="claims-run")
    assert prediction.case_id == "labelled-case"
    assert prediction.detected is True
    assert prediction.risk_rule_ids == ["ISAC-R001"]
    assert prediction.assertion_ids == ["ISAC-R001"]
    assert prediction.citations[0].target_id == "ISAC-R001"
    assert prediction.citations[0].locator == "L1"
    assert prediction.run_id == "claims-run"


def test_prediction_adapter_deduplicates_repeated_normalized_evidence() -> None:
    result = ExtractClaimsResult.model_validate(
        {
            "run_id": "claims-run-dedup",
            "summary": "ISAC result",
            "domain_profile_activation": {
                "effective_profile": "isac_phy",
                "profile_version": "1.0.0",
            },
            "isac_analysis": {
                "findings": [
                    {
                        "rule_id": "ISAC-R001",
                        "status": "risk",
                        "summary": "Risk",
                        "rationale": "Evidence",
                        "citations": [
                            {
                                "source_id": "paper_1",
                                "support": "mentions",
                                "locator": "L1",
                                "rationale": "The source supports the rule.",
                            }
                        ],
                    },
                    {
                        "rule_id": "ISAC-R001",
                        "status": "risk",
                        "summary": "Repeated risk",
                        "rationale": "Repeated evidence",
                        "citations": [
                            {
                                "source_id": "paper_1",
                                "support": "mentions",
                                "locator": "L1",
                                "rationale": "The same source supports the rule.",
                            }
                        ],
                    },
                ]
            },
        }
    )

    prediction = prediction_from_claims_result(result)

    assert prediction.risk_rule_ids == ["ISAC-R001"]
    assert prediction.assertion_ids == ["ISAC-R001"]
    assert len(prediction.citations) == 1


def test_calibration_fixture_requires_profile_version() -> None:
    with pytest.raises(ValueError, match="profile_version"):
        load_calibration_cases({"cases": []})


def test_public_candidate_records_keep_source_integrity_without_becoming_labels() -> None:
    payload = json.loads((PROJECT_ROOT / "evals" / "isac_public_candidate_cases.json").read_text(encoding="utf-8"))

    assert payload["benchmark_status"] == "not_eligible_without_two_expert_adjudication"
    assert payload["review_protocol"]["split_frozen"] is False
    assert len(payload["cases"]) == 5
    for case in payload["cases"]:
        assert case["benchmark_eligible"] is False
        assert case["split_status"] == "proposed_only_not_frozen"
        assert case["label_status"] == "single_reviewer_public_metadata_review"
        assert hashlib.sha256(case["source_url"].encode("utf-8")).hexdigest() == case["source_locator_sha256"]

    # The public records intentionally do not use the Evidence Card schema and
    # cannot be silently promoted to calibration or held-out ground truth.
    with pytest.raises(ValidationError):
        load_calibration_cases(payload)
    with pytest.raises(ValueError, match="human annotation fixture"):
        load_expert_calibration_cases(payload, require_provenance=True)


def test_calibration_fixture_rejects_wrong_profile_version() -> None:
    payload = json.loads((PROJECT_ROOT / "evals" / "synthetic_isac_calibration.json").read_text(encoding="utf-8"))
    payload["profile_version"] = "0.0.0"

    with pytest.raises(ValueError, match="does not match expected profile"):
        load_calibration_cases(payload)


def _threshold_case(case_id: str, split: ISACCaseSplit, expected_isac: bool, confidence: float) -> ISACCalibrationCase:
    return ISACCalibrationCase(
        label=ISACEvidenceCard(
            case_id=case_id,
            split=split,
            expected_isac=expected_isac,
            group_id=case_id,
        ),
        predictions=[ISACPrediction(case_id=case_id, detected=confidence >= 0.8, confidence=confidence)],
    )


def test_threshold_selection_uses_calibration_only_and_can_be_frozen_for_held_out() -> None:
    cases = [
        _threshold_case("cal-pos", ISACCaseSplit.CALIBRATION, True, 0.70),
        _threshold_case("cal-neg", ISACCaseSplit.CALIBRATION, False, 0.20),
        # This deliberately disagrees with calibration.  It must not influence
        # the selected threshold or make the calibration result look better.
        _threshold_case("held-neg", ISACCaseSplit.HELD_OUT, False, 0.95),
    ]

    selection = select_activation_threshold(cases, candidate_thresholds=[0.5, 0.8], max_false_activation_rate=0)
    assert selection.selected_threshold == 0.5
    assert selection.calibration_case_count == 2
    assert selection.metrics.false_activation_rate == 0

    frozen = apply_activation_threshold(cases, selection.selected_threshold)
    report = evaluate_isac_calibration(frozen)
    assert report.by_split[ISACCaseSplit.CALIBRATION.value].activation.recall == 1
    assert report.by_split[ISACCaseSplit.HELD_OUT.value].activation.false_positive == 1


def test_report_label_fingerprint_survives_frozen_threshold_application() -> None:
    cases = [
        _threshold_case("cal-pos", ISACCaseSplit.CALIBRATION, True, 0.70),
        _threshold_case("cal-neg", ISACCaseSplit.CALIBRATION, False, 0.20),
        _threshold_case("held-pos", ISACCaseSplit.HELD_OUT, True, 0.90),
    ]
    before = evaluate_isac_calibration(cases)
    frozen = apply_activation_threshold(cases, 0.5)
    after = evaluate_isac_calibration(frozen)
    assert before.label_fingerprint == after.label_fingerprint
    assert before.prediction_fingerprint != after.prediction_fingerprint


def test_threshold_selection_requires_confidence_for_every_calibration_case() -> None:
    cases = [
        _threshold_case("cal-pos", ISACCaseSplit.CALIBRATION, True, 0.70),
        ISACCalibrationCase(
            label=ISACEvidenceCard(case_id="cal-neg", split="calibration", expected_isac=False),
            predictions=[ISACPrediction(case_id="cal-neg", detected=False)],
        ),
    ]
    with pytest.raises(ValueError, match="requires confidence"):
        select_activation_threshold(cases)


def test_split_validation_rejects_group_and_content_hash_leakage() -> None:
    shared = "a" * 64
    cases = [
        ISACCalibrationCase(
            label=ISACEvidenceCard(
                case_id="calibration-paper-a",
                split="calibration",
                expected_isac=True,
                group_id="paper-a",
                content_hash=shared,
            ),
            predictions=[ISACPrediction(case_id="calibration-paper-a", detected=True)],
        ),
        ISACCalibrationCase(
            label=ISACEvidenceCard(
                case_id="held-out-paper-a",
                split="held_out",
                expected_isac=True,
                group_id="paper-a",
                content_hash=shared,
            ),
            predictions=[ISACPrediction(case_id="held-out-paper-a", detected=True)],
        ),
    ]
    with pytest.raises(ValueError, match="split leakage"):
        evaluate_isac_calibration(cases)


def test_expert_loader_rejects_synthetic_cases_and_requires_calibration_and_held_out() -> None:
    payload = {
        "profile_version": "1.0.0",
        "annotation_policy": "expert",
        "cases": [
            {
                "label": {
                    "case_id": "expert-cal",
                    "split": "calibration",
                    "expected_isac": True,
                    "annotation_source": "expert",
                },
                "predictions": [{"case_id": "expert-cal", "detected": True}],
            },
            {
                "label": {
                    "case_id": "expert-held",
                    "split": "held_out",
                    "expected_isac": False,
                    "annotation_source": "expert",
                },
                "predictions": [{"case_id": "expert-held", "detected": False}],
            },
        ],
    }
    assert len(load_expert_calibration_cases(payload)) == 2
    payload["cases"][0]["label"]["annotation_source"] = "synthetic"
    with pytest.raises(ValueError, match="requires every case"):
        load_expert_calibration_cases(payload)


def test_strict_expert_loader_requires_review_protocol_and_source_hashes() -> None:
    payload = {
        "profile_version": "1.0.0",
        "annotation_policy": "expert",
        "cases": [
            {
                "label": {
                    "case_id": "expert-cal",
                    "split": "calibration",
                    "expected_isac": True,
                    "annotation_source": "expert",
                },
                "predictions": [{"case_id": "expert-cal", "detected": True}],
            },
            {
                "label": {
                    "case_id": "expert-held",
                    "split": "held_out",
                    "expected_isac": False,
                    "annotation_source": "expert",
                },
                "predictions": [{"case_id": "expert-held", "detected": False}],
            },
        ],
    }
    with pytest.raises(ValueError, match="annotation_protocol"):
        load_expert_calibration_cases(payload, require_provenance=True)


def _strict_expert_payload() -> dict[str, object]:
    cal_hash = "a" * 64
    held_hash = "b" * 64
    return {
        "profile_version": "1.0.0",
        "annotation_policy": "expert",
        "annotation_protocol": {
            "dataset_id": "isac-human-v1",
            "annotation_schema_version": "isac-evidence-card-v1",
            "minimum_independent_annotators": 2,
            "annotator_ids": ["annotator-a", "annotator-b"],
            "adjudicator_id": "adjudicator-c",
            "adjudication_record_id": "adj-001",
            "adjudication_required": True,
            "adjudication_completed": True,
            "split_frozen": True,
            "source_material_policy": "deidentified_full_text_with_page_or_line_locators",
            "split_policy": "grouped_by_source_before_calibration_and_held_out_freeze",
            "source_manifest": {"expert-cal": cal_hash, "expert-held": held_hash},
            "agreement_metric": "cohen_kappa",
            "agreement_value": 0.82,
            "agreement_case_count": 2,
        },
        "cases": [
            {
                "label": {
                    "case_id": "expert-cal",
                    "split": "calibration",
                    "group_id": "paper-cal",
                    "content_hash": cal_hash,
                    "expected_isac": True,
                    "annotation_source": "expert",
                },
                "predictions": [{"case_id": "expert-cal", "detected": True, "run_id": "run-cal"}],
            },
            {
                "label": {
                    "case_id": "expert-held",
                    "split": "held_out",
                    "group_id": "paper-held",
                    "content_hash": held_hash,
                    "expected_isac": False,
                    "annotation_source": "expert",
                },
                "predictions": [{"case_id": "expert-held", "detected": False, "run_id": "run-held"}],
            },
        ],
    }


def test_strict_expert_loader_accepts_complete_deidentified_protocol() -> None:
    payload = _strict_expert_payload()
    assert len(load_expert_calibration_cases(payload, require_provenance=True)) == 2


def test_strict_expert_loader_rejects_source_manifest_mismatch() -> None:
    payload = _strict_expert_payload()
    protocol = payload["annotation_protocol"]
    assert isinstance(protocol, dict)
    protocol["source_manifest"]["expert-held"] = "c" * 64
    with pytest.raises(ValueError, match="source_manifest hash mismatch"):
        load_expert_calibration_cases(payload, require_provenance=True)


def test_annotation_protocol_rejects_duplicate_annotator_ids() -> None:
    with pytest.raises(ValidationError, match="annotator_ids must be unique"):
        ISACAnnotationProtocol(
            dataset_id="dataset",
            annotation_schema_version="v1",
            minimum_independent_annotators=2,
            annotator_ids=["same", "same"],
            adjudicator_id="adj",
            adjudication_record_id="record",
            source_material_policy="deidentified source",
            split_policy="grouped",
            source_manifest={"case": "a" * 64},
            agreement_metric="cohen_kappa",
            agreement_value=0.8,
            agreement_case_count=1,
        )


def test_calibration_case_rejects_duplicate_prediction_run_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate run_id"):
        ISACCalibrationCase(
            label=ISACEvidenceCard(case_id="duplicate-run", split="calibration", expected_isac=True),
            predictions=[
                ISACPrediction(case_id="duplicate-run", detected=True, run_id="run-1"),
                ISACPrediction(case_id="duplicate-run", detected=True, run_id="run-1"),
            ],
        )
