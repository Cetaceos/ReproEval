from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hy3_reproeval.annotation_packet import finalize_annotation_packet, prepare_annotation_packet
from hy3_reproeval.annotations import validate_annotation_bundles
from hy3_reproeval.cli import main
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.freeze import create_dataset_freeze


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _manifest() -> Path:
    return _project_root() / "evals" / "p1_transfer_dataset" / "dataset.json"


def _freeze(tmp_path: Path) -> Path:
    freeze_path = tmp_path / "dataset-freeze.json"
    freeze = create_dataset_freeze(_manifest())
    freeze_path.write_text(freeze.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return freeze_path


def _prepare(tmp_path: Path, annotator_id: str) -> tuple[Path, Path]:
    freeze_path = _freeze(tmp_path)
    packet_path = tmp_path / f"packet-{annotator_id}"
    prepare_annotation_packet(
        _manifest(),
        freeze_path,
        packet_path,
        assignment_id=f"p1-{annotator_id}",
        annotator_id=annotator_id,
        annotation_bundle_id=f"p1-bundle-{annotator_id}",
    )
    return packet_path, freeze_path


def _complete_responses(packet_path: Path) -> None:
    assignment = json.loads((packet_path / "annotator" / "assignment.json").read_text(encoding="utf-8"))
    sources_by_item = {item["item_id"]: item["sources"] for item in assignment["items"]}
    path = packet_path / "annotator" / "responses.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["annotation_date"] = "2026-09-02"
    payload["annotator_profile"] = {
        "expertise_description": "Independent research-report reviewer for packet workflow testing.",
        "independent_annotation": True,
        "blind_to_system_scores": True,
        "rubric_training_completed": True,
        "conflict_of_interest_disclosed": True,
        "conflict_of_interest_present": False,
    }
    for response in payload["responses"]:
        for dimension in response["dimensions"]:
            dimension.update(
                status="assessed",
                score=4,
                rationale="The report contains direct evidence supporting this assessment.",
                evidence_lines=[1],
                error_codes=[],
            )
            if dimension["dimension"] in {
                "factual_accuracy",
                "evidence_traceability",
                "numerical_consistency",
            }:
                dimension["source_evidence"] = [
                    {
                        "source_id": sources_by_item[response["item_id"]][0]["source_id"],
                        "evidence_lines": [1],
                    }
                ]
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def test_packet_blinds_labels_and_excludes_development_split(tmp_path: Path) -> None:
    packet_path, _ = _prepare(tmp_path, "reviewer-a")
    annotator_root = packet_path / "annotator"
    assignment_text = (annotator_root / "assignment.json").read_text(encoding="utf-8")
    assignment = json.loads(assignment_text)
    coordinator_text = (packet_path / "coordinator_manifest.json").read_text(encoding="utf-8")
    coordinator = json.loads(coordinator_text)

    assert len(assignment["items"]) == 12
    assert len(list((annotator_root / "reports").iterdir())) == 12
    assert len(list((annotator_root / "sources").iterdir())) == 12
    assert assignment["schema_version"] == "1.1"
    assert all(item["item_id"].startswith("item-") for item in assignment["items"])
    assert all(item["report_path"].startswith("reports/item-") for item in assignment["items"])
    assert all(len(item["sources"]) == 1 for item in assignment["items"])
    assert all(item["sources"][0]["source_id"] == "source-001" for item in assignment["items"])
    for private_field in ("quality_tier", "label_source", "expected_error_codes", "mutation_manifest"):
        assert private_field not in assignment_text
    assert all(item["group_id"] != "p1-transfer-01-gpu-to-cpu-edge" for item in coordinator["items"])
    assert "quality_tier" not in coordinator_text

    public_text = "\n".join(path.read_text(encoding="utf-8") for path in annotator_root.rglob("*") if path.is_file())
    manifest = json.loads(_manifest().read_text(encoding="utf-8"))
    for group in manifest["groups"]:
        assert group["group_id"] not in public_text
        for report in group["reports"]:
            assert report["report_id"] not in public_text

    first_item = assignment["items"][0]
    report_lines = (annotator_root / first_item["report_path"]).read_text(encoding="utf-8").splitlines()
    assert report_lines[0].startswith("L000001 | ")
    source = first_item["sources"][0]
    source_payload = (annotator_root / source["source_path"]).read_bytes()
    assert source_payload.decode("utf-8").splitlines()[0].startswith("L000001 | ")
    assert hashlib.sha256(source_payload).hexdigest().upper() == source["numbered_source_sha256"]
    assert source["source_sha256"] != source["numbered_source_sha256"]


def test_two_completed_packets_emit_valid_benchmark_ready_bundles(tmp_path: Path) -> None:
    freeze_path = _freeze(tmp_path)
    bundle_paths: list[Path] = []
    for annotator_id in ("reviewer-a", "reviewer-b"):
        packet_path = tmp_path / f"packet-{annotator_id}"
        prepare_annotation_packet(
            _manifest(),
            freeze_path,
            packet_path,
            assignment_id=f"p1-{annotator_id}",
            annotator_id=annotator_id,
            annotation_bundle_id=f"p1-bundle-{annotator_id}",
        )
        _complete_responses(packet_path)
        bundle_path = tmp_path / f"bundle-{annotator_id}.json"
        bundle = finalize_annotation_packet(_manifest(), freeze_path, packet_path, bundle_path)
        assert len(bundle.annotations) == 12
        assert bundle.schema_version == "1.1"
        assert all(
            dimension.source_evidence
            for annotation in bundle.annotations
            for dimension in annotation.dimensions
            if dimension.dimension.value in {"factual_accuracy", "evidence_traceability", "numerical_consistency"}
        )
        bundle_paths.append(bundle_path)

    result = validate_annotation_bundles(
        _manifest(),
        bundle_paths,
        dataset_freeze_path=freeze_path,
    )

    assert result.annotator_count == 2
    assert result.human_annotation_count == 24
    assert result.benchmark_target_report_count == 12
    assert result.independently_double_annotated_report_count == 12
    assert result.benchmark_ready is True


def test_finalizer_accepts_display_line_ids_and_source_lines_alias(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")
    _complete_responses(packet_path)
    responses_path = packet_path / "annotator" / "responses.json"
    responses = json.loads(responses_path.read_text(encoding="utf-8"))
    responses["annotator_profile"]["expertise_description"] = "x" * 600
    first_dimension = responses["responses"][0]["dimensions"][0]
    first_dimension["evidence_lines"] = ["L000001"]
    source_reference = first_dimension["source_evidence"][0]
    source_reference["lines"] = source_reference.pop("evidence_lines")
    source_reference["lines"] = ["L000001"]
    responses_path.write_text(json.dumps(responses, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    bundle = finalize_annotation_packet(
        _manifest(),
        freeze_path,
        packet_path,
        tmp_path / "bundle.json",
    )

    assert all(
        isinstance(line, int)
        for annotation in bundle.annotations
        for dimension in annotation.dimensions
        for line in dimension.evidence_lines
    )
    assert all(
        isinstance(line, int)
        for annotation in bundle.annotations
        for dimension in annotation.dimensions
        for reference in dimension.source_evidence
        for line in reference.evidence_lines
    )


def test_finalizer_rejects_malformed_display_line_id(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")
    _complete_responses(packet_path)
    responses_path = packet_path / "annotator" / "responses.json"
    responses = json.loads(responses_path.read_text(encoding="utf-8"))
    responses["responses"][0]["dimensions"][0]["evidence_lines"] = ["line one"]
    responses_path.write_text(json.dumps(responses, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="invalid displayed line identifier"):
        finalize_annotation_packet(_manifest(), freeze_path, packet_path, tmp_path / "bundle.json")


def test_finalizer_rejects_tampered_blinded_report(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")
    _complete_responses(packet_path)
    report_path = next((packet_path / "annotator" / "reports").iterdir())
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\nTampered.\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="fingerprint changed"):
        finalize_annotation_packet(_manifest(), freeze_path, packet_path, tmp_path / "bundle.json")


def test_finalizer_rejects_tampered_blinded_source(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")
    _complete_responses(packet_path)
    source_path = next((packet_path / "annotator" / "sources").iterdir())
    source_path.write_text(source_path.read_text(encoding="utf-8") + "L999999 | Tampered.\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="blinded source fingerprint changed"):
        finalize_annotation_packet(_manifest(), freeze_path, packet_path, tmp_path / "bundle.json")


def test_finalizer_rejects_changed_assignment(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")
    _complete_responses(packet_path)
    assignment_path = packet_path / "annotator" / "assignment.json"
    assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
    assignment["instructions"].append("Changed after assignment.")
    assignment_path.write_text(json.dumps(assignment, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="fingerprint changed"):
        finalize_annotation_packet(_manifest(), freeze_path, packet_path, tmp_path / "bundle.json")


def test_finalizer_rejects_changed_coordinator_inventory(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")
    _complete_responses(packet_path)
    coordinator_path = packet_path / "coordinator_manifest.json"
    coordinator = json.loads(coordinator_path.read_text(encoding="utf-8"))
    coordinator["items"][0]["group_id"] = "p1-transfer-01-gpu-to-cpu-edge"
    coordinator_path.write_text(json.dumps(coordinator, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="every validation/test report exactly once"):
        finalize_annotation_packet(_manifest(), freeze_path, packet_path, tmp_path / "bundle.json")


def test_finalizer_rejects_changed_coordinator_source_inventory(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")
    _complete_responses(packet_path)
    coordinator_path = packet_path / "coordinator_manifest.json"
    coordinator = json.loads(coordinator_path.read_text(encoding="utf-8"))
    coordinator["items"][0]["sources"][0]["artifact_id"] = "changed-artifact"
    coordinator_path.write_text(json.dumps(coordinator, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="coordinator source inventory changed"):
        finalize_annotation_packet(_manifest(), freeze_path, packet_path, tmp_path / "bundle.json")


def test_finalizer_rejects_out_of_range_source_evidence(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")
    _complete_responses(packet_path)
    responses_path = packet_path / "annotator" / "responses.json"
    responses = json.loads(responses_path.read_text(encoding="utf-8"))
    responses["responses"][0]["dimensions"][0]["source_evidence"][0]["evidence_lines"] = [999]
    responses_path.write_text(json.dumps(responses, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="source evidence line is outside"):
        finalize_annotation_packet(_manifest(), freeze_path, packet_path, tmp_path / "bundle.json")


def test_finalizer_requires_source_evidence_for_source_grounded_dimensions(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")
    _complete_responses(packet_path)
    responses_path = packet_path / "annotator" / "responses.json"
    responses = json.loads(responses_path.read_text(encoding="utf-8"))
    factual = next(
        dimension
        for dimension in responses["responses"][0]["dimensions"]
        if dimension["dimension"] == "factual_accuracy"
    )
    factual["source_evidence"] = []
    responses_path.write_text(json.dumps(responses, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="requires source evidence"):
        finalize_annotation_packet(_manifest(), freeze_path, packet_path, tmp_path / "bundle.json")


def test_finalizer_rejects_incomplete_responses(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")

    with pytest.raises(EvaluationInputError, match="profile field"):
        finalize_annotation_packet(_manifest(), freeze_path, packet_path, tmp_path / "bundle.json")


def test_finalizer_rejects_ineligible_independent_profile(tmp_path: Path) -> None:
    packet_path, freeze_path = _prepare(tmp_path, "reviewer-a")
    _complete_responses(packet_path)
    responses_path = packet_path / "annotator" / "responses.json"
    responses = json.loads(responses_path.read_text(encoding="utf-8"))
    responses["annotator_profile"]["blind_to_system_scores"] = False
    responses_path.write_text(json.dumps(responses, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="trained, system-score-blind"):
        finalize_annotation_packet(_manifest(), freeze_path, packet_path, tmp_path / "bundle.json")


def test_prepare_packet_refuses_nonempty_output(tmp_path: Path) -> None:
    freeze_path = _freeze(tmp_path)
    packet_path = tmp_path / "packet"
    packet_path.mkdir()
    (packet_path / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="absent or empty"):
        prepare_annotation_packet(
            _manifest(),
            freeze_path,
            packet_path,
            assignment_id="p1-reviewer-a",
            annotator_id="reviewer-a",
            annotation_bundle_id="p1-bundle-reviewer-a",
        )


def test_annotation_packet_cli_prepares_and_finalizes_bundle(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    freeze_path = _freeze(tmp_path)
    packet_path = tmp_path / "packet"
    bundle_path = tmp_path / "bundle.json"

    assert (
        main(
            [
                "prepare-annotation-packet",
                "--manifest",
                str(_manifest()),
                "--dataset-freeze",
                str(freeze_path),
                "--output-dir",
                str(packet_path),
                "--assignment-id",
                "p1-reviewer-a",
                "--annotator-id",
                "reviewer-a",
                "--bundle-id",
                "p1-bundle-reviewer-a",
            ]
        )
        == 0
    )
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["item_count"] == 12
    _complete_responses(packet_path)

    assert (
        main(
            [
                "finalize-annotation-packet",
                "--manifest",
                str(_manifest()),
                "--dataset-freeze",
                str(freeze_path),
                "--packet-dir",
                str(packet_path),
                "--output",
                str(bundle_path),
            ]
        )
        == 0
    )
    finalized = json.loads(capsys.readouterr().out)
    assert finalized["annotation_bundle_id"] == "p1-bundle-reviewer-a"
    assert bundle_path.is_file()
