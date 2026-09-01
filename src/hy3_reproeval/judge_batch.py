"""Resumable online Judge Record generation for versioned ReproEval datasets."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from . import __version__
from .dataset import DatasetReportEntry, LoadedDatasetManifest, load_dataset_manifest, validate_dataset_manifest
from .errors import EvaluationInputError
from .evaluator import _rubric_sha256
from .freeze import optional_dataset_freeze_sha256
from .judge import MAX_JUDGE_RECORD_BYTES, StructuredJudgeClient, load_judge_record, request_judge_record
from .models import JudgeRecord, Scenario, StrictModel
from .rubric import RubricDefinition, load_public_rubric
from .validators import LoadedEvaluationCase, load_evaluation_case

if TYPE_CHECKING:
    from hy3_reproscope_mcp.config import Settings

JUDGE_RECORD_INDEX_NAME = "judge_record_index.json"
JUDGE_RECORD_LOCK_NAME = ".judge-record-generation.lock"
MAX_JUDGE_RECORD_INDEX_BYTES = 4 * 1024 * 1024


class JudgeRecordIndexEntry(StrictModel):
    group_id: str
    report_id: str
    case_id: str
    scenario: Scenario
    case_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    report_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    record_path: str
    record_file_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    request_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    response_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")


class JudgeRecordIndex(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    dataset_freeze_sha256: str | None = Field(default=None, pattern=r"^[A-F0-9]{64}$")
    run_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    started_at_utc: str | None = Field(default=None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T.+Z$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    model: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    expected_record_count: int = Field(ge=1)
    record_count: int = Field(ge=0)
    complete: bool
    records: list[JudgeRecordIndexEntry]

    @model_validator(mode="after")
    def validate_inventory(self) -> JudgeRecordIndex:
        if (self.run_id is None) != (self.started_at_utc is None):
            raise ValueError("Judge Record index run ID and UTC start time must be declared together")
        if self.record_count != len(self.records):
            raise ValueError("Judge Record index record_count does not match records")
        if self.record_count > self.expected_record_count:
            raise ValueError("Judge Record index contains more records than expected")
        if self.complete and self.record_count != self.expected_record_count:
            raise ValueError("complete Judge Record index must contain every expected record")
        report_ids = [record.report_id for record in self.records]
        record_paths = [record.record_path for record in self.records]
        if len(report_ids) != len(set(report_ids)):
            raise ValueError("Judge Record index report IDs must be unique")
        if len(record_paths) != len(set(record_paths)):
            raise ValueError("Judge Record index paths must be unique")
        return self


@dataclass(frozen=True, slots=True)
class LoadedJudgeRecordIndex:
    index: JudgeRecordIndex
    index_path: Path
    root: Path
    index_sha256: str
    record_paths_by_report_id: dict[str, Path]


async def generate_dataset_judge_records(
    dataset_path: str | Path,
    output_dir: str | Path,
    *,
    judge_client: StructuredJudgeClient | None = None,
    model: str | None = None,
    provider: str | None = None,
    resume: bool = False,
    dataset_freeze_path: str | Path | None = None,
) -> JudgeRecordIndex:
    """Generate one verified semantic Judge Record per report and update a durable index."""

    output_root = Path(output_dir).expanduser().resolve()
    if not output_root.is_dir():
        raise EvaluationInputError(f"Judge Record output directory does not exist: {output_root.as_posix()}")
    with _exclusive_generation_lock(output_root):
        return await _generate_dataset_judge_records_unlocked(
            dataset_path,
            output_root,
            judge_client=judge_client,
            model=model,
            provider=provider,
            resume=resume,
            dataset_freeze_path=dataset_freeze_path,
        )


async def _generate_dataset_judge_records_unlocked(
    dataset_path: str | Path,
    output_dir: str | Path,
    *,
    judge_client: StructuredJudgeClient | None = None,
    model: str | None = None,
    provider: str | None = None,
    resume: bool = False,
    dataset_freeze_path: str | Path | None = None,
) -> JudgeRecordIndex:
    """Generate one verified semantic Judge Record per report and update a durable index."""

    validate_dataset_manifest(dataset_path)
    dataset = load_dataset_manifest(dataset_path)
    dataset_freeze_sha256 = optional_dataset_freeze_sha256(dataset_freeze_path, dataset_path)
    output_root = Path(output_dir).expanduser().resolve()
    if not output_root.is_dir():
        raise EvaluationInputError(f"Judge Record output directory does not exist: {output_root.as_posix()}")
    active_client, active_model, active_provider, runtime_settings = _resolve_runtime(
        judge_client,
        model=model,
        provider=provider,
    )
    rubric = load_public_rubric()
    rubric_sha256 = _rubric_sha256(rubric)
    inventory = _report_inventory(dataset)
    index_path = output_root / JUDGE_RECORD_INDEX_NAME
    target_paths = {
        report_id: output_root / _record_filename(loaded.report_sha256)
        for report_id, (_, _, loaded) in inventory.items()
    }
    if not resume and (index_path.exists() or any(path.exists() for path in target_paths.values())):
        raise EvaluationInputError("Judge Record output already exists; use resume only after reviewing the prior run")
    previous: LoadedJudgeRecordIndex | None = None
    if resume and index_path.exists():
        previous = validate_judge_record_index(
            index_path,
            dataset_path,
            require_complete=False,
            dataset_freeze_path=dataset_freeze_path,
        )
        if previous.index.dataset_freeze_sha256 != dataset_freeze_sha256:
            raise EvaluationInputError("resumed Judge Record index uses a different Dataset Freeze binding")
        if previous.index.model != active_model or previous.index.provider != active_provider:
            raise EvaluationInputError("resumed Judge Record index uses a different model or provider")

    entries: list[JudgeRecordIndexEntry] = []
    run_id = uuid4().hex
    started_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if previous is not None:
        run_id = previous.index.run_id or run_id
        started_at_utc = previous.index.started_at_utc or started_at_utc
    _write_index(
        index_path,
        _build_index(
            dataset,
            rubric,
            rubric_sha256,
            active_model,
            active_provider,
            inventory,
            entries,
            dataset_freeze_sha256=dataset_freeze_sha256,
            run_id=run_id,
            started_at_utc=started_at_utc,
            complete=False,
        ),
    )
    owned_client = None
    if active_client is None:
        from hy3_reproscope_mcp.hy3_client import Hy3Client

        if runtime_settings is None:
            raise EvaluationInputError("Hy3 runtime settings are unavailable")
        owned_client = Hy3Client(runtime_settings)
        active_client = owned_client
    try:
        for report_id, (group_id, entry, loaded) in inventory.items():
            record_path = target_paths[report_id]
            if record_path.exists():
                if not resume:
                    raise EvaluationInputError(f"Judge Record already exists: {record_path.as_posix()}")
                record = load_judge_record(record_path, loaded, rubric, rubric_sha256)
                if record.model != active_model or record.provider != active_provider:
                    raise EvaluationInputError(
                        f"resumed Judge Record for report '{report_id}' uses a different model or provider"
                    )
            else:
                record = await request_judge_record(
                    loaded,
                    rubric,
                    rubric_sha256,
                    active_client,
                    model=active_model,
                    provider=active_provider,
                )
                _write_record(record_path, record)
            entries.append(_index_entry(group_id, entry, loaded, record_path, record, output_root))
            _write_index(
                index_path,
                _build_index(
                    dataset,
                    rubric,
                    rubric_sha256,
                    active_model,
                    active_provider,
                    inventory,
                    entries,
                    dataset_freeze_sha256=dataset_freeze_sha256,
                    run_id=run_id,
                    started_at_utc=started_at_utc,
                    complete=False,
                ),
            )
    finally:
        if owned_client is not None:
            await owned_client.close()

    completed = _build_index(
        dataset,
        rubric,
        rubric_sha256,
        active_model,
        active_provider,
        inventory,
        entries,
        dataset_freeze_sha256=dataset_freeze_sha256,
        run_id=run_id,
        started_at_utc=started_at_utc,
        complete=True,
    )
    _write_index(index_path, completed)
    return completed


@contextmanager
def _exclusive_generation_lock(output_root: Path) -> Iterator[None]:
    lock_path = output_root / JUDGE_RECORD_LOCK_NAME
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise EvaluationInputError(
            "Judge Record generation is already active for this output directory; "
            f"if the prior process terminated, inspect and remove {lock_path.as_posix()} before retrying"
        ) from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    finally:
        os.close(descriptor)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def validate_judge_record_index(
    index_path: str | Path,
    dataset_path: str | Path,
    *,
    require_complete: bool = True,
    dataset_freeze_path: str | Path | None = None,
) -> LoadedJudgeRecordIndex:
    dataset = load_dataset_manifest(dataset_path)
    resolved_index = Path(index_path).expanduser().resolve()
    payload = _read_limited(resolved_index, MAX_JUDGE_RECORD_INDEX_BYTES, "Judge Record index")
    try:
        index = JudgeRecordIndex.model_validate_json(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid Judge Record index: {exc}") from exc
    if require_complete and not index.complete:
        raise EvaluationInputError("Judge Record index is incomplete")
    expected_identity = (
        dataset.manifest.dataset_id,
        dataset.manifest.dataset_version,
        dataset.manifest_sha256,
    )
    if (index.dataset_id, index.dataset_version, index.dataset_manifest_sha256) != expected_identity:
        raise EvaluationInputError("Judge Record index does not match the current Dataset Manifest")
    expected_freeze_sha256 = optional_dataset_freeze_sha256(dataset_freeze_path, dataset_path)
    if expected_freeze_sha256 is not None and index.dataset_freeze_sha256 != expected_freeze_sha256:
        raise EvaluationInputError("Judge Record index does not match the verified Dataset Freeze")
    rubric = load_public_rubric()
    rubric_sha256 = _rubric_sha256(rubric)
    if index.rubric_version != rubric.rubric_version or index.rubric_sha256 != rubric_sha256:
        raise EvaluationInputError("Judge Record index does not match the current public Rubric")
    inventory = _report_inventory(dataset)
    if index.expected_record_count != len(inventory):
        raise EvaluationInputError("Judge Record index expected count does not match the dataset")
    if index.complete and {record.report_id for record in index.records} != set(inventory):
        raise EvaluationInputError("complete Judge Record index report inventory does not match the dataset")

    root = resolved_index.parent.resolve()
    paths: dict[str, Path] = {}
    for index_entry in index.records:
        inventory_item = inventory.get(index_entry.report_id)
        if inventory_item is None:
            raise EvaluationInputError(f"Judge Record index references unknown report '{index_entry.report_id}'")
        group_id, entry, loaded = inventory_item
        if (
            index_entry.group_id != group_id
            or index_entry.case_id != loaded.case.case_id
            or index_entry.scenario is not loaded.case.scenario
            or index_entry.case_manifest_sha256 != loaded.manifest_sha256
            or index_entry.report_sha256 != entry.report_sha256
        ):
            raise EvaluationInputError(f"Judge Record index metadata mismatch for report '{entry.report_id}'")
        record_path = _resolve_index_path(root, index_entry.record_path)
        record_bytes = _read_limited(record_path, MAX_JUDGE_RECORD_BYTES, "Judge Record")
        if _sha256(record_bytes) != index_entry.record_file_sha256:
            raise EvaluationInputError(f"Judge Record file SHA-256 mismatch for report '{entry.report_id}'")
        record = load_judge_record(record_path, loaded, rubric, rubric_sha256)
        if record.model != index.model or record.provider != index.provider:
            raise EvaluationInputError(f"Judge Record model/provider mismatch for report '{entry.report_id}'")
        if record.request_sha256 != index_entry.request_sha256 or record.response_sha256 != index_entry.response_sha256:
            raise EvaluationInputError(f"Judge Record request/response mismatch for report '{entry.report_id}'")
        paths[entry.report_id] = record_path
    return LoadedJudgeRecordIndex(
        index=index,
        index_path=resolved_index,
        root=root,
        index_sha256=_sha256(payload),
        record_paths_by_report_id=paths,
    )


def _resolve_runtime(
    judge_client: StructuredJudgeClient | None,
    *,
    model: str | None,
    provider: str | None,
) -> tuple[StructuredJudgeClient | None, str, str, Settings | None]:
    if judge_client is not None:
        if not model or not provider:
            raise EvaluationInputError("injected Judge client requires explicit model and provider provenance")
        return judge_client, model, provider, None

    from hy3_reproscope_mcp.config import Settings

    settings = Settings()
    return (
        None,
        model or settings.hy3_model,
        provider or settings.resolved_api_provider(),
        settings,
    )


def _report_inventory(
    dataset: LoadedDatasetManifest,
) -> dict[str, tuple[str, DatasetReportEntry, LoadedEvaluationCase]]:
    inventory: dict[str, tuple[str, DatasetReportEntry, LoadedEvaluationCase]] = {}
    for group in dataset.manifest.groups:
        for entry in group.reports:
            loaded = load_evaluation_case(dataset.resolve(entry.case_path, "evaluation case"))
            inventory[entry.report_id] = (group.group_id, entry, loaded)
    return inventory


def _build_index(
    dataset: LoadedDatasetManifest,
    rubric: RubricDefinition,
    rubric_sha256: str,
    model: str,
    provider: str,
    inventory: dict[str, tuple[str, DatasetReportEntry, LoadedEvaluationCase]],
    entries: list[JudgeRecordIndexEntry],
    *,
    dataset_freeze_sha256: str | None,
    run_id: str,
    started_at_utc: str,
    complete: bool,
) -> JudgeRecordIndex:
    return JudgeRecordIndex(
        engine_version=__version__,
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        dataset_manifest_sha256=dataset.manifest_sha256,
        dataset_freeze_sha256=dataset_freeze_sha256,
        run_id=run_id,
        started_at_utc=started_at_utc,
        rubric_version=rubric.rubric_version,
        rubric_sha256=rubric_sha256,
        model=model,
        provider=provider,
        expected_record_count=len(inventory),
        record_count=len(entries),
        complete=complete,
        records=list(entries),
    )


def _index_entry(
    group_id: str,
    entry: DatasetReportEntry,
    loaded: LoadedEvaluationCase,
    record_path: Path,
    record: JudgeRecord,
    output_root: Path,
) -> JudgeRecordIndexEntry:
    return JudgeRecordIndexEntry(
        group_id=group_id,
        report_id=entry.report_id,
        case_id=loaded.case.case_id,
        scenario=loaded.case.scenario,
        case_manifest_sha256=loaded.manifest_sha256,
        report_sha256=loaded.report_sha256,
        record_path=record_path.relative_to(output_root).as_posix(),
        record_file_sha256=_sha256(record_path.read_bytes()),
        request_sha256=record.request_sha256,
        response_sha256=record.response_sha256,
    )


def _record_filename(report_sha256: str) -> str:
    return f"judge-{report_sha256[:16].lower()}.json"


def _write_record(path: Path, record: JudgeRecord) -> None:
    path.write_bytes((record.model_dump_json(indent=2) + "\n").encode("utf-8"))


def _write_index(path: Path, index: JudgeRecordIndex) -> None:
    path.write_bytes((index.model_dump_json(indent=2) + "\n").encode("utf-8"))


def _resolve_index_path(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise EvaluationInputError("Judge Record index paths must be relative")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise EvaluationInputError(f"Judge Record index path escapes its root: {raw_path}")
    return resolved


def _read_limited(path: Path, maximum_bytes: int, label: str) -> bytes:
    if not path.is_file():
        raise EvaluationInputError(f"{label} does not exist or is not a file: {path.as_posix()}")
    if path.stat().st_size > maximum_bytes:
        raise EvaluationInputError(f"{label} exceeds {maximum_bytes} bytes: {path.as_posix()}")
    return path.read_bytes()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()
