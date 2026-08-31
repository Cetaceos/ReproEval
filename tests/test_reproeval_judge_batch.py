from __future__ import annotations

from pathlib import Path

import pytest

from hy3_reproeval.benchmark import BenchmarkMode, run_dataset_benchmark
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.judge_batch import (
    JUDGE_RECORD_INDEX_NAME,
    JudgeRecordIndex,
    generate_dataset_judge_records,
    validate_judge_record_index,
)


class FakeBatchJudgeClient:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.call_count = 0
        self.fail_on_call = fail_on_call

    async def complete_structured(self, messages, response_model, **kwargs):
        self.call_count += 1
        if self.call_count == self.fail_on_call:
            raise RuntimeError("synthetic interrupted API call")
        return response_model.model_validate(
            {
                "schema_version": "1.0",
                "assessments": [
                    {
                        "dimension": "reasoning_consistency",
                        "score": 4,
                        "rationale": "The evidence and conclusion are connected for this protocol test.",
                        "evidence_lines": [9],
                        "error_code": None,
                    },
                    {
                        "dimension": "clarity_actionability",
                        "score": 4,
                        "rationale": "The final section is locally identifiable for this protocol test.",
                        "evidence_lines": [13],
                        "error_code": None,
                    },
                ],
            }
        )


class FailIfCalledJudgeClient(FakeBatchJudgeClient):
    async def complete_structured(self, messages, response_model, **kwargs):
        raise AssertionError("resume should reuse every verified Judge Record")


def _public_manifest() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dataset" / "sample_dataset.json"


async def test_batch_generation_writes_complete_lf_index_and_records(tmp_path: Path) -> None:
    client = FakeBatchJudgeClient()

    index = await generate_dataset_judge_records(
        _public_manifest(),
        tmp_path,
        judge_client=client,
        model="hy3-test",
        provider="test-provider",
    )

    assert index.complete is True
    assert index.record_count == 3
    assert client.call_count == 3
    index_path = tmp_path / JUDGE_RECORD_INDEX_NAME
    assert index_path.is_file()
    assert b"\r\n" not in index_path.read_bytes()
    for entry in index.records:
        record_path = tmp_path / entry.record_path
        assert record_path.is_file()
        assert b"\r\n" not in record_path.read_bytes()
    loaded = validate_judge_record_index(index_path, _public_manifest())
    assert loaded.index == index
    assert len(loaded.record_paths_by_report_id) == 3


async def test_generated_index_is_consumable_by_replay_benchmark(tmp_path: Path) -> None:
    await generate_dataset_judge_records(
        _public_manifest(),
        tmp_path,
        judge_client=FakeBatchJudgeClient(),
        model="hy3-test",
        provider="test-provider",
    )

    result = await run_dataset_benchmark(
        _public_manifest(),
        mode=BenchmarkMode.REPLAY,
        judge_index_path=tmp_path / JUDGE_RECORD_INDEX_NAME,
    )

    assert result.judge_record_index_sha256 is not None
    assert result.overall.ranking_eligible_report_count == 3


async def test_resume_reuses_verified_records_without_api_calls(tmp_path: Path) -> None:
    await generate_dataset_judge_records(
        _public_manifest(),
        tmp_path,
        judge_client=FakeBatchJudgeClient(),
        model="hy3-test",
        provider="test-provider",
    )

    resumed = await generate_dataset_judge_records(
        _public_manifest(),
        tmp_path,
        judge_client=FailIfCalledJudgeClient(),
        model="hy3-test",
        provider="test-provider",
        resume=True,
    )

    assert resumed.complete is True
    assert resumed.record_count == 3


async def test_interrupted_run_retains_partial_index_and_can_resume(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="interrupted API call"):
        await generate_dataset_judge_records(
            _public_manifest(),
            tmp_path,
            judge_client=FakeBatchJudgeClient(fail_on_call=2),
            model="hy3-test",
            provider="test-provider",
        )
    partial = JudgeRecordIndex.model_validate_json((tmp_path / JUDGE_RECORD_INDEX_NAME).read_bytes())
    assert partial.complete is False
    assert partial.record_count == 1

    client = FakeBatchJudgeClient()
    completed = await generate_dataset_judge_records(
        _public_manifest(),
        tmp_path,
        judge_client=client,
        model="hy3-test",
        provider="test-provider",
        resume=True,
    )

    assert completed.complete is True
    assert completed.record_count == 3
    assert client.call_count == 2


async def test_generation_rejects_existing_output_without_resume(tmp_path: Path) -> None:
    await generate_dataset_judge_records(
        _public_manifest(),
        tmp_path,
        judge_client=FakeBatchJudgeClient(),
        model="hy3-test",
        provider="test-provider",
    )

    with pytest.raises(EvaluationInputError, match="output already exists"):
        await generate_dataset_judge_records(
            _public_manifest(),
            tmp_path,
            judge_client=FakeBatchJudgeClient(),
            model="hy3-test",
            provider="test-provider",
        )


async def test_index_validation_rejects_tampered_record(tmp_path: Path) -> None:
    index = await generate_dataset_judge_records(
        _public_manifest(),
        tmp_path,
        judge_client=FakeBatchJudgeClient(),
        model="hy3-test",
        provider="test-provider",
    )
    record_path = tmp_path / index.records[0].record_path
    record_path.write_bytes(record_path.read_bytes() + b"\n")

    with pytest.raises(EvaluationInputError, match="file SHA-256 mismatch"):
        validate_judge_record_index(tmp_path / JUDGE_RECORD_INDEX_NAME, _public_manifest())
