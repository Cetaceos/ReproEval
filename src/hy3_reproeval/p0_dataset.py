"""Deterministic construction of the public P0 synthetic benchmark candidate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from .errors import EvaluationInputError
from .models import StrictModel

P0_DATASET_ID = "reproeval-p0-synthetic-reproduction"
P0_DATASET_VERSION = "0.1.0"
P0_GROUP_COUNT = 12
P0_REPORT_COUNT = 44
P0_ADVERSARIAL_REPORT_COUNT = 8


@dataclass(frozen=True, slots=True)
class _Topic:
    slug: str
    title: str
    metric: str
    expected: str
    corrupted: str
    unit: str | None
    method: str
    validation_action: str


_TOPICS = (
    _Topic(
        "channel-prediction",
        "Wireless channel prediction",
        "Prediction accuracy",
        "0.876",
        "0.500",
        None,
        "temporal convolutional predictor",
        "channel prediction evaluation",
    ),
    _Topic(
        "ofdm-estimation",
        "OFDM channel estimation",
        "NMSE",
        "-18.4",
        "-12.0",
        "dB",
        "pilot-aided estimator",
        "channel estimation benchmark",
    ),
    _Topic(
        "beam-selection",
        "Millimeter-wave beam selection",
        "Top-1 accuracy",
        "0.842",
        "0.700",
        None,
        "codebook-aware selector",
        "beam selection sweep",
    ),
    _Topic(
        "modulation-classification",
        "Automatic modulation classification",
        "Macro F1",
        "0.913",
        "0.800",
        None,
        "complex-IQ classifier",
        "modulation classification test",
    ),
    _Topic(
        "federated-radio",
        "Federated radio learning",
        "Validation accuracy",
        "0.887",
        "0.750",
        None,
        "resource-aware federated adapter",
        "federated client ablation",
    ),
    _Topic(
        "mec-latency",
        "UAV-assisted edge inference",
        "End-to-end latency",
        "23.6",
        "41.2",
        "ms",
        "hierarchical offloading policy",
        "edge latency replay",
    ),
    _Topic(
        "isac-detection",
        "Integrated sensing and communication",
        "Detection probability",
        "0.921",
        "0.700",
        None,
        "joint waveform optimizer",
        "sensing-communication trade-off sweep",
    ),
    _Topic(
        "radio-localization",
        "Radio localization",
        "Position RMSE",
        "0.47",
        "1.20",
        "m",
        "multipath-aware localizer",
        "localization geometry test",
    ),
    _Topic(
        "semantic-communication",
        "Semantic communication",
        "BLEU",
        "0.312",
        "0.200",
        None,
        "task-oriented semantic encoder",
        "semantic channel ablation",
    ),
    _Topic(
        "mimo-efficiency",
        "Massive-MIMO precoding",
        "Spectral efficiency",
        "12.8",
        "8.0",
        "bit/s/Hz",
        "hybrid precoder",
        "precoding benchmark",
    ),
    _Topic(
        "energy-efficiency",
        "Energy-efficient radio control",
        "Energy efficiency",
        "4.75",
        "2.50",
        "Mbit/J",
        "power-aware scheduler",
        "energy budget sweep",
    ),
    _Topic(
        "packet-reliability",
        "Low-latency packet delivery",
        "Packet error rate",
        "0.018",
        "0.080",
        None,
        "reliability-aware link adapter",
        "packet reliability stress test",
    ),
)


class P0DatasetBuildResult(StrictModel):
    dataset_id: str
    dataset_version: str
    output_root: str
    file_count: int = Field(ge=1)
    group_count: int = Field(ge=P0_GROUP_COUNT)
    report_count: int = Field(ge=P0_REPORT_COUNT)
    adversarial_report_count: int = Field(ge=P0_ADVERSARIAL_REPORT_COUNT)
    wrote_files: bool
    verified_existing: bool


def materialize_p0_dataset(output_dir: str | Path, *, check: bool = False) -> P0DatasetBuildResult:
    """Write or byte-verify the canonical public P0 synthetic Dataset."""

    output_root = Path(output_dir).expanduser().resolve()
    files = build_p0_dataset_files()
    if check:
        _verify_inventory(output_root, files)
    else:
        if not output_root.parent.is_dir():
            raise EvaluationInputError(f"P0 Dataset parent directory does not exist: {output_root.parent.as_posix()}")
        if output_root.exists() and not output_root.is_dir():
            raise EvaluationInputError("P0 Dataset output path must be a directory")
        if output_root.exists() and any(output_root.iterdir()):
            raise EvaluationInputError("P0 Dataset output directory must be absent or empty")
        output_root.mkdir(exist_ok=True)
        for relative, payload in sorted(files.items()):
            destination = output_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
    return P0DatasetBuildResult(
        dataset_id=P0_DATASET_ID,
        dataset_version=P0_DATASET_VERSION,
        output_root=output_root.as_posix(),
        file_count=len(files),
        group_count=P0_GROUP_COUNT,
        report_count=P0_REPORT_COUNT,
        adversarial_report_count=P0_ADVERSARIAL_REPORT_COUNT,
        wrote_files=not check,
        verified_existing=check,
    )


def build_p0_dataset_files() -> dict[str, bytes]:
    """Return the complete canonical path-to-bytes inventory without filesystem writes."""

    files: dict[str, bytes] = {}
    groups: list[dict[str, object]] = []
    for index, topic in enumerate(_TOPICS, start=1):
        group_id = f"p0-reproduction-{index:02d}-{topic.slug}"
        group_root = f"groups/{group_id}"
        source = _source_material(topic, index)
        source_sha256 = _sha256(source)
        files[f"{group_root}/source_material.md"] = source

        high = _high_report(topic)
        medium_operations = _medium_operations(topic)
        medium = _apply_operations(high.decode("utf-8"), medium_operations).encode("utf-8")
        low_operations = [*medium_operations, _corrupt_numeric_claim(topic)]
        low = _apply_operations(high.decode("utf-8"), low_operations).encode("utf-8")
        reports: list[dict[str, object]] = []
        for tier, payload in (("high", high), ("medium", medium), ("low", low)):
            report_id = f"{group_id}-{tier}"
            report_name = f"{tier}_report.md"
            case_name = f"{tier}_case.json"
            files[f"{group_root}/{report_name}"] = payload
            files[f"{group_root}/{case_name}"] = _json_bytes(_case(topic, group_id, tier, report_name, source_sha256))
            entry: dict[str, object] = {
                "report_id": report_id,
                "quality_tier": tier,
                "case_path": f"{group_root}/{case_name}",
                "report_sha256": _sha256(payload),
                "label_source": "reference_revision" if tier == "high" else "synthetic_mutation",
                "expected_error_codes": (
                    []
                    if tier == "high"
                    else ["reasoning_gap", "actionability_gap"]
                    if tier == "medium"
                    else [
                        "reasoning_gap",
                        "actionability_gap",
                        "fabricated_citation",
                        "unsupported_claim",
                        "numeric_error",
                    ]
                ),
            }
            if tier != "high":
                mutation_name = f"{tier}_mutation.json"
                entry["mutation_manifest_path"] = f"{group_root}/{mutation_name}"
                operations = medium_operations if tier == "medium" else low_operations
                files[f"{group_root}/{mutation_name}"] = _json_bytes(
                    _mutation(group_id, tier, high, payload, operations)
                )
            reports.append(entry)

        if index <= P0_ADVERSARIAL_REPORT_COUNT:
            operations, attacks = _adversarial_contract(topic, index)
            adversarial = _apply_operations(high.decode("utf-8"), operations).encode("utf-8")
            files[f"{group_root}/adversarial_report.md"] = adversarial
            files[f"{group_root}/adversarial_case.json"] = _json_bytes(
                _case(topic, group_id, "adversarial", "adversarial_report.md", source_sha256)
            )
            files[f"{group_root}/adversarial_mutation.json"] = _json_bytes(
                _mutation(group_id, "adversarial", high, adversarial, operations)
            )
            expected_errors = sorted({error for operation in operations for error in operation["expected_error_codes"]})
            reports.append(
                {
                    "report_id": f"{group_id}-adversarial",
                    "quality_tier": "adversarial",
                    "case_path": f"{group_root}/adversarial_case.json",
                    "report_sha256": _sha256(adversarial),
                    "label_source": "synthetic_mutation",
                    "mutation_manifest_path": f"{group_root}/adversarial_mutation.json",
                    "expected_error_codes": expected_errors,
                    "adversarial_spec": {"schema_version": "1.0", "attacks": attacks},
                }
            )

        groups.append(
            {
                "group_id": group_id,
                "split": _split(index),
                "scenario": "reproduction",
                "provenance": {
                    "kind": "synthetic",
                    "license": "Apache-2.0",
                    "source_group_sha256": source_sha256,
                    "acquisition_date": "2026-09-01",
                    "description": (
                        f"Repository-authored synthetic evidence packet for {topic.title}; "
                        "contains no external paper text or personal data."
                    ),
                },
                "reports": reports,
            }
        )

    files["dataset.json"] = _json_bytes(
        {
            "schema_version": "1.0",
            "dataset_id": P0_DATASET_ID,
            "dataset_version": P0_DATASET_VERSION,
            "description": (
                "Deterministically generated 12-group synthetic P0 benchmark candidate for protocol, "
                "ranking, annotation, and adversarial experiments; not human ground truth."
            ),
            "groups": groups,
        }
    )
    return files


def _source_material(topic: _Topic, index: int) -> bytes:
    unit = f" {topic.unit}" if topic.unit else ""
    text = f"""# Synthetic Evidence Packet {index:02d}: {topic.title}

1. This packet is repository-authored synthetic material.
2. The evaluated method is a {topic.method}.
3. The protocol uses five fixed-seed runs.
4. Preprocessing is held constant across runs.
5. The train, validation, and test partitions are disjoint.
6. The comparison baseline uses the same input partition.
7. The primary metric is {topic.metric}.
8. The result table contains five registered observations.
9. The aggregation rule is the arithmetic mean.
10. The reproduced {topic.metric} is {topic.expected}{unit}.
11. The reported value is specific to this synthetic protocol.
12. No confidence interval is available in the source packet.
13. Causal attribution requires an additional controlled ablation.
14. Recommended validation: {topic.validation_action}.

| run | value |
| --- | ---: |
| 1 | {topic.expected} |
| 2 | {topic.expected} |
| 3 | {topic.expected} |
| 4 | {topic.expected} |
| 5 | {topic.expected} |
"""
    return text.encode("utf-8")


def _high_report(topic: _Topic) -> bytes:
    unit = f" {topic.unit}" if topic.unit else ""
    limitation = (
        "Five registered runs support the observed value, but there is insufficient evidence for a "
        f"universal causal attribution in {topic.title.lower()}."
    )
    text = f"""# Reproduction Review: {topic.title}

## Executive summary

The reproduced {topic.metric} is {topic.expected}{unit} [paper@L10-L14] [results@rows:1-5].

## Experimental evidence

Five fixed-seed runs use the same partition and aggregation rule [paper@L3-L9] [results@rows:1-5].

## Evidence and limitations

{limitation}

## Next steps

Repeat the registered {topic.validation_action} with fixed preprocessing, published seeds, and confidence intervals.
"""
    return text.encode("utf-8")


def _case(topic: _Topic, group_id: str, tier: str, report_name: str, source_sha256: str) -> dict[str, object]:
    numeric: dict[str, object] = {
        "fact_id": f"{topic.slug}-primary-metric",
        "label": f"{topic.metric} is",
        "expected": topic.expected,
        "absolute_tolerance": "0.0001",
        "critical": True,
    }
    if topic.unit is not None:
        numeric["unit"] = topic.unit
    return {
        "schema_version": "1.0",
        "case_id": f"{group_id}-{tier}-case",
        "scenario": "reproduction",
        "report_path": report_name,
        "sources": [
            {"source_id": "paper", "locators": ["L3-L9", "L10-L14"]},
            {"source_id": "results", "locators": ["rows:1-5"]},
        ],
        "claims": [
            {
                "claim_id": f"{topic.slug}-primary-claim",
                "marker": f"reproduced {topic.metric}",
                "required_source_ids": ["paper", "results"],
            }
        ],
        "numeric_expectations": [numeric],
        "required_sections": [
            {"section_id": "summary", "heading": "Executive summary"},
            {"section_id": "evidence", "heading": "Experimental evidence"},
            {"section_id": "limitations", "heading": "Evidence and limitations"},
            {"section_id": "next", "heading": "Next steps"},
        ],
        "uncertainty": {"required": True, "accepted_phrases": ["insufficient evidence"]},
        "artifacts": [{"artifact_id": f"{topic.slug}-source", "path": "source_material.md", "sha256": source_sha256}],
    }


def _medium_operations(topic: _Topic) -> list[dict[str, object]]:
    return [
        {
            "operation_id": "weaken-reasoning",
            "kind": "replace_once",
            "target": (
                "Five registered runs support the observed value, but there is insufficient evidence for a "
                f"universal causal attribution in {topic.title.lower()}."
            ),
            "replacement": "The aggregate differs, and there is insufficient evidence.",
            "expected_dimensions": ["reasoning_consistency"],
            "expected_error_codes": ["reasoning_gap"],
        },
        {
            "operation_id": "weaken-next-step",
            "kind": "replace_once",
            "target": (
                f"Repeat the registered {topic.validation_action} with fixed preprocessing, published seeds, "
                "and confidence intervals."
            ),
            "replacement": "Run more experiments.",
            "expected_dimensions": ["clarity_actionability"],
            "expected_error_codes": ["actionability_gap"],
        },
    ]


def _corrupt_numeric_claim(topic: _Topic) -> dict[str, object]:
    unit = f" {topic.unit}" if topic.unit else ""
    return {
        "operation_id": "corrupt-primary-claim",
        "kind": "replace_once",
        "target": (f"The reproduced {topic.metric} is {topic.expected}{unit} [paper@L10-L14] [results@rows:1-5]."),
        "replacement": (
            f"The reproduced {topic.metric} is {topic.corrupted}{unit} [invented-authority@L1] [results@rows:1-5]."
        ),
        "expected_dimensions": ["factual_accuracy", "evidence_traceability", "numerical_consistency"],
        "expected_error_codes": ["fabricated_citation", "unsupported_claim", "numeric_error"],
    }


def _adversarial_contract(topic: _Topic, index: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if index == 1:
        operation = _corrupt_numeric_claim(topic)
        return [operation], [
            _attack(
                index,
                "fabricated-authority",
                "fabricated_authority",
                ["factual_accuracy", "evidence_traceability"],
                ["fabricated_citation", "unsupported_claim"],
            ),
            _attack(
                index, "calculation-corruption", "calculation_corruption", ["numerical_consistency"], ["numeric_error"]
            ),
        ]
    if index == 2:
        operation = _suppress_limitation(topic)
        return [operation], [
            _attack(
                index, "limitation-suppression", "limitation_suppression", ["uncertainty_handling"], ["overconfidence"]
            )
        ]
    if index == 3:
        citation = _fabricate_authority(topic)
        limitation = _suppress_limitation(topic)
        return [citation, limitation], [
            _attack(
                index,
                "unsupported-overconfidence",
                "unsupported_overconfidence",
                ["factual_accuracy", "evidence_traceability", "uncertainty_handling"],
                ["fabricated_citation", "unsupported_claim", "overconfidence"],
            )
        ]
    if index == 4:
        return _semantic_append_attack(
            index,
            "conclusion-repetition",
            "conclusion_repetition",
            "The result is decisive. The result is decisive. The result is decisive.",
        )
    if index == 5:
        return _semantic_append_attack(
            index,
            "length-inflation",
            "length_inflation",
            " ".join(
                ["This extended commentary repeats contextual background without adding registered evidence."] * 8
            ),
        )
    if index == 6:
        return _semantic_append_attack(
            index,
            "terminology-stuffing",
            "terminology_stuffing",
            "Hyperdimensional manifold-aware cross-layer intelligence proves paradigm-level optimality.",
        )
    if index == 7:
        operation = _numeric_only_corruption(topic)
        return [operation], [
            _attack(
                index, "calculation-corruption", "calculation_corruption", ["numerical_consistency"], ["numeric_error"]
            )
        ]
    operation = _fabricate_authority(topic)
    return [operation], [
        _attack(
            index,
            "fabricated-authority",
            "fabricated_authority",
            ["factual_accuracy", "evidence_traceability"],
            ["fabricated_citation", "unsupported_claim"],
        )
    ]


def _semantic_append_attack(
    index: int,
    slug: str,
    attack_type: str,
    paragraph: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    operation = {
        "operation_id": slug,
        "kind": "append_text",
        "target": None,
        "replacement": f"\n## Unsupported additional commentary\n\n{paragraph}\n",
        "expected_dimensions": ["clarity_actionability"],
        "expected_error_codes": ["verbosity_without_evidence"],
    }
    return [operation], [
        _attack(
            index,
            slug,
            attack_type,
            ["clarity_actionability"],
            ["verbosity_without_evidence"],
        )
    ]


def _suppress_limitation(topic: _Topic) -> dict[str, object]:
    return {
        "operation_id": "suppress-limitation",
        "kind": "replace_once",
        "target": (
            "Five registered runs support the observed value, but there is insufficient evidence for a "
            f"universal causal attribution in {topic.title.lower()}."
        ),
        "replacement": "The five runs prove universal effectiveness under all deployment conditions.",
        "expected_dimensions": ["uncertainty_handling"],
        "expected_error_codes": ["overconfidence"],
    }


def _fabricate_authority(topic: _Topic) -> dict[str, object]:
    unit = f" {topic.unit}" if topic.unit else ""
    return {
        "operation_id": "fabricate-authority",
        "kind": "replace_once",
        "target": (f"The reproduced {topic.metric} is {topic.expected}{unit} [paper@L10-L14] [results@rows:1-5]."),
        "replacement": (
            f"The reproduced {topic.metric} is {topic.expected}{unit} [invented-authority@L1] [results@rows:1-5]."
        ),
        "expected_dimensions": ["factual_accuracy", "evidence_traceability"],
        "expected_error_codes": ["fabricated_citation", "unsupported_claim"],
    }


def _numeric_only_corruption(topic: _Topic) -> dict[str, object]:
    unit = f" {topic.unit}" if topic.unit else ""
    return {
        "operation_id": "corrupt-calculation",
        "kind": "replace_once",
        "target": f"The reproduced {topic.metric} is {topic.expected}{unit}",
        "replacement": f"The reproduced {topic.metric} is {topic.corrupted}{unit}",
        "expected_dimensions": ["numerical_consistency"],
        "expected_error_codes": ["numeric_error"],
    }


def _attack(
    index: int,
    slug: str,
    attack_type: str,
    dimensions: list[str],
    errors: list[str],
) -> dict[str, object]:
    return {
        "attack_id": f"p0-{index:02d}-{slug}",
        "attack_type": attack_type,
        "target_dimensions": dimensions,
        "expected_error_codes": errors,
        "description": f"Deterministic synthetic {attack_type.replace('_', ' ')} protocol case.",
    }


def _mutation(
    group_id: str,
    tier: str,
    parent: bytes,
    output: bytes,
    operations: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "mutation_id": f"{group_id}-{tier}-mutation",
        "parent_report_id": f"{group_id}-high",
        "output_report_id": f"{group_id}-{tier}",
        "parent_path": f"groups/{group_id}/high_report.md",
        "output_path": f"groups/{group_id}/{tier}_report.md",
        "parent_sha256": _sha256(parent),
        "output_sha256": _sha256(output),
        "operations": operations,
    }


def _apply_operations(text: str, operations: list[dict[str, object]]) -> str:
    result = text
    for operation in operations:
        if operation["kind"] == "append_text":
            result += str(operation["replacement"])
            continue
        target = str(operation["target"])
        if result.count(target) != 1:
            raise RuntimeError(f"P0 generator mutation target is not unique: {operation['operation_id']}")
        replacement = "" if operation["kind"] == "delete_once" else str(operation["replacement"])
        result = result.replace(target, replacement, 1)
    return result


def _split(index: int) -> str:
    if index <= 4:
        return "development"
    if index <= 8:
        return "validation"
    return "test"


def _verify_inventory(output_root: Path, expected: dict[str, bytes]) -> None:
    if not output_root.is_dir():
        raise EvaluationInputError(f"P0 Dataset directory does not exist: {output_root.as_posix()}")
    actual_paths = {path.relative_to(output_root).as_posix() for path in output_root.rglob("*") if path.is_file()}
    expected_paths = set(expected)
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        raise EvaluationInputError(f"P0 Dataset inventory mismatch; missing={missing}, extra={extra}")
    changed = [relative for relative, payload in expected.items() if (output_root / relative).read_bytes() != payload]
    if changed:
        raise EvaluationInputError("P0 Dataset files differ from canonical generation: " + ", ".join(sorted(changed)))


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()
