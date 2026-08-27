from __future__ import annotations

import pytest

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.errors import MissingCredentialError


def test_settings_use_documented_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "HY3_BASE_URL",
        "HY3_API_KEY",
        "HY3_MODEL",
        "HY3_API_PROVIDER",
        "HY3_REASONING_EFFORT",
        "HY3_TEMPERATURE",
        "HY3_TOP_P",
        "HY3_TIMEOUT_SECONDS",
        "HY3_MAX_RETRIES",
        "HY3_MAX_TOKENS",
        "REPROSCOPE_WORKSPACE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.hy3_base_url == "http://127.0.0.1:8000/v1"
    assert settings.hy3_model == "hy3"
    assert settings.hy3_api_provider == "auto"
    assert settings.resolved_api_provider() == "self_hosted"
    assert settings.hy3_reasoning_effort == "high"
    assert settings.hy3_temperature == 0.9
    assert settings.hy3_top_p == 1.0
    assert settings.hy3_max_retries == 2
    assert settings.hy3_max_tokens == 16000
    assert str(settings.reproscope_workspace) == ".hy3-reproscope"


def test_settings_read_environment_and_hide_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HY3_BASE_URL", "https://example.test/v1/")
    monkeypatch.setenv("HY3_API_KEY", "top-secret-value")
    monkeypatch.setenv("HY3_MODEL", "hy3-preview")
    monkeypatch.setenv("HY3_REASONING_EFFORT", "low")

    settings = Settings()

    assert settings.hy3_base_url == "https://example.test/v1"
    assert settings.hy3_model == "hy3-preview"
    assert settings.hy3_reasoning_effort == "low"
    assert settings.require_api_key() == "top-secret-value"
    assert "top-secret-value" not in repr(settings)


@pytest.mark.parametrize("value", [None, "", "${HY3_API_KEY}", "replace-with-your-key"])
def test_missing_or_unexpanded_api_key_is_actionable(value: str | None) -> None:
    settings = Settings(HY3_API_KEY=value)

    with pytest.raises(MissingCredentialError) as exc_info:
        settings.require_api_key()

    payload = exc_info.value.to_public_dict()
    assert payload["code"] == "MISSING_CREDENTIAL"
    assert payload["retryable"] is False
    assert "HY3_API_KEY" in str(payload["hint"])


def test_invalid_base_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="absolute HTTP"):
        Settings(HY3_BASE_URL="not-a-url")


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://tokenhub.tencentmaas.com/v1", "tokenhub"),
        ("https://tokenhub-intl.tencentmaas.com/v1", "tokenhub"),
        ("https://api.lkeap.cloud.tencent.com/plan/v3", "tokenhub"),
        ("http://127.0.0.1:8000/v1", "self_hosted"),
    ],
)
def test_provider_is_inferred_from_base_url(base_url: str, expected: str) -> None:
    settings = Settings(HY3_BASE_URL=base_url)

    assert settings.resolved_api_provider() == expected


def test_explicit_provider_overrides_url_inference() -> None:
    settings = Settings(
        HY3_BASE_URL="https://tokenhub.tencentmaas.com/v1",
        HY3_API_PROVIDER="self_hosted",
    )

    assert settings.resolved_api_provider() == "self_hosted"
