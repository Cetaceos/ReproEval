from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import shutil
import stat
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

CASE_ID = "differt2d-v0.3.4-figure2"
ARCHIVE_SIZE = 30_520_081
ARCHIVE_MD5 = "A4497F4CCABA5CE5D8F867EC5B4D176C"
ARCHIVE_SHA256 = "F61FA9F76F3614449480BFF9314D9F1DB7FF9414C9BC526AEF0473ED4DA6BABE"
ZIP_ROOT = "jeertmans-DiffeRT2d-744a27e"
ENTRYPOINT = PurePosixPath(ZIP_ROOT, "papers/joss/plot_ris_power_map.py")
ENTRYPOINT_SHA256 = "E9F5BDE138A6C64841E6970CCC28958A2B6B47F253216A69F18A439EF242F7A1"
REFERENCE_IMAGE = PurePosixPath(ZIP_ROOT, "papers/joss/static/ris_power_map.png")
REFERENCE_IMAGE_SHA256 = "D9DA4C4DDBBEDAB3B8F009FE1CE6EA18989A9F885E784804CB5454BE2C88FCE1"
LOCKFILE = PurePosixPath(ZIP_ROOT, "requirements.lock")
LOCKFILE_SHA256 = "372759137EE67F16CA776D5BC960D7D9344DBB745D4AC47D16F345B3C396F97A"
MAX_FILES = 10_000
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
SENSITIVE_MARKERS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


class ProtocolError(RuntimeError):
    """Raised when source or evidence violates the frozen case protocol."""


def _digest(path: Path, algorithm: str = "sha256") -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().upper()


def _payload_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(canonical).hexdigest().upper()


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalized.encode("utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _internal_symlink_target(bundle: zipfile.ZipFile, member: zipfile.ZipInfo) -> str:
    try:
        target = bundle.read(member).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolError(f"symbolic link target is not UTF-8: {member.filename}") from exc
    if "\\" in target or PurePosixPath(target).is_absolute():
        raise ProtocolError(f"symbolic link has an unsafe target: {member.filename}")
    resolved = PurePosixPath(posixpath.normpath(str(PurePosixPath(member.filename).parent / target)))
    if not resolved.parts or resolved.parts[0] != ZIP_ROOT or ".." in resolved.parts:
        raise ProtocolError(f"symbolic link escapes the source root: {member.filename}")
    return resolved.as_posix()


def inspect_archive(archive: Path) -> dict[str, Any]:
    archive = archive.resolve()
    if not archive.is_file():
        raise ProtocolError(f"archive does not exist: {archive}")
    size = archive.stat().st_size
    md5 = _digest(archive, "md5")
    sha256 = _digest(archive)
    if (size, md5, sha256) != (ARCHIVE_SIZE, ARCHIVE_MD5, ARCHIVE_SHA256):
        raise ProtocolError("archive size or digest does not match the frozen Zenodo v0.3.4 source")

    names: set[str] = set()
    file_count = 0
    total_bytes = 0
    skipped_symlinks: list[dict[str, str]] = []
    entrypoint_sha256: str | None = None
    reference_sha256: str | None = None
    lockfile_sha256: str | None = None
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            path = PurePosixPath(member.filename)
            if "\\" in member.filename or path.is_absolute() or ".." in path.parts:
                raise ProtocolError(f"unsafe ZIP member path: {member.filename}")
            normalized = path.as_posix().rstrip("/")
            if normalized in names:
                raise ProtocolError(f"duplicate ZIP member path: {member.filename}")
            names.add(normalized)
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                skipped_symlinks.append(
                    {
                        "path": member.filename,
                        "resolved_target": _internal_symlink_target(bundle, member),
                    }
                )
                continue
            if member.is_dir():
                continue
            file_count += 1
            total_bytes += member.file_size
            if member.file_size > MAX_MEMBER_BYTES:
                raise ProtocolError(f"ZIP member exceeds the per-file limit: {member.filename}")
            if file_count > MAX_FILES or total_bytes > MAX_TOTAL_BYTES:
                raise ProtocolError("source archive exceeds the case extraction limits")
            if path == ENTRYPOINT:
                entrypoint_sha256 = hashlib.sha256(bundle.read(member)).hexdigest().upper()
            if path == REFERENCE_IMAGE:
                reference_sha256 = hashlib.sha256(bundle.read(member)).hexdigest().upper()
            if path == LOCKFILE:
                lockfile_sha256 = hashlib.sha256(bundle.read(member)).hexdigest().upper()

    missing_symlink_targets = [item for item in skipped_symlinks if item["resolved_target"] not in names]
    if missing_symlink_targets:
        raise ProtocolError("source archive contains an internal symbolic link with a missing target")
    if entrypoint_sha256 != ENTRYPOINT_SHA256:
        raise ProtocolError("the official Figure 2 entrypoint is missing or has changed")
    if reference_sha256 != REFERENCE_IMAGE_SHA256:
        raise ProtocolError("the archived Figure 2 reference image is missing or has changed")
    if lockfile_sha256 != LOCKFILE_SHA256:
        raise ProtocolError("the upstream dependency lockfile is missing or has changed")
    return {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "status": "verified",
        "archive": {
            "path": str(archive),
            "size_bytes": size,
            "md5": md5,
            "sha256": sha256,
            "file_count": file_count,
            "uncompressed_bytes": total_bytes,
            "skipped_internal_symlinks": skipped_symlinks,
        },
        "entrypoint": {"path": ENTRYPOINT.as_posix(), "sha256": entrypoint_sha256},
        "reference_image": {"path": REFERENCE_IMAGE.as_posix(), "sha256": reference_sha256},
        "lockfile": {"path": LOCKFILE.as_posix(), "sha256": lockfile_sha256},
    }


def safe_extract(archive: Path, destination: Path) -> Path:
    inspect_archive(archive)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            relative = PurePosixPath(member.filename)
            if stat.S_ISLNK(member.external_attr >> 16):
                continue
            target = destination.joinpath(*relative.parts).resolve()
            if not target.is_relative_to(destination):
                raise ProtocolError(f"ZIP member escapes extraction root: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    source_root = destination / ZIP_ROOT
    if not source_root.is_dir():
        raise ProtocolError("the expected source root was not extracted")
    return source_root


def _sanitized_environment(run_dir: Path) -> tuple[dict[str, str], list[str]]:
    allowed = {
        "ALLUSERSPROFILE",
        "APPDATA",
        "COMSPEC",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "NUMBER_OF_PROCESSORS",
        "OS",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    inherited = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    inherited.update(
        {
            "JAX_PLATFORM_NAME": "cpu",
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": str(run_dir / "work" / "matplotlib"),
            "PYTHONNOUSERSITE": "1",
            "XLA_PYTHON_CLIENT_PREALLOCATE": "false",
        }
    )
    rejected = sorted(key for key in os.environ if any(marker in key.upper() for marker in SENSITIVE_MARKERS))
    return inherited, rejected


def _inventory(evidence_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(item for item in evidence_dir.rglob("*") if item.is_file()):
        if path.name == "run_manifest.json":
            continue
        items.append(
            {
                "path": path.relative_to(evidence_dir).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _digest(path),
            }
        )
    return items


def _classify(metrics_path: Path) -> str:
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    image = metrics["image_comparison"]
    grid_ok = metrics["power_linear"]["shape"] == [300, 300]
    if not grid_ok or not image["shape_matches"]:
        return "artifact_divergence"
    if image["pixel_exact"]:
        return "exact"
    error = image["normalized_mean_absolute_error"]
    if error is not None and error <= image["visual_threshold"]:
        return "visually_consistent"
    return "artifact_divergence"


def run_case(archive: Path, python: Path, output_root: Path, timeout: int) -> Path:
    archive = archive.resolve()
    python = python.resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"differt2d-v0.3.4-{stamp}-{ARCHIVE_SHA256[:8].lower()}"
    run_dir = output_root.resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir = run_dir / "evidence"
    logs_dir = evidence_dir / "logs"
    logs_dir.mkdir(parents=True)
    started = datetime.now(UTC)
    command: list[str] = []
    exit_code: int | None = None
    error: str | None = None
    timed_out = False
    rejected_environment: list[str] = []
    inspected: dict[str, Any] | None = None

    try:
        inspected = inspect_archive(archive)
        if not python.is_file():
            raise ProtocolError(f"dedicated Python executable does not exist: {python}")
        source_root = safe_extract(archive, run_dir / "work" / "source")
        reference = source_root / Path(*REFERENCE_IMAGE.parts[1:])
        capture = Path(__file__).with_name("capture_figure2.py").resolve()
        command = [
            str(python),
            str(capture),
            "--source-root",
            str(source_root),
            "--evidence-dir",
            str(evidence_dir),
            "--reference-image",
            str(reference),
        ]
        environment, rejected_environment = _sanitized_environment(run_dir)
        completed = subprocess.run(
            command,
            cwd=source_root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        exit_code = completed.returncode
        _write_text(logs_dir / "stdout.txt", completed.stdout)
        _write_text(logs_dir / "stderr.txt", completed.stderr)
        if exit_code != 0:
            error = f"fixed Figure 2 process exited with code {exit_code}"
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        error = f"fixed Figure 2 process exceeded {timeout} seconds"
        _write_text(logs_dir / "stdout.txt", exc.stdout or "")
        _write_text(logs_dir / "stderr.txt", exc.stderr or "")
    except Exception as exc:  # evidence must survive all failure paths
        error = f"{type(exc).__name__}: {exc}"
        (logs_dir / "stdout.txt").touch()
        _write_text(logs_dir / "stderr.txt", error + "\n")

    metrics_path = evidence_dir / "metrics.json"
    outcome = _classify(metrics_path) if error is None and metrics_path.is_file() else "failed"
    finished = datetime.now(UTC)
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "run_id": run_id,
        "status": "succeeded" if outcome != "failed" else "failed",
        "outcome": outcome,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "source": inspected
        or {
            "schema_version": "1.0",
            "case_id": CASE_ID,
            "status": "failed",
            "archive": {"path": str(archive)},
        },
        "execution": {
            "python": str(python),
            "command": command,
            "entrypoint_allowlisted": True,
            "credentials_forwarded": False,
            "rejected_sensitive_environment_names": rejected_environment,
            "network_required": False,
            "network_isolation": "not_enforced_by_the_windows_runner",
            "timeout_seconds": timeout,
            "timed_out": timed_out,
            "exit_code": exit_code,
            "error": error,
        },
        "artifacts": _inventory(evidence_dir),
    }
    manifest["manifest_payload_sha256"] = _payload_sha256(manifest)
    _write_json(evidence_dir / "run_manifest.json", manifest)
    return evidence_dir / "run_manifest.json"


def verify_run(run_dir: Path) -> dict[str, Any]:
    evidence_dir = run_dir.resolve()
    if (evidence_dir / "evidence").is_dir():
        evidence_dir /= "evidence"
    manifest_path = evidence_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_payload_hash = manifest.pop("manifest_payload_sha256", None)
    actual_payload_hash = _payload_sha256(manifest)
    if expected_payload_hash != actual_payload_hash:
        raise ProtocolError("run manifest canonical payload hash does not match")
    for item in manifest["artifacts"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ProtocolError(f"unsafe evidence path in run manifest: {item['path']}")
        path = evidence_dir.joinpath(*relative.parts).resolve()
        if not path.is_relative_to(evidence_dir) or not path.is_file():
            raise ProtocolError(f"evidence file is missing: {item['path']}")
        if path.stat().st_size != item["size_bytes"] or _digest(path) != item["sha256"]:
            raise ProtocolError(f"evidence file failed size or SHA-256 verification: {item['path']}")
    return {
        "schema_version": "1.0",
        "case_id": manifest["case_id"],
        "run_id": manifest["run_id"],
        "status": "verified",
        "outcome": manifest["outcome"],
        "artifact_count": len(manifest["artifacts"]),
        "manifest_payload_sha256": expected_payload_hash,
    }


def export_public_evidence(run_dir: Path, output_dir: Path) -> Path:
    verify_run(run_dir)
    evidence_dir = run_dir.resolve()
    if (evidence_dir / "evidence").is_dir():
        evidence_dir /= "evidence"
    source_manifest_path = evidence_dir / "run_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if source_manifest["status"] != "succeeded":
        raise ProtocolError("only a successful verified run can be exported as public evidence")

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    copies = {
        "environment.json": "environment.json",
        "metrics.json": "metrics.json",
        "logs/stdout.txt": "stdout.txt",
        "logs/stderr.txt": "stderr.txt",
        "artifacts/ris_power_map.png": "ris_power_map_reproduced.png",
    }
    for source_name, output_name in copies.items():
        shutil.copy2(evidence_dir / Path(*PurePosixPath(source_name).parts), output_dir / output_name)

    environment_path = output_dir / "environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    environment["python"]["executable"] = "<dedicated-python-path-omitted>"
    _write_json(environment_path, environment)
    metrics_path = output_dir / "metrics.json"
    _write_json(metrics_path, json.loads(metrics_path.read_text(encoding="utf-8")))
    for log_name in ("stdout.txt", "stderr.txt"):
        log_path = output_dir / log_name
        _write_text(log_path, log_path.read_text(encoding="utf-8"))

    source = source_manifest["source"]
    public_manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": source_manifest["case_id"],
        "run_id": source_manifest["run_id"],
        "status": source_manifest["status"],
        "outcome": source_manifest["outcome"],
        "started_at": source_manifest["started_at"],
        "finished_at": source_manifest["finished_at"],
        "duration_seconds": source_manifest["duration_seconds"],
        "source": {
            "archive_filename": Path(source["archive"]["path"]).name,
            "archive_size_bytes": source["archive"]["size_bytes"],
            "archive_md5": source["archive"]["md5"],
            "archive_sha256": source["archive"]["sha256"],
            "entrypoint": source["entrypoint"],
            "reference_image": source["reference_image"],
            "lockfile": source["lockfile"],
            "skipped_internal_symlinks": source["archive"]["skipped_internal_symlinks"],
        },
        "execution": {
            "entrypoint_allowlisted": source_manifest["execution"]["entrypoint_allowlisted"],
            "credentials_forwarded": source_manifest["execution"]["credentials_forwarded"],
            "network_required": source_manifest["execution"]["network_required"],
            "network_isolation": source_manifest["execution"]["network_isolation"],
            "timeout_seconds": source_manifest["execution"]["timeout_seconds"],
            "timed_out": source_manifest["execution"]["timed_out"],
            "exit_code": source_manifest["execution"]["exit_code"],
        },
        "source_run_manifest_sha256": _digest(source_manifest_path),
        "published_files": _inventory(output_dir),
        "omitted_private_artifacts": [
            "the downloaded third-party archive and extracted source",
            "local absolute paths and the dedicated environment",
            "the compressed numerical NPZ and generated PDF",
        ],
        "claim_boundary": (
            "This exact result applies only to the archived JOSS Figure 2 program under the recorded environment; "
            "it is not an independent validation of the full paper or radio-propagation accuracy."
        ),
    }
    public_manifest["manifest_payload_sha256"] = _payload_sha256(public_manifest)
    output_path = output_dir / "public_evidence_manifest.json"
    _write_json(output_path, public_manifest)
    return output_path


def verify_public_evidence(evidence_dir: Path) -> dict[str, Any]:
    evidence_dir = evidence_dir.resolve()
    manifest_path = evidence_dir / "public_evidence_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_payload_hash = manifest.pop("manifest_payload_sha256", None)
    if expected_payload_hash != _payload_sha256(manifest):
        raise ProtocolError("public evidence manifest canonical payload hash does not match")
    for item in manifest["published_files"]:
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ProtocolError(f"unsafe public evidence path: {item['path']}")
        path = evidence_dir.joinpath(*relative.parts).resolve()
        if not path.is_relative_to(evidence_dir) or not path.is_file():
            raise ProtocolError(f"published evidence file is missing: {item['path']}")
        if path.stat().st_size != item["size_bytes"] or _digest(path) != item["sha256"]:
            raise ProtocolError(f"published evidence failed size or SHA-256 verification: {item['path']}")
    return {
        "schema_version": "1.0",
        "case_id": manifest["case_id"],
        "run_id": manifest["run_id"],
        "status": "verified",
        "outcome": manifest["outcome"],
        "published_file_count": len(manifest["published_files"]),
        "manifest_payload_sha256": expected_payload_hash,
    }


def prepare_source(archive: Path, destination: Path, manifest_path: Path) -> None:
    inspected = inspect_archive(archive)
    source_root = safe_extract(archive, destination)
    payload = {
        "schema_version": "1.0",
        "case_id": CASE_ID,
        "status": "prepared",
        "source_root": str(source_root),
        "source": inspected,
    }
    payload["manifest_payload_sha256"] = _payload_sha256(payload)
    _write_json(manifest_path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and run the frozen DiffeRT2d v0.3.4 Figure 2 case.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Verify the frozen archive without extracting it.")
    inspect_parser.add_argument("--archive", required=True, type=Path)
    inspect_parser.add_argument("--output", required=True, type=Path)

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Verify and safely extract the source for environment setup.",
    )
    prepare_parser.add_argument("--archive", required=True, type=Path)
    prepare_parser.add_argument("--destination", required=True, type=Path)
    prepare_parser.add_argument("--output", required=True, type=Path)

    run_parser = subparsers.add_parser("run", help="Run only the frozen Figure 2 entrypoint and capture evidence.")
    run_parser.add_argument("--archive", required=True, type=Path)
    run_parser.add_argument("--python", required=True, type=Path)
    run_parser.add_argument("--output-root", required=True, type=Path)
    run_parser.add_argument("--timeout", type=int, default=1800)

    verify_parser = subparsers.add_parser("verify", help="Verify a completed or failed evidence bundle.")
    verify_parser.add_argument("--run-dir", required=True, type=Path)

    export_parser = subparsers.add_parser("export", help="Export a verified run without private local paths.")
    export_parser.add_argument("--run-dir", required=True, type=Path)
    export_parser.add_argument("--output-dir", required=True, type=Path)

    verify_public_parser = subparsers.add_parser("verify-public", help="Verify an exported public evidence bundle.")
    verify_public_parser.add_argument("--evidence-dir", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "inspect":
        payload = inspect_archive(args.archive)
        payload["manifest_payload_sha256"] = _payload_sha256(payload)
        _write_json(args.output, payload)
        print(args.output.resolve())
    elif args.command == "prepare":
        prepare_source(args.archive, args.destination, args.output)
        print(args.output.resolve())
    elif args.command == "run":
        manifest = run_case(args.archive, args.python, args.output_root, args.timeout)
        print(manifest)
        return 0 if json.loads(manifest.read_text(encoding="utf-8"))["status"] == "succeeded" else 1
    elif args.command == "verify":
        print(json.dumps(verify_run(args.run_dir), indent=2))
    elif args.command == "export":
        print(export_public_evidence(args.run_dir, args.output_dir))
    else:
        print(json.dumps(verify_public_evidence(args.evidence_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
