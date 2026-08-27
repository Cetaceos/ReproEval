"""Bounded static scanning for repository reproducibility conditions."""

from __future__ import annotations

import ast
import configparser
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .config import Settings
from .models import SourceReference, SourceType, ToolWarning
from .repository_models import (
    EnvironmentVariableSignal,
    RepositoryAuditGap,
    RepositoryAuditResult,
    RepositoryDependency,
    RepositoryEntrypoint,
    RepositoryFileKind,
    RepositoryGapSeverity,
    RepositoryInspectedFile,
    RepositoryReadinessMetrics,
)
from .workspace import Workspace, make_relative_path, sha256_bytes

MAX_REPOSITORY_FILE_BYTES = 2 * 1024 * 1024
MAX_REPOSITORY_TOTAL_BYTES = 12 * 1024 * 1024
DEFAULT_MAX_PYTHON_FILES = 200
EXCLUDED_DIRECTORY_NAMES = {
    ".audit-pytest",
    ".git",
    ".hy3-reproscope",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".test-tmp",
    ".venv",
    ".verify-venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "site-packages",
    "venv",
}
EXCLUDED_DIRECTORY_PREFIXES = (".audit-pytest",)
LOCKFILE_NAMES = {
    "conda-lock.yml",
    "conda-lock.yaml",
    "pipfile.lock",
    "poetry.lock",
    "pdm.lock",
    "requirements.lock",
    "uv.lock",
}
ROOT_FILE_KINDS = {
    ".env.example": RepositoryFileKind.ENVIRONMENT_EXAMPLE,
    "environment.yml": RepositoryFileKind.DEPENDENCY_SPEC,
    "environment.yaml": RepositoryFileKind.DEPENDENCY_SPEC,
    "pipfile": RepositoryFileKind.DEPENDENCY_SPEC,
    "pyproject.toml": RepositoryFileKind.PROJECT_MANIFEST,
    "pytest.ini": RepositoryFileKind.TEST_CONFIGURATION,
    "setup.cfg": RepositoryFileKind.PROJECT_MANIFEST,
    "setup.py": RepositoryFileKind.PROJECT_MANIFEST,
    "tox.ini": RepositoryFileKind.TEST_CONFIGURATION,
}
SAFE_COMMAND_PREFIXES = (
    "conda ",
    "nox",
    "pip ",
    "poetry ",
    "pytest",
    "python -m pip ",
    "python -m pytest",
    "tox",
    "uv ",
)
ENVIRONMENT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
REQUIREMENT_NAME_PATTERN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
DOWNLOAD_HASH_PATTERN = re.compile(
    r"(?i)(?:--hash\s*(?:=|\s+)\s*sha256:|\bhash\s*=\s*[\"']?sha256:|[#&?]sha256=)([0-9a-f]{64})"
)
INVALID_DOWNLOAD_HASH_PATTERN = re.compile(r"(?i)(?:--hash\s*(?:=|\s+)\s*sha256:|[#&?]sha256=)([0-9a-f]+)")


@dataclass
class _ScanState:
    sources: list[SourceReference] = field(default_factory=list)
    warnings: list[ToolWarning] = field(default_factory=list)
    inspected_files: list[RepositoryInspectedFile] = field(default_factory=list)
    dependencies: list[RepositoryDependency] = field(default_factory=list)
    entrypoints: list[RepositoryEntrypoint] = field(default_factory=list)
    environment_sources: dict[str, set[str]] = field(default_factory=dict)
    install_commands: set[str] = field(default_factory=set)
    test_commands: set[str] = field(default_factory=set)
    package_managers: set[str] = field(default_factory=set)
    python_requirement: str | None = None
    has_test_configuration: bool = False
    environment_example_present: bool = False
    download_hashes_present: bool = False
    download_hash_dependencies: set[str] = field(default_factory=set)
    scan_truncated: bool = False
    total_bytes: int = 0


def audit_repository(
    *,
    run_id: str,
    repository_path: str,
    settings: Settings,
    max_python_files: int = DEFAULT_MAX_PYTHON_FILES,
) -> RepositoryAuditResult:
    """Statically inspect bounded repository metadata without executing repository code."""

    workspace = Workspace(settings)
    repository_root = workspace.resolve_input_directory(repository_path)
    state = _ScanState()
    candidates, python_candidates = _discover_candidates(repository_root, max_python_files=max_python_files)
    state.scan_truncated = python_candidates > max_python_files
    if state.scan_truncated:
        state.warnings.append(
            ToolWarning(
                code="REPOSITORY_SCAN_TRUNCATED",
                message=f"Python source scan was limited to the first {max_python_files} files.",
            )
        )

    max_file_bytes = min(settings.reproscope_max_file_mb * 1024 * 1024, MAX_REPOSITORY_FILE_BYTES)
    for candidate, kind in candidates:
        if state.total_bytes >= MAX_REPOSITORY_TOTAL_BYTES:
            state.scan_truncated = True
            state.warnings.append(
                ToolWarning(
                    code="REPOSITORY_TOTAL_BYTES_LIMIT",
                    message="Repository scan stopped after reaching its deterministic total-byte limit.",
                )
            )
            break
        _inspect_candidate(
            candidate,
            kind=kind,
            repository_root=repository_root,
            workspace=workspace,
            state=state,
            max_file_bytes=max_file_bytes,
        )

    dependencies = _deduplicate_dependencies(state.dependencies)
    entrypoints = _deduplicate_entrypoints(state.entrypoints)
    environment_variables = [
        EnvironmentVariableSignal(name=name, source_paths=sorted(paths))
        for name, paths in sorted(state.environment_sources.items())
    ]
    metadata_file_count = sum(
        file.kind
        in {
            RepositoryFileKind.PROJECT_MANIFEST,
            RepositoryFileKind.DEPENDENCY_SPEC,
            RepositoryFileKind.LOCKFILE,
        }
        for file in state.inspected_files
    )
    python_file_count = sum(file.kind is RepositoryFileKind.PYTHON_SOURCE for file in state.inspected_files)
    pinned_count = sum(dependency.pinned for dependency in dependencies)
    dependency_names = {_normalized_dependency_name(dependency.name) for dependency in dependencies}
    hashed_dependency_names = dependency_names & state.download_hash_dependencies
    download_hash_count = len(hashed_dependency_names)
    metrics = RepositoryReadinessMetrics(
        metadata_file_count=metadata_file_count,
        python_file_count=python_file_count,
        dependency_count=len(dependencies),
        pinned_dependency_ratio=_ratio(pinned_count, len(dependencies)),
        has_lockfile=any(file.kind is RepositoryFileKind.LOCKFILE for file in state.inspected_files),
        has_download_hashes=state.download_hashes_present,
        download_hash_count=download_hash_count,
        download_hash_coverage=_ratio(download_hash_count, len(dependency_names)) if dependency_names else None,
        download_hashes_complete=bool(dependency_names) and dependency_names <= state.download_hash_dependencies,
        has_python_requirement=state.python_requirement is not None,
        has_install_instructions=bool(state.install_commands),
        has_test_configuration=state.has_test_configuration,
        has_test_instructions=bool(state.test_commands),
        has_declared_entrypoint=bool(entrypoints),
        environment_example_present=state.environment_example_present,
        scan_truncated=state.scan_truncated,
    )
    gaps = _build_gaps(metrics=metrics, environment_variables=environment_variables)
    summary = (
        f"Statically inspected {len(state.inspected_files)} files, found {len(dependencies)} dependencies, "
        f"{len(entrypoints)} entrypoints, {len(environment_variables)} environment-variable names, "
        f"and {len(gaps)} reproducibility gaps without executing repository code."
    )
    return RepositoryAuditResult(
        run_id=run_id,
        repository_root=make_relative_path(repository_root, workspace.allowed_roots),
        summary=summary,
        package_managers=sorted(state.package_managers),
        python_requirement=state.python_requirement,
        dependencies=dependencies,
        entrypoints=entrypoints,
        environment_variables=environment_variables,
        install_commands=sorted(state.install_commands),
        test_commands=sorted(state.test_commands),
        inspected_files=state.inspected_files,
        gaps=gaps,
        metrics=metrics,
        sources=state.sources,
        warnings=state.warnings,
    )


def _discover_candidates(
    repository_root: Path,
    *,
    max_python_files: int,
) -> tuple[list[tuple[Path, RepositoryFileKind]], int]:
    metadata: dict[Path, RepositoryFileKind] = {}
    for path in repository_root.iterdir():
        if not path.is_file() or path.is_symlink():
            continue
        name = path.name.lower()
        if name in LOCKFILE_NAMES:
            metadata[path] = RepositoryFileKind.LOCKFILE
        elif name in ROOT_FILE_KINDS:
            metadata[path] = ROOT_FILE_KINDS[name]
        elif name.startswith("requirements") and path.suffix.lower() in {".in", ".txt"}:
            metadata[path] = RepositoryFileKind.DEPENDENCY_SPEC
        elif name.startswith("readme"):
            metadata[path] = RepositoryFileKind.DOCUMENTATION

    python_paths = _discover_python_paths(repository_root, metadata_paths=set(metadata))
    selected_python = python_paths[:max_python_files]
    candidates = sorted(metadata.items(), key=lambda item: item[0].name.lower())
    candidates.extend((path, RepositoryFileKind.PYTHON_SOURCE) for path in selected_python)
    return candidates, len(python_paths)


def _discover_python_paths(repository_root: Path, *, metadata_paths: set[Path]) -> list[Path]:
    python_paths: list[Path] = []
    for current_root, directory_names, file_names in os.walk(repository_root, followlinks=False):
        current_path = Path(current_root)
        directory_names[:] = sorted(
            (
                name
                for name in directory_names
                if not _is_excluded_directory(name) and not (current_path / name).is_symlink()
            ),
            key=str.lower,
        )
        for file_name in sorted(file_names, key=str.lower):
            path = current_path / file_name
            if path.suffix.lower() == ".py" and not path.is_symlink() and path not in metadata_paths:
                python_paths.append(path)
    return python_paths


def _is_excluded_directory(name: str) -> bool:
    normalized = name.casefold()
    return normalized in EXCLUDED_DIRECTORY_NAMES or normalized.startswith(EXCLUDED_DIRECTORY_PREFIXES)


def _inspect_candidate(
    path: Path,
    *,
    kind: RepositoryFileKind,
    repository_root: Path,
    workspace: Workspace,
    state: _ScanState,
    max_file_bytes: int,
) -> None:
    resolved = path.resolve()
    try:
        relative_path = resolved.relative_to(repository_root).as_posix()
    except ValueError:
        state.warnings.append(
            ToolWarning(
                code="REPOSITORY_PATH_ESCAPE_SKIPPED",
                message=f"Skipped a repository path that resolved outside the repository root: {path.name}",
            )
        )
        return
    size_bytes = resolved.stat().st_size
    if size_bytes > max_file_bytes:
        state.scan_truncated = True
        state.warnings.append(
            ToolWarning(
                code="REPOSITORY_FILE_TOO_LARGE",
                message=f"Skipped repository file above the static scan limit: {relative_path}",
            )
        )
        return
    if state.total_bytes + size_bytes > MAX_REPOSITORY_TOTAL_BYTES:
        state.scan_truncated = True
        state.total_bytes = MAX_REPOSITORY_TOTAL_BYTES
        state.warnings.append(
            ToolWarning(
                code="REPOSITORY_TOTAL_BYTES_LIMIT",
                message="Repository scan stopped before a file that would exceed its total-byte limit.",
            )
        )
        return

    content = resolved.read_bytes()
    state.total_bytes += len(content)
    source_id = f"repo_{len(state.sources) + 1}"
    source_type = _source_type(path)
    source_path = make_relative_path(resolved, workspace.allowed_roots)
    content_hash = sha256_bytes(content)
    reference = SourceReference(
        source_id=source_id,
        source_path=source_path,
        source_type=source_type,
        content_hash=content_hash,
    )
    state.sources.append(reference)
    parsed = True
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
        parsed = False
        state.warnings.append(
            ToolWarning(
                code="REPOSITORY_NON_UTF8_SKIPPED",
                message=f"Recorded but did not parse non-UTF-8 repository file: {relative_path}",
                source_references=[reference],
            )
        )
    state.inspected_files.append(
        RepositoryInspectedFile(
            source_id=source_id,
            relative_path=relative_path,
            kind=kind,
            content_hash=content_hash,
            size_bytes=size_bytes,
            parsed=parsed,
        )
    )
    if not parsed:
        return
    _parse_candidate(
        path,
        relative_path=relative_path,
        kind=kind,
        text=text,
        state=state,
        reference=reference,
    )


def _parse_candidate(
    path: Path,
    *,
    relative_path: str,
    kind: RepositoryFileKind,
    text: str,
    state: _ScanState,
    reference: SourceReference,
) -> None:
    name = path.name.lower()
    if kind is RepositoryFileKind.LOCKFILE:
        state.package_managers.add(_manager_for_lockfile(name))
        if _contains_download_hashes(text):
            state.download_hashes_present = True
        elif (
            name in LOCKFILE_NAMES
            and name != "requirements.lock"
            and state.dependencies
            and INVALID_DOWNLOAD_HASH_PATTERN.search(text)
        ):
            # The gap is emitted after all files are inspected; this warning is
            # only for malformed hash declarations and never executes pip.
            state.warnings.append(
                ToolWarning(
                    code="REPOSITORY_DOWNLOAD_HASH_INVALID",
                    message=f"A dependency lockfile contains a malformed SHA-256 download hash: {relative_path}",
                    source_references=[reference],
                )
            )
        if name == "requirements.lock":
            _parse_requirements(text, relative_path=relative_path, state=state)
    elif name == "pyproject.toml":
        if _contains_download_hashes(text):
            state.download_hashes_present = True
        _parse_pyproject(text, relative_path=relative_path, state=state, reference=reference)
    elif name == "setup.cfg":
        _parse_setup_cfg(text, relative_path=relative_path, state=state, reference=reference)
    elif name == "setup.py":
        _parse_python(text, relative_path=relative_path, state=state, reference=reference)
        state.package_managers.add("pip")
    elif name.startswith("requirements"):
        _parse_requirements(text, relative_path=relative_path, state=state)
        state.package_managers.add("pip")
    elif name in {"environment.yml", "environment.yaml"}:
        _parse_conda_environment(text, relative_path=relative_path, state=state)
        state.package_managers.add("conda")
    elif name == "pipfile":
        state.package_managers.add("pipenv")
    elif kind is RepositoryFileKind.ENVIRONMENT_EXAMPLE:
        state.environment_example_present = True
        _parse_environment_names(text, relative_path=relative_path, state=state)
    elif kind is RepositoryFileKind.DOCUMENTATION:
        _parse_documentation_commands(text, state=state)
    elif kind is RepositoryFileKind.TEST_CONFIGURATION:
        state.has_test_configuration = True
    elif kind is RepositoryFileKind.PYTHON_SOURCE:
        _parse_python(text, relative_path=relative_path, state=state, reference=reference)


def _parse_pyproject(
    text: str,
    *,
    relative_path: str,
    state: _ScanState,
    reference: SourceReference,
) -> None:
    try:
        payload = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        state.warnings.append(
            ToolWarning(
                code="REPOSITORY_TOML_PARSE_ERROR",
                message=f"Could not parse TOML metadata: {relative_path}",
                source_references=[reference],
            )
        )
        _mark_unparsed(state, relative_path)
        return
    state.package_managers.add("pip")
    project = payload.get("project", {})
    if isinstance(project, dict):
        python_requirement = project.get("requires-python")
        if isinstance(python_requirement, str) and python_requirement.strip():
            state.python_requirement = python_requirement.strip()
        dependencies = project.get("dependencies", [])
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if isinstance(dependency, str):
                    _append_dependency(state, dependency, group="runtime", source_path=relative_path)
        optional = project.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group, group_dependencies in optional.items():
                if isinstance(group_dependencies, list):
                    for dependency in group_dependencies:
                        if isinstance(dependency, str):
                            _append_dependency(
                                state,
                                dependency,
                                group=f"optional:{group}",
                                source_path=relative_path,
                            )
        for scripts_key, kind in (("scripts", "console_script"), ("gui-scripts", "gui_script")):
            scripts = project.get(scripts_key, {})
            if isinstance(scripts, dict):
                for script_name, target in scripts.items():
                    if isinstance(target, str):
                        state.entrypoints.append(
                            RepositoryEntrypoint(
                                name=str(script_name),
                                target=target,
                                kind=kind,
                                source_path=relative_path,
                            )
                        )
    tool = payload.get("tool", {})
    if isinstance(tool, dict):
        if "pytest" in tool:
            state.has_test_configuration = True
        poetry = tool.get("poetry")
        if isinstance(poetry, dict):
            state.package_managers.add("poetry")
            poetry_dependencies = poetry.get("dependencies", {})
            if isinstance(poetry_dependencies, dict):
                for name, constraint in poetry_dependencies.items():
                    if str(name).lower() == "python":
                        if state.python_requirement is None and isinstance(constraint, str):
                            state.python_requirement = constraint
                        continue
                    requirement = str(name)
                    if isinstance(constraint, str):
                        normalized_constraint = constraint.strip()
                        if normalized_constraint and normalized_constraint[0].isdigit():
                            normalized_constraint = f"=={normalized_constraint}"
                        requirement += normalized_constraint
                    _append_dependency(state, requirement, group="runtime", source_path=relative_path)
            poetry_scripts = poetry.get("scripts", {})
            if isinstance(poetry_scripts, dict):
                for script_name, target in poetry_scripts.items():
                    if isinstance(target, str):
                        state.entrypoints.append(
                            RepositoryEntrypoint(
                                name=str(script_name),
                                target=target,
                                kind="console_script",
                                source_path=relative_path,
                            )
                        )


def _parse_setup_cfg(
    text: str,
    *,
    relative_path: str,
    state: _ScanState,
    reference: SourceReference,
) -> None:
    parser = configparser.ConfigParser()
    try:
        parser.read_string(text)
    except configparser.Error:
        state.warnings.append(
            ToolWarning(
                code="REPOSITORY_CONFIG_PARSE_ERROR",
                message=f"Could not parse setup configuration: {relative_path}",
                source_references=[reference],
            )
        )
        _mark_unparsed(state, relative_path)
        return
    state.package_managers.add("pip")
    if parser.has_option("options", "python_requires") and state.python_requirement is None:
        state.python_requirement = parser.get("options", "python_requires").strip()
    if parser.has_option("options", "install_requires"):
        for dependency in parser.get("options", "install_requires").splitlines():
            _append_dependency(state, dependency, group="runtime", source_path=relative_path)
    section = "options.entry_points"
    if parser.has_option(section, "console_scripts"):
        for entrypoint in parser.get(section, "console_scripts").splitlines():
            if "=" not in entrypoint:
                continue
            name, target = entrypoint.split("=", 1)
            state.entrypoints.append(
                RepositoryEntrypoint(
                    name=name.strip(),
                    target=target.strip(),
                    kind="console_script",
                    source_path=relative_path,
                )
            )


def _parse_requirements(text: str, *, relative_path: str, state: _ScanState) -> None:
    current_dependency_name: str | None = None
    for line in text.splitlines():
        line_has_download_hash = _contains_download_hashes(line)
        if line_has_download_hash:
            state.download_hashes_present = True
            if current_dependency_name is not None:
                state.download_hash_dependencies.add(current_dependency_name)
        elif INVALID_DOWNLOAD_HASH_PATTERN.search(line):
            state.warnings.append(
                ToolWarning(
                    code="REPOSITORY_DOWNLOAD_HASH_INVALID",
                    message=f"A requirements file contains a malformed SHA-256 download hash: {relative_path}",
                )
            )
        normalized = line.split("#", 1)[0].strip()
        if not normalized or normalized.startswith(("-", "--", "git+", "http://", "https://")):
            continue
        _append_dependency(state, normalized, group="runtime", source_path=relative_path)
        match = REQUIREMENT_NAME_PATTERN.match(normalized)
        current_dependency_name = _normalized_dependency_name(match.group(1)) if match else None
        if line_has_download_hash and current_dependency_name is not None:
            state.download_hash_dependencies.add(current_dependency_name)


def _parse_conda_environment(text: str, *, relative_path: str, state: _ScanState) -> None:
    in_dependencies = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies:":
            in_dependencies = True
            continue
        if in_dependencies and line and not line.startswith((" ", "\t")):
            in_dependencies = False
        if in_dependencies and stripped.startswith("- "):
            dependency = stripped[2:].strip()
            if dependency and dependency != "pip:":
                match = REQUIREMENT_NAME_PATTERN.match(dependency)
                if match is not None and match.group(1).lower() == "python":
                    if state.python_requirement is None:
                        state.python_requirement = dependency[match.end() :].strip() or None
                    continue
                _append_dependency(state, dependency, group="conda", source_path=relative_path)


def _parse_environment_names(text: str, *, relative_path: str, state: _ScanState) -> None:
    for line in text.splitlines():
        normalized = line.strip()
        if not normalized or normalized.startswith("#") or "=" not in normalized:
            continue
        name = normalized.split("=", 1)[0].strip()
        if ENVIRONMENT_NAME_PATTERN.fullmatch(name):
            state.environment_sources.setdefault(name, set()).add(relative_path)


def _parse_documentation_commands(text: str, *, state: _ScanState) -> None:
    in_fence = False
    accepted_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                in_fence = False
                accepted_fence = False
            else:
                language = stripped[3:].strip().lower()
                in_fence = True
                accepted_fence = language in {"", "bash", "console", "powershell", "shell", "sh", "zsh"}
            continue
        if not in_fence or not accepted_fence:
            continue
        command = stripped.removeprefix("$").removeprefix(">").strip()
        lowered = command.lower()
        if not command or not lowered.startswith(SAFE_COMMAND_PREFIXES):
            continue
        command = _sanitize_documented_command(command)
        lowered = command.lower()
        if " install" in f" {lowered}" or lowered.startswith(("pip install", "uv sync", "poetry install")):
            state.install_commands.add(command)
        if lowered.startswith(("pytest", "python -m pytest", "tox", "nox")):
            state.test_commands.add(command)


def _parse_python(
    text: str,
    *,
    relative_path: str,
    state: _ScanState,
    reference: SourceReference,
) -> None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        state.warnings.append(
            ToolWarning(
                code="REPOSITORY_PYTHON_PARSE_ERROR",
                message=f"Could not statically parse Python source: {relative_path}",
                source_references=[reference],
            )
        )
        _mark_unparsed(state, relative_path)
        return
    for node in ast.walk(tree):
        environment_name = _environment_name_from_node(node)
        if environment_name is not None:
            state.environment_sources.setdefault(environment_name, set()).add(relative_path)
        if isinstance(node, ast.If) and _is_main_guard(node.test):
            state.entrypoints.append(
                RepositoryEntrypoint(
                    name=relative_path,
                    target=relative_path,
                    kind="python_main_guard",
                    source_path=relative_path,
                )
            )


def _environment_name_from_node(node: ast.AST) -> str | None:
    candidate: str | None = None
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.args:
            is_getenv = (
                isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "getenv"
            )
            is_environ_get = (
                isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "os"
                and node.func.value.attr == "environ"
                and node.func.attr == "get"
            )
            if is_getenv or is_environ_get:
                candidate = _literal_string(node.args[0])
        if candidate is None:
            for keyword in node.keywords:
                if keyword.arg == "validation_alias":
                    candidate = _literal_string(keyword.value)
                    break
    elif (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "os"
        and node.value.attr == "environ"
    ):
        candidate = _literal_string(node.slice)
    return candidate if candidate and ENVIRONMENT_NAME_PATTERN.fullmatch(candidate) else None


def _is_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
        return False
    values = [node.left, *node.comparators]
    return any(isinstance(value, ast.Name) and value.id == "__name__" for value in values) and any(
        _literal_string(value) == "__main__" for value in values
    )


def _append_dependency(
    state: _ScanState,
    requirement: str,
    *,
    group: str,
    source_path: str,
) -> None:
    normalized = requirement.strip()
    if not normalized:
        return
    match = REQUIREMENT_NAME_PATTERN.match(normalized)
    if match is None:
        return
    name = match.group(1)
    normalized_name = _normalized_dependency_name(name)
    if _contains_download_hashes(normalized):
        state.download_hashes_present = True
        state.download_hash_dependencies.add(normalized_name)
    constraint = normalized[match.end() :].strip() or None
    if constraint is not None and "://" in constraint:
        constraint = "<direct-reference>"
    state.dependencies.append(
        RepositoryDependency(
            name=name,
            constraint=constraint,
            group=group,
            source_path=source_path,
            pinned=_is_pinned(constraint),
        )
    )


def _is_pinned(constraint: str | None) -> bool:
    if constraint is None:
        return False
    normalized = constraint.replace(" ", "")
    normalized = re.sub(r"^\[[^\]]+\]", "", normalized)
    exact_pep = normalized.startswith(("==", "===")) and not normalized.endswith(".*")
    exact_conda = normalized.startswith("=") and not normalized.startswith(("==", "=>", "=<", "=!"))
    exact_poetry = re.fullmatch(r"\d+(?:\.\d+)*(?:[A-Za-z0-9.-]+)?", normalized) is not None
    return exact_pep or exact_conda or exact_poetry


def _build_gaps(
    *,
    metrics: RepositoryReadinessMetrics,
    environment_variables: list[EnvironmentVariableSignal],
) -> list[RepositoryAuditGap]:
    gaps: list[RepositoryAuditGap] = []

    def add(code: str, severity: RepositoryGapSeverity, message: str, remediation: str) -> None:
        gaps.append(
            RepositoryAuditGap(
                code=code,
                severity=severity,
                message=message,
                remediation=remediation,
            )
        )

    if metrics.metadata_file_count == 0:
        add(
            "MISSING_PROJECT_METADATA",
            RepositoryGapSeverity.HIGH,
            "No supported project metadata or dependency file was found at the repository root.",
            "Add pyproject.toml or an explicit environment/dependency specification.",
        )
    if metrics.dependency_count == 0:
        add(
            "DEPENDENCIES_NOT_DECLARED",
            RepositoryGapSeverity.MEDIUM,
            "No statically parseable dependency declarations were found.",
            "Declare runtime dependencies in pyproject.toml, requirements.txt, or environment.yml.",
        )
    elif not metrics.has_lockfile:
        add(
            "LOCKFILE_NOT_FOUND",
            RepositoryGapSeverity.MEDIUM,
            "Dependencies are declared but no supported lockfile was found.",
            "Commit a lockfile or a fully resolved environment export for repeatable installation.",
        )
    elif metrics.dependency_count and not metrics.download_hashes_complete:
        add(
            "DOWNLOAD_HASHES_NOT_LOCKED",
            RepositoryGapSeverity.LOW,
            (
                "A dependency lockfile was found, but per-download SHA-256 hashes do not cover every inspected "
                f"dependency ({metrics.download_hash_count}/{metrics.dependency_count})."
            ),
            "Generate a platform-aware hash-checked lockfile (for example with pip-compile "
            "--generate-hashes) and install with --require-hashes.",
        )
    if metrics.dependency_count and metrics.pinned_dependency_ratio < 1 and not metrics.has_lockfile:
        add(
            "DEPENDENCIES_NOT_FULLY_PINNED",
            RepositoryGapSeverity.LOW,
            "At least one dependency is not pinned to an exact version in the inspected specifications.",
            "Provide a lockfile or a reproducible constraints file instead of relying only on ranges.",
        )
    if not metrics.has_python_requirement:
        add(
            "PYTHON_VERSION_UNSPECIFIED",
            RepositoryGapSeverity.MEDIUM,
            "No Python version constraint was found in supported project metadata.",
            "Declare requires-python or an equivalent interpreter constraint.",
        )
    if not metrics.has_install_instructions:
        add(
            "INSTALL_COMMAND_NOT_DOCUMENTED",
            RepositoryGapSeverity.MEDIUM,
            "No supported installation command was found in root README code blocks.",
            "Document a minimal installation command in a shell code block.",
        )
    if not metrics.has_declared_entrypoint:
        add(
            "ENTRYPOINT_NOT_FOUND",
            RepositoryGapSeverity.LOW,
            "No console script, GUI script, or Python main guard was found in the bounded scan.",
            "Document or declare the command used to start the project.",
        )
    if not metrics.has_test_configuration and not metrics.has_test_instructions:
        add(
            "TEST_PROCEDURE_NOT_FOUND",
            RepositoryGapSeverity.MEDIUM,
            "No supported test configuration or documented test command was found.",
            "Add a test configuration and document the verification command.",
        )
    if environment_variables and not metrics.environment_example_present:
        add(
            "ENVIRONMENT_EXAMPLE_NOT_FOUND",
            RepositoryGapSeverity.MEDIUM,
            "Environment-variable names are referenced but no .env.example file was found.",
            "Add a placeholder-only .env.example without credentials or private endpoint values.",
        )
    if metrics.scan_truncated:
        add(
            "REPOSITORY_SCAN_INCOMPLETE",
            RepositoryGapSeverity.MEDIUM,
            "The bounded static scan did not inspect every candidate file.",
            "Reduce the repository scope or raise max_python_files within the documented limit.",
        )
    return gaps


def _deduplicate_dependencies(dependencies: list[RepositoryDependency]) -> list[RepositoryDependency]:
    unique: dict[tuple[str, str, str, str], RepositoryDependency] = {}
    for dependency in dependencies:
        key = (
            dependency.name.lower().replace("_", "-"),
            dependency.constraint or "",
            dependency.group,
            dependency.source_path,
        )
        unique.setdefault(key, dependency)
    return sorted(
        unique.values(),
        key=lambda dependency: (
            dependency.name.lower(),
            dependency.group,
            dependency.source_path,
            dependency.constraint or "",
        ),
    )


def _deduplicate_entrypoints(entrypoints: list[RepositoryEntrypoint]) -> list[RepositoryEntrypoint]:
    unique = {
        (entrypoint.name, entrypoint.target, entrypoint.kind, entrypoint.source_path): entrypoint
        for entrypoint in entrypoints
    }
    return sorted(unique.values(), key=lambda entrypoint: (entrypoint.kind, entrypoint.name, entrypoint.source_path))


def _mark_unparsed(state: _ScanState, relative_path: str) -> None:
    for index, inspected in enumerate(state.inspected_files):
        if inspected.relative_path == relative_path:
            state.inspected_files[index] = inspected.model_copy(update={"parsed": False})
            return


def _source_type(path: Path) -> SourceType:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return SourceType.PYTHON
    if suffix == ".toml" or path.name.lower() in {"poetry.lock", "pdm.lock", "uv.lock"}:
        return SourceType.TOML
    if suffix == ".json" or path.name.lower() == "pipfile.lock":
        return SourceType.JSON
    if suffix in {".yaml", ".yml"}:
        return SourceType.YAML
    if suffix in {".md", ".markdown"}:
        return SourceType.MARKDOWN
    return SourceType.TEXT


def _manager_for_lockfile(name: str) -> str:
    if name == "poetry.lock":
        return "poetry"
    if name == "uv.lock":
        return "uv"
    if name == "pipfile.lock":
        return "pipenv"
    if name.startswith("conda-lock"):
        return "conda"
    if name == "pdm.lock":
        return "pdm"
    return "pip"


def _literal_string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _sanitize_documented_command(command: str) -> str:
    sanitized = re.sub(
        r"(?i)(--(?:api-key|extra-index-url|index-url|password|token)\s+)\S+",
        r"\1<redacted>",
        command,
    )
    sanitized = re.sub(r"(?i)(https?://)[^/\s@]+@", r"\1<redacted>@", sanitized)
    return sanitized[:500]


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _contains_download_hashes(text: str) -> bool:
    """Detect explicit package download hashes without treating arbitrary file hashes as locks."""

    return bool(DOWNLOAD_HASH_PATTERN.search(text))


def _normalized_dependency_name(name: str) -> str:
    return name.casefold().replace("_", "-").replace(".", "-")
