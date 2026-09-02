"""One-command orchestration for frozen repeated Hy3 Judge experiments."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from . import __version__
from .benchmark import BenchmarkMode, DatasetBenchmarkResult, run_dataset_benchmark
from .dataset import load_dataset_manifest, validate_dataset_manifest
from .errors import EvaluationInputError
from .freeze import create_dataset_freeze, verify_dataset_freeze
from .judge import StructuredJudgeClient
from .judge_batch import JUDGE_RECORD_INDEX_NAME, generate_dataset_judge_records, validate_judge_record_index
from .models import StrictModel
from .results_export import export_benchmark_results
from .stability import BenchmarkStabilityResult, analyze_benchmark_stability

EXPERIMENT_MANIFEST_NAME = "judge_experiment.json"
EXPERIMENT_FREEZE_NAME = "dataset_freeze.json"
EXPERIMENT_STABILITY_NAME = "benchmark_stability.json"
EXPERIMENT_REVIEW_DIR = "review"
EXPERIMENT_LOCK_NAME = ".judge-experiment.lock"
MAX_EXPERIMENT_MANIFEST_BYTES = 4 * 1024 * 1024
MIN_EXPERIMENT_RUNS = 2
MAX_EXPERIMENT_RUNS = 10

JudgeClientFactory = Callable[[int], StructuredJudgeClient | None]


class JudgeExperimentRun(StrictModel):
    run_number: int = Field(ge=1)
    status: Literal["pending", "running", "completed"]
    judge_output_dir: str
    judge_index_path: str
    benchmark_path: str
    judge_run_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    judge_record_index_sha256: str | None = Field(default=None, pattern=r"^[A-F0-9]{64}$")
    report_count: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_state(self) -> JudgeExperimentRun:
        expected_root = f"judge-run-{self.run_number:02d}"
        expected = (
            expected_root,
            f"{expected_root}/{JUDGE_RECORD_INDEX_NAME}",
            f"benchmark-run-{self.run_number:02d}.json",
        )
        if (self.judge_output_dir, self.judge_index_path, self.benchmark_path) != expected:
            raise ValueError("experiment run paths do not match the canonical inventory")
        identity = (self.judge_run_id, self.judge_record_index_sha256, self.report_count)
        if self.status == "completed" and any(value is None for value in identity):
            raise ValueError("completed experiment run requires its complete identity")
        if self.status != "completed" and any(value is not None for value in identity):
            raise ValueError("incomplete experiment run cannot declare a completed identity")
        return self


class JudgeExperiment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    experiment_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    started_at_utc: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T.+Z$")
    status: Literal["running", "completed"]
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_path: str
    dataset_freeze_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    requested_run_count: int = Field(ge=MIN_EXPERIMENT_RUNS, le=MAX_EXPERIMENT_RUNS)
    model: str | None = Field(default=None, min_length=1)
    provider: str | None = Field(default=None, min_length=1)
    runs: list[JudgeExperimentRun]
    stability_path: str | None = None
    review_dir: str | None = None

    @model_validator(mode="after")
    def validate_runs(self) -> JudgeExperiment:
        if self.dataset_freeze_path != EXPERIMENT_FREEZE_NAME:
            raise ValueError("experiment Dataset Freeze path must use the canonical relative path")
        if len(self.runs) != self.requested_run_count:
            raise ValueError("experiment run inventory does not match requested_run_count")
        if [run.run_number for run in self.runs] != list(range(1, self.requested_run_count + 1)):
            raise ValueError("experiment runs must be ordered and consecutively numbered")
        if self.status == "completed" and any(run.status != "completed" for run in self.runs):
            raise ValueError("completed experiment requires every Judge run to be completed")
        if self.status == "completed" and (self.stability_path is None or self.review_dir is None):
            raise ValueError("completed experiment requires stability and review outputs")
        if self.status == "completed" and (self.model is None or self.provider is None):
            raise ValueError("completed experiment requires model and provider provenance")
        if self.status == "completed" and (
            self.stability_path != EXPERIMENT_STABILITY_NAME or self.review_dir != EXPERIMENT_REVIEW_DIR
        ):
            raise ValueError("completed experiment outputs must use canonical relative paths")
        if self.status == "running" and (self.stability_path is not None or self.review_dir is not None):
            raise ValueError("running experiment cannot declare final outputs")
        return self


async def run_judge_experiment(
    dataset_path: str | Path,
    output_dir: str | Path,
    *,
    runs: int = 3,
    model: str | None = None,
    provider: str | None = None,
    resume: bool = False,
    judge_client_factory: JudgeClientFactory | None = None,
) -> JudgeExperiment:
    """Run or resume a frozen repeated-Judge experiment and export review artifacts."""

    if not MIN_EXPERIMENT_RUNS <= runs <= MAX_EXPERIMENT_RUNS:
        raise EvaluationInputError(
            f"Judge experiment runs must be between {MIN_EXPERIMENT_RUNS} and {MAX_EXPERIMENT_RUNS}"
        )
    validate_dataset_manifest(dataset_path)
    output_root = _prepare_output_root(output_dir, resume=resume)
    with _exclusive_experiment_lock(output_root):
        experiment = _load_or_create_experiment(
            dataset_path,
            output_root,
            runs=runs,
            model=model,
            provider=provider,
            resume=resume,
        )
        if experiment.status == "completed":
            await _verify_completed_experiment(experiment, dataset_path, output_root)
            return experiment

        freeze_path = output_root / experiment.dataset_freeze_path
        for run in experiment.runs:
            if run.status == "completed":
                await _verify_completed_run(run, dataset_path, freeze_path, output_root)
                continue
            run.status = "running"
            _write_experiment(output_root, experiment)
            judge_root = output_root / run.judge_output_dir
            judge_root.mkdir(exist_ok=True)
            should_resume = any(judge_root.iterdir())
            client = judge_client_factory(run.run_number) if judge_client_factory is not None else None
            active_model = experiment.model or model
            active_provider = experiment.provider or provider
            index = await generate_dataset_judge_records(
                dataset_path,
                judge_root,
                judge_client=client,
                model=active_model,
                provider=active_provider,
                resume=should_resume,
                dataset_freeze_path=freeze_path,
            )
            index_path = output_root / run.judge_index_path
            benchmark = await run_dataset_benchmark(
                dataset_path,
                mode=BenchmarkMode.REPLAY,
                judge_index_path=index_path,
                dataset_freeze_path=freeze_path,
            )
            benchmark_path = output_root / run.benchmark_path
            _write_json(benchmark_path, benchmark)
            run.status = "completed"
            run.judge_run_id = index.run_id
            run.judge_record_index_sha256 = _file_sha256(index_path)
            run.report_count = index.record_count
            if experiment.model is None:
                experiment.model = index.model
            if experiment.provider is None:
                experiment.provider = index.provider
            _write_experiment(output_root, experiment)

        benchmark_paths = [output_root / run.benchmark_path for run in experiment.runs]
        stability = analyze_benchmark_stability(benchmark_paths)
        stability_path = output_root / EXPERIMENT_STABILITY_NAME
        _write_json(stability_path, stability)
        review_root = output_root / EXPERIMENT_REVIEW_DIR
        if review_root.exists():
            _verify_review_bundle(review_root, benchmark_paths, stability_path)
        else:
            temporary_review = output_root / f".{EXPERIMENT_REVIEW_DIR}-{uuid4().hex}.tmp"
            export_benchmark_results(benchmark_paths, stability_path, temporary_review)
            temporary_review.rename(review_root)
        experiment.status = "completed"
        experiment.stability_path = EXPERIMENT_STABILITY_NAME
        experiment.review_dir = EXPERIMENT_REVIEW_DIR
        _write_experiment(output_root, experiment)
        return experiment


def _prepare_output_root(path: str | Path, *, resume: bool) -> Path:
    output_root = Path(path).expanduser().resolve()
    if output_root.exists() and not output_root.is_dir():
        raise EvaluationInputError("Judge experiment output path must be a directory")
    if not output_root.parent.is_dir():
        raise EvaluationInputError(f"Judge experiment parent directory does not exist: {output_root.parent.as_posix()}")
    if resume:
        if not output_root.is_dir():
            raise EvaluationInputError("resumed Judge experiment output directory does not exist")
    elif output_root.exists() and any(output_root.iterdir()):
        raise EvaluationInputError("Judge experiment output directory must be absent or empty")
    output_root.mkdir(exist_ok=True)
    return output_root


def _load_or_create_experiment(
    dataset_path: str | Path,
    output_root: Path,
    *,
    runs: int,
    model: str | None,
    provider: str | None,
    resume: bool,
) -> JudgeExperiment:
    manifest_path = output_root / EXPERIMENT_MANIFEST_NAME
    freeze_path = output_root / EXPERIMENT_FREEZE_NAME
    dataset = load_dataset_manifest(dataset_path)
    if resume:
        experiment = _load_experiment(manifest_path)
        verification = verify_dataset_freeze(freeze_path, dataset_path)
        identity = (
            experiment.dataset_id,
            experiment.dataset_version,
            experiment.dataset_manifest_sha256,
            experiment.dataset_freeze_sha256,
        )
        current = (
            dataset.manifest.dataset_id,
            dataset.manifest.dataset_version,
            dataset.manifest_sha256,
            verification.freeze_sha256,
        )
        if identity != current:
            raise EvaluationInputError("resumed Judge experiment uses a different Dataset or Freeze")
        if experiment.requested_run_count != runs:
            raise EvaluationInputError("resumed Judge experiment uses a different run count")
        if model is not None and experiment.model is not None and model != experiment.model:
            raise EvaluationInputError("resumed Judge experiment uses a different model")
        if provider is not None and experiment.provider is not None and provider != experiment.provider:
            raise EvaluationInputError("resumed Judge experiment uses a different provider")
        return experiment
    if manifest_path.exists() or freeze_path.exists():
        raise EvaluationInputError("new Judge experiment output already contains experiment artifacts")
    freeze = create_dataset_freeze(dataset_path)
    _write_json(freeze_path, freeze)
    experiment = JudgeExperiment(
        engine_version=__version__,
        experiment_id=uuid4().hex,
        started_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        status="running",
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        dataset_manifest_sha256=dataset.manifest_sha256,
        dataset_freeze_path=EXPERIMENT_FREEZE_NAME,
        dataset_freeze_sha256=freeze.freeze_sha256,
        requested_run_count=runs,
        model=model,
        provider=provider,
        runs=[
            JudgeExperimentRun(
                run_number=number,
                status="pending",
                judge_output_dir=f"judge-run-{number:02d}",
                judge_index_path=f"judge-run-{number:02d}/{JUDGE_RECORD_INDEX_NAME}",
                benchmark_path=f"benchmark-run-{number:02d}.json",
            )
            for number in range(1, runs + 1)
        ],
    )
    _write_experiment(output_root, experiment)
    return experiment


async def _verify_completed_run(
    run: JudgeExperimentRun,
    dataset_path: str | Path,
    freeze_path: Path,
    output_root: Path,
) -> None:
    loaded = validate_judge_record_index(
        output_root / run.judge_index_path,
        dataset_path,
        dataset_freeze_path=freeze_path,
    )
    if loaded.index.run_id != run.judge_run_id or loaded.index_sha256 != run.judge_record_index_sha256:
        raise EvaluationInputError(f"completed Judge experiment run {run.run_number} index identity changed")
    benchmark_path = output_root / run.benchmark_path
    benchmark = _load_benchmark(benchmark_path)
    recomputed = await run_dataset_benchmark(
        dataset_path,
        mode=BenchmarkMode.REPLAY,
        judge_index_path=output_root / run.judge_index_path,
        dataset_freeze_path=freeze_path,
    )
    if benchmark.model_dump(exclude={"engine_version"}) != recomputed.model_dump(exclude={"engine_version"}):
        raise EvaluationInputError(f"completed Judge experiment run {run.run_number} Benchmark changed")
    if benchmark.judge_run_id != run.judge_run_id or run.report_count != loaded.index.record_count:
        raise EvaluationInputError(f"completed Judge experiment run {run.run_number} Benchmark identity changed")


async def _verify_completed_experiment(
    experiment: JudgeExperiment,
    dataset_path: str | Path,
    output_root: Path,
) -> None:
    freeze_path = output_root / experiment.dataset_freeze_path
    verification = verify_dataset_freeze(freeze_path, dataset_path)
    if verification.freeze_sha256 != experiment.dataset_freeze_sha256:
        raise EvaluationInputError("completed Judge experiment Freeze identity changed")
    for run in experiment.runs:
        await _verify_completed_run(run, dataset_path, freeze_path, output_root)
    stability_path = output_root / (experiment.stability_path or "")
    recomputed = analyze_benchmark_stability([output_root / run.benchmark_path for run in experiment.runs])
    stored = _load_stability(stability_path)
    if recomputed.model_dump(exclude={"engine_version"}) != stored.model_dump(exclude={"engine_version"}):
        raise EvaluationInputError("completed Judge experiment Stability result changed")
    review_manifest = output_root / (experiment.review_dir or "") / "export_manifest.json"
    if not review_manifest.is_file():
        raise EvaluationInputError("completed Judge experiment review manifest is missing")
    _verify_review_bundle(
        review_manifest.parent,
        [output_root / run.benchmark_path for run in experiment.runs],
        stability_path,
    )


def _verify_review_bundle(review_root: Path, benchmark_paths: list[Path], stability_path: Path) -> None:
    manifest_path = review_root / "export_manifest.json"
    payload = _read_limited(manifest_path, MAX_EXPERIMENT_MANIFEST_BYTES, "review export manifest")
    try:
        manifest = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationInputError(f"invalid review export manifest: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("outputs"), list):
        raise EvaluationInputError("invalid review export manifest inventory")
    stability = _load_stability(stability_path)
    expected_identity = (
        stability.dataset_id,
        stability.dataset_version,
        stability.dataset_manifest_sha256,
        stability.dataset_freeze_sha256,
        stability.rubric_version,
        stability.rubric_sha256,
        stability.run_count,
        stability.judge_record_index_sha256s,
        stability.judge_run_ids,
    )
    observed_identity = (
        manifest.get("dataset_id"),
        manifest.get("dataset_version"),
        manifest.get("dataset_manifest_sha256"),
        manifest.get("dataset_freeze_sha256"),
        manifest.get("rubric_version"),
        manifest.get("rubric_sha256"),
        manifest.get("run_count"),
        manifest.get("judge_record_index_sha256s"),
        manifest.get("judge_run_ids"),
    )
    if observed_identity != expected_identity:
        raise EvaluationInputError("review export experiment identity changed")
    expected_benchmarks = [_file_sha256(path) for path in benchmark_paths]
    if manifest.get("benchmark_result_sha256s") != expected_benchmarks:
        raise EvaluationInputError("review export Benchmark fingerprints changed")
    if manifest.get("stability_result_sha256") != _file_sha256(stability_path):
        raise EvaluationInputError("review export Stability fingerprint changed")
    expected_outputs = {"summary.md", "benchmark_runs.csv", "report_stability.csv", "dimension_stability.csv"}
    if (
        len(manifest["outputs"]) != len(expected_outputs)
        or {entry.get("path") for entry in manifest["outputs"] if isinstance(entry, dict)} != expected_outputs
    ):
        raise EvaluationInputError("review export file inventory changed")
    for entry in manifest["outputs"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise EvaluationInputError("invalid review export file entry")
        path = (review_root / entry["path"]).resolve()
        if not path.is_relative_to(review_root.resolve()) or not path.is_file():
            raise EvaluationInputError("review export file is missing or escapes its directory")
        if path.stat().st_size != entry.get("bytes") or _file_sha256(path) != entry.get("sha256"):
            raise EvaluationInputError(f"review export file fingerprint changed: {entry['path']}")


def _load_experiment(path: Path) -> JudgeExperiment:
    payload = _read_limited(path, MAX_EXPERIMENT_MANIFEST_BYTES, "Judge experiment manifest")
    try:
        return JudgeExperiment.model_validate_json(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid Judge experiment manifest: {exc}") from exc


def _load_benchmark(path: Path) -> DatasetBenchmarkResult:
    payload = _read_limited(path, 32 * 1024 * 1024, "Dataset Benchmark result")
    try:
        return DatasetBenchmarkResult.model_validate_json(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid Dataset Benchmark result: {exc}") from exc


def _load_stability(path: Path) -> BenchmarkStabilityResult:
    payload = _read_limited(path, 32 * 1024 * 1024, "Benchmark Stability result")
    try:
        return BenchmarkStabilityResult.model_validate_json(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid Benchmark Stability result: {exc}") from exc


def _read_limited(path: Path, maximum_bytes: int, label: str) -> bytes:
    if not path.is_file():
        raise EvaluationInputError(f"{label} does not exist: {path.as_posix()}")
    if path.stat().st_size > maximum_bytes:
        raise EvaluationInputError(f"{label} exceeds {maximum_bytes} bytes")
    return path.read_bytes()


def _write_experiment(output_root: Path, experiment: JudgeExperiment) -> None:
    _write_json(output_root / EXPERIMENT_MANIFEST_NAME, experiment)


def _write_json(path: Path, model: StrictModel) -> None:
    path.write_bytes((model.model_dump_json(indent=2) + "\n").encode("utf-8"))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


@contextmanager
def _exclusive_experiment_lock(output_root: Path) -> Iterator[None]:
    lock_path = output_root / EXPERIMENT_LOCK_NAME
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise EvaluationInputError(
            "Judge experiment is already active for this output directory; inspect the lock before resuming"
        ) from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    finally:
        os.close(descriptor)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)
