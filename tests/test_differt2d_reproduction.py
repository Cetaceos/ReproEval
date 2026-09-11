from __future__ import annotations

import csv
import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest

from case_studies.differt2d_v0_3_4.scripts import capture_figure2 as capture
from case_studies.differt2d_v0_3_4.scripts import run_reproduction as runner


def _write_archive(path: Path, *, unsafe_name: str | None = None) -> None:
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(runner.ENTRYPOINT.as_posix(), b"print('fixed entrypoint')\n")
        bundle.writestr(runner.REFERENCE_IMAGE.as_posix(), b"reference-image")
        bundle.writestr(runner.LOCKFILE.as_posix(), b"locked-dependencies")
        if unsafe_name is not None:
            bundle.writestr(unsafe_name, b"escape")


def _bind_test_archive(monkeypatch: pytest.MonkeyPatch, archive: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        entrypoint = bundle.read(runner.ENTRYPOINT.as_posix())
        reference = bundle.read(runner.REFERENCE_IMAGE.as_posix())
        lockfile = bundle.read(runner.LOCKFILE.as_posix())
    monkeypatch.setattr(runner, "ARCHIVE_SIZE", archive.stat().st_size)
    monkeypatch.setattr(runner, "ARCHIVE_MD5", hashlib.md5(archive.read_bytes()).hexdigest().upper())
    monkeypatch.setattr(runner, "ARCHIVE_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest().upper())
    monkeypatch.setattr(runner, "ENTRYPOINT_SHA256", hashlib.sha256(entrypoint).hexdigest().upper())
    monkeypatch.setattr(runner, "REFERENCE_IMAGE_SHA256", hashlib.sha256(reference).hexdigest().upper())
    monkeypatch.setattr(runner, "LOCKFILE_SHA256", hashlib.sha256(lockfile).hexdigest().upper())


def _append_symlink(archive: Path, name: str, target: str, target_path: str | None = None) -> None:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr(info, target)
        if target_path is not None:
            bundle.writestr(target_path, b"target")


def test_source_manifest_and_runner_share_frozen_hashes() -> None:
    root = Path(__file__).resolve().parents[1] / "case_studies" / "differt2d_v0_3_4"
    source = json.loads((root / "source_manifest.json").read_text(encoding="utf-8"))
    protocol = json.loads((root / "experiment_protocol.json").read_text(encoding="utf-8"))

    assert source["archive"]["sha256_observed_2026_09_09"] == runner.ARCHIVE_SHA256
    assert source["entrypoint"]["sha256"] == runner.ENTRYPOINT_SHA256
    assert source["upstream_reference"]["sha256"] == runner.REFERENCE_IMAGE_SHA256
    assert source["environment"]["lockfile_sha256"] == runner.LOCKFILE_SHA256
    assert protocol["case_id"] == source["case_id"] == runner.CASE_ID
    assert protocol["execution_policy"]["entrypoint_allowlist"] == ["papers/joss/plot_ris_power_map.py"]


def test_committed_public_evidence_matches_protocol_and_locked_environment() -> None:
    evidence = Path(__file__).resolve().parents[1] / "case_studies" / "differt2d_v0_3_4" / "evidence"
    verification = runner.verify_public_evidence(evidence)
    environment = json.loads((evidence / "environment.json").read_text(encoding="utf-8"))
    serialized = (evidence / "public_evidence_manifest.json").read_text(encoding="utf-8")

    assert verification["outcome"] == "exact"
    assert verification["published_file_count"] == 6
    assert environment["python"]["version"] == "3.11.8"
    assert environment["python"]["executable"] == "<dedicated-python-path-omitted>"
    assert environment["packages"] == capture.EXPECTED_PACKAGES
    assert "HY3_API_KEY" not in serialized
    assert "E:" not in serialized
    assert "C:" not in serialized

    with (evidence / "figure2_summary.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["case_id"] == runner.CASE_ID
    assert rows[0]["power_grid_rows"] == "300"
    assert rows[0]["power_grid_columns"] == "300"
    assert rows[0]["pixel_mae"] == "0.0"
    assert rows[0]["pixel_exact"] == "True"


def test_flat_summary_is_derived_from_verified_metrics(tmp_path: Path) -> None:
    evidence = Path(__file__).resolve().parents[1] / "case_studies" / "differt2d_v0_3_4" / "evidence"
    metrics = json.loads((evidence / "metrics.json").read_text(encoding="utf-8"))
    output = tmp_path / "figure2_summary.csv"

    runner._write_result_summary_csv(output, metrics, duration_seconds=30.16)

    assert output.read_bytes() == (evidence / "figure2_summary.csv").read_bytes()


def test_inspect_and_safe_extract_verified_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "source.zip"
    _write_archive(archive)
    _bind_test_archive(monkeypatch, archive)

    inspected = runner.inspect_archive(archive)
    source_root = runner.safe_extract(archive, tmp_path / "source")

    assert inspected["status"] == "verified"
    assert inspected["archive"]["file_count"] == 3
    assert (source_root / "papers" / "joss" / "plot_ris_power_map.py").is_file()


def test_safe_internal_symlink_is_recorded_and_not_materialized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "source.zip"
    _write_archive(archive)
    link_name = f"{runner.ZIP_ROOT}/docs/link.txt"
    target_name = f"{runner.ZIP_ROOT}/target.txt"
    _append_symlink(archive, link_name, "../target.txt", target_name)
    _bind_test_archive(monkeypatch, archive)

    inspected = runner.inspect_archive(archive)
    source_root = runner.safe_extract(archive, tmp_path / "source")

    assert inspected["archive"]["skipped_internal_symlinks"] == [{"path": link_name, "resolved_target": target_name}]
    assert not (source_root / "docs" / "link.txt").exists()
    assert (source_root / "target.txt").read_bytes() == b"target"


def test_escaping_symlink_target_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "source.zip"
    _write_archive(archive)
    _append_symlink(archive, f"{runner.ZIP_ROOT}/docs/link.txt", "../../../escape.txt")
    _bind_test_archive(monkeypatch, archive)

    with pytest.raises(runner.ProtocolError, match="escapes the source root"):
        runner.inspect_archive(archive)


@pytest.mark.parametrize("unsafe_name", ["../escape.txt", "/absolute.txt"])
def test_inspect_rejects_unsafe_zip_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsafe_name: str,
) -> None:
    archive = tmp_path / "unsafe.zip"
    _write_archive(archive, unsafe_name=unsafe_name)
    _bind_test_archive(monkeypatch, archive)

    with pytest.raises(runner.ProtocolError, match="unsafe ZIP member path"):
        runner.inspect_archive(archive)


def test_sanitized_environment_drops_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HY3_API_KEY", "must-not-leak")
    monkeypatch.setenv("UNRELATED_VALUE", "also-not-inherited")

    environment, rejected = runner._sanitized_environment(tmp_path)

    assert "HY3_API_KEY" not in environment
    assert "UNRELATED_VALUE" not in environment
    assert "HY3_API_KEY" in rejected
    assert environment["JAX_PLATFORM_NAME"] == "cpu"
    assert environment["MPLBACKEND"] == "Agg"


def test_evidence_writers_use_repository_lf_bytes(tmp_path: Path) -> None:
    json_path = tmp_path / "evidence.json"
    text_path = tmp_path / "stdout.txt"

    runner._write_json(json_path, {"message": "line one\r\nline two"})
    runner._write_text(text_path, "line one\r\nline two\r")

    assert b"\r" not in json_path.read_bytes()
    assert text_path.read_bytes() == b"line one\nline two\n"


def test_verify_run_rejects_tampered_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    artifact = evidence / "metrics.json"
    artifact.write_text('{"result": "original"}\n', encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "case_id": runner.CASE_ID,
        "run_id": "test-run",
        "outcome": "exact",
        "artifacts": [
            {
                "path": "metrics.json",
                "size_bytes": artifact.stat().st_size,
                "sha256": runner._digest(artifact),
            }
        ],
    }
    manifest["manifest_payload_sha256"] = runner._payload_sha256(manifest)
    runner._write_json(evidence / "run_manifest.json", manifest)
    artifact.write_text('{"result": "tampered"}\n', encoding="utf-8")

    with pytest.raises(runner.ProtocolError, match="size or SHA-256"):
        runner.verify_run(evidence)


def test_verify_run_rejects_tampered_manifest(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    manifest = {
        "schema_version": "1.0",
        "case_id": runner.CASE_ID,
        "run_id": "test-run",
        "outcome": "failed",
        "artifacts": [],
    }
    manifest["manifest_payload_sha256"] = runner._payload_sha256(manifest)
    manifest["outcome"] = "exact"
    runner._write_json(evidence / "run_manifest.json", manifest)

    with pytest.raises(runner.ProtocolError, match="canonical payload"):
        runner.verify_run(evidence)


def test_verify_public_evidence_rejects_tampered_file(tmp_path: Path) -> None:
    evidence = tmp_path / "public"
    evidence.mkdir()
    result = evidence / "metrics.json"
    result.write_text('{"outcome": "exact"}\n', encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "case_id": runner.CASE_ID,
        "run_id": "public-test-run",
        "outcome": "exact",
        "published_files": [
            {
                "path": result.name,
                "size_bytes": result.stat().st_size,
                "sha256": runner._digest(result),
            }
        ],
    }
    manifest["manifest_payload_sha256"] = runner._payload_sha256(manifest)
    runner._write_json(evidence / "public_evidence_manifest.json", manifest)
    result.write_text('{"outcome": "changed"}\n', encoding="utf-8")

    with pytest.raises(runner.ProtocolError, match="published evidence failed"):
        runner.verify_public_evidence(evidence)


def test_run_case_records_source_validation_failure(tmp_path: Path) -> None:
    invalid_archive = tmp_path / "invalid.zip"
    invalid_archive.write_bytes(b"not-the-frozen-archive")

    manifest_path = runner.run_case(
        invalid_archive,
        tmp_path / "missing-python.exe",
        tmp_path / "runs",
        timeout=1,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verification = runner.verify_run(manifest_path.parent)

    assert manifest["status"] == "failed"
    assert manifest["outcome"] == "failed"
    assert manifest["source"]["status"] == "failed"
    assert manifest["execution"]["exit_code"] is None
    assert "archive size or digest" in manifest["execution"]["error"]
    assert verification["status"] == "verified"
