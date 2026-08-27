from __future__ import annotations

import json

import pytest

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.errors import PathPolicyError
from hy3_reproscope_mcp.execution import preflight_third_party_execution
from hy3_reproscope_mcp.repository_scanner import audit_repository as scan_repository
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import audit_repository


def _settings(tmp_path) -> Settings:
    return Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(tmp_path),
        REPROSCOPE_WORKSPACE=tmp_path / "artifacts",
    )


def test_repository_audit_extracts_static_reproducibility_conditions(tmp_path) -> None:
    repository = tmp_path / "sample-repository"
    source_dir = repository / "src" / "sample"
    source_dir.mkdir(parents=True)
    (repository / "pyproject.toml").write_text(
        """
[project]
name = "sample"
requires-python = ">=3.11"
dependencies = [
  "pydantic>=2",
  "numpy==2.0.0",
  "private-lib @ https://user:secret@example.invalid/private.whl",
]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
sample-cli = "sample.main:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
""".strip(),
        encoding="utf-8",
    )
    (repository / "uv.lock").write_text("version = 1\nrevision = 1\n", encoding="utf-8")
    (repository / "README.md").write_text(
        """
# Sample

```bash
python -m pip install --extra-index-url https://user:secret@example.invalid/simple -e .
python -m pytest -q
```
""".strip(),
        encoding="utf-8",
    )
    (repository / ".env.example").write_text(
        "SERVICE_ENDPOINT=https://example.invalid\nAPI_TOKEN=replace-me\n",
        encoding="utf-8",
    )
    (repository / ".env").write_text("REAL_SECRET=must-not-be-read\n", encoding="utf-8")
    (source_dir / "main.py").write_text(
        """
import os
from pydantic import Field

ENDPOINT = os.getenv("SERVICE_ENDPOINT")
TOKEN = os.environ["API_TOKEN"]
ALIAS = Field(validation_alias="MODEL_NAME")

def main() -> None:
    return None

if __name__ == "__main__":
    main()
""".strip(),
        encoding="utf-8",
    )
    app = AppContext(settings=_settings(tmp_path))

    result = audit_repository(app, repository_path=str(repository), max_python_files=50)

    assert result.executed_repository_code is False
    assert result.execution_policy == "static_read_only"
    assert result.execution_preflight.status == "not_requested"
    assert result.execution_preflight.executed is False
    assert result.repository_root == "sample-repository"
    assert result.package_managers == ["pip", "uv"]
    assert result.python_requirement == ">=3.11"
    assert [(item.name, item.constraint, item.pinned) for item in result.dependencies] == [
        ("numpy", "==2.0.0", True),
        ("private-lib", "<direct-reference>", False),
        ("pydantic", ">=2", False),
        ("pytest", ">=8", False),
    ]
    assert result.metrics.dependency_count == 4
    assert result.metrics.pinned_dependency_ratio == 0.25
    assert result.metrics.has_lockfile is True
    assert result.metrics.has_python_requirement is True
    assert result.metrics.has_install_instructions is True
    assert result.metrics.has_test_configuration is True
    assert result.metrics.has_test_instructions is True
    assert result.metrics.has_declared_entrypoint is True
    assert result.metrics.environment_example_present is True
    assert {entrypoint.kind for entrypoint in result.entrypoints} == {"console_script", "python_main_guard"}
    assert [signal.name for signal in result.environment_variables] == [
        "API_TOKEN",
        "MODEL_NAME",
        "SERVICE_ENDPOINT",
    ]
    inspected_paths = {item.relative_path for item in result.inspected_files}
    assert ".env" not in inspected_paths
    assert ".env.example" in inspected_paths
    assert all("must-not-be-read" not in source.model_dump_json() for source in result.sources)
    assert result.install_commands == ["python -m pip install --extra-index-url <redacted> -e ."]
    assert "user:secret" not in result.model_dump_json()
    assert not any(gap.code == "LOCKFILE_NOT_FOUND" for gap in result.gaps)
    assert not any(gap.code == "ENVIRONMENT_EXAMPLE_NOT_FOUND" for gap in result.gaps)
    assert result.artifact_integrity is not None
    assert len(result.artifacts) == 2
    artifact_path = tmp_path / "artifacts" / result.artifacts[0].relative_path
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["executed_repository_code"] is False
    assert "REAL_SECRET" not in artifact_path.read_text(encoding="utf-8")
    assert "user:secret" not in artifact_path.read_text(encoding="utf-8")


def test_repository_scan_reports_bounded_and_malformed_inputs(tmp_path) -> None:
    repository = tmp_path / "bounded"
    repository.mkdir()
    (repository / "pyproject.toml").write_text("[project\nname = 'broken'\n", encoding="utf-8")
    (repository / "a.py").write_text("import os\nVALUE = os.getenv('FIRST_NAME')\n", encoding="utf-8")
    (repository / "b.py").write_text("import os\nVALUE = os.getenv('SECOND_NAME')\n", encoding="utf-8")

    result = scan_repository(
        run_id="repository_test",
        repository_path=str(repository),
        settings=_settings(tmp_path),
        max_python_files=1,
    )

    assert result.metrics.scan_truncated is True
    assert result.metrics.python_file_count == 1
    assert [signal.name for signal in result.environment_variables] == ["FIRST_NAME"]
    assert any(warning.code == "REPOSITORY_SCAN_TRUNCATED" for warning in result.warnings)
    assert any(warning.code == "REPOSITORY_TOML_PARSE_ERROR" for warning in result.warnings)
    assert any(gap.code == "REPOSITORY_SCAN_INCOMPLETE" for gap in result.gaps)
    pyproject = next(item for item in result.inspected_files if item.relative_path == "pyproject.toml")
    assert pyproject.parsed is False


def test_repository_scan_excludes_local_environment_and_validation_directories(tmp_path) -> None:
    repository = tmp_path / "clean-scope"
    repository.mkdir()
    (repository / "main.py").write_text("import os\nVALUE = os.getenv('PROJECT_VALUE')\n", encoding="utf-8")
    excluded_directories = [".test-tmp", ".verify-venv", ".audit-pytest-worker", ".venv", "venv"]
    for directory_name in excluded_directories:
        directory = repository / directory_name
        directory.mkdir()
        (directory / "leaked.py").write_text(
            "import os\nVALUE = os.getenv('SHOULD_NOT_BE_SCANNED')\n",
            encoding="utf-8",
        )

    result = scan_repository(
        run_id="repository_clean_scope",
        repository_path=str(repository),
        settings=_settings(tmp_path),
    )

    assert result.metrics.python_file_count == 1
    assert result.metrics.scan_truncated is False
    assert [signal.name for signal in result.environment_variables] == ["PROJECT_VALUE"]
    assert all(
        not item.relative_path.startswith(tuple(f"{name}/" for name in excluded_directories))
        for item in result.inspected_files
    )


def test_requirements_lock_is_parsed_as_exact_pip_lockfile(tmp_path) -> None:
    repository = tmp_path / "locked"
    repository.mkdir()
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "locked"\nrequires-python = ">=3.11"\ndependencies = ["pydantic>=2"]\n',
        encoding="utf-8",
    )
    (repository / "requirements.lock").write_text(
        'pydantic==2.13.4\npywin32==312; sys_platform == "win32"\n',
        encoding="utf-8",
    )

    result = scan_repository(
        run_id="repository_requirements_lock",
        repository_path=str(repository),
        settings=_settings(tmp_path),
    )

    assert result.metrics.has_lockfile is True
    assert result.package_managers == ["pip"]
    locked = [dependency for dependency in result.dependencies if dependency.source_path == "requirements.lock"]
    assert [(dependency.name, dependency.constraint, dependency.pinned) for dependency in locked] == [
        ("pydantic", "==2.13.4", True),
        ("pywin32", '==312; sys_platform == "win32"', True),
    ]
    assert not any(gap.code in {"LOCKFILE_NOT_FOUND", "DEPENDENCIES_NOT_FULLY_PINNED"} for gap in result.gaps)
    assert any(gap.code == "DOWNLOAD_HASHES_NOT_LOCKED" for gap in result.gaps)


def test_requirements_lock_records_download_hash_presence(tmp_path) -> None:
    repository = tmp_path / "hashed"
    repository.mkdir()
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "hashed"\nrequires-python = ">=3.11"\ndependencies = ["pydantic==2.13.4"]\n',
        encoding="utf-8",
    )
    (repository / "requirements.lock").write_text(
        "pydantic==2.13.4 \\\n  --hash=sha256:" + "a" * 64 + "\n",
        encoding="utf-8",
    )

    result = scan_repository(
        run_id="repository_hashed_lock",
        repository_path=str(repository),
        settings=_settings(tmp_path),
    )

    assert result.metrics.has_download_hashes is True
    assert result.metrics.download_hash_count == 1
    assert result.metrics.download_hash_coverage == 1
    assert result.metrics.download_hashes_complete is True
    assert not any(gap.code == "DOWNLOAD_HASHES_NOT_LOCKED" for gap in result.gaps)


def test_pyproject_url_fragment_download_hash_is_detected(tmp_path) -> None:
    repository = tmp_path / "fragment-hashed"
    repository.mkdir()
    digest = "b" * 64
    (repository / "pyproject.toml").write_text(
        "[project]\n"
        'name = "fragment-hashed"\n'
        'requires-python = ">=3.11"\n'
        f'dependencies = ["demo @ https://example.invalid/demo.whl#sha256={digest}"]\n',
        encoding="utf-8",
    )
    (repository / "requirements.lock").write_text("demo==1.0.0\n", encoding="utf-8")

    result = scan_repository(
        run_id="repository_fragment_hash",
        repository_path=str(repository),
        settings=_settings(tmp_path),
    )

    assert result.metrics.has_download_hashes is True
    assert result.metrics.download_hashes_complete is True
    assert not any(gap.code == "DOWNLOAD_HASHES_NOT_LOCKED" for gap in result.gaps)


def test_partial_download_hash_coverage_remains_a_lock_gap(tmp_path) -> None:
    repository = tmp_path / "partially-hashed"
    repository.mkdir()
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "partially-hashed"\nrequires-python = ">=3.11"\n'
        'dependencies = ["pydantic==2.13.4", "numpy==2.0.0"]\n',
        encoding="utf-8",
    )
    (repository / "requirements.lock").write_text(
        "pydantic==2.13.4 \\\n  --hash=sha256:" + "a" * 64 + "\nnumpy==2.0.0\n",
        encoding="utf-8",
    )

    result = scan_repository(
        run_id="repository_partial_hash",
        repository_path=str(repository),
        settings=_settings(tmp_path),
    )

    assert result.metrics.has_download_hashes is True
    assert result.metrics.download_hash_count == 1
    assert result.metrics.download_hash_coverage == 0.5
    assert result.metrics.download_hashes_complete is False
    assert any(gap.code == "DOWNLOAD_HASHES_NOT_LOCKED" for gap in result.gaps)


def test_repository_with_only_readme_does_not_count_as_project_metadata(tmp_path) -> None:
    repository = tmp_path / "readme-only"
    repository.mkdir()
    (repository / "README.md").write_text("# Notes\n", encoding="utf-8")

    result = scan_repository(
        run_id="repository_readme_only",
        repository_path=str(repository),
        settings=_settings(tmp_path),
    )

    assert result.metrics.metadata_file_count == 0
    assert any(gap.code == "MISSING_PROJECT_METADATA" for gap in result.gaps)


def test_repository_audit_rejects_directory_outside_allowed_roots(tmp_path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    settings = Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(allowed),
        REPROSCOPE_WORKSPACE=allowed / "artifacts",
    )

    with pytest.raises(PathPolicyError, match="outside REPROSCOPE_ALLOWED_ROOTS"):
        scan_repository(
            run_id="repository_outside",
            repository_path=str(outside),
            settings=settings,
        )


def test_third_party_execution_preflight_is_default_deny_and_non_executing() -> None:
    preflight = preflight_third_party_execution("python train.py --epochs 2", allowed_root="repo")

    assert preflight.status == "denied"
    assert preflight.requested is True
    assert preflight.command_hash is not None
    assert preflight.allowed_root == "repo"
    assert preflight.sandbox_required is True
    assert preflight.network_access == "disabled"
    assert preflight.credentials_available is False
    assert preflight.executed is False


def test_repository_tool_records_requested_execution_without_running_it(tmp_path) -> None:
    repository = tmp_path / "execution-request"
    repository.mkdir()
    (repository / "pyproject.toml").write_text(
        '[project]\nname = "execution-request"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )

    result = audit_repository(
        AppContext(settings=_settings(tmp_path)),
        repository_path=str(repository),
        execution_command="python train.py --epochs 2",
    )

    assert result.execution_preflight.status == "denied"
    assert result.execution_preflight.requested is True
    assert result.execution_preflight.executed is False
    assert result.execution_preflight.allowed_root == "execution-request"
