"""Domain exceptions with safe, actionable messages for MCP clients."""

from __future__ import annotations

from typing import ClassVar


class ReproScopeError(Exception):
    """Base exception for failures that can be shown to an MCP client."""

    code: ClassVar[str] = "REPROSCOPE_ERROR"
    default_retryable: ClassVar[bool] = False

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.retryable = self.default_retryable if retryable is None else retryable

    def to_public_dict(self) -> dict[str, str | bool | None]:
        """Return a serializable error payload without traceback or secrets."""

        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "retryable": self.retryable,
        }


class ConfigurationError(ReproScopeError):
    code = "CONFIGURATION_ERROR"


class MissingCredentialError(ConfigurationError):
    code = "MISSING_CREDENTIAL"


class PathPolicyError(ReproScopeError):
    code = "PATH_POLICY_ERROR"


class UnsupportedFileTypeError(ReproScopeError):
    code = "UNSUPPORTED_FILE_TYPE"


class FileTooLargeError(ReproScopeError):
    code = "FILE_TOO_LARGE"


class TotalInputTooLargeError(ReproScopeError):
    code = "TOTAL_INPUT_TOO_LARGE"


class ParseError(ReproScopeError):
    code = "PARSE_ERROR"


class Hy3APIError(ReproScopeError):
    code = "HY3_API_ERROR"
    default_retryable = True


class Hy3TimeoutError(Hy3APIError):
    code = "HY3_TIMEOUT"


class StructuredOutputValidationError(ReproScopeError):
    code = "STRUCTURED_OUTPUT_VALIDATION_ERROR"


class ArtifactNotFoundError(ReproScopeError):
    code = "ARTIFACT_NOT_FOUND"


class ArtifactIntegrityError(ReproScopeError):
    code = "ARTIFACT_INTEGRITY_ERROR"


class ArtifactSchemaCompatibilityError(ReproScopeError):
    code = "ARTIFACT_SCHEMA_INCOMPATIBLE"


class ArtifactLineageError(ReproScopeError):
    code = "ARTIFACT_LINEAGE_ERROR"


class EvidenceGraphValidationError(ReproScopeError):
    code = "EVIDENCE_GRAPH_VALIDATION_ERROR"


class InsufficientEvidenceError(ReproScopeError):
    code = "INSUFFICIENT_EVIDENCE"


class MetricMappingError(ReproScopeError):
    code = "METRIC_MAPPING_ERROR"


class GroupFilterError(ReproScopeError):
    code = "GROUP_FILTER_ERROR"


class WorkspaceError(ReproScopeError):
    code = "WORKSPACE_ERROR"
