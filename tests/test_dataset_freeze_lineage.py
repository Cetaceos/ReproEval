from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from hy3_reproeval.agreement import analyze_annotation_agreement
from hy3_reproeval.annotations import validate_annotation_bundles
from hy3_reproeval.benchmark import BenchmarkMode, run_dataset_benchmark
from hy3_reproeval.consensus import finalize_annotation_consensus
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.freeze import DatasetFreeze, create_dataset_freeze
from hy3_reproeval.judge_batch import (
    JUDGE_RECORD_INDEX_NAME,
    generate_dataset_judge_records,
    validate_judge_record_index,
)


class _FakeJudgeClient:
    async def complete_structured(self, messages, response_model, **kwargs):
        return response_model.model_validate(
            {
                "schema_version": "1.0",
                "assessments": [
                    {
                        "dimension": "reasoning_consistency",
                        "score": 4,
                        "rationale": "The conclusion follows from cited evidence in this lineage test.",
                        "evidence_lines": [9],
                        "error_code": None,
                    },
                    {
                        "dimension": "clarity_actionability",
                        "score": 4,
                        "rationale": "The report exposes an actionable conclusion in this lineage test.",
                        "evidence_lines": [13],
                        "error_code": None,
                    },
                ],
            }
        )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _manifest() -> Path:
    return _project_root() / "examples" / "dataset" / "sample_dataset.json"


def _synthetic_bundle() -> Path:
    return _project_root() / "examples" / "annotations" / "synthetic_annotation_bundle.json"


def _write_freeze(tmp_path: Path) -> tuple[Path, DatasetFreeze]:
    freeze = create_dataset_freeze(_manifest())
    path = tmp_path / "dataset-freeze.json"
    path.write_bytes((freeze.model_dump_json(indent=2) + "\n").encode("utf-8"))
    return path, freeze


def _write_bound_bundle(tmp_path: Path, freeze_sha256: str) -> Path:
    payload = json.loads(_synthetic_bundle().read_text(encoding="utf-8"))
    payload["dataset_freeze_sha256"] = freeze_sha256
    path = tmp_path / "annotation-bundle.json"
    path.write_bytes(json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8") + b"\n")
    return path


async def test_freeze_fingerprint_flows_through_judge_and_benchmark(tmp_path: Path) -> None:
    freeze_path, freeze = _write_freeze(tmp_path)
    judge_dir = tmp_path / "judge"
    judge_dir.mkdir()

    index = await generate_dataset_judge_records(
        _manifest(),
        judge_dir,
        judge_client=_FakeJudgeClient(),
        model="hy3-test",
        provider="test-provider",
        dataset_freeze_path=freeze_path,
    )
    loaded = validate_judge_record_index(
        judge_dir / JUDGE_RECORD_INDEX_NAME,
        _manifest(),
        dataset_freeze_path=freeze_path,
    )
    benchmark = await run_dataset_benchmark(
        _manifest(),
        mode=BenchmarkMode.REPLAY,
        judge_index_path=judge_dir / JUDGE_RECORD_INDEX_NAME,
        dataset_freeze_path=freeze_path,
    )

    assert index.dataset_freeze_sha256 == freeze.freeze_sha256
    assert loaded.index.dataset_freeze_sha256 == freeze.freeze_sha256
    assert benchmark.dataset_freeze_sha256 == freeze.freeze_sha256

    with pytest.raises(EvaluationInputError, match="--dataset-freeze"):
        await run_dataset_benchmark(
            _manifest(),
            mode=BenchmarkMode.REPLAY,
            judge_index_path=judge_dir / JUDGE_RECORD_INDEX_NAME,
        )
    with pytest.raises(EvaluationInputError, match="different Dataset Freeze binding"):
        await generate_dataset_judge_records(
            _manifest(),
            judge_dir,
            judge_client=_FakeJudgeClient(),
            model="hy3-test",
            provider="test-provider",
            resume=True,
        )


def test_freeze_fingerprint_flows_through_annotation_outputs(tmp_path: Path) -> None:
    freeze_path, freeze = _write_freeze(tmp_path)
    bundle_path = _write_bound_bundle(tmp_path, freeze.freeze_sha256)

    validation = validate_annotation_bundles(
        _manifest(),
        [bundle_path],
        dataset_freeze_path=freeze_path,
    )
    agreement = analyze_annotation_agreement(
        _manifest(),
        [bundle_path],
        dataset_freeze_path=freeze_path,
    )
    consensus = finalize_annotation_consensus(
        _manifest(),
        [bundle_path],
        dataset_freeze_path=freeze_path,
    )

    assert validation.dataset_freeze_sha256 == freeze.freeze_sha256
    assert agreement.dataset_freeze_sha256 == freeze.freeze_sha256
    assert consensus.dataset_freeze_sha256 == freeze.freeze_sha256

    with pytest.raises(EvaluationInputError, match="--dataset-freeze"):
        validate_annotation_bundles(_manifest(), [bundle_path])


async def test_strict_freeze_rejects_unbound_judge_index(tmp_path: Path) -> None:
    freeze_path, _ = _write_freeze(tmp_path)
    judge_dir = tmp_path / "judge"
    judge_dir.mkdir()
    await generate_dataset_judge_records(
        _manifest(),
        judge_dir,
        judge_client=_FakeJudgeClient(),
        model="hy3-test",
        provider="test-provider",
    )

    with pytest.raises(EvaluationInputError, match="verified Dataset Freeze"):
        validate_judge_record_index(
            judge_dir / JUDGE_RECORD_INDEX_NAME,
            _manifest(),
            dataset_freeze_path=freeze_path,
        )


def test_strict_freeze_rejects_unbound_annotation_bundle(tmp_path: Path) -> None:
    freeze_path, _ = _write_freeze(tmp_path)

    with pytest.raises(EvaluationInputError, match="verified Dataset Freeze"):
        validate_annotation_bundles(
            _manifest(),
            [_synthetic_bundle()],
            dataset_freeze_path=freeze_path,
        )


def test_system_human_comparison_rejects_unbound_benchmark(tmp_path: Path) -> None:
    freeze_path, freeze = _write_freeze(tmp_path)
    bundle_path = _write_bound_bundle(tmp_path, freeze.freeze_sha256)
    benchmark = asyncio.run(run_dataset_benchmark(_manifest(), mode=BenchmarkMode.REPLAY))
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_bytes((benchmark.model_dump_json(indent=2) + "\n").encode("utf-8"))

    with pytest.raises(EvaluationInputError, match="different Dataset Freeze fingerprint"):
        analyze_annotation_agreement(
            _manifest(),
            [bundle_path],
            benchmark_result_path=benchmark_path,
            dataset_freeze_path=freeze_path,
        )
