"""Check release archives for required package data and forbidden local files."""

from __future__ import annotations

import argparse
import hashlib
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
    "docs/ANNOTATION_PROTOCOL.md",
    "docs/JUDGE_BATCH.md",
    "docs/PROJECT_PROPOSAL_CN.md",
    "docs/reproscope/RELEASE_EVIDENCE_0.15_CN.md",
}
REQUIRED_SDIST_FILES = {
    "CHANGELOG.md",
    "examples/annotations/synthetic_annotation_bundle.json",
    "examples/dataset/adversarial_case.json",
    "examples/dataset/adversarial_mutation.json",
    "examples/dataset/adversarial_report.md",
    "examples/dataset/sample_adversarial_dataset.json",
    "requirements.lock",
}
FORBIDDEN_SDIST_PATHS = {
    "PR_DESCRIPTION_CN.md",
}
FORBIDDEN_SDIST_SUFFIXES = {".mp4"}


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
