"""Safe local workspace and artifact utilities."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .config import Settings
from .errors import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactSchemaCompatibilityError,
    FileTooLargeError,
    ParseError,
    PathPolicyError,
    ReproScopeError,
    WorkspaceError,
)
from .models import (
    SCHEMA_VERSION,
    ArtifactReference,
    ParentArtifactReference,
    RunManifest,
    RunRecoverySnapshot,
    RunStatus,
    RunStatusEvent,
    ToolResultBase,
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_text(content: str) -> str:
    return sha256_bytes(content.encode("utf-8"))


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    """Hash a JSON payload independently of formatting and its integrity marker."""

    canonical_payload = deepcopy(payload)
    canonical_payload.pop("artifact_integrity", None)
    canonical = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256_text(canonical)


def parent_artifact_reference(role: str, artifact: ArtifactReference) -> ParentArtifactReference:
    """Attach a semantic role to an exact artifact reference."""

    return ParentArtifactReference(role=role, **artifact.model_dump())


def make_relative_path(path: Path, roots: tuple[Path, ...]) -> str:
    resolved = path.resolve()
    for root in roots:
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    return resolved.as_posix()


class Workspace:
    """Read user-provided files and write generated artifacts under policy checks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.allowed_roots = settings.allowed_roots()
        self.workspace_path = settings.reproscope_workspace.expanduser().resolve()

    def resolve_input_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        if not any(self._is_relative_to(resolved, root) for root in self.allowed_roots):
            roots = "; ".join(root.as_posix() for root in self.allowed_roots)
            raise PathPolicyError(
                f"Input path is outside REPROSCOPE_ALLOWED_ROOTS: {raw_path}",
                hint=f"Set REPROSCOPE_ALLOWED_ROOTS to include the directory. Current roots: {roots}",
            )
        if not resolved.is_file():
            raise PathPolicyError(f"Input path is not a readable file: {raw_path}")

        max_bytes = self.settings.reproscope_max_file_mb * 1024 * 1024
        file_size = resolved.stat().st_size
        if file_size > max_bytes:
            raise FileTooLargeError(
                f"Input file exceeds REPROSCOPE_MAX_FILE_MB: {raw_path}",
                hint=f"File size is {file_size} bytes; limit is {max_bytes} bytes.",
            )
        return resolved

    def resolve_input_directory(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        if not any(self._is_relative_to(resolved, root) for root in self.allowed_roots):
            roots = "; ".join(root.as_posix() for root in self.allowed_roots)
            raise PathPolicyError(
                f"Input directory is outside REPROSCOPE_ALLOWED_ROOTS: {raw_path}",
                hint=f"Set REPROSCOPE_ALLOWED_ROOTS to include the directory. Current roots: {roots}",
            )
        if not resolved.is_dir():
            raise PathPolicyError(f"Input path is not a readable directory: {raw_path}")
        return resolved

    def read_bytes(self, raw_path: str) -> tuple[Path, bytes]:
        resolved = self.resolve_input_path(raw_path)
        return resolved, resolved.read_bytes()

    def write_json_artifact(self, run_id: str, name: str, payload: dict[str, Any]) -> ArtifactReference:
        safe_name = name.replace("/", "_").replace("\\", "_")
        artifact_dir = self.workspace_path / run_id
        artifact_path = artifact_dir / safe_name
        document = deepcopy(payload)
        document.pop("artifact_integrity", None)
        document.setdefault("schema_version", SCHEMA_VERSION)
        payload_hash = canonical_payload_hash(document)
        document["artifact_integrity"] = {
            "algorithm": "sha256",
            "payload_hash": payload_hash,
        }
        try:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            content = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
            serialized = (content + "\n").encode("utf-8")
            artifact_path.write_bytes(serialized)
        except OSError as exc:
            raise WorkspaceError(
                f"Could not write ReproScope artifact: {artifact_path}",
                hint="Check REPROSCOPE_WORKSPACE permissions.",
            ) from exc

        return ArtifactReference(
            run_id=run_id,
            artifact_type="json",
            relative_path=make_relative_path(artifact_path, (self.workspace_path,)),
            content_hash=sha256_bytes(serialized),
            payload_hash=payload_hash,
            schema_version=str(document.get("schema_version", SCHEMA_VERSION)),
        )

    def read_json_artifact(self, raw_path: str) -> dict[str, Any]:
        payload, _ = self.read_json_artifact_with_reference(raw_path)
        return payload

    def read_json_artifact_with_reference(
        self,
        raw_path: str,
        *,
        expected_schema: str | None = None,
    ) -> tuple[dict[str, Any], ArtifactReference]:
        artifact_path = self.resolve_artifact_path(raw_path)
        try:
            content = artifact_path.read_bytes()
            payload = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ParseError(f"Artifact is not valid JSON: {raw_path}") from exc
        except UnicodeDecodeError as exc:
            raise ParseError(f"Artifact is not valid UTF-8 JSON: {raw_path}") from exc
        except OSError as exc:
            raise WorkspaceError(f"Could not read ReproScope artifact: {raw_path}") from exc
        if not isinstance(payload, dict):
            raise ParseError(f"Artifact must contain a JSON object: {raw_path}")
        if expected_schema is not None:
            self.require_artifact_schema(raw_path, payload, expected_schema)
        self._verify_json_integrity(raw_path, payload)
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ParseError(f"Artifact has no valid run_id: {raw_path}")
        integrity = payload.get("artifact_integrity")
        return payload, ArtifactReference(
            run_id=run_id,
            artifact_type="json",
            relative_path=make_relative_path(artifact_path, (self.workspace_path,)),
            content_hash=sha256_bytes(content),
            payload_hash=integrity["payload_hash"] if isinstance(integrity, dict) else None,
            schema_version=str(payload.get("schema_version", "legacy")),
        )

    @staticmethod
    def require_artifact_schema(raw_path: str, payload: dict[str, Any], expected_schema: str) -> None:
        """Reject artifacts that are not produced for the current business schema.

        ``read_json_artifact`` intentionally remains a low-level forensic reader. Business
        tools call this guard before Pydantic validation so old, missing, and future schemas
        receive one actionable compatibility error instead of an incidental field error.
        """

        actual = payload.get("schema_version")
        if actual != expected_schema:
            actual_label = "missing" if actual is None else str(actual)
            raise ArtifactSchemaCompatibilityError(
                f"Artifact Schema {actual_label} is not compatible with this tool. "
                f"Expected Schema {expected_schema}. Regenerate the upstream artifact.",
                hint=f"Re-run the upstream ReproScope tool to produce Schema {expected_schema}: {raw_path}",
            )

    def resolve_artifact_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace_path / candidate
        resolved = candidate.resolve()
        if not self._is_relative_to(resolved, self.workspace_path):
            raise PathPolicyError(
                f"Artifact path is outside REPROSCOPE_WORKSPACE: {raw_path}",
                hint=f"Use a path under {self.workspace_path.as_posix()}.",
            )
        if not resolved.is_file():
            raise ArtifactNotFoundError(f"ReproScope artifact was not found: {raw_path}")
        max_bytes = self.settings.reproscope_max_file_mb * 1024 * 1024
        file_size = resolved.stat().st_size
        if file_size > max_bytes:
            raise FileTooLargeError(
                f"Artifact exceeds REPROSCOPE_MAX_FILE_MB: {raw_path}",
                hint=f"File size is {file_size} bytes; limit is {max_bytes} bytes.",
            )
        return resolved

    def read_run_manifest(self, run_id: str) -> RunManifest:
        """Read and validate one persisted run manifest without executing anything."""

        if not run_id or not all(character.isalnum() or character in "_-" for character in run_id):
            raise PathPolicyError("Run ID contains unsupported path characters.")
        payload, _ = self.read_json_artifact_with_reference(
            f"{run_id}/run_manifest.json",
            expected_schema=SCHEMA_VERSION,
        )
        try:
            manifest = RunManifest.model_validate(payload)
        except ValidationError as exc:
            raise ParseError(f"Run manifest is not valid: {run_id}") from exc
        if manifest.run_id != run_id:
            raise ArtifactIntegrityError(f"Run manifest ID does not match its requested path: {run_id}")
        return manifest

    def inspect_run(self, run_id: str) -> RunRecoverySnapshot:
        """Return deterministic recovery guidance for a run; never resumes it automatically."""

        manifest = self.read_run_manifest(run_id)
        if manifest.status is RunStatus.COMPLETED:
            recovery_action = "reuse_completed"
            resume_from = "completed_artifacts"
            recovery_reason = "The run is completed; reuse its immutable artifacts instead of rerunning it."
        elif manifest.status is RunStatus.RUNNING:
            recovery_action = "inspect_only"
            resume_from = "manual_inspection"
            recovery_reason = "The run is marked running; inspect its manifest before deciding whether to restart."
        else:
            recovery_action = "restart_from_recorded_inputs"
            resume_from = "recorded_inputs"
            recovery_reason = "The run is incomplete; a caller may restart it using its recorded inputs and parents."
        return RunRecoverySnapshot(
            run_id=manifest.run_id,
            tool_name=manifest.tool_name,
            schema_version=manifest.schema_version,
            status=manifest.status,
            created_at=manifest.created_at,
            updated_at=manifest.updated_at,
            artifact_count=len(manifest.artifacts),
            parent_artifact_count=len(manifest.parent_artifacts),
            reusable_artifacts=list(manifest.artifacts),
            recovery_action=recovery_action,
            resume_from=resume_from,
            recovery_reason=recovery_reason,
            error_code=manifest.error_code,
        )

    def write_text_artifact(
        self,
        run_id: str,
        name: str,
        content: str,
        *,
        artifact_type: str,
    ) -> ArtifactReference:
        safe_name = name.replace("/", "_").replace("\\", "_")
        artifact_dir = self.workspace_path / run_id
        artifact_path = artifact_dir / safe_name
        normalized_content = content.rstrip() + "\n"
        try:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            serialized = normalized_content.encode("utf-8")
            artifact_path.write_bytes(serialized)
        except OSError as exc:
            raise WorkspaceError(
                f"Could not write ReproScope artifact: {artifact_path}",
                hint="Check REPROSCOPE_WORKSPACE permissions.",
            ) from exc
        return ArtifactReference(
            run_id=run_id,
            artifact_type=artifact_type,
            relative_path=make_relative_path(artifact_path, (self.workspace_path,)),
            content_hash=sha256_bytes(serialized),
        )

    @staticmethod
    def _verify_json_integrity(raw_path: str, payload: dict[str, Any]) -> None:
        integrity = payload.get("artifact_integrity")
        if integrity is None:
            schema_version = payload.get("schema_version")
            if schema_version is not None and _schema_at_least(str(schema_version), "1.6"):
                raise ArtifactIntegrityError(
                    f"Artifact is missing its integrity marker: {raw_path}",
                    hint="Re-run the upstream tool instead of editing generated JSON artifacts.",
                )
            return
        if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
            raise ArtifactIntegrityError(
                f"Artifact has an unsupported integrity marker: {raw_path}",
                hint="Re-run the upstream tool with the current ReproScope version.",
            )
        expected = integrity.get("payload_hash")
        actual = canonical_payload_hash(payload)
        if not isinstance(expected, str) or expected != actual:
            raise ArtifactIntegrityError(
                f"Artifact payload hash does not match its content: {raw_path}",
                hint="The artifact may have been modified after creation; re-run the upstream tool.",
            )

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False


class RunManifestWriter:
    """Persist one tool run's state transitions without masking tool failures."""

    def __init__(self, workspace: Workspace, *, run_id: str, tool_name: str) -> None:
        self.workspace = workspace
        now = datetime.now(UTC)
        self.manifest = RunManifest(
            run_id=run_id,
            tool_name=tool_name,
            created_at=now,
            updated_at=now,
            status_history=[RunStatusEvent(status=RunStatus.CREATED, timestamp=now)],
        )
        self._persist()

    def mark_running(self) -> ArtifactReference:
        return self._transition(RunStatus.RUNNING)

    def mark_completed(self, result: ToolResultBase) -> ArtifactReference:
        self.manifest.sources = list(result.sources)
        self.manifest.parent_artifacts = list(result.parent_artifacts)
        self.manifest.artifacts = list(result.artifacts)
        self.manifest.profile_versions = dict(result.profile_versions)
        self.manifest.registry_hashes = dict(result.registry_hashes)
        self.manifest.error_code = None
        self.manifest.error_message = None
        return self._transition(RunStatus.COMPLETED)

    def mark_failed(self, error: Exception) -> ArtifactReference:
        if isinstance(error, ReproScopeError):
            self.manifest.error_code = error.code
            self.manifest.error_message = error.message
        else:
            self.manifest.error_code = "INTERNAL_ERROR"
            self.manifest.error_message = "The tool failed unexpectedly."
        return self._transition(RunStatus.FAILED)

    def _transition(self, status: RunStatus) -> ArtifactReference:
        now = datetime.now(UTC)
        self.manifest.status = status
        self.manifest.updated_at = now
        self.manifest.status_history.append(RunStatusEvent(status=status, timestamp=now))
        return self._persist()

    def _persist(self) -> ArtifactReference:
        return self.workspace.write_json_artifact(
            self.manifest.run_id,
            "run_manifest.json",
            self.manifest.model_dump(mode="json"),
        )


def _schema_at_least(actual: str, minimum: str) -> bool:
    try:
        actual_parts = tuple(int(part) for part in actual.split("."))
        minimum_parts = tuple(int(part) for part in minimum.split("."))
    except ValueError:
        return True
    width = max(len(actual_parts), len(minimum_parts))
    return actual_parts + (0,) * (width - len(actual_parts)) >= minimum_parts + (0,) * (width - len(minimum_parts))
