"""Structured models for deterministic repository reproducibility audits."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from .models import StrictModel, ToolResultBase


class RepositoryFileKind(StrEnum):
    PROJECT_MANIFEST = "project_manifest"
    DEPENDENCY_SPEC = "dependency_spec"
    LOCKFILE = "lockfile"
    PYTHON_SOURCE = "python_source"
    DOCUMENTATION = "documentation"
    ENVIRONMENT_EXAMPLE = "environment_example"
    TEST_CONFIGURATION = "test_configuration"
    OTHER_CONFIGURATION = "other_configuration"


class RepositoryGapSeverity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RepositoryInspectedFile(StrictModel):
    source_id: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    kind: RepositoryFileKind
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    parsed: bool


class RepositoryDependency(StrictModel):
    name: str = Field(min_length=1)
    constraint: str | None = None
    group: str = Field(default="runtime", min_length=1)
    source_path: str = Field(min_length=1)
    pinned: bool = False


class RepositoryEntrypoint(StrictModel):
    name: str = Field(min_length=1)
    target: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    source_path: str = Field(min_length=1)


class EnvironmentVariableSignal(StrictModel):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    source_paths: list[str] = Field(min_length=1)


class RepositoryAuditGap(StrictModel):
    code: str = Field(min_length=1)
    severity: RepositoryGapSeverity
    message: str = Field(min_length=1)
    remediation: str = Field(min_length=1)


class ThirdPartyExecutionPreflight(StrictModel):
    """A non-executing record for a future third-party execution request."""

    status: Literal["not_requested", "denied"] = "not_requested"
    requested: bool = False
    command_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    allowed_root: str | None = None
    sandbox_required: bool = True
    network_access: Literal["disabled"] = "disabled"
    credentials_available: Literal[False] = False
    executed: Literal[False] = False
    reason: str = (
        "Third-party code execution is disabled in ReproScope 0.15.0; use an independently reviewed external "
        "sandbox adapter before requesting execution."
    )


class RepositoryReadinessMetrics(StrictModel):
    metadata_file_count: int = Field(ge=0)
    python_file_count: int = Field(ge=0)
    dependency_count: int = Field(ge=0)
    pinned_dependency_ratio: float = Field(ge=0, le=1)
    has_lockfile: bool
    has_download_hashes: bool = False
    download_hash_count: int = Field(default=0, ge=0)
    download_hash_coverage: float | None = Field(default=None, ge=0, le=1)
    download_hashes_complete: bool = False
    has_python_requirement: bool
    has_install_instructions: bool
    has_test_configuration: bool
    has_test_instructions: bool
    has_declared_entrypoint: bool
    environment_example_present: bool
    scan_truncated: bool


class RepositoryAuditResult(ToolResultBase):
    repository_root: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    package_managers: list[str] = Field(default_factory=list)
    python_requirement: str | None = None
    dependencies: list[RepositoryDependency] = Field(default_factory=list)
    entrypoints: list[RepositoryEntrypoint] = Field(default_factory=list)
    environment_variables: list[EnvironmentVariableSignal] = Field(default_factory=list)
    install_commands: list[str] = Field(default_factory=list)
    test_commands: list[str] = Field(default_factory=list)
    inspected_files: list[RepositoryInspectedFile] = Field(default_factory=list)
    gaps: list[RepositoryAuditGap] = Field(default_factory=list)
    metrics: RepositoryReadinessMetrics
    execution_policy: Literal["static_read_only"] = "static_read_only"
    execution_preflight: ThirdPartyExecutionPreflight = Field(default_factory=ThirdPartyExecutionPreflight)
    executed_repository_code: Literal[False] = False
