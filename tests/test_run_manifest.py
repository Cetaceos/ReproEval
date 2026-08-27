from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.errors import PathPolicyError
from hy3_reproscope_mcp.models import RunManifest, RunStatus
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import extract_claims
from hy3_reproscope_mcp.workspace import Workspace


class FakeHy3Client:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    async def complete_structured(
        self,
        messages: Sequence[Mapping[str, str]],
        response_model: type[BaseModel],
        **_: Any,
    ) -> BaseModel:
        if self.error is not None:
            raise self.error
        return response_model.model_validate(
            {
                "run_id": "model_run",
                "summary": "One claim was extracted.",
            }
        )


def _settings(tmp_path) -> Settings:
    return Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(tmp_path),
        REPROSCOPE_WORKSPACE=tmp_path / "artifacts",
    )


def _read_only_manifest(settings: Settings) -> RunManifest:
    manifest_paths = list(settings.reproscope_workspace.glob("claims_*/run_manifest.json"))
    assert len(manifest_paths) == 1
    payload = Workspace(settings).read_json_artifact(str(manifest_paths[0]))
    return RunManifest.model_validate(payload)


@pytest.mark.asyncio
async def test_successful_tool_run_persists_completed_manifest(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    paper_path.write_text("Reported accuracy: 0.91", encoding="utf-8")
    settings = _settings(tmp_path)

    result = await extract_claims(
        AppContext(settings=settings, hy3_client=FakeHy3Client()),
        paper_paths=[str(paper_path)],
        focus=None,
    )

    manifest = _read_only_manifest(settings)
    assert manifest.run_id == result.run_id
    assert manifest.tool_name == "reproscope_extract_claims"
    assert manifest.status is RunStatus.COMPLETED
    assert [event.status for event in manifest.status_history] == [
        RunStatus.CREATED,
        RunStatus.RUNNING,
        RunStatus.COMPLETED,
    ]
    assert manifest.sources == result.sources
    assert manifest.artifacts == result.artifacts[:-1]
    assert result.artifacts[-1].relative_path == f"{result.run_id}/run_manifest.json"
    assert manifest.error_code is None
    assert manifest.error_message is None
    snapshot = Workspace(settings).inspect_run(result.run_id)
    assert snapshot.recovery_action == "reuse_completed"
    assert snapshot.resume_from == "completed_artifacts"
    assert snapshot.reusable_artifacts == manifest.artifacts


@pytest.mark.asyncio
async def test_domain_failure_persists_public_error_code_and_reraises(tmp_path) -> None:
    settings = _settings(tmp_path)

    with pytest.raises(PathPolicyError):
        await extract_claims(
            AppContext(settings=settings, hy3_client=FakeHy3Client()),
            paper_paths=[str(tmp_path / "missing.md")],
            focus=None,
        )

    manifest = _read_only_manifest(settings)
    assert manifest.status is RunStatus.FAILED
    assert [event.status for event in manifest.status_history] == [
        RunStatus.CREATED,
        RunStatus.RUNNING,
        RunStatus.FAILED,
    ]
    assert manifest.error_code == "PATH_POLICY_ERROR"
    assert manifest.error_message is not None
    assert "missing.md" in manifest.error_message
    snapshot = Workspace(settings).inspect_run(manifest.run_id)
    assert snapshot.recovery_action == "restart_from_recorded_inputs"
    assert snapshot.resume_from == "recorded_inputs"
    assert snapshot.error_code == "PATH_POLICY_ERROR"


@pytest.mark.asyncio
async def test_unexpected_failure_is_redacted_in_manifest(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    paper_path.write_text("Reported accuracy: 0.91", encoding="utf-8")
    settings = _settings(tmp_path)

    with pytest.raises(RuntimeError, match="private diagnostic"):
        await extract_claims(
            AppContext(
                settings=settings,
                hy3_client=FakeHy3Client(error=RuntimeError("private diagnostic")),
            ),
            paper_paths=[str(paper_path)],
            focus=None,
        )

    manifest = _read_only_manifest(settings)
    assert manifest.status is RunStatus.FAILED
    assert manifest.error_code == "INTERNAL_ERROR"
    assert manifest.error_message == "The tool failed unexpectedly."
    assert "private diagnostic" not in manifest.model_dump_json()
