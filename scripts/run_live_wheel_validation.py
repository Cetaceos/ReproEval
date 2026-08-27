"""Run the three live Hy3 workflows from one exact 0.15.0 wheel.

The command is deliberately opt-in.  Without ``--execute`` it only verifies
the wheel metadata and digest.  With ``--execute`` it requires
``REPROSCOPE_RUN_LIVE=1`` and a configured ``HY3_API_KEY`` in the parent
process, creates an isolated virtual environment, installs the locked
dependencies, installs the wheel without dependency resolution, and runs the
existing live validation scripts.  A caller may retain artifacts under the
ignored project ``.hy3-reproscope`` directory and select individual workflows
for bounded retries.  No credential or absolute local path is written to the
result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

try:
    from scripts.live_validation_security import enforce_live_summary_security
except ModuleNotFoundError:  # Direct ``python scripts/run_live_wheel_validation.py`` invocation.
    from live_validation_security import enforce_live_summary_security

from hy3_reproscope_mcp import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SCRIPTS = {
    "paper": "run_live_validation.py",
    "transfer": "run_live_transfer_validation.py",
    "isac": "run_live_isac_validation.py",
}
LIVE_SCRIPTS = tuple(WORKFLOW_SCRIPTS.values())
LIVE_SCRIPT_BOOTSTRAP = (
    "import runpy, sys; "
    "from pathlib import Path; "
    "project_root, script_path = sys.argv[1:3]; "
    "sys.path[:0] = [project_root, str(Path(script_path).parent)]; "
    "sys.argv = [script_path]; "
    "runpy.run_path(script_path, run_name='__main__')"
)
CONTROLLED_EXECUTION_OPT_IN = "REPROSCOPE_ALLOW_CONTROLLED_EXECUTION"
COMMAND_TIMEOUT_ENV = "REPROSCOPE_LIVE_COMMAND_TIMEOUT_SECONDS"
DEFAULT_COMMAND_TIMEOUT_SECONDS = 900
MIN_COMMAND_TIMEOUT_SECONDS = 30
MAX_COMMAND_TIMEOUT_SECONDS = 1800
MAX_COMMAND_OUTPUT_CHARS = 1_000_000
_ABSOLUTE_PATH = re.compile(r"(?i)(?:[a-z]:[\\/]|/home/|/Users/|/tmp/)[^\s\"']+")
_TOKEN = re.compile(r"(?i)(?:sk-|key[-_ ]?|token[-_ ]?)[A-Za-z0-9._-]{12,}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def wheel_metadata(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        candidates = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(candidates) != 1:
            raise ValueError("wheel must contain exactly one dist-info/METADATA file")
        fields: dict[str, str] = {}
        for line in archive.read(candidates[0]).decode("utf-8").splitlines():
            if ": " in line:
                key, value = line.split(": ", 1)
                if key in {"Name", "Version", "Requires-Python"}:
                    fields[key] = value
        return fields


def _redact(text: str, environment: dict[str, str], project_root: Path) -> str:
    result = text
    for secret_name in ("HY3_API_KEY", "OPENAI_API_KEY", "TOKENHUB_API_KEY"):
        secret = environment.get(secret_name, "")
        if secret:
            result = result.replace(secret, "[REDACTED]")
    result = _TOKEN.sub("[REDACTED]", result)
    return _ABSOLUTE_PATH.sub("[REDACTED_PATH]", result.replace(str(project_root), "[PROJECT_ROOT]"))


def _json_from_stdout(stdout: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index in range(len(stdout) - 1, -1, -1):
        if stdout[index] != "{":
            continue
        try:
            value, end = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if end == len(stdout[index:].rstrip()) and isinstance(value, dict):
            return value
    raise ValueError("live validation did not return a JSON object")


def _command_timeout_seconds(environment: dict[str, str]) -> int:
    raw_value = environment.get(COMMAND_TIMEOUT_ENV)
    if raw_value is None:
        return DEFAULT_COMMAND_TIMEOUT_SECONDS
    try:
        timeout_seconds = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{COMMAND_TIMEOUT_ENV} must be an integer") from exc
    if not MIN_COMMAND_TIMEOUT_SECONDS <= timeout_seconds <= MAX_COMMAND_TIMEOUT_SECONDS:
        raise RuntimeError(
            f"{COMMAND_TIMEOUT_ENV} must be between {MIN_COMMAND_TIMEOUT_SECONDS} "
            f"and {MAX_COMMAND_TIMEOUT_SECONDS} seconds"
        )
    return timeout_seconds


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    expect_json: bool = True,
) -> dict[str, Any]:
    if not command or any(not isinstance(part, str) or not part or "\x00" in part for part in command):
        raise RuntimeError("child command must be a non-empty NUL-free argv")
    timeout_seconds = _command_timeout_seconds(environment)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"child command exceeded {timeout_seconds}s") from exc
    if len(completed.stdout) > MAX_COMMAND_OUTPUT_CHARS or len(completed.stderr) > MAX_COMMAND_OUTPUT_CHARS:
        raise RuntimeError("child command output exceeded the publication limit")
    if completed.returncode != 0:
        detail = _redact((completed.stderr or completed.stdout)[-4000:], environment, cwd)
        raise RuntimeError(f"command failed ({completed.returncode}): {detail}")
    return _json_from_stdout(completed.stdout) if expect_json else {}


def _default_wheel() -> Path:
    matches = sorted((PROJECT_ROOT / "dist").glob(f"hy3_reproeval-{__version__}-*.whl"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected exactly one {__version__} wheel under dist; build one first or pass --wheel explicitly"
        )
    return matches[0]


def _isolated_live_script_command(
    python_path: Path,
    script: str,
    *,
    project_root: Path = PROJECT_ROOT,
) -> list[str]:
    if script not in LIVE_SCRIPTS:
        raise RuntimeError(f"live validation script is not allowlisted: {script}")
    resolved_root = project_root.resolve()
    scripts_root = (resolved_root / "scripts").resolve()
    script_path = (scripts_root / script).resolve()
    if script_path.parent != scripts_root or script_path.name != script or not script_path.is_file():
        raise RuntimeError(f"live validation script must be a regular allowlisted file under {scripts_root}")
    return [
        str(python_path),
        "-I",
        "-c",
        LIVE_SCRIPT_BOOTSTRAP,
        str(resolved_root),
        str(script_path),
    ]


def _resolve_live_workspace(
    workspace: Path | None,
    temporary_root: Path,
    *,
    project_root: Path = PROJECT_ROOT,
) -> tuple[Path, bool]:
    if workspace is None:
        return temporary_root / "workspace", False
    allowed_root = (project_root.resolve() / ".hy3-reproscope").resolve()
    resolved_workspace = workspace.resolve()
    try:
        relative_workspace = resolved_workspace.relative_to(allowed_root)
    except ValueError as exc:
        raise RuntimeError("retained live workspace must be under the project .hy3-reproscope directory") from exc
    if not relative_workspace.parts:
        raise RuntimeError("retained live workspace must be a child of the project .hy3-reproscope directory")
    return resolved_workspace, True


def _preflight(wheel: Path) -> dict[str, Any]:
    resolved = wheel.resolve()
    if not resolved.is_file() or resolved.suffix != ".whl":
        raise ValueError(f"wheel does not exist or is not a .whl file: {wheel}")
    metadata = wheel_metadata(resolved)
    expected_name = "hy3-reproeval"
    if metadata.get("Name") != expected_name or metadata.get("Version") != __version__:
        raise ValueError(
            f"wheel metadata mismatch: expected {expected_name} {__version__}, "
            f"got {metadata.get('Name')} {metadata.get('Version')}"
        )
    return {
        "wheel_name": resolved.name,
        "wheel_sha256": sha256_file(resolved),
        "package_version": metadata["Version"],
        "requires_python": metadata.get("Requires-Python"),
    }


def _execute(
    wheel: Path,
    summary: dict[str, Any],
    *,
    scripts: tuple[str, ...] = LIVE_SCRIPTS,
    workspace: Path | None = None,
) -> dict[str, Any]:
    if os.environ.get("REPROSCOPE_RUN_LIVE") != "1":
        raise RuntimeError("set REPROSCOPE_RUN_LIVE=1 to execute live Hy3 validation")
    if os.environ.get(CONTROLLED_EXECUTION_OPT_IN) != "1":
        raise RuntimeError(
            f"set {CONTROLLED_EXECUTION_OPT_IN}=1 only after reviewing the external execution boundary; "
            "the default is deny and this script does not provide a sandbox"
        )
    if not os.environ.get("HY3_API_KEY"):
        raise RuntimeError("HY3_API_KEY is not configured in the parent process")

    resolved_wheel = wheel.resolve()
    dist_root = (PROJECT_ROOT / "dist").resolve()
    try:
        resolved_wheel.relative_to(dist_root)
    except ValueError as exc:
        raise RuntimeError("controlled wheel execution only accepts a wheel under the project dist directory") from exc
    if not scripts or len(set(scripts)) != len(scripts) or any(script not in LIVE_SCRIPTS for script in scripts):
        raise RuntimeError("controlled wheel execution requires a non-empty unique workflow allowlist")

    with tempfile.TemporaryDirectory(prefix="reproscope-live-wheel-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        venv_dir = temporary_root / "venv"
        workspace_path, retained = _resolve_live_workspace(workspace, temporary_root)
        environment = {
            key: value
            for key in (
                "HY3_API_KEY",
                "HY3_BASE_URL",
                "HY3_MODEL",
                "HY3_API_PROVIDER",
                "HY3_REASONING_EFFORT",
                "HY3_TEMPERATURE",
                "HY3_TOP_P",
                "HY3_TIMEOUT_SECONDS",
                "HY3_MAX_RETRIES",
                "HY3_MAX_TOKENS",
                COMMAND_TIMEOUT_ENV,
                "SYSTEMROOT",
                "WINDIR",
                "LANG",
                "LC_ALL",
            )
            if (value := os.environ.get(key))
        }
        environment.update(
            {
                "REPROSCOPE_RUN_LIVE": "1",
                "REPROSCOPE_PROMPT_INJECTION_POLICY": "reject",
                "REPROSCOPE_ALLOWED_ROOTS": str(PROJECT_ROOT),
                "REPROSCOPE_WORKSPACE": str(workspace_path),
                "TMP": str(temporary_root),
                "TEMP": str(temporary_root),
            }
        )
        _run_command(
            [sys.executable, "-I", "-m", "venv", str(venv_dir)],
            cwd=PROJECT_ROOT,
            environment=environment,
            expect_json=False,
        )
        python_path = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _run_command(
            [
                str(python_path),
                "-I",
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "-r",
                "requirements.lock",
            ],
            cwd=PROJECT_ROOT,
            environment=environment,
            expect_json=False,
        )
        _run_command(
            [str(python_path), "-I", "-m", "pip", "install", "--no-deps", str(resolved_wheel)],
            cwd=PROJECT_ROOT,
            environment=environment,
            expect_json=False,
        )
        results: dict[str, Any] = {}
        for script in scripts:
            result = _run_command(
                _isolated_live_script_command(python_path, script),
                cwd=PROJECT_ROOT,
                environment=environment,
            )
            if result.get("status") != "passed":
                raise RuntimeError(f"{script} returned a non-passed status")
            results[script.removesuffix(".py")] = result
        summary["live_execution"] = True
        summary["requested_workflows"] = [name for name, script in WORKFLOW_SCRIPTS.items() if script in scripts]
        summary["artifact_retention"] = "persistent" if retained else "ephemeral"
        if retained:
            summary["workspace_relative"] = workspace_path.relative_to(PROJECT_ROOT).as_posix()
        summary["workflows"] = results
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, help="Exact 0.15.0 wheel; defaults to the sole wheel in dist/")
    parser.add_argument("--execute", action="store_true", help="Install the wheel and call the real Hy3 endpoint")
    parser.add_argument(
        "--workflow",
        action="append",
        choices=tuple(WORKFLOW_SCRIPTS),
        help="Workflow to run; repeat for multiple workflows. Defaults to paper, transfer, and isac.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Retain artifacts in a child directory under the project .hy3-reproscope directory.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()
    wheel = (args.wheel or _default_wheel()).resolve()
    summary = {"status": "ready_for_live", "live_execution": False, **_preflight(wheel)}
    if args.execute:
        workflows = tuple(WORKFLOW_SCRIPTS[name] for name in (args.workflow or tuple(WORKFLOW_SCRIPTS)))
        summary = _execute(wheel, summary, scripts=workflows, workspace=args.workspace)
        summary["status"] = "passed"
    enforce_live_summary_security(summary)
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
