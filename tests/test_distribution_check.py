from __future__ import annotations

import pytest

from scripts.check_distribution import _validate_public_mcp_config


def _config(*, command: str = "C:/path/to/ReproEval/.venv/Scripts/python.exe", api_key: str | None = None):
    env = {
        "HY3_BASE_URL": "https://tokenhub.tencentmaas.com/v1",
        "HY3_API_KEY": api_key or "YOUR_HY3_API_KEY",
        "REPROSCOPE_ALLOWED_ROOTS": "C:/path/to/ReproEval",
    }
    return {"mcpServers": {"hy3-reproeval": {"command": command, "args": ["-m", "hy3_reproscope_mcp"], "env": env}}}


def test_public_mcp_template_is_accepted() -> None:
    _validate_public_mcp_config(_config())


@pytest.mark.parametrize(
    ("command", "api_key"),
    [
        ("E:/project/.venv/Scripts/python.exe", "YOUR_HY3_API_KEY"),
        ("C:/path/to/ReproEval/.reproeval/workbuddy-mcp.ps1", "YOUR_HY3_API_KEY"),
        ("C:/path/to/ReproEval/.venv/Scripts/python.exe", "secret-value"),
    ],
)
def test_private_mcp_configuration_is_rejected(command: str, api_key: str) -> None:
    with pytest.raises(ValueError):
        _validate_public_mcp_config(_config(command=command, api_key=api_key))


def test_mcp_configuration_without_api_key_placeholder_is_rejected() -> None:
    payload = _config()
    del payload["mcpServers"]["hy3-reproeval"]["env"]["HY3_API_KEY"]

    with pytest.raises(ValueError, match="HY3_API_KEY placeholder"):
        _validate_public_mcp_config(payload)
