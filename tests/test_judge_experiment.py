from __future__ import annotations

import json
from pathlib import Path

import pytest

from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.judge_experiment import (
    EXPERIMENT_LOCK_NAME,
    EXPERIMENT_MANIFEST_NAME,
    JudgeExperiment,
    run_judge_experiment,
)
from hy3_reproeval.stability import BenchmarkStabilityResult


class ExperimentJudgeClient:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.call_count = 0
        self.fail_on_call = fail_on_call

    async def complete_structured(self, messages, response_model, **kwargs):
        self.call_count += 1
        if self.call_count == self.fail_on_call:
            raise RuntimeError("synthetic interrupted experiment")
        return response_model.model_validate(
            {
                "schema_version": "1.0",
                "assessments": [
                    {
                        "dimension": "reasoning_consistency",
                        "score": 4,
                        "rationale": "The report connects evidence and conclusion in this protocol test.",
                        "evidence_lines": [9],
                        "error_code": None,
                    },
                    {
                        "dimension": "clarity_actionability",
                        "score": 4,
                        "rationale": "The report exposes a locally identifiable action in this protocol test.",
                        "evidence_lines": [13],
                        "error_code": None,
                    },
                ],
            }
        )


def _manifest() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "dataset" / "sample_dataset.json"


def _p1_manifest() -> Path:
    return Path(__file__).resolve().parents[1] / "evals" / "p1_transfer_dataset" / "dataset.json"


async def test_experiment_runs_complete_frozen_three_run_pipeline(tmp_path: Path) -> None:
    clients: list[ExperimentJudgeClient] = []

    def factory(run_number: int) -> ExperimentJudgeClient:
        assert run_number == len(clients) + 1
        client = ExperimentJudgeClient()
        clients.append(client)
        return client

    result = await run_judge_experiment(
        _manifest(),
        tmp_path / "experiment",
        model="hy3-test",
        provider="test-provider",
        judge_client_factory=factory,
    )

    assert result.status == "completed"
    assert result.requested_run_count == 3
    assert len({run.judge_run_id for run in result.runs}) == 3
    assert all(run.status == "completed" and run.report_count == 3 for run in result.runs)
    assert [client.call_count for client in clients] == [3, 3, 3]
    root = tmp_path / "experiment"
    assert (root / "dataset_freeze.json").is_file()
    assert (root / "review" / "summary.md").is_file()
    assert (root / "review" / "export_manifest.json").is_file()
    assert not (root / EXPERIMENT_LOCK_NAME).exists()
    stability = BenchmarkStabilityResult.model_validate_json((root / "benchmark_stability.json").read_bytes())
    assert stability.run_count == 3
    assert stability.overall.protocol_coverage_ready is True


async def test_canonical_p1_experiment_covers_all_reports_across_three_runs(tmp_path: Path) -> None:
    clients: list[ExperimentJudgeClient] = []

    def factory(_: int) -> ExperimentJudgeClient:
        client = ExperimentJudgeClient()
        clients.append(client)
        return client

    result = await run_judge_experiment(
        _p1_manifest(),
        tmp_path / "p1-experiment",
        model="hy3-test",
        provider="test-provider",
        judge_client_factory=factory,
    )

    assert result.status == "completed"
    assert all(run.report_count == 15 for run in result.runs)
    assert [client.call_count for client in clients] == [15, 15, 15]
    stability = BenchmarkStabilityResult.model_validate_json(
        (tmp_path / "p1-experiment" / "benchmark_stability.json").read_bytes()
    )
    assert stability.overall.report_count == 15
    assert stability.overall.fully_scored_report_count == 15
    assert stability.overall.protocol_coverage_ready is True


async def test_completed_experiment_resume_verifies_without_judge_calls(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    original = await run_judge_experiment(
        _manifest(),
        root,
        runs=2,
        model="hy3-test",
        provider="test-provider",
        judge_client_factory=lambda _: ExperimentJudgeClient(),
    )
    original_bytes = (root / EXPERIMENT_MANIFEST_NAME).read_bytes()

    resumed = await run_judge_experiment(
        _manifest(),
        root,
        runs=2,
        model="hy3-test",
        provider="test-provider",
        resume=True,
        judge_client_factory=lambda _: pytest.fail("completed resume must not call the Judge"),
    )

    assert resumed == original
    assert (root / EXPERIMENT_MANIFEST_NAME).read_bytes() == original_bytes


async def test_interrupted_experiment_resumes_partial_run_and_finishes(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    first = ExperimentJudgeClient(fail_on_call=2)
    with pytest.raises(RuntimeError, match="interrupted experiment"):
        await run_judge_experiment(
            _manifest(),
            root,
            runs=2,
            model="hy3-test",
            provider="test-provider",
            judge_client_factory=lambda _: first,
        )
    partial = JudgeExperiment.model_validate_json((root / EXPERIMENT_MANIFEST_NAME).read_bytes())
    assert partial.status == "running"
    assert partial.runs[0].status == "running"
    assert not (root / EXPERIMENT_LOCK_NAME).exists()

    resumed_clients: list[ExperimentJudgeClient] = []

    def resume_factory(_: int) -> ExperimentJudgeClient:
        client = ExperimentJudgeClient()
        resumed_clients.append(client)
        return client

    completed = await run_judge_experiment(
        _manifest(),
        root,
        runs=2,
        model="hy3-test",
        provider="test-provider",
        resume=True,
        judge_client_factory=resume_factory,
    )

    assert completed.status == "completed"
    assert [client.call_count for client in resumed_clients] == [2, 3]


async def test_completed_experiment_resume_rejects_tampered_benchmark(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    await run_judge_experiment(
        _manifest(),
        root,
        runs=2,
        model="hy3-test",
        provider="test-provider",
        judge_client_factory=lambda _: ExperimentJudgeClient(),
    )
    benchmark_path = root / "benchmark-run-01.json"
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    payload["warnings"].append("tampered")
    benchmark_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="Benchmark changed"):
        await run_judge_experiment(
            _manifest(),
            root,
            runs=2,
            model="hy3-test",
            provider="test-provider",
            resume=True,
            judge_client_factory=lambda _: ExperimentJudgeClient(),
        )


async def test_completed_experiment_resume_rejects_tampered_review_file(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    await run_judge_experiment(
        _manifest(),
        root,
        runs=2,
        model="hy3-test",
        provider="test-provider",
        judge_client_factory=lambda _: ExperimentJudgeClient(),
    )
    summary_path = root / "review" / "summary.md"
    summary_path.write_text(summary_path.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="review export file fingerprint changed"):
        await run_judge_experiment(
            _manifest(),
            root,
            runs=2,
            model="hy3-test",
            provider="test-provider",
            resume=True,
            judge_client_factory=lambda _: ExperimentJudgeClient(),
        )


async def test_experiment_rejects_active_writer_lock(tmp_path: Path) -> None:
    root = tmp_path / "experiment"
    root.mkdir()
    (root / EXPERIMENT_LOCK_NAME).write_text("pid=123\n", encoding="ascii")

    with pytest.raises(EvaluationInputError, match="already active"):
        await run_judge_experiment(
            _manifest(),
            root,
            runs=2,
            model="hy3-test",
            provider="test-provider",
            resume=True,
        )
