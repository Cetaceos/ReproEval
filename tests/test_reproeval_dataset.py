from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hy3_reproeval.dataset import (
    AdversarialAttackType,
    DatasetSplit,
    QualityTier,
    replay_mutation_manifest,
    validate_dataset_manifest,
)
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.models import ErrorCode


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


def _high_report() -> str:
    return """# Reproduction Review

## Executive summary

The reproduced Accuracy is 0.876 [paper@L3-L4] [results@rows:1-5].

## Evidence and limitations

Five runs support the gap, but there is insufficient evidence for one causal attribution.

## Next steps

Run the registered ablation with fixed preprocessing and confidence intervals.
"""


def _medium_report() -> str:
    return (
        _high_report()
        .replace(
            "Five runs support the gap, but there is insufficient evidence for one causal attribution.",
            "The result is different. There is insufficient evidence.",
        )
        .replace(
            "Run the registered ablation with fixed preprocessing and confidence intervals.",
            "Do more work.",
        )
    )


def _low_report() -> str:
    return _medium_report().replace(
        "The reproduced Accuracy is 0.876 [paper@L3-L4] [results@rows:1-5].",
        "The reproduced Accuracy is 0.500 [invented@L1] [results@rows:1-5].",
    )


def _case(case_id: str, report_path: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "scenario": "reproduction",
        "report_path": report_path,
        "sources": [
            {"source_id": "paper", "locators": ["L3-L4"]},
            {"source_id": "results", "locators": ["rows:1-5"]},
        ],
        "claims": [
            {
                "claim_id": "accuracy",
                "marker": "reproduced Accuracy",
                "required_source_ids": ["paper", "results"],
            }
        ],
        "numeric_expectations": [
            {
                "fact_id": "accuracy",
                "label": "Accuracy is",
                "expected": "0.876",
                "absolute_tolerance": "0.0001",
                "critical": True,
            }
        ],
        "required_sections": [
            {"section_id": "summary", "heading": "Executive summary"},
            {"section_id": "limitations", "heading": "Evidence and limitations"},
            {"section_id": "next", "heading": "Next steps"},
        ],
        "uncertainty": {"required": True, "accepted_phrases": ["insufficient evidence"]},
        "artifacts": [],
    }


def _operation(
    operation_id: str,
    target: str,
    replacement: str,
    dimensions: list[str],
    errors: list[str],
) -> dict[str, object]:
    return {
        "operation_id": operation_id,
        "kind": "replace_once",
        "target": target,
        "replacement": replacement,
        "expected_dimensions": dimensions,
        "expected_error_codes": errors,
    }


def _write_dataset(tmp_path: Path, *, include_adversarial: bool = False) -> Path:
    high = _high_report()
    medium = _medium_report()
    low = _low_report()
    adversarial = high.replace(
        "The reproduced Accuracy is 0.876 [paper@L3-L4] [results@rows:1-5].",
        "The reproduced Accuracy is 0.500 [invented@L1] [results@rows:1-5].",
    )
    reports = [("high.md", high), ("medium.md", medium), ("low.md", low)]
    if include_adversarial:
        reports.append(("adversarial.md", adversarial))
    for name, text in reports:
        (tmp_path / name).write_bytes(text.encode("utf-8"))
    cases = [("case-high", "high.md"), ("case-medium", "medium.md"), ("case-low", "low.md")]
    if include_adversarial:
        cases.append(("case-adversarial", "adversarial.md"))
    for case_id, report_path in cases:
        (tmp_path / f"{case_id}.json").write_text(
            json.dumps(_case(case_id, report_path)),
            encoding="utf-8",
        )

    medium_operations = [
        _operation(
            "weaken-reasoning",
            "Five runs support the gap, but there is insufficient evidence for one causal attribution.",
            "The result is different. There is insufficient evidence.",
            ["reasoning_consistency"],
            ["reasoning_gap"],
        ),
        _operation(
            "weaken-next-step",
            "Run the registered ablation with fixed preprocessing and confidence intervals.",
            "Do more work.",
            ["clarity_actionability"],
            ["actionability_gap"],
        ),
    ]
    low_operations = [
        *medium_operations,
        _operation(
            "corrupt-result",
            "The reproduced Accuracy is 0.876 [paper@L3-L4] [results@rows:1-5].",
            "The reproduced Accuracy is 0.500 [invented@L1] [results@rows:1-5].",
            ["factual_accuracy", "evidence_traceability", "numerical_consistency"],
            ["fabricated_citation", "unsupported_claim", "numeric_error"],
        ),
    ]
    mutations = [
        ("mutation-medium", "report-medium", "medium.md", medium, medium_operations),
        ("mutation-low", "report-low", "low.md", low, low_operations),
    ]
    if include_adversarial:
        mutations.append(
            (
                "mutation-adversarial",
                "report-adversarial",
                "adversarial.md",
                adversarial,
                [
                    _operation(
                        "adversarial-corrupt-result",
                        "The reproduced Accuracy is 0.876 [paper@L3-L4] [results@rows:1-5].",
                        "The reproduced Accuracy is 0.500 [invented@L1] [results@rows:1-5].",
                        ["factual_accuracy", "evidence_traceability", "numerical_consistency"],
                        ["fabricated_citation", "unsupported_claim", "numeric_error"],
                    )
                ],
            )
        )
    for mutation_id, report_id, output_path, output_text, operations in mutations:
        payload = {
            "schema_version": "1.0",
            "mutation_id": mutation_id,
            "parent_report_id": "report-high",
            "output_report_id": report_id,
            "parent_path": "high.md",
            "output_path": output_path,
            "parent_sha256": _sha256(high),
            "output_sha256": _sha256(output_text),
            "operations": operations,
        }
        (tmp_path / f"{mutation_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    manifest = {
        "schema_version": "1.0",
        "dataset_id": "sample-dataset",
        "dataset_version": "0.1.0",
        "description": "Synthetic three-tier report dataset for protocol validation.",
        "groups": [
            {
                "group_id": "source-group-1",
                "split": "development",
                "scenario": "reproduction",
                "provenance": {
                    "kind": "synthetic",
                    "license": "Apache-2.0",
                    "source_group_sha256": hashlib.sha256(b"source-group-1").hexdigest().upper(),
                    "acquisition_date": "2026-08-30",
                    "description": "Repository-authored synthetic evidence group.",
                },
                "reports": [
                    {
                        "report_id": "report-high",
                        "quality_tier": "high",
                        "case_path": "case-high.json",
                        "report_sha256": _sha256(high),
                        "label_source": "reference_revision",
                        "expected_error_codes": [],
                    },
                    {
                        "report_id": "report-medium",
                        "quality_tier": "medium",
                        "case_path": "case-medium.json",
                        "report_sha256": _sha256(medium),
                        "label_source": "synthetic_mutation",
                        "mutation_manifest_path": "mutation-medium.json",
                        "expected_error_codes": ["reasoning_gap", "actionability_gap"],
                    },
                    {
                        "report_id": "report-low",
                        "quality_tier": "low",
                        "case_path": "case-low.json",
                        "report_sha256": _sha256(low),
                        "label_source": "synthetic_mutation",
                        "mutation_manifest_path": "mutation-low.json",
                        "expected_error_codes": [
                            "reasoning_gap",
                            "actionability_gap",
                            "fabricated_citation",
                            "unsupported_claim",
                            "numeric_error",
                        ],
                    },
                ],
            }
        ],
    }
    if include_adversarial:
        manifest["groups"][0]["reports"].append(
            {
                "report_id": "report-adversarial",
                "quality_tier": "adversarial",
                "case_path": "case-adversarial.json",
                "report_sha256": _sha256(adversarial),
                "label_source": "synthetic_mutation",
                "mutation_manifest_path": "mutation-adversarial.json",
                "expected_error_codes": [
                    "fabricated_citation",
                    "unsupported_claim",
                    "numeric_error",
                ],
                "adversarial_spec": {
                    "schema_version": "1.0",
                    "attacks": [
                        {
                            "attack_id": "attack-fabricated-authority-001",
                            "attack_type": "fabricated_authority",
                            "target_dimensions": ["factual_accuracy", "evidence_traceability"],
                            "expected_error_codes": ["fabricated_citation", "unsupported_claim"],
                            "description": "Replace valid evidence with an invented authority marker.",
                        },
                        {
                            "attack_id": "attack-calculation-corruption-001",
                            "attack_type": "calculation_corruption",
                            "target_dimensions": ["numerical_consistency"],
                            "expected_error_codes": ["numeric_error"],
                            "description": "Replace the registered result with an incorrect value.",
                        },
                    ],
                },
            }
        )
    manifest_path = tmp_path / "dataset.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_dataset_validator_replays_mutations_and_closes_expected_errors(tmp_path: Path) -> None:
    result = validate_dataset_manifest(_write_dataset(tmp_path))

    assert result.valid is True
    assert result.group_count == 1
    assert result.report_count == 3
    assert result.mutation_count == 2
    assert result.split_counts == {DatasetSplit.DEVELOPMENT: 1}
    assert result.tier_counts[QualityTier.HIGH] == 1
    assert result.deterministic_error_counts[ErrorCode.FABRICATED_CITATION] == 1
    assert result.deterministic_error_counts[ErrorCode.UNSUPPORTED_CLAIM] == 1
    assert result.deterministic_error_counts[ErrorCode.NUMERIC_ERROR] == 1
    assert any("P0 target" in warning for warning in result.warnings)


def test_dataset_validates_adversarial_attack_contract(tmp_path: Path) -> None:
    result = validate_dataset_manifest(_write_dataset(tmp_path, include_adversarial=True))

    assert result.report_count == 4
    assert result.adversarial_report_count == 1
    assert result.attack_instance_count == 2
    assert result.attack_type_counts == {
        AdversarialAttackType.FABRICATED_AUTHORITY: 1,
        AdversarialAttackType.CALCULATION_CORRUPTION: 1,
    }


def test_dataset_rejects_adversarial_report_without_attack_spec(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path, include_adversarial=True)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    del payload["groups"][0]["reports"][3]["adversarial_spec"]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="requires adversarial_spec"):
        validate_dataset_manifest(manifest_path)


def test_dataset_rejects_attack_error_absent_from_report_labels(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path, include_adversarial=True)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["groups"][0]["reports"][3]["adversarial_spec"]["attacks"][0][
        "expected_error_codes"
    ].append("overconfidence")
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="attack errors must be declared"):
        validate_dataset_manifest(manifest_path)


def test_dataset_rejects_attack_dimension_absent_from_mutation(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path, include_adversarial=True)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["groups"][0]["reports"][3]["adversarial_spec"]["attacks"][0][
        "target_dimensions"
    ].append("content_completeness")
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="dimensions must be covered"):
        validate_dataset_manifest(manifest_path)


def test_dataset_rejects_attack_id_reused_by_another_report(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path, include_adversarial=True)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    duplicate = json.loads(json.dumps(payload["groups"][0]["reports"][3]))
    duplicate["report_id"] = "report-adversarial-human-reviewed"
    duplicate["case_path"] = "unused-case.json"
    duplicate["report_sha256"] = "A" * 64
    duplicate["label_source"] = "human_reviewed"
    del duplicate["mutation_manifest_path"]
    payload["groups"][0]["reports"].append(duplicate)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="attack IDs must be globally unique"):
        validate_dataset_manifest(manifest_path)


def test_mutation_replay_rejects_tampered_output(tmp_path: Path) -> None:
    _write_dataset(tmp_path)
    (tmp_path / "medium.md").write_bytes((_medium_report() + "tampered").encode("utf-8"))

    with pytest.raises(EvaluationInputError, match="stored mutation output"):
        replay_mutation_manifest(tmp_path / "mutation-medium.json", root=tmp_path)


def test_mutation_replay_rejects_missing_output_directory(tmp_path: Path) -> None:
    _write_dataset(tmp_path)
    mutation_path = tmp_path / "mutation-medium.json"
    payload = json.loads(mutation_path.read_text(encoding="utf-8"))
    payload["output_path"] = "missing/medium.md"
    mutation_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="output directory does not exist"):
        replay_mutation_manifest(mutation_path, root=tmp_path, write=True)


def test_dataset_rejects_undeclared_deterministic_error(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["groups"][0]["reports"][2]["expected_error_codes"] = [
        "reasoning_gap",
        "actionability_gap",
    ]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="undeclared deterministic errors"):
        validate_dataset_manifest(manifest_path)


def test_dataset_rejects_expected_error_without_mutation_operation(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path)
    mutation_path = tmp_path / "mutation-medium.json"
    payload = json.loads(mutation_path.read_text(encoding="utf-8"))
    payload["operations"][1]["expected_error_codes"] = []
    mutation_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="do not close over"):
        validate_dataset_manifest(manifest_path)


def test_dataset_rejects_contract_drift_within_source_group(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path)
    case_path = tmp_path / "case-medium.json"
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    payload["required_sections"] = payload["required_sections"][:-1]
    case_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="multiple evaluation contracts"):
        validate_dataset_manifest(manifest_path)


def test_dataset_rejects_case_path_escape(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["groups"][0]["reports"][0]["case_path"] = "../outside.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="escapes the dataset root"):
        validate_dataset_manifest(manifest_path)


def test_dataset_rejects_source_group_leakage_across_splits(tmp_path: Path) -> None:
    manifest_path = _write_dataset(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    duplicate = json.loads(json.dumps(payload["groups"][0]))
    duplicate["group_id"] = "source-group-2"
    duplicate["split"] = "test"
    for index, report in enumerate(duplicate["reports"], start=10):
        report["report_id"] += "-copy"
        report["report_sha256"] = f"{index:X}" * 64
    payload["groups"].append(duplicate)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="source group cannot appear"):
        validate_dataset_manifest(manifest_path)
