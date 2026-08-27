from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import run_live_wheel_validation
from scripts.live_validation_security import LiveValidationSecurityError, enforce_live_summary_security
from scripts.run_live_wheel_validation import (
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    _command_timeout_seconds,
    _execute,
    _isolated_live_script_command,
    _resolve_live_workspace,
)


def _valid_summary() -> dict[str, object]:
    return {
        "status": "passed",
        "tools": {
            "paper": {
                "run_id": "paper_abc",
                "artifacts": [
                    {
                        "artifact_type": "json",
                        "content_hash": "a" * 64,
                        "payload_hash": "b" * 64,
                    }
                ],
                "run_manifest": {"status": "completed"},
            },
            "audit_repository": {
                "execution_preflight": {
                    "status": "denied",
                    "executed": False,
                    "credentials_available": False,
                }
            },
        },
    }


def test_live_summary_security_accepts_redacted_completed_summary() -> None:
    enforce_live_summary_security(_valid_summary())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda summary: summary["tools"]["paper"]["artifacts"][0].update(api_key="secret"),
        lambda summary: summary["tools"]["audit_repository"]["execution_preflight"].update(executed=True),
        lambda summary: summary["tools"]["audit_repository"]["execution_preflight"].update(credentials_available=True),
        lambda summary: summary["tools"]["paper"]["artifacts"][0].update(content_hash="not-a-hash"),
        lambda summary: summary["tools"]["paper"]["artifacts"][0].update(artifact_type="binary"),
        lambda summary: summary["tools"]["paper"]["run_manifest"].update(status="failed"),
        lambda summary: summary["tools"]["paper"]["artifacts"][0].pop("payload_hash"),
        lambda summary: summary.update(status="failed"),
    ],
)
def test_live_summary_security_fails_closed(mutation) -> None:
    summary = _valid_summary()
    mutation(summary)

    with pytest.raises(LiveValidationSecurityError):
        enforce_live_summary_security(summary)


def test_wheel_live_execution_requires_second_explicit_opt_in(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("REPROSCOPE_RUN_LIVE", "1")
    monkeypatch.setenv("HY3_API_KEY", "placeholder")
    monkeypatch.delenv("REPROSCOPE_ALLOW_CONTROLLED_EXECUTION", raising=False)

    with pytest.raises(RuntimeError, match="default is deny"):
        _execute(tmp_path / "candidate.whl", {"status": "ready_for_live"})


def test_wheel_live_execution_rejects_wheels_outside_dist(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("REPROSCOPE_RUN_LIVE", "1")
    monkeypatch.setenv("REPROSCOPE_ALLOW_CONTROLLED_EXECUTION", "1")
    monkeypatch.setenv("HY3_API_KEY", "placeholder")

    with pytest.raises(RuntimeError, match="under the project dist directory"):
        _execute(tmp_path / "candidate.whl", {"status": "ready_for_live"})


@pytest.mark.parametrize("script", ["not_allowlisted.py", "../run_live_validation.py", "scripts/other.py"])
def test_isolated_live_script_command_rejects_non_allowlisted_paths(script: str) -> None:
    with pytest.raises(RuntimeError, match="not allowlisted"):
        _isolated_live_script_command(Path(sys.executable), script)


def test_isolated_live_script_command_rejects_allowlisted_path_escape(monkeypatch, tmp_path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "escape.py").write_text("raise AssertionError\n", encoding="utf-8")
    monkeypatch.setattr(run_live_wheel_validation, "LIVE_SCRIPTS", ("../escape.py",))

    with pytest.raises(RuntimeError, match="regular allowlisted file"):
        _isolated_live_script_command(Path(sys.executable), "../escape.py", project_root=tmp_path)


def test_isolated_live_script_command_bootstraps_sibling_import_under_isolated_mode(monkeypatch, tmp_path) -> None:
    scripts_root = tmp_path / "scripts"
    scripts_root.mkdir()
    (scripts_root / "shared.py").write_text("VALUE = 'bootstrap-ok'\n", encoding="utf-8")
    (scripts_root / "probe.py").write_text("from shared import VALUE\nprint(VALUE)\n", encoding="utf-8")
    monkeypatch.setattr(run_live_wheel_validation, "LIVE_SCRIPTS", ("probe.py",))

    command = _isolated_live_script_command(Path(sys.executable), "probe.py", project_root=tmp_path)
    completed = subprocess.run(
        command,
        cwd=tmp_path,
        env={key: value for key, value in os.environ.items() if key in {"SYSTEMROOT", "WINDIR"}},
        check=True,
        capture_output=True,
        text=True,
    )

    assert command[1:3] == ["-I", "-c"]
    assert completed.stdout.strip() == "bootstrap-ok"


def test_live_command_timeout_has_bounded_default_and_override() -> None:
    assert _command_timeout_seconds({}) == DEFAULT_COMMAND_TIMEOUT_SECONDS == 900
    assert _command_timeout_seconds({"REPROSCOPE_LIVE_COMMAND_TIMEOUT_SECONDS": "1200"}) == 1200


def test_live_command_timeout_rejects_invalid_or_unbounded_values() -> None:
    for value in ("not-an-integer", "29", "1801"):
        with pytest.raises(RuntimeError, match="REPROSCOPE_LIVE_COMMAND_TIMEOUT_SECONDS"):
            _command_timeout_seconds({"REPROSCOPE_LIVE_COMMAND_TIMEOUT_SECONDS": value})


def test_retained_live_workspace_must_be_a_child_of_private_project_root(tmp_path) -> None:
    project_root = tmp_path / "project"
    retained = project_root / ".hy3-reproscope" / "final-live"

    resolved, is_retained = _resolve_live_workspace(retained, tmp_path / "temporary", project_root=project_root)

    assert resolved == retained.resolve()
    assert is_retained is True


def test_retained_live_workspace_rejects_root_and_path_escape(tmp_path) -> None:
    project_root = tmp_path / "project"
    private_root = project_root / ".hy3-reproscope"
    for workspace in (private_root, project_root / "published", private_root / ".." / "escaped"):
        with pytest.raises(RuntimeError, match="retained live workspace"):
            _resolve_live_workspace(workspace, tmp_path / "temporary", project_root=project_root)


@pytest.mark.parametrize("path", ["reports/foo/..", "%2e%2e/private.json", "reports\nprivate.json"])
def test_live_summary_security_rejects_normalized_private_paths(path: str) -> None:
    summary = _valid_summary()
    summary["tools"]["paper"]["report_path"] = path

    with pytest.raises(LiveValidationSecurityError):
        enforce_live_summary_security(summary)


def test_live_summary_security_rejects_sequence_cycles() -> None:
    summary = _valid_summary()
    cycle: list[object] = []
    cycle.append(cycle)
    summary["cycle"] = cycle

    with pytest.raises(LiveValidationSecurityError, match="Cyclic"):
        enforce_live_summary_security(summary)


def test_live_summary_security_rejects_empty_artifact_lists() -> None:
    summary = _valid_summary()
    summary["tools"]["paper"]["artifacts"] = []

    with pytest.raises(LiveValidationSecurityError, match="must not be empty"):
        enforce_live_summary_security(summary)


def test_live_summary_security_accepts_markdown_without_payload_hash() -> None:
    summary = _valid_summary()
    artifact = summary["tools"]["paper"]["artifacts"][0]
    artifact.update(artifact_type="markdown", payload_hash=None)

    enforce_live_summary_security(summary)


def test_live_summary_security_rejects_markdown_payload_hash_claim() -> None:
    summary = _valid_summary()
    artifact = summary["tools"]["paper"]["artifacts"][0]
    artifact.update(artifact_type="markdown")

    with pytest.raises(LiveValidationSecurityError, match="must not claim a payload_hash"):
        enforce_live_summary_security(summary)
