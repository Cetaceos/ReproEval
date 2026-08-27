"""Security gates for redacted live-validation summaries.

The live scripts call Hy3 only for the documented synthetic workflows.  This
module validates the JSON summary before it is printed so a CI log cannot
silently claim execution, leak credential-shaped fields, or publish an
incomplete artifact hash.  It does not inspect or execute repository code.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import unquote

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "client_secret",
    "password",
    "private_key",
    "credentials_available",
)
HASH_KEYS = {
    "command_hash",
    "content_hash",
    "manifest_content_hash",
    "payload_hash",
    "wheel_sha256",
}
PATH_KEYS = {"relative_path", "report_path", "manifest_path"}
EXECUTION_KEYS = {
    "executed",
    "executed_repository_code",
}
BOOLEAN_KEYS = {"live_execution"}
MAX_SUMMARY_NODES = 10_000
MAX_SUMMARY_DEPTH = 32
MAX_STRING_CHARS = 200_000
MAX_SEQUENCE_ITEMS = 5_000


class LiveValidationSecurityError(RuntimeError):
    """Raised when a live-validation summary fails the publication gate."""


def enforce_live_summary_security(summary: Mapping[str, Any]) -> None:
    """Fail closed on unsafe or incomplete live-validation JSON summaries.

    The check is deliberately structural. It does not claim that a model
    response or detector is intrinsically safe; it only prevents the runner
    from publishing a summary that contradicts the server's execution and
    artifact-integrity contract.
    """

    if summary.get("status") not in {"passed", "ready_for_live"}:
        raise LiveValidationSecurityError("Live validation did not finish with an accepted status.")
    _walk_summary(summary, path="$", seen=set(), state=[0])


def _walk_summary(value: Any, *, path: str, seen: set[int], state: list[int], depth: int = 0) -> None:
    state[0] += 1
    if state[0] > MAX_SUMMARY_NODES:
        raise LiveValidationSecurityError("Live summary exceeds the structural node limit.")
    if depth > MAX_SUMMARY_DEPTH:
        raise LiveValidationSecurityError("Live summary exceeds the structural depth limit.")
    if isinstance(value, str):
        if len(value) > MAX_STRING_CHARS:
            raise LiveValidationSecurityError(f"String value exceeds the summary limit at {path}.")
        return
    if isinstance(value, Mapping):
        object_id = id(value)
        if object_id in seen:
            raise LiveValidationSecurityError(f"Cyclic summary value at {path}.")
        seen.add(object_id)
        try:
            if len(value) > MAX_SEQUENCE_ITEMS:
                raise LiveValidationSecurityError(f"Mapping exceeds the summary limit at {path}.")
            for raw_key, child in value.items():
                if not isinstance(raw_key, str):
                    raise LiveValidationSecurityError(f"Summary keys must be strings: {path}.")
                key = raw_key
                normalized = key.casefold().replace("-", "_")
                child_path = f"{path}.{key}"
                if any(part in normalized for part in SENSITIVE_KEY_PARTS) and child not in (None, "", False, []):
                    raise LiveValidationSecurityError(f"Sensitive field was present in live summary: {child_path}.")
                if normalized in EXECUTION_KEYS and child is not False:
                    raise LiveValidationSecurityError(f"Execution flag was not false in live summary: {child_path}.")
                if normalized in BOOLEAN_KEYS and not isinstance(child, bool):
                    raise LiveValidationSecurityError(f"Boolean field was not a JSON boolean: {child_path}.")
                if normalized in PATH_KEYS and isinstance(child, str) and _is_absolute_or_parent_path(child):
                    raise LiveValidationSecurityError(
                        f"Absolute/private path was present in live summary: {child_path}."
                    )
                if normalized == "status" and path.endswith(".run_manifest") and child != "completed":
                    raise LiveValidationSecurityError(f"Run manifest was not completed: {child_path}.")
                if normalized == "artifacts":
                    _validate_artifacts(child, child_path)
                if normalized in HASH_KEYS and child is not None and not SHA256_RE.fullmatch(str(child)):
                    raise LiveValidationSecurityError(f"Invalid SHA-256 field in live summary: {child_path}.")
                _walk_summary(child, path=child_path, seen=seen, state=state, depth=depth + 1)
        finally:
            seen.remove(object_id)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        object_id = id(value)
        if object_id in seen:
            raise LiveValidationSecurityError(f"Cyclic summary value at {path}.")
        seen.add(object_id)
        if len(value) > MAX_SEQUENCE_ITEMS:
            raise LiveValidationSecurityError(f"Sequence exceeds the summary limit at {path}.")
        try:
            for index, child in enumerate(value):
                _walk_summary(child, path=f"{path}[{index}]", seen=seen, state=state, depth=depth + 1)
        finally:
            seen.remove(object_id)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise LiveValidationSecurityError(f"Non-finite numeric values are not allowed at {path}.")
    if value is not None and not isinstance(value, (bool, int, float, bytes, bytearray)):
        raise LiveValidationSecurityError(f"Unsupported summary value type at {path}.")
    if isinstance(value, (bytes, bytearray)):
        raise LiveValidationSecurityError(f"Binary summary values are not allowed at {path}.")


def _validate_artifacts(value: Any, path: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise LiveValidationSecurityError(f"Artifact summary must be a list: {path}.")
    if not value:
        raise LiveValidationSecurityError(f"Artifact summary must not be empty: {path}.")
    for index, artifact in enumerate(value):
        if not isinstance(artifact, Mapping):
            raise LiveValidationSecurityError(f"Artifact summary entry must be an object: {path}[{index}].")
        content_hash = artifact.get("content_hash")
        if not isinstance(content_hash, str) or not SHA256_RE.fullmatch(content_hash):
            raise LiveValidationSecurityError(f"Artifact summary lacks a valid content_hash: {path}[{index}].")
        artifact_type = artifact.get("artifact_type")
        payload_hash = artifact.get("payload_hash")
        if artifact_type == "json":
            if not isinstance(payload_hash, str) or not SHA256_RE.fullmatch(payload_hash):
                raise LiveValidationSecurityError(f"JSON artifact lacks a valid payload_hash: {path}[{index}].")
        elif artifact_type == "markdown":
            if payload_hash is not None:
                raise LiveValidationSecurityError(f"Markdown artifact must not claim a payload_hash: {path}[{index}].")
        else:
            raise LiveValidationSecurityError(f"Unsupported artifact type in live summary: {path}[{index}].")


def _is_absolute_or_parent_path(value: str) -> bool:
    normalized = unquote(value.replace("\\", "/"))
    if any(ord(character) < 32 for character in normalized):
        return True
    parts = normalized.split("/")
    return bool(
        re.match(r"^[A-Za-z]:/", normalized)
        or normalized.startswith("/")
        or normalized.startswith("//")
        or ".." in parts
    )


__all__ = ["LiveValidationSecurityError", "enforce_live_summary_security"]
