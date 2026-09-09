from __future__ import annotations

import json
from pathlib import Path

import pytest

from hy3_reproeval.adjudication_packet import finalize_adjudication_packet, prepare_adjudication_packet
from hy3_reproeval.annotation_packet import finalize_annotation_packet, prepare_annotation_packet
from hy3_reproeval.consensus import finalize_annotation_consensus
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


def _complete_independent_packet(packet_path: Path, *, disputed_report_id: str | None = None) -> None:
    assignment = json.loads((packet_path / "annotator" / "assignment.json").read_text(encoding="utf-8"))
    coordinator = json.loads((packet_path / "coordinator_manifest.json").read_text(encoding="utf-8"))
    report_by_item = {item["item_id"]: item["report_id"] for item in coordinator["items"]}
    sources_by_item = {item["item_id"]: item["sources"] for item in assignment["items"]}
    responses_path = packet_path / "annotator" / "responses.json"
    payload = json.loads(responses_path.read_text(encoding="utf-8"))
    payload["annotation_date"] = "2026-09-08"
    payload["annotator_profile"] = {
        "expertise_description": "Independent reviewer used to exercise the adjudication protocol.",
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
                rationale="The report and source directly support this assessment.",
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
            if (
                report_by_item[response["item_id"]] == disputed_report_id
                and dimension["dimension"] == "factual_accuracy"
            ):
                dimension["score"] = 3
                dimension["error_codes"] = ["unsupported_claim"]
                dimension["rationale"] = "One factual claim is not fully supported by the cited source."
    responses_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def _two_parent_bundles(tmp_path: Path) -> tuple[Path, list[Path], str]:
    freeze_path = _freeze(tmp_path)
    manifest = json.loads(_manifest().read_text(encoding="utf-8"))
    disputed_report_id = next(
        report["report_id"]
        for group in manifest["groups"]
        if group["split"] in {"validation", "test"}
        for report in group["reports"]
    )
    bundles: list[Path] = []
    for annotator_id in ("reviewer-a", "reviewer-b"):
        packet = tmp_path / f"packet-{annotator_id}"
        prepare_annotation_packet(
            _manifest(),
            freeze_path,
            packet,
            assignment_id=f"assignment-{annotator_id}",
            annotator_id=annotator_id,
            annotation_bundle_id=f"bundle-{annotator_id}",
        )
        _complete_independent_packet(
            packet,
            disputed_report_id=disputed_report_id if annotator_id == "reviewer-b" else None,
        )
        bundle_path = tmp_path / f"bundle-{annotator_id}.json"
        finalize_annotation_packet(_manifest(), freeze_path, packet, bundle_path)
        bundles.append(bundle_path)
    return freeze_path, bundles, disputed_report_id


def _complete_adjudication_packet(packet_path: Path) -> None:
    assignment = json.loads((packet_path / "annotator" / "assignment.json").read_text(encoding="utf-8"))
    sources_by_item = {item["item_id"]: item["sources"] for item in assignment["items"]}
    responses_path = packet_path / "annotator" / "responses.json"
    payload = json.loads(responses_path.read_text(encoding="utf-8"))
    payload["annotation_date"] = "2026-09-08"
    payload["annotator_profile"] = {
        "expertise_description": "Third reviewer trained on the public ReproEval Rubric.",
        "independent_annotation": False,
        "blind_to_system_scores": True,
        "rubric_training_completed": True,
        "conflict_of_interest_disclosed": True,
        "conflict_of_interest_present": False,
    }
    for response in payload["responses"]:
        for dimension in response["dimensions"]:
            dimension.update(
                status="assessed",
                score=3,
                rationale="The source supports the core statement but not every factual detail.",
                evidence_lines=["L000001"],
                error_codes=["unsupported_claim"],
                source_evidence=[
                    {
                        "source_id": sources_by_item[response["item_id"]][0]["source_id"],
                        "lines": ["L000001"],
                    }
                ],
            )
    responses_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def test_adjudication_packet_is_blind_and_resolves_consensus(tmp_path: Path) -> None:
    freeze_path, bundles, disputed_report_id = _two_parent_bundles(tmp_path)
    packet = tmp_path / "adjudication"
    result = prepare_adjudication_packet(
        _manifest(),
        freeze_path,
        bundles,
        packet,
        assignment_id="adjudication-c",
        adjudicator_id="reviewer-c",
        annotation_bundle_id="bundle-c",
    )

    assert result.disputed_report_count == 1
    assert result.disputed_dimension_count == 1
    assignment_path = packet / "annotator" / "assignment.json"
    assignment = json.loads(assignment_path.read_text(encoding="utf-8"))
    public_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (packet / "annotator").rglob("*") if path.is_file()
    )
    assert len(assignment["items"]) == 1
    assert (packet / "annotator" / "README_CN.md").is_file()
    assert assignment["items"][0]["disputed_dimensions"][0]["dimension"] == "factual_accuracy"
    assert {item["assessment_id"] for item in assignment["items"][0]["parent_assessments"]} == {
        "parent-001",
        "parent-002",
    }
    for private_value in ("reviewer-a", "reviewer-b", "bundle-reviewer-a", "bundle-reviewer-b", disputed_report_id):
        assert private_value not in public_text
    for private_field in ("quality_tier", "mutation_manifest", "system_score", "expected_error_codes"):
        assert f'"{private_field}"' not in public_text

    _complete_adjudication_packet(packet)
    output = tmp_path / "bundle-c.json"
    adjudication = finalize_adjudication_packet(_manifest(), freeze_path, bundles, packet, output)
    assert adjudication.annotation_round.value == "adjudication"
    assert adjudication.parent_annotation_bundle_sha256.keys() == {"bundle-reviewer-a", "bundle-reviewer-b"}
    assert len(adjudication.annotations) == 1

    consensus = finalize_annotation_consensus(
        _manifest(),
        [*bundles, output],
        dataset_freeze_path=freeze_path,
    )
    assert consensus.consensus_ready is True
    assert consensus.adjudication_required_item_count == 1
    assert consensus.adjudication_resolved_item_count == 1
    assert consensus.unresolved_adjudication_item_count == 0


def test_finalizer_rejects_changed_parent_bundle(tmp_path: Path) -> None:
    freeze_path, bundles, _ = _two_parent_bundles(tmp_path)
    packet = tmp_path / "adjudication"
    prepare_adjudication_packet(
        _manifest(),
        freeze_path,
        bundles,
        packet,
        assignment_id="adjudication-c",
        adjudicator_id="reviewer-c",
        annotation_bundle_id="bundle-c",
    )
    _complete_adjudication_packet(packet)
    changed = json.loads(bundles[0].read_text(encoding="utf-8"))
    changed["annotator"]["expertise_description"] += " Changed after packet preparation."
    bundles[0].write_text(json.dumps(changed, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="fingerprint changed"):
        finalize_adjudication_packet(_manifest(), freeze_path, bundles, packet, tmp_path / "bundle-c.json")


def test_prepare_rejects_parent_annotator_as_adjudicator(tmp_path: Path) -> None:
    freeze_path, bundles, _ = _two_parent_bundles(tmp_path)

    with pytest.raises(EvaluationInputError, match="distinct"):
        prepare_adjudication_packet(
            _manifest(),
            freeze_path,
            bundles,
            tmp_path / "adjudication",
            assignment_id="adjudication-a",
            adjudicator_id="reviewer-a",
            annotation_bundle_id="bundle-c",
        )


def test_finalizer_rejects_tampered_adjudication_source(tmp_path: Path) -> None:
    freeze_path, bundles, _ = _two_parent_bundles(tmp_path)
    packet = tmp_path / "adjudication"
    prepare_adjudication_packet(
        _manifest(),
        freeze_path,
        bundles,
        packet,
        assignment_id="adjudication-c",
        adjudicator_id="reviewer-c",
        annotation_bundle_id="bundle-c",
    )
    _complete_adjudication_packet(packet)
    source = next((packet / "annotator" / "sources").iterdir())
    source.write_text(source.read_text(encoding="utf-8") + "L999999 | Tampered.\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="source fingerprint changed"):
        finalize_adjudication_packet(_manifest(), freeze_path, bundles, packet, tmp_path / "bundle-c.json")
