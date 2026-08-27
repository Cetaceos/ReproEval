from __future__ import annotations

import sys

import pytest

from hy3_reproscope_mcp.execution import (
    ControlledExecutionDenied,
    ControlledExecutionPolicy,
    preflight_third_party_execution,
    run_controlled_command,
)


def test_controlled_execution_requires_explicit_opt_in(tmp_path) -> None:
    script = tmp_path / "entry.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    with pytest.raises(ControlledExecutionDenied, match="opt-in"):
        run_controlled_command(
            [sys.executable, str(script)],
            allowed_root=tmp_path,
            policy=ControlledExecutionPolicy(),
        )


def test_controlled_execution_requires_an_external_sandbox(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REPROSCOPE_ALLOW_CONTROLLED_EXECUTION", "1")
    script = tmp_path / "entry.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    with pytest.raises(ControlledExecutionDenied, match="external sandbox"):
        run_controlled_command(
            [sys.executable, str(script)],
            allowed_root=tmp_path,
            policy=ControlledExecutionPolicy(),
        )


@pytest.mark.parametrize(
    "command",
    [
        "python -c print('unsafe')",
        ["python", "-m", "module"],
        ["python", "-", "input"],
        ["python", "entry.py", "..\\outside.txt"],
    ],
)
def test_controlled_execution_rejects_shell_or_escape_commands(tmp_path, command, monkeypatch) -> None:
    monkeypatch.setenv("REPROSCOPE_ALLOW_CONTROLLED_EXECUTION", "1")
    script = tmp_path / "entry.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    with pytest.raises(ControlledExecutionDenied):
        run_controlled_command(
            command,
            allowed_root=tmp_path,
            policy=ControlledExecutionPolicy(sandbox="bwrap"),
        )


def test_controlled_execution_rejects_secret_environment_and_outside_cwd(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("REPROSCOPE_ALLOW_CONTROLLED_EXECUTION", "1")
    script = tmp_path / "entry.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    outside = tmp_path.parent

    with pytest.raises(ControlledExecutionDenied, match="environment variable"):
        run_controlled_command(
            ["python", str(script)],
            allowed_root=tmp_path,
            policy=ControlledExecutionPolicy(sandbox="bwrap"),
            env={"API_KEY": "secret"},
        )
    with pytest.raises(ControlledExecutionDenied, match="cwd"):
        run_controlled_command(
            ["python", str(script)],
            allowed_root=tmp_path,
            cwd=outside,
            policy=ControlledExecutionPolicy(sandbox="bwrap"),
        )


def test_preflight_remains_default_deny_and_hashes_only_the_command() -> None:
    result = preflight_third_party_execution("python entry.py", allowed_root="repo")

    assert result.status == "denied"
    assert result.requested is True
    assert result.executed is False
    assert result.network_access == "disabled"
    assert result.credentials_available is False
    assert result.command_hash is not None
