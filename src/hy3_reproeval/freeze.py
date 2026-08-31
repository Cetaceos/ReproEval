"""Tamper-evident Dataset Freeze artifacts for controlled experiments."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import __version__
from .dataset import (
    DatasetSplit,
    LoadedDatasetManifest,
    load_dataset_manifest,
    validate_dataset_manifest,
)
from .errors import EvaluationInputError
from .evaluator import _rubric_sha256
from .models import StrictModel
from .rubric import load_public_rubric
from .validators import load_evaluation_case

MAX_DATASET_FREEZE_BYTES = 8 * 1024 * 1024
P0_SOURCE_GROUP_TARGET = 12
P0_ADVERSARIAL_REPORT_TARGET = 8


class FrozenFileRole(StrEnum):
    DATASET_MANIFEST = "dataset_manifest"
    EVALUATION_CASE = "evaluation_case"
    REPORT = "report"
    EVIDENCE_ARTIFACT = "evidence_artifact"
    MUTATION_MANIFEST = "mutation_manifest"
    JUDGE_RECORD = "judge_record"


class FrozenFile(StrictModel):
    path: str = Field(min_length=1)
    roles: list[FrozenFileRole] = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[A-F0-9]{64}$")

    @model_validator(mode="after")
    def validate_roles(self) -> FrozenFile:
        if len(self.roles) != len(set(self.roles)):
            raise ValueError("frozen file roles must be unique")
        return self


class DatasetFreezeReadiness(StrictModel):
    source_group_count: int = Field(ge=1)
    required_source_group_count: int = Field(default=P0_SOURCE_GROUP_TARGET, ge=1)
    validation_group_count: int = Field(ge=0)
    test_group_count: int = Field(ge=0)
    adversarial_report_count: int = Field(ge=0)
    required_adversarial_report_count: int = Field(default=P0_ADVERSARIAL_REPORT_TARGET, ge=1)
    source_group_target_met: bool
    validation_split_present: bool
    test_split_present: bool
    adversarial_target_met: bool
    meets_p0_dataset_targets: bool
    unmet_requirements: list[str] = Field(default_factory=list)


class DatasetFreezeBody(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    rubric_version: str
    rubric_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    group_count: int = Field(ge=1)
    report_count: int = Field(ge=3)
    file_count: int = Field(ge=1)
    files: list[FrozenFile] = Field(min_length=1)
    readiness: DatasetFreezeReadiness
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_file_inventory(self) -> DatasetFreezeBody:
        if self.file_count != len(self.files):
            raise ValueError("Dataset Freeze file_count must match its file inventory")
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Dataset Freeze file paths must be unique")
        if paths != sorted(paths):
            raise ValueError("Dataset Freeze files must use canonical path order")
        return self


class DatasetFreeze(DatasetFreezeBody):
    freeze_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")


class DatasetFreezeVerification(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    engine_version: str
    freeze_engine_version: str
    dataset_id: str
    dataset_version: str
    dataset_manifest_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    freeze_sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    valid: Literal[True] = True
    file_count: int = Field(ge=1)
    readiness: DatasetFreezeReadiness
    warnings: list[str] = Field(default_factory=list)


def create_dataset_freeze(
    manifest_path: str | Path,
    *,
    require_p0_ready: bool = False,
) -> DatasetFreeze:
    """Validate and fingerprint every registered Dataset input."""

    validation = validate_dataset_manifest(manifest_path)
    dataset = load_dataset_manifest(manifest_path)
    rubric = load_public_rubric()
    files = _collect_registered_files(dataset)
    readiness = _readiness(validation.group_count, validation.split_counts, validation.adversarial_report_count)
    if require_p0_ready and not readiness.meets_p0_dataset_targets:
        raise EvaluationInputError(
            "dataset does not meet P0 freeze requirements: " + ", ".join(readiness.unmet_requirements)
        )
    warnings = list(validation.warnings)
    warnings.append(
        "Dataset Freeze binds registered inputs only; it does not establish Judge, annotation, "
        "agreement, consensus, or held-out performance readiness."
    )
    body = DatasetFreezeBody(
        engine_version=__version__,
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.manifest.dataset_version,
        dataset_manifest_sha256=dataset.manifest_sha256,
        rubric_version=rubric.rubric_version,
        rubric_sha256=_rubric_sha256(rubric),
        group_count=validation.group_count,
        report_count=validation.report_count,
        file_count=len(files),
        files=files,
        readiness=readiness,
        warnings=warnings,
    )
    return DatasetFreeze(
        **body.model_dump(),
        freeze_sha256=_canonical_sha256(body.model_dump(mode="json")),
    )


def verify_dataset_freeze(
    freeze_path: str | Path,
    manifest_path: str | Path,
) -> DatasetFreezeVerification:
    """Verify a stored freeze against its self-digest and current Dataset bytes."""

    resolved_freeze = Path(freeze_path).expanduser().resolve()
    payload = _read_limited(resolved_freeze, MAX_DATASET_FREEZE_BYTES, "Dataset Freeze")
    try:
        freeze = DatasetFreeze.model_validate_json(payload)
    except ValueError as exc:
        raise EvaluationInputError(f"invalid Dataset Freeze: {exc}") from exc
    body = DatasetFreezeBody.model_validate(freeze.model_dump(exclude={"freeze_sha256"}))
    if _canonical_sha256(body.model_dump(mode="json")) != freeze.freeze_sha256:
        raise EvaluationInputError("Dataset Freeze SHA-256 does not match its canonical payload")

    current = create_dataset_freeze(manifest_path)
    _verify_identity(freeze, current)
    if freeze.files != current.files:
        raise EvaluationInputError("Dataset Freeze file inventory does not match current registered inputs")
    if freeze.readiness != current.readiness:
        raise EvaluationInputError("Dataset Freeze readiness no longer matches the current Dataset")
    warnings = list(freeze.warnings)
    if freeze.engine_version != __version__:
        warnings.append(
            f"Freeze was created by engine {freeze.engine_version} and verified by {__version__}."
        )
    return DatasetFreezeVerification(
        engine_version=__version__,
        freeze_engine_version=freeze.engine_version,
        dataset_id=freeze.dataset_id,
        dataset_version=freeze.dataset_version,
        dataset_manifest_sha256=freeze.dataset_manifest_sha256,
        freeze_sha256=freeze.freeze_sha256,
        file_count=freeze.file_count,
        readiness=freeze.readiness,
        warnings=warnings,
    )


def _collect_registered_files(dataset: LoadedDatasetManifest) -> list[FrozenFile]:
    root = dataset.root
    inventory: dict[str, tuple[Path, set[FrozenFileRole]]] = {}

    def register(path: Path, role: FrozenFileRole) -> None:
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise EvaluationInputError(f"frozen file escapes the Dataset root: {resolved.as_posix()}")
        relative = resolved.relative_to(root).as_posix()
        if relative in inventory:
            inventory[relative][1].add(role)
        else:
            inventory[relative] = (resolved, {role})

    register(dataset.manifest_path, FrozenFileRole.DATASET_MANIFEST)
    for group in dataset.manifest.groups:
        for entry in group.reports:
            case_path = dataset.resolve(entry.case_path, "evaluation case")
            loaded = load_evaluation_case(case_path)
            register(case_path, FrozenFileRole.EVALUATION_CASE)
            register(loaded.report_path, FrozenFileRole.REPORT)
            for artifact in loaded.case.artifacts:
                artifact_path = (loaded.root / artifact.path).resolve()
                if not artifact_path.is_relative_to(loaded.root):
                    raise EvaluationInputError(
                        f"evidence artifact path escapes its Case root: {artifact.path}"
                    )
                register(artifact_path, FrozenFileRole.EVIDENCE_ARTIFACT)
            if entry.mutation_manifest_path is not None:
                register(
                    dataset.resolve(entry.mutation_manifest_path, "mutation manifest"),
                    FrozenFileRole.MUTATION_MANIFEST,
                )
            if entry.judge_record_path is not None:
                register(
                    dataset.resolve(entry.judge_record_path, "Judge record"),
                    FrozenFileRole.JUDGE_RECORD,
                )
    return [
        FrozenFile(
            path=relative,
            roles=sorted(roles, key=str),
            size_bytes=path.stat().st_size,
            sha256=_file_sha256(path),
        )
        for relative, (path, roles) in sorted(inventory.items())
    ]


def _readiness(
    group_count: int,
    split_counts: dict[DatasetSplit, int],
    adversarial_report_count: int,
) -> DatasetFreezeReadiness:
    source_group_target_met = group_count >= P0_SOURCE_GROUP_TARGET
    validation_present = split_counts.get(DatasetSplit.VALIDATION, 0) > 0
    test_present = split_counts.get(DatasetSplit.TEST, 0) > 0
    adversarial_target_met = adversarial_report_count >= P0_ADVERSARIAL_REPORT_TARGET
    unmet: list[str] = []
    if not source_group_target_met:
        unmet.append(f"at least {P0_SOURCE_GROUP_TARGET} source groups")
    if not validation_present:
        unmet.append("a validation split")
    if not test_present:
        unmet.append("a test split")
    if not adversarial_target_met:
        unmet.append(f"at least {P0_ADVERSARIAL_REPORT_TARGET} adversarial reports")
    return DatasetFreezeReadiness(
        source_group_count=group_count,
        validation_group_count=split_counts.get(DatasetSplit.VALIDATION, 0),
        test_group_count=split_counts.get(DatasetSplit.TEST, 0),
        adversarial_report_count=adversarial_report_count,
        source_group_target_met=source_group_target_met,
        validation_split_present=validation_present,
        test_split_present=test_present,
        adversarial_target_met=adversarial_target_met,
        meets_p0_dataset_targets=not unmet,
        unmet_requirements=unmet,
    )


def _verify_identity(freeze: DatasetFreeze, current: DatasetFreeze) -> None:
    frozen_identity = (
        freeze.dataset_id,
        freeze.dataset_version,
        freeze.dataset_manifest_sha256,
        freeze.rubric_version,
        freeze.rubric_sha256,
        freeze.group_count,
        freeze.report_count,
        freeze.file_count,
    )
    current_identity = (
        current.dataset_id,
        current.dataset_version,
        current.dataset_manifest_sha256,
        current.rubric_version,
        current.rubric_sha256,
        current.group_count,
        current.report_count,
        current.file_count,
    )
    if frozen_identity != current_identity:
        raise EvaluationInputError("Dataset Freeze identity does not match the current Dataset and Rubric")


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        raise EvaluationInputError(f"frozen input does not exist or is not a file: {path.as_posix()}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _read_limited(path: Path, maximum_bytes: int, label: str) -> bytes:
    if not path.is_file():
        raise EvaluationInputError(f"{label} does not exist or is not a file: {path.as_posix()}")
    if path.stat().st_size > maximum_bytes:
        raise EvaluationInputError(f"{label} exceeds {maximum_bytes} bytes: {path.as_posix()}")
    return path.read_bytes()


def _canonical_sha256(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest().upper()
