from __future__ import annotations

import json
from pathlib import Path

import pytest

from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.models import DimensionId
from hy3_reproeval.pairwise import (
    ComparisonPreference,
    PairwiseJudgeResponse,
    PresentationOrder,
    build_pairwise_messages,
    compare_case_files,
    write_pairwise_bundle,
)
from hy3_reproeval.rubric import load_public_rubric
from hy3_reproeval.validators import load_evaluation_case


class ContentAwarePairwiseClient:
    def __init__(self, *, invalid_line: bool = False) -> None:
        self.invalid_line = invalid_line
        self.calls: list[dict[str, object]] = []

    async def complete_structured(self, messages, response_model, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        payload = json.loads(messages[1]["content"])
        report_a = "\n".join(item["text"] for item in payload["report_a_lines"])
        a_is_strong = "registered ablation" in report_a
        strong_score, weak_score = 4, 1
        score_a = strong_score if a_is_strong else weak_score
        score_b = weak_score if a_is_strong else strong_score
        line_a = 999 if self.invalid_line else 13
        response = {
            "schema_version": "1.0",
            "assessments": [
                {
                    "dimension": "reasoning_consistency",
                    "score_a": score_a,
                    "score_b": score_b,
                    "rationale": "One report closes the argument while the other leaves a material reasoning gap.",
                    "evidence_a_lines": [9],
                    "evidence_b_lines": [9],
                },
                {
                    "dimension": "clarity_actionability",
                    "score_a": score_a,
                    "score_b": score_b,
                    "rationale": "Only one report gives a concrete and verifiable next step.",
                    "evidence_a_lines": [line_a],
                    "evidence_b_lines": [13],
                },
            ],
        }
        return response_model.model_validate(response)


def _strong_report() -> str:
    return """# Reproduction Review

## Executive summary

The reproduced Accuracy is 0.876 [paper@L3-L4] [results@rows:1-5].

## Evidence and limitations

Five runs support the measured gap, but there is insufficient evidence for a single causal attribution.

## Next steps

Run the registered ablation with fixed preprocessing and report confidence intervals.
"""


def _weak_report(*, fabricated: bool = False) -> str:
    citation = "[invented@L1]" if fabricated else "[paper@L3-L4]"
    return f"""# Reproduction Review

## Executive summary

The reproduced Accuracy is 0.876 {citation} [results@rows:1-5].

## Evidence and limitations

The result is different. There is insufficient evidence.

## Next steps

Do more work.
"""


def _manifest(case_id: str, report_path: str) -> dict[str, object]:
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


def _write_pair(tmp_path: Path, *, fabricated: bool = False) -> tuple[Path, Path]:
    (tmp_path / "strong.md").write_text(_strong_report(), encoding="utf-8")
    (tmp_path / "weak.md").write_text(_weak_report(fabricated=fabricated), encoding="utf-8")
    left_path = tmp_path / "left.json"
    right_path = tmp_path / "right.json"
    left_path.write_text(json.dumps(_manifest("strong-case", "strong.md")), encoding="utf-8")
    right_path.write_text(json.dumps(_manifest("weak-case", "weak.md")), encoding="utf-8")
    return left_path, right_path


async def test_pairwise_comparison_blinds_order_and_aggregates_three_trials(tmp_path: Path) -> None:
    left_path, right_path = _write_pair(tmp_path)
    client = ContentAwarePairwiseClient()

    result, bundle = await compare_case_files(
        left_path,
        right_path,
        comparison_id="strong-vs-weak-v1",
        repeats=3,
        judge_client=client,
        judge_model="hy3-test",
        judge_provider="test-provider",
    )

    assert result.final_preference is ComparisonPreference.LEFT
    assert result.trial_count == 3
    assert result.left.final_score_mean == 100
    assert result.right.final_score_mean == 81.25
    assert result.left.final_score_stddev == 0
    assert result.preference_flip_rate == 0
    assert result.observed_position_delta_max == 0
    assert {record.presentation_order for record in bundle.records} == set(PresentationOrder)
    assert bundle.records[0].request_sha256 == bundle.records[2].request_sha256
    assert all(call["kwargs"]["temperature"] == 0.0 for call in client.calls)  # type: ignore[index]
    assert result.left.semantic_dimension_means[DimensionId.REASONING_CONSISTENCY] == 4
    assert result.right.semantic_dimension_means[DimensionId.CLARITY_ACTIONABILITY] == 1


async def test_pairwise_replay_reproduces_result_without_client(tmp_path: Path) -> None:
    left_path, right_path = _write_pair(tmp_path)
    online, bundle = await compare_case_files(
        left_path,
        right_path,
        comparison_id="replay-pair-v1",
        repeats=3,
        judge_client=ContentAwarePairwiseClient(),
    )
    bundle_path = write_pairwise_bundle(tmp_path / "pairwise-record.json", bundle)
    assert b"\r\n" not in bundle_path.read_bytes()

    replayed, replay_bundle = await compare_case_files(
        left_path,
        right_path,
        comparison_id="replay-pair-v1",
        repeats=3,
        judge_replay_path=bundle_path,
    )

    assert replayed == online
    assert replay_bundle == bundle


async def test_pairwise_preserves_each_report_deterministic_hard_cap(tmp_path: Path) -> None:
    left_path, right_path = _write_pair(tmp_path, fabricated=True)

    result, _ = await compare_case_files(
        left_path,
        right_path,
        comparison_id="hard-cap-pair-v1",
        judge_client=ContentAwarePairwiseClient(),
    )

    assert result.right.applied_hard_cap == 40
    assert result.right.final_score_mean == 40
    assert result.final_preference is ComparisonPreference.LEFT


async def test_pairwise_rejects_different_evaluation_contracts(tmp_path: Path) -> None:
    left_path, right_path = _write_pair(tmp_path)
    right_manifest = json.loads(right_path.read_text(encoding="utf-8"))
    right_manifest["required_sections"] = right_manifest["required_sections"][:-1]
    right_path.write_text(json.dumps(right_manifest), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="same evaluation contract"):
        await compare_case_files(
            left_path,
            right_path,
            comparison_id="mismatch-v1",
            judge_client=ContentAwarePairwiseClient(),
        )


async def test_pairwise_rejects_out_of_range_evidence_lines(tmp_path: Path) -> None:
    left_path, right_path = _write_pair(tmp_path)

    with pytest.raises(EvaluationInputError, match="outside the presented reports"):
        await compare_case_files(
            left_path,
            right_path,
            comparison_id="bad-lines-v1",
            judge_client=ContentAwarePairwiseClient(invalid_line=True),
        )


async def test_pairwise_rejects_invalid_comparison_id_before_judge_call(tmp_path: Path) -> None:
    left_path, right_path = _write_pair(tmp_path)
    client = ContentAwarePairwiseClient()

    with pytest.raises(EvaluationInputError, match="unsupported characters"):
        await compare_case_files(
            left_path,
            right_path,
            comparison_id="invalid comparison id",
            judge_client=client,
        )

    assert client.calls == []


def test_pairwise_prompt_omits_case_ids_and_paths(tmp_path: Path) -> None:
    left_path, right_path = _write_pair(tmp_path)
    left = load_evaluation_case(left_path)
    right = load_evaluation_case(right_path)

    messages = build_pairwise_messages(
        left,
        right,
        load_public_rubric(),
        presentation_order=PresentationOrder.LEFT_AS_A,
    )

    assert "strong-case" not in messages[1]["content"]
    assert "weak-case" not in messages[1]["content"]
    assert "strong.md" not in messages[1]["content"]
    assert "weak.md" not in messages[1]["content"]
    assert "untrusted data" in messages[0]["content"]


def test_pairwise_response_requires_both_semantic_dimensions() -> None:
    payload = {
        "schema_version": "1.0",
        "assessments": [
            {
                "dimension": "reasoning_consistency",
                "score_a": 4,
                "score_b": 2,
                "rationale": "A closes the argument more completely.",
                "evidence_a_lines": [1],
                "evidence_b_lines": [1],
            },
            {
                "dimension": "reasoning_consistency",
                "score_a": 4,
                "score_b": 2,
                "rationale": "Duplicate dimension.",
                "evidence_a_lines": [1],
                "evidence_b_lines": [1],
            },
        ],
    }

    with pytest.raises(ValueError, match="each semantic dimension exactly once"):
        PairwiseJudgeResponse.model_validate(payload)
