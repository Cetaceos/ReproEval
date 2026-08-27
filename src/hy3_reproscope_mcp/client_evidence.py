"""Validation for credential-free MCP client acceptance evidence.

GUI screenshots are useful evidence, but they are not a substitute for the
server-owned run manifest and artifact hashes.  This module validates the
small JSON record captured alongside a screenshot or recording without
accepting secrets, local paths, or an incomplete tool list.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal

from pydantic import Field, model_validator

from . import __version__
from .models import SCHEMA_VERSION, StrictModel

EXPECTED_CLIENT_TOOLS = (
    "reproscope_extract_claims",
    "reproscope_compare_results",
    "reproscope_score_paper",
    "reproscope_build_evidence_graph",
    "reproscope_render_report",
    "reproscope_extract_solution_profile",
    "reproscope_assess_transfer",
    "reproscope_build_transfer_graph",
    "reproscope_render_transfer_report",
    "reproscope_audit_repository",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RELATIVE_PATH = re.compile(r"^(?![A-Za-z]:)(?!/)(?!\\)(?!.*(?:^|/|\\)\.\.(?:/|\\|$)).+$")
_SECRET_MARKERS = re.compile(
    r"(?:api[_ -]?key|authorization\s*:\s*bearer|access[_ -]?token|secret|password|private[_ -]?key|\.env)",
    re.IGNORECASE,
)


class ClientEvidenceArtifact(StrictModel):
    run_id: str = Field(min_length=1, max_length=128)
    artifact_type: str = Field(min_length=1, max_length=100)
    relative_path: str = Field(min_length=1, max_length=500)
    content_hash: str = Field(pattern=_SHA256.pattern)
    payload_hash: str = Field(pattern=_SHA256.pattern)

    @model_validator(mode="after")
    def validate_relative_path(self) -> ClientEvidenceArtifact:
        if not _RELATIVE_PATH.fullmatch(self.relative_path):
            raise ValueError("artifact relative_path must be repository/workspace relative")
        return self


class ClientEvidenceCall(StrictModel):
    tool_name: str = Field(min_length=1, max_length=100)
    run_id: str = Field(min_length=1, max_length=128)
    status: Literal["completed"]
    artifacts: list[ClientEvidenceArtifact] = Field(min_length=1)
    graph_validated: bool | None = None

    @model_validator(mode="after")
    def validate_graph_marker(self) -> ClientEvidenceCall:
        if (
            self.tool_name
            in {
                "reproscope_build_evidence_graph",
                "reproscope_build_transfer_graph",
            }
            and self.graph_validated is not True
        ):
            raise ValueError(f"{self.tool_name} evidence must include graph_validated=true")
        return self


class ClientValidationEvidence(StrictModel):
    evidence_version: Literal["1"] = "1"
    client: Literal["codebuddy", "visual_studio_code"]
    client_version: str = Field(min_length=1, max_length=100)
    server_version: Literal[__version__] = __version__
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    operating_system: str = Field(min_length=1, max_length=100)
    python_version: str = Field(min_length=1, max_length=100)
    tool_names: list[str] = Field(default_factory=list)
    calls: list[ClientEvidenceCall] = Field(min_length=1)
    screenshot_ref: str | None = Field(default=None, max_length=500)
    recording_ref: str | None = Field(default=None, max_length=500)
    secrets_redacted: Literal[True] = True

    @model_validator(mode="after")
    def validate_evidence(self) -> ClientValidationEvidence:
        if tuple(self.tool_names) != EXPECTED_CLIENT_TOOLS:
            if set(self.tool_names) != set(EXPECTED_CLIENT_TOOLS):
                raise ValueError("tool_names must contain exactly the ten 0.15.0 ReproScope tools")
            raise ValueError("tool_names must use the canonical order from the ten-tool acceptance prompt")
        known_tools = set(EXPECTED_CLIENT_TOOLS)
        for call in self.calls:
            if call.tool_name not in known_tools:
                raise ValueError(f"unknown client tool in evidence: {call.tool_name}")
            if any(artifact.run_id != call.run_id for artifact in call.artifacts):
                raise ValueError("each artifact must belong to its call run_id")
        for reference in (self.screenshot_ref, self.recording_ref):
            if reference is not None and not _RELATIVE_PATH.fullmatch(reference):
                raise ValueError("screenshot_ref and recording_ref must be relative paths")
        return self


def validate_client_evidence(payload: Mapping[str, object]) -> ClientValidationEvidence:
    """Validate a sanitized evidence record and reject secret-like content."""

    for key, value in _walk_strings(payload):
        if _SECRET_MARKERS.search(value):
            raise ValueError(f"client evidence contains a forbidden secret marker at {key}")
    return ClientValidationEvidence.model_validate(payload)


def _walk_strings(value: object, path: str = "$"):
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield from _walk_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        yield path, value


__all__ = [
    "EXPECTED_CLIENT_TOOLS",
    "ClientEvidenceArtifact",
    "ClientEvidenceCall",
    "ClientValidationEvidence",
    "validate_client_evidence",
]
