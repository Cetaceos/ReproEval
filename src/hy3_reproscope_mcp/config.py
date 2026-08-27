"""Environment-only configuration for Hy3 ReproScope."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .errors import MissingCredentialError

Hy3APIProvider = Literal["auto", "tokenhub", "self_hosted"]

_TOKENHUB_HOSTS = {
    "tokenhub.tencentmaas.com",
    "tokenhub.tencentmaas.cn",
    "tokenhub-intl.tencentmaas.com",
    "tokenhub-intl.tencentmaas.cn",
    "api.lkeap.cloud.tencent.com",
}


class Settings(BaseSettings):
    """Runtime settings loaded from explicit environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=None,
        case_sensitive=False,
        extra="ignore",
    )

    hy3_base_url: str = Field(
        default="http://127.0.0.1:8000/v1",
        validation_alias="HY3_BASE_URL",
    )
    hy3_api_key: SecretStr | None = Field(default=None, validation_alias="HY3_API_KEY")
    hy3_model: str = Field(default="hy3", min_length=1, validation_alias="HY3_MODEL")
    hy3_api_provider: Hy3APIProvider = Field(default="auto", validation_alias="HY3_API_PROVIDER")
    hy3_reasoning_effort: Literal["no_think", "low", "high"] = Field(
        default="high",
        validation_alias="HY3_REASONING_EFFORT",
    )
    hy3_temperature: float = Field(default=0.9, ge=0.0, le=2.0, validation_alias="HY3_TEMPERATURE")
    hy3_top_p: float = Field(default=1.0, gt=0.0, le=1.0, validation_alias="HY3_TOP_P")
    hy3_timeout_seconds: float = Field(default=120.0, gt=0.0, validation_alias="HY3_TIMEOUT_SECONDS")
    hy3_max_retries: int = Field(default=2, ge=0, le=5, validation_alias="HY3_MAX_RETRIES")
    hy3_max_tokens: int = Field(default=16000, ge=256, le=128000, validation_alias="HY3_MAX_TOKENS")

    reproscope_workspace: Path = Field(
        default=Path(".hy3-reproscope"),
        validation_alias="REPROSCOPE_WORKSPACE",
    )
    reproscope_allowed_roots: str | None = Field(default=None, validation_alias="REPROSCOPE_ALLOWED_ROOTS")
    reproscope_max_file_mb: int = Field(default=50, ge=1, le=1024, validation_alias="REPROSCOPE_MAX_FILE_MB")
    reproscope_max_source_chars: int = Field(
        default=24000,
        ge=1000,
        le=200000,
        validation_alias="REPROSCOPE_MAX_SOURCE_CHARS",
    )
    reproscope_max_total_chars: int = Field(
        default=120000,
        ge=5000,
        le=500000,
        validation_alias="REPROSCOPE_MAX_TOTAL_CHARS",
    )
    reproscope_prompt_injection_policy: Literal["warn", "reject"] = Field(
        # Evidence is untrusted by default.  A caller may explicitly opt into
        # ``warn`` after manual review, but normal MCP and live-validation
        # paths must fail closed before any source reaches Hy3.
        default="reject",
        validation_alias="REPROSCOPE_PROMPT_INJECTION_POLICY",
    )
    reproscope_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias="REPROSCOPE_LOG_LEVEL",
    )

    @field_validator("hy3_base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("HY3_BASE_URL must be an absolute HTTP(S) URL")
        return normalized

    @field_validator("reproscope_workspace", mode="before")
    @classmethod
    def expand_workspace(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    def require_api_key(self) -> str:
        """Return the API key or raise a safe, actionable configuration error."""

        key = self.hy3_api_key.get_secret_value() if self.hy3_api_key else ""
        normalized_key = key.strip().lower()
        placeholder_keys = {"replace-with-your-key", "your_hy3_api_key", "your-hy3-api-key"}
        if not key or (key.startswith("${") and key.endswith("}")) or normalized_key in placeholder_keys:
            raise MissingCredentialError(
                "HY3_API_KEY is not configured.",
                hint=(
                    "Set HY3_API_KEY in the parent process or MCP client environment. "
                    "Use EMPTY explicitly for an unauthenticated local endpoint."
                ),
            )
        return key

    def resolved_api_provider(self) -> Literal["tokenhub", "self_hosted"]:
        """Resolve automatic provider selection from the configured API hostname."""

        if self.hy3_api_provider != "auto":
            return self.hy3_api_provider
        hostname = (urlparse(self.hy3_base_url).hostname or "").lower()
        return "tokenhub" if hostname in _TOKENHUB_HOSTS else "self_hosted"

    def allowed_roots(self) -> tuple[Path, ...]:
        """Return canonical directories that local file tools may read from."""

        raw_roots = self.reproscope_allowed_roots
        if raw_roots:
            roots = tuple(
                Path(raw_root.strip()).expanduser().resolve()
                for raw_root in raw_roots.split(os.pathsep)
                if raw_root.strip()
            )
            if roots:
                return roots
        return (Path.cwd().resolve(),)
