"""Deterministic construction of the public P1 transfer-generalization Dataset."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from .errors import EvaluationInputError
from .models import StrictModel

P1_TRANSFER_DATASET_ID = "reproeval-p1-synthetic-transfer"
P1_TRANSFER_DATASET_VERSION = "0.1.0"
P1_TRANSFER_GROUP_COUNT = 5
P1_TRANSFER_REPORT_COUNT = 15


@dataclass(frozen=True, slots=True)
class _TransferTopic:
    slug: str
    title: str
    source_component: str
    target_context: str
    constraint_label: str
    expected: str
    corrupted: str
    unit: str | None
    adaptation: str
    validation_action: str


_TOPICS = (
    _TransferTopic(
        "gpu-to-cpu-edge",
        "GPU inference pipeline to CPU edge deployment",
        "CUDA-batched inference pipeline",
        "CPU-only roadside edge node",
        "memory budget",
        "8",
        "16",
        "GB",
        "replace CUDA kernels and re-profile the batch scheduler",
        "measure peak memory and p95 latency on the target node",
    ),
    _TransferTopic(
        "federated-uav-link",
        "Centralized federated coordinator to intermittent UAV links",
        "synchronous federated coordinator",
        "UAV-assisted MEC network with intermittent uplinks",
        "uplink budget",
        "20",
        "80",
        "Mbps",
        "add bounded-staleness aggregation and resumable client updates",
        "replay the registered outage trace and measure convergence delay",
    ),
    _TransferTopic(
        "mmwave-to-sub6-array",
        "Millimeter-wave beam selector to a sub-6 GHz array",
        "codebook-aware millimeter-wave beam selector",
        "eight-antenna sub-6 GHz access point",
        "antenna count",
        "8",
        "64",
        None,
        "replace the beam codebook and retrain the array-dependent features",
        "run an eight-antenna coverage and handover sweep",
    ),
    _TransferTopic(
        "isac-bandwidth-transfer",
        "Wideband ISAC detector to a narrowband sensing modem",
        "joint wideband sensing and communication detector",
        "narrowband industrial sensing modem",
        "bandwidth limit",
        "20",
        "100",
        "MHz",
        "redesign the waveform front end and recalibrate sensing thresholds",
        "measure detection probability and link error rate across the target band",
    ),
    _TransferTopic(
        "semantic-codec-embedded",
        "Cloud semantic codec to an embedded terminal",
        "cloud-hosted semantic communication codec",
        "battery-powered embedded terminal",
        "latency budget",
        "40",
        "10",
        "ms",
        "quantize the encoder and replace cloud-only preprocessing",
        "measure end-to-end latency, task accuracy, and energy on target hardware",
    ),
)


class P1TransferDatasetBuildResult(StrictModel):
    dataset_id: str
    dataset_version: str
    output_root: str
    file_count: int = Field(ge=1)
    group_count: int = Field(ge=P1_TRANSFER_GROUP_COUNT)
    report_count: int = Field(ge=P1_TRANSFER_REPORT_COUNT)
    mutation_count: int = Field(ge=10)
    wrote_files: bool
    verified_existing: bool


def materialize_p1_transfer_dataset(output_dir: str | Path, *, check: bool = False) -> P1TransferDatasetBuildResult:
    """Write or byte-verify the canonical public P1 transfer Dataset."""

    output_root = Path(output_dir).expanduser().resolve()
    files = build_p1_transfer_dataset_files()
    if check:
        _verify_inventory(output_root, files)
    else:
        if not output_root.parent.is_dir():
            raise EvaluationInputError(f"P1 Dataset parent directory does not exist: {output_root.parent.as_posix()}")
        if output_root.exists() and not output_root.is_dir():
            raise EvaluationInputError("P1 Dataset output path must be a directory")
        if output_root.exists() and any(output_root.iterdir()):
            raise EvaluationInputError("P1 Dataset output directory must be absent or empty")
        output_root.mkdir(exist_ok=True)
        for relative, payload in sorted(files.items()):
            destination = output_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
    return P1TransferDatasetBuildResult(
        dataset_id=P1_TRANSFER_DATASET_ID,
        dataset_version=P1_TRANSFER_DATASET_VERSION,
        output_root=output_root.as_posix(),
        file_count=len(files),
        group_count=P1_TRANSFER_GROUP_COUNT,
        report_count=P1_TRANSFER_REPORT_COUNT,
        mutation_count=P1_TRANSFER_GROUP_COUNT * 2,
        wrote_files=not check,
        verified_existing=check,
    )


def build_p1_transfer_dataset_files() -> dict[str, bytes]:
    """Return the canonical P1 transfer Dataset path-to-bytes inventory."""

    files: dict[str, bytes] = {}
    groups: list[dict[str, object]] = []
    for index, topic in enumerate(_TOPICS, start=1):
        group_id = f"p1-transfer-{index:02d}-{topic.slug}"
        group_root = f"groups/{group_id}"
        source = _source_material(topic, index)
        source_sha256 = _sha256(source)
        files[f"{group_root}/source_material.md"] = source
        high = _high_report(topic)
        medium_operations = _medium_operations(topic)
        medium = _apply_operations(high.decode("utf-8"), medium_operations).encode("utf-8")
        low_operations = [*medium_operations, _corrupt_target_constraint(topic)]
        low = _apply_operations(high.decode("utf-8"), low_operations).encode("utf-8")
        reports: list[dict[str, object]] = []
        for tier, payload, operations in (
            ("high", high, []),
            ("medium", medium, medium_operations),
            ("low", low, low_operations),
        ):
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
            if operations:
                mutation_name = f"{tier}_mutation.json"
                entry["mutation_manifest_path"] = f"{group_root}/{mutation_name}"
                files[f"{group_root}/{mutation_name}"] = _json_bytes(
                    _mutation(group_id, tier, high, payload, operations)
                )
            reports.append(entry)
        groups.append(
            {
                "group_id": group_id,
                "split": _split(index),
                "scenario": "transfer",
                "provenance": {
                    "kind": "synthetic",
                    "license": "Apache-2.0",
                    "source_group_sha256": source_sha256,
                    "acquisition_date": "2026-09-01",
                    "description": (
                        f"Repository-authored synthetic solution and target packet for {topic.title}; "
                        "contains no patent text, third-party code, or personal data."
                    ),
                },
                "reports": reports,
            }
        )
    files["dataset.json"] = _json_bytes(
        {
            "schema_version": "1.0",
            "dataset_id": P1_TRANSFER_DATASET_ID,
            "dataset_version": P1_TRANSFER_DATASET_VERSION,
            "description": (
                "Deterministically generated five-group synthetic P1 Dataset for testing transfer-report "
                "quality generalization; not a measured deployment-feasibility benchmark or human ground truth."
            ),
            "groups": groups,
        }
    )
    return files


def _source_material(topic: _TransferTopic, index: int) -> bytes:
    unit = f" {topic.unit}" if topic.unit else ""
    return f"""# Synthetic Transfer Packet {index:02d}: {topic.title}

1. This packet is repository-authored synthetic material.
2. The source solution uses a {topic.source_component}.
3. Its reusable interface is documented, but deployment scripts are environment-specific.
4. The source evaluation does not include the target hardware or radio context.
5. Direct reuse is therefore not established by the source evidence.
6. The candidate adaptation is to {topic.adaptation}.
7. Component-level reuse remains conditional on target-side validation.
8. No target performance point estimate is available.
9. The target context is a {topic.target_context}.
10. The registered target {topic.constraint_label} is {topic.expected}{unit}.
11. The target uses a different runtime or signal configuration from the source solution.
12. Compatibility must be measured rather than inferred from the source benchmark.
13. A failed constraint check blocks deployment but does not invalidate the source method.
14. Recommended validation is to {topic.validation_action}.
15. Legal, licensing, and operational approval remain outside this synthetic packet.
""".encode()


def _high_report(topic: _TransferTopic) -> bytes:
    unit = f" {topic.unit}" if topic.unit else ""
    text = (
        f"# Transfer Review: {topic.title}\n\n"
        "## Decision summary\n\n"
        "The transfer decision is conditional because the proposed adaptation must fit the target "
        f"{topic.constraint_label} of {topic.expected}{unit} [solution@L2-L8] [target@L9-L14].\n\n"
        "## Compatibility evidence\n\n"
        "The reusable source interface is documented, while the target runtime or signal configuration differs "
        "[solution@L2-L8] [target@L9-L14].\n\n"
        "## Risks and limitations\n\n"
        "There is insufficient evidence for a target performance point estimate; compatibility and deployment "
        "readiness require target-side measurements.\n\n"
        "## Validation plan\n\n"
        f"First {topic.validation_action}; reject deployment if the registered constraint or acceptance metric "
        "fails.\n"
    )
    return text.encode()


def _case(
    topic: _TransferTopic,
    group_id: str,
    tier: str,
    report_name: str,
    source_sha256: str,
) -> dict[str, object]:
    numeric: dict[str, object] = {
        "fact_id": f"{topic.slug}-target-constraint",
        "label": f"{topic.constraint_label} of",
        "expected": topic.expected,
        "absolute_tolerance": "0",
        "critical": True,
    }
    if topic.unit is not None:
        numeric["unit"] = topic.unit
    return {
        "schema_version": "1.0",
        "case_id": f"{group_id}-{tier}-case",
        "scenario": "transfer",
        "report_path": report_name,
        "sources": [
            {"source_id": "solution", "locators": ["L2-L8"]},
            {"source_id": "target", "locators": ["L9-L14"]},
        ],
        "claims": [
            {
                "claim_id": f"{topic.slug}-conditional-decision",
                "marker": "transfer decision is conditional",
                "required_source_ids": ["solution", "target"],
            }
        ],
        "numeric_expectations": [numeric],
        "required_sections": [
            {"section_id": "decision", "heading": "Decision summary"},
            {"section_id": "compatibility", "heading": "Compatibility evidence"},
            {"section_id": "risks", "heading": "Risks and limitations"},
            {"section_id": "validation", "heading": "Validation plan"},
        ],
        "uncertainty": {"required": True, "accepted_phrases": ["insufficient evidence"]},
        "artifacts": [{"artifact_id": f"{topic.slug}-packet", "path": "source_material.md", "sha256": source_sha256}],
    }


def _medium_operations(topic: _TransferTopic) -> list[dict[str, object]]:
    return [
        {
            "operation_id": "weaken-transfer-reasoning",
            "kind": "replace_once",
            "target": (
                "There is insufficient evidence for a target performance point estimate; compatibility and "
                "deployment readiness require target-side measurements."
            ),
            "replacement": "The environments differ, and there is insufficient evidence.",
            "expected_dimensions": ["reasoning_consistency"],
            "expected_error_codes": ["reasoning_gap"],
        },
        {
            "operation_id": "weaken-validation-plan",
            "kind": "replace_once",
            "target": (
                f"First {topic.validation_action}; reject deployment if the registered constraint or "
                "acceptance metric fails."
            ),
            "replacement": "Run more target tests.",
            "expected_dimensions": ["clarity_actionability"],
            "expected_error_codes": ["actionability_gap"],
        },
    ]


def _corrupt_target_constraint(topic: _TransferTopic) -> dict[str, object]:
    unit = f" {topic.unit}" if topic.unit else ""
    return {
        "operation_id": "corrupt-target-constraint",
        "kind": "replace_once",
        "target": (
            "The transfer decision is conditional because the proposed adaptation must fit the target "
            f"{topic.constraint_label} of {topic.expected}{unit} [solution@L2-L8] [target@L9-L14]."
        ),
        "replacement": (
            "The transfer decision is conditional because the proposed adaptation fits the target "
            f"{topic.constraint_label} of {topic.corrupted}{unit} [solution@L2-L8] [invented-target@L1]."
        ),
        "expected_dimensions": ["factual_accuracy", "evidence_traceability", "numerical_consistency"],
        "expected_error_codes": ["fabricated_citation", "unsupported_claim", "numeric_error"],
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
        target = str(operation["target"])
        if result.count(target) != 1:
            raise RuntimeError(f"P1 generator mutation target is not unique: {operation['operation_id']}")
        result = result.replace(target, str(operation["replacement"]), 1)
    return result


def _split(index: int) -> str:
    if index == 1:
        return "development"
    if index <= 3:
        return "validation"
    return "test"


def _verify_inventory(output_root: Path, expected: dict[str, bytes]) -> None:
    if not output_root.is_dir():
        raise EvaluationInputError(f"P1 Dataset directory does not exist: {output_root.as_posix()}")
    actual_paths = {path.relative_to(output_root).as_posix() for path in output_root.rglob("*") if path.is_file()}
    expected_paths = set(expected)
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        raise EvaluationInputError(f"P1 Dataset inventory mismatch; missing={missing}, extra={extra}")
    changed = [relative for relative, payload in expected.items() if (output_root / relative).read_bytes() != payload]
    if changed:
        raise EvaluationInputError("P1 Dataset files differ from canonical generation: " + ", ".join(sorted(changed)))


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()
