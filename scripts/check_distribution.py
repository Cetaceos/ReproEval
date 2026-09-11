"""Check release archives for required package data and forbidden local files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from pathlib import Path

from hy3_reproeval import __version__

FORBIDDEN_PARTS = {
    ".env",
    ".venv",
    ".vscode",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
}
REQUIRED_PACKAGE_DATA = {
    "hy3_reproeval": {
        "data/adjudicator_guide_cn.md",
        "data/rubric.yaml",
    },
    "hy3_reproscope_mcp": {
        "profiles/isac_phy/data/assumptions.json",
        "profiles/isac_phy/data/metrics.json",
        "profiles/isac_phy/data/risk_rules.json",
        "profiles/isac_phy/data/taxonomy.json",
    },
}
REQUIRED_SDIST_DOCS = {
    "docs/ADVERSARIAL_PROTOCOL.md",
    "docs/ANNOTATION_PACKET.md",
    "docs/ANNOTATION_PROTOCOL.md",
    "docs/DATASET_FREEZE.md",
    "docs/DIFFERT2D_REPRODUCTION_PROTOCOL_CN.md",
    "docs/JUDGE_BATCH.md",
    "docs/P0_DATASET.md",
    "docs/REAL_PAPER_HUMAN_VALIDATION_CN.md",
    "docs/REAL_PAPER_PILOT.md",
    "docs/REAL_PAPER_JUDGE_EXPERIMENT_CN.md",
    "docs/REFERENCE_GENERATION_REVIEW_CN.md",
    "docs/STABILITY_PROTOCOL.md",
    "docs/WORKBUDDY_FINAL_DEMO_CN.md",
    "docs/PROJECT_PROPOSAL_CN.md",
    "docs/reproscope/RELEASE_EVIDENCE_0.15_CN.md",
}
REQUIRED_SDIST_FILES = {
    "CHANGELOG.md",
    "case_studies/differt2d_v0_3_4/README.md",
    "case_studies/differt2d_v0_3_4/RESULT.md",
    "case_studies/differt2d_v0_3_4/TRANSFER_SOURCE_EVIDENCE.md",
    "case_studies/differt2d_v0_3_4/experiment_protocol.json",
    "case_studies/differt2d_v0_3_4/source_manifest.json",
    "case_studies/differt2d_v0_3_4/scripts/capture_figure2.py",
    "case_studies/differt2d_v0_3_4/scripts/run_reproduction.py",
    "case_studies/differt2d_v0_3_4/evidence/environment.json",
    "case_studies/differt2d_v0_3_4/evidence/figure2_summary.csv",
    "case_studies/differt2d_v0_3_4/evidence/metrics.json",
    "case_studies/differt2d_v0_3_4/evidence/public_evidence_manifest.json",
    "case_studies/differt2d_v0_3_4/evidence/ris_power_map_reproduced.png",
    "case_studies/differt2d_v0_3_4/evidence/stderr.txt",
    "case_studies/differt2d_v0_3_4/evidence/stdout.txt",
    "examples/annotations/synthetic_annotation_bundle.json",
    "examples/dataset/adversarial_case.json",
    "examples/dataset/adversarial_mutation.json",
    "examples/dataset/adversarial_report.md",
    "examples/dataset/sample_adversarial_dataset.json",
    "examples/differt2d_uav_isac_target.md",
    "evals/p0_dataset/dataset.json",
    "evals/real_paper_pilot/dataset.json",
    "results/real_paper_judge/export_manifest.json",
    "results/real_paper_judge_figures/figure_manifest.json",
    "results/real_paper_human_consensus/export_manifest.json",
    "requirements.lock",
}
FORBIDDEN_SDIST_PATHS = {
    "PR_DESCRIPTION_CN.md",
}
FORBIDDEN_SDIST_SUFFIXES = {".mp4"}
_SAFE_API_KEY_PLACEHOLDERS = {"YOUR_HY3_API_KEY", "${HY3_API_KEY}"}
_PRIVATE_MCP_MARKERS = ("private-env", "workbuddy-mcp.ps1", "/users/", "/home/")
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[a-z]:/", re.IGNORECASE)


def _archive_names(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            return archive.getnames()
    raise ValueError(f"Unsupported distribution archive: {path.name}")


def _relative_package_data(names: list[str], package: str) -> set[str]:
    result: set[str] = set()
    marker = f"{package}/"
    for name in names:
        if marker in name:
            result.add(name.split(marker, 1)[1])
    return result


def _contains_archive_path(names: list[str], relative_path: str) -> bool:
    normalized_target = relative_path.replace("\\", "/")
    return any(name.replace("\\", "/").endswith(f"/{normalized_target}") for name in names)


def _archive_text(path: Path, relative_path: str) -> str:
    names = _archive_names(path)
    normalized_target = relative_path.replace("\\", "/")
    matches = [name for name in names if name.replace("\\", "/").endswith(f"/{normalized_target}")]
    if len(matches) != 1:
        raise ValueError(f"Expected one {relative_path} in {path.name}, found {len(matches)}")
    member = matches[0]
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.read(member).decode("utf-8")
    with tarfile.open(path, "r:gz") as archive:
        handle = archive.extractfile(member)
        if handle is None:
            raise ValueError(f"Could not read {relative_path} from {path.name}")
        return handle.read().decode("utf-8")


def _validate_public_mcp_config(payload: object) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("mcpServers"), dict):
        raise ValueError(".mcp.json must contain an mcpServers object")
    servers = payload["mcpServers"]
    if not servers:
        raise ValueError(".mcp.json must declare at least one MCP server")
    for server_name, server in servers.items():
        if not isinstance(server, dict):
            raise ValueError(f"MCP server {server_name!r} must be an object")
        env = server.get("env")
        if not isinstance(env, dict):
            raise ValueError(f"MCP server {server_name!r} must contain an env object")
        if env.get("HY3_API_KEY") not in _SAFE_API_KEY_PLACEHOLDERS:
            raise ValueError(f"MCP server {server_name!r} must use a public HY3_API_KEY placeholder")
        for value in _string_values(server):
            normalized = value.replace("\\", "/").casefold()
            if any(marker in normalized for marker in _PRIVATE_MCP_MARKERS):
                raise ValueError(f"Private MCP path or launcher found for server {server_name!r}")
            if _WINDOWS_ABSOLUTE_PATH.match(normalized) and "/path/to/" not in normalized:
                raise ValueError(f"Machine-specific absolute path found for MCP server {server_name!r}")


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _string_values(child)]
    if isinstance(value, list):
        return [item for child in value for item in _string_values(child)]
    return []


def check_archive(path: Path) -> None:
    names = _archive_names(path)
    forbidden = [name for name in names if any(part in FORBIDDEN_PARTS for part in Path(name).parts)]
    if forbidden:
        raise ValueError(f"Forbidden local files in {path.name}: {', '.join(sorted(forbidden))}")
    if any(name.endswith(".pyc") for name in names):
        raise ValueError(f"Python bytecode found in {path.name}")
    if path.suffix == ".whl":
        missing = {
            package: sorted(required - _relative_package_data(names, package))
            for package, required in REQUIRED_PACKAGE_DATA.items()
        }
        missing = {package: paths for package, paths in missing.items() if paths}
        if missing:
            raise ValueError(f"Missing wheel package data in {path.name}: {missing}")
    elif path.name.endswith(".tar.gz"):
        missing_files = sorted(
            relative for relative in REQUIRED_SDIST_FILES if not _contains_archive_path(names, relative)
        )
        if missing_files:
            raise ValueError(f"Missing required sdist files in {path.name}: {', '.join(missing_files)}")
        missing_docs = sorted(
            relative for relative in REQUIRED_SDIST_DOCS if not _contains_archive_path(names, relative)
        )
        if missing_docs:
            raise ValueError(f"Missing release evidence docs in {path.name}: {', '.join(missing_docs)}")
        leaked = sorted(relative for relative in FORBIDDEN_SDIST_PATHS if _contains_archive_path(names, relative))
        if leaked:
            raise ValueError(f"Local-only docs found in {path.name}: {', '.join(leaked)}")
        large_media = sorted(name for name in names if Path(name).suffix.lower() in FORBIDDEN_SDIST_SUFFIXES)
        if large_media:
            raise ValueError(f"Repository-only media found in {path.name}: {', '.join(large_media)}")
        try:
            mcp_payload = json.loads(_archive_text(path, ".mcp.json"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid .mcp.json in {path.name}: {exc}") from exc
        _validate_public_mcp_config(mcp_payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist", type=Path)
    parser.add_argument("--version", default=__version__)
    args = parser.parse_args()
    wheel_name = f"-{args.version}-"
    sdist_name = f"-{args.version}.tar.gz"
    archives = sorted(
        [
            *args.dist.glob(f"*{wheel_name}*.whl"),
            *args.dist.glob(f"*{sdist_name}"),
        ]
    )
    if not archives:
        raise SystemExit(f"No {args.version} wheel or sdist found in {args.dist}")
    for archive in archives:
        check_archive(archive)
        print(f"{archive.name}\t{_sha256(archive)}")
    print(f"checked {len(archives)} distribution archives")


if __name__ == "__main__":
    main()
