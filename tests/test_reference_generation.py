from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.real_pilot import REAL_PILOT_GROUP_COUNT, materialize_real_pilot
from hy3_reproeval.reference_generation import (
    GroundedDraftText,
    ReferenceDraftResponse,
    ReferenceExperimentPlan,
    generate_reference_candidates,
    validate_reference_reviews,
)
from hy3_reproscope_mcp.config import Settings


class _FakeGenerationClient:
    async def complete_structured(self, messages, response_model, **kwargs):
        assert "source_packet" in messages[1]["content"]
        assert kwargs == {"reasoning_effort": "high", "temperature": 0.0, "repair_once": True}
        response = ReferenceDraftResponse(
            readiness_assessment="The registered evidence supports a bounded readiness assessment.",
            central_claim=GroundedDraftText(
                text="the software provides the capability described in the registered paper evidence",
                evidence_ids=["E01"],
            ),
            numeric_fact_evidence_ids=["E02"],
            evidence_assessment=GroundedDraftText(
                text="The paper and software links identify a concrete implementation candidate",
                evidence_ids=["E01", "E03"],
            ),
            material_limitation=GroundedDraftText(
                text="Paper-level evidence cannot establish independent numerical agreement",
                evidence_ids=["E04"],
            ),
            next_experiment=ReferenceExperimentPlan(
                objective="Test the registered paper-backed capability under a controlled rerun",
                environment_plan=(
                    "Start from the registered publication archive and derive a pinned environment from its "
                    "machine-readable dependency declarations."
                ),
                procedure=(
                    "Identify the archived example corresponding to the registered evidence, record the exact "
                    "command selected from the archive, and execute it while preserving standard output and errors."
                ),
                expected_outputs="Preserve the produced metric table or figure and a complete runtime log.",
                comparison_criteria=(
                    "Compare the produced artifact with the paper-reported fact using a tolerance declared before "
                    "execution."
                ),
                unresolved_inputs=[
                    "Exact runtime and dependency versions must be read from the registered archive.",
                    "The archived example filename and accepted comparison tolerance remain to be confirmed.",
                ],
                evidence_ids=["E01", "E02"],
            ),
        )
        return response_model.model_validate(response.model_dump())


@pytest.mark.asyncio
async def test_reference_generation_is_traceable_and_human_pending(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    output_root = tmp_path / "generation"
    materialize_real_pilot(dataset_root)

    index = await generate_reference_candidates(
        dataset_root / "dataset.json",
        output_root,
        client=_FakeGenerationClient(),
        settings=Settings(HY3_MODEL="hy3"),
    )
    validation = validate_reference_reviews(dataset_root / "dataset.json", output_root)

    assert index.item_count == REAL_PILOT_GROUP_COUNT
    assert validation.pending_count == REAL_PILOT_GROUP_COUNT
    assert validation.approved_for_promotion is False
    candidate = next(output_root.glob("groups/*/candidate.md")).read_text(encoding="utf-8")
    record = json.loads(next(output_root.glob("groups/*/generation_record.json")).read_text(encoding="utf-8"))
    assert record["model"] == "hy3"
    assert record["provider"] == "self_hosted"
    assert "not an independent reproduction result" in candidate
    assert "[evidence@E01]" in candidate
    assert "Inputs to confirm before execution" in candidate
    with pytest.raises(EvaluationInputError, match="completed human approval"):
        validate_reference_reviews(dataset_root / "dataset.json", output_root, require_approved=True)


@pytest.mark.asyncio
async def test_reference_review_requires_complete_human_signoff(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    output_root = tmp_path / "generation"
    materialize_real_pilot(dataset_root)
    await generate_reference_candidates(
        dataset_root / "dataset.json",
        output_root,
        client=_FakeGenerationClient(),
        settings=Settings(),
    )

    for path in output_root.glob("groups/*/review_form.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(
            {
                "status": "approved",
                "reviewer_id": "reviewer-a",
                "review_date": "2026-09-08",
                "reviewer_expertise": "Researcher with communications and reproducibility-review experience.",
            }
        )
        payload["checklist"] = {key: True for key in payload["checklist"]}
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    result = validate_reference_reviews(dataset_root / "dataset.json", output_root, require_approved=True)
    assert result.approved_count == REAL_PILOT_GROUP_COUNT
    assert result.approved_for_promotion is True


@pytest.mark.asyncio
async def test_reference_review_rejects_candidate_tampering(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    output_root = tmp_path / "generation"
    materialize_real_pilot(dataset_root)
    await generate_reference_candidates(
        dataset_root / "dataset.json",
        output_root,
        client=_FakeGenerationClient(),
        settings=Settings(),
    )
    candidate = next(output_root.glob("groups/*/candidate.md"))
    candidate.write_text(candidate.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="candidate fingerprint changed"):
        validate_reference_reviews(dataset_root / "dataset.json", output_root)


@pytest.mark.asyncio
async def test_reference_review_recomputes_record_lineage(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    output_root = tmp_path / "generation"
    materialize_real_pilot(dataset_root)
    await generate_reference_candidates(
        dataset_root / "dataset.json",
        output_root,
        client=_FakeGenerationClient(),
        settings=Settings(),
    )

    index_path = output_root / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    item = index["items"][0]
    record_path = output_root / item["generation_record_path"]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["response"]["central_claim"]["text"] = "a jointly tampered unsupported claim"
    record_bytes = (json.dumps(record, indent=2) + "\n").encode()
    record_path.write_bytes(record_bytes)
    item["generation_record_sha256"] = hashlib.sha256(record_bytes).hexdigest().upper()
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="generation or review lineage changed"):
        validate_reference_reviews(dataset_root / "dataset.json", output_root)
