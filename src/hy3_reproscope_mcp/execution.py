"""Execution safety boundaries.

The repository auditor remains static and default-deny.  The optional runner
below is deliberately a separate, explicit API for an already provisioned
external sandbox adapter.  It is *not* a general shell and does not claim to
make Python code trustworthy.  In particular, execution is refused unless a
known OS sandbox (currently ``bubblewrap`` on Linux or ``sandbox-exec`` on
macOS) is available and requested by the caller.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import signal
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Literal

from .repository_models import ThirdPartyExecutionPreflight
from .workspace import sha256_text


class ControlledExecutionError(RuntimeError):
    """Base error for an explicitly requested, but unsafe, execution."""


class ControlledExecutionDenied(ControlledExecutionError):
    """Raised when a command cannot satisfy the execution policy."""


class ControlledExecutionTimeout(ControlledExecutionError):
    """Raised when the child process exceeds the configured wall-clock limit."""


@dataclass(frozen=True, slots=True)
class ControlledExecutionPolicy:
    """Narrow policy for a pre-provisioned external sandbox.

    The default policy is intentionally not runnable: a caller must select a
    supported sandbox kind and an explicit Python executable allowlist.  This
    keeps accidentally passing an arbitrary command or inherited credentials
    from turning the MCP server into a code runner.
    """

    sandbox: Literal["bwrap", "sandbox-exec"] | None = None
    allowed_executables: tuple[str, ...] = ("python", "python3", "python.exe")
    max_timeout_seconds: float = 30.0
    max_output_bytes: int = 64 * 1024
    max_args: int = 32
    max_command_bytes: int = 8 * 1024
    max_cpu_seconds: int = 30
    max_memory_bytes: int = 512 * 1024 * 1024
    max_file_bytes: int = 16 * 1024 * 1024
    allowed_env_keys: tuple[str, ...] = ("LANG", "LC_ALL", "TZ")

    def __post_init__(self) -> None:
        if self.sandbox not in {None, "bwrap", "sandbox-exec"}:
            raise ValueError("sandbox must be 'bwrap', 'sandbox-exec', or None")
        if not self.allowed_executables:
            raise ValueError("allowed_executables cannot be empty")
        if not 0 < self.max_timeout_seconds <= 300:
            raise ValueError("max_timeout_seconds must be in (0, 300]")
        if not 1024 <= self.max_output_bytes <= 16 * 1024 * 1024:
            raise ValueError("max_output_bytes must be between 1024 and 16 MiB")
        if not 1 <= self.max_args <= 128:
            raise ValueError("max_args must be between 1 and 128")
        if not 128 <= self.max_command_bytes <= 64 * 1024:
            raise ValueError("max_command_bytes must be between 128 and 64 KiB")
        if not 1 <= self.max_cpu_seconds <= 300:
            raise ValueError("max_cpu_seconds must be between 1 and 300")
        if not 16 * 1024 * 1024 <= self.max_memory_bytes <= 4 * 1024 * 1024 * 1024:
            raise ValueError("max_memory_bytes must be between 16 MiB and 4 GiB")
        if not 0 <= self.max_file_bytes <= 1024 * 1024 * 1024:
            raise ValueError("max_file_bytes must be between 0 and 1 GiB")


@dataclass(frozen=True, slots=True)
class ControlledExecutionResult:
    """Redacted, bounded result from a controlled child process."""

    returncode: int
    timed_out: bool
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    command_hash: str
    sandbox: str
    network_access: Literal["disabled"] = "disabled"


_SHELL_META = frozenset(";&|<>`$\n\r")
_SECRET_ENV_PARTS = (
    "key",
    "token",
    "secret",
    "password",
    "credential",
    "authorization",
)


def _command_tokens(command: Sequence[str] | str, *, max_args: int, max_bytes: int) -> list[str]:
    if isinstance(command, str):
        if not command.strip():
            raise ControlledExecutionDenied("execution command cannot be empty")
        if any(character in command for character in _SHELL_META):
            raise ControlledExecutionDenied("shell syntax is not allowed; pass an argv sequence")
        try:
            tokens = shlex.split(command, posix=os.name != "nt")
        except ValueError as exc:
            raise ControlledExecutionDenied("execution command could not be parsed as argv") from exc
    elif isinstance(command, Sequence) and not isinstance(command, (bytes, bytearray)):
        tokens = [item for item in command]
    else:
        raise ControlledExecutionDenied("execution command must be a string or argv sequence")
    if not tokens or any(not isinstance(token, str) or not token for token in tokens):
        raise ControlledExecutionDenied("execution command contains an empty or non-string argument")
    if len(tokens) > max_args:
        raise ControlledExecutionDenied(f"execution command has more than {max_args} arguments")
    if any("\x00" in token for token in tokens):
        raise ControlledExecutionDenied("execution command contains a NUL byte")
    if len("\0".join(tokens).encode("utf-8")) > max_bytes:
        raise ControlledExecutionDenied("execution command exceeds the byte limit")
    return tokens


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_root_and_cwd(allowed_root: str | Path, cwd: str | Path | None) -> tuple[Path, Path]:
    root = Path(allowed_root).expanduser().resolve()
    if not root.is_dir():
        raise ControlledExecutionDenied("allowed_root must be an existing directory")
    working = (root if cwd is None else Path(cwd).expanduser()).resolve()
    if not working.is_dir() or not _inside(root, working):
        raise ControlledExecutionDenied("cwd must be an existing directory inside allowed_root")
    return root, working


def _resolve_python_command(tokens: list[str], root: Path, policy: ControlledExecutionPolicy) -> list[str]:
    executable = Path(tokens[0]).name.casefold()
    allowed_names = {Path(value).name.casefold() for value in policy.allowed_executables}
    if executable not in allowed_names:
        raise ControlledExecutionDenied(f"executable is not on the allowlist: {executable}")
    # The only supported interpreter is the current, trusted Python runtime;
    # arbitrary PATH lookup would make the policy dependent on the caller's
    # ambient environment.
    if executable not in {"python", "python3", "python.exe"}:
        raise ControlledExecutionDenied("only the current Python interpreter is supported")
    if len(tokens) < 2 or tokens[1].startswith("-"):
        raise ControlledExecutionDenied("a script path is required; -c, -m, and stdin execution are disabled")
    script = Path(tokens[1]).expanduser()
    resolved_script = script.resolve() if script.is_absolute() else (root / script).resolve()
    if not _inside(root, resolved_script) or not resolved_script.is_file() or resolved_script.suffix.lower() != ".py":
        raise ControlledExecutionDenied("script must be a .py file inside allowed_root")
    # Reject path-like arguments escaping the root.  Options remain available
    # for benign, script-defined flags; shell parsing is never involved.
    for argument in tokens[2:]:
        raw_path = argument.split("=", 1)[1] if argument.startswith("--") and "=" in argument else argument
        if raw_path.startswith("-"):
            continue
        if "/" in raw_path or "\\" in raw_path or Path(raw_path).is_absolute():
            candidate = Path(raw_path)
            candidate = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
            if not _inside(root, candidate):
                raise ControlledExecutionDenied("path argument escapes allowed_root")
    return [sys.executable, "-I", str(resolved_script), *tokens[2:]]


def _safe_environment(
    supplied: Mapping[str, str] | None,
    root: Path,
    policy: ControlledExecutionPolicy,
) -> dict[str, str]:
    result = {
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }
    allowed = {key.casefold() for key in policy.allowed_env_keys}
    for key, value in (supplied or {}).items():
        if not isinstance(key, str) or not isinstance(value, str) or "\x00" in key or "\x00" in value:
            raise ControlledExecutionDenied("environment keys and values must be NUL-free strings")
        normalized = key.casefold()
        if normalized not in allowed:
            raise ControlledExecutionDenied(f"environment variable is not allowlisted: {key}")
        if any(part in normalized for part in _SECRET_ENV_PARTS):
            raise ControlledExecutionDenied(f"secret-like environment variable is forbidden: {key}")
        # Values that look like paths must stay within the execution root.
        for part in value.split(os.pathsep):
            if "/" in part or "\\" in part or Path(part).is_absolute():
                candidate = Path(part)
                candidate = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
                if not _inside(root, candidate):
                    raise ControlledExecutionDenied(f"environment path escapes allowed_root: {key}")
        result[key] = value
    return result


def _sandbox_command(command: list[str], root: Path, cwd: Path, policy: ControlledExecutionPolicy) -> list[str]:
    if policy.sandbox is None:
        raise ControlledExecutionDenied(
            "an external sandbox adapter is required; set policy.sandbox to 'bwrap' or 'sandbox-exec'"
        )
    if policy.sandbox == "bwrap":
        if os.name == "nt":
            raise ControlledExecutionDenied("bubblewrap is unavailable on Windows")
        launcher = next(
            (candidate for candidate in (Path("/usr/bin/bwrap"), Path("/bin/bwrap")) if candidate.is_file()),
            None,
        )
        if not launcher:
            raise ControlledExecutionDenied("bubblewrap is not installed; refusing unsandboxed execution")
        workspace_mount = Path("/workspace")
        mapped_command = [_map_sandbox_path(argument, root, workspace_mount) for argument in command]
        mapped_cwd = _map_sandbox_path(str(cwd), root, workspace_mount)
        # Start with an empty root and bind only the runtime libraries and the
        # read-only project workspace.  ``--unshare-all`` includes a private
        # network namespace; the external binary is still an independent trust
        # boundary and must be reviewed by the deployment operator.
        runtime_mounts = [
            path for path in ("/usr", "/usr/local", "/opt", "/bin", "/lib", "/lib64") if Path(path).exists()
        ]
        runtime_bind_args: list[str] = []
        for path in runtime_mounts:
            runtime_bind_args.extend(("--ro-bind", path, path))
        return [
            str(launcher),
            "--die-with-parent",
            "--unshare-all",
            "--new-session",
            "--tmpfs",
            "/",
            *runtime_bind_args,
            "--dir",
            str(workspace_mount),
            "--ro-bind",
            str(root),
            str(workspace_mount),
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--tmpfs",
            "/tmp",
            "--chdir",
            mapped_cwd,
            "--",
            *mapped_command,
        ]
    if os.name != "posix" or sys.platform != "darwin":
        raise ControlledExecutionDenied("sandbox-exec is supported only on macOS")
    launcher = Path("/usr/bin/sandbox-exec")
    if not launcher.is_file():
        raise ControlledExecutionDenied("sandbox-exec is not installed; refusing unsandboxed execution")
    profile_root = str(root).replace("\\", "\\\\").replace('"', '\\"')
    profile = (
        "(version 1) (deny default) (allow process*) "
        f'(allow file-read* (subpath "{profile_root}")) '
        f'(allow file-write* (subpath "{profile_root}")) (deny network*)'
    )
    return [str(launcher), "-p", profile, *command]


def _map_sandbox_path(value: str, root: Path, workspace_mount: Path) -> str:
    """Map paths inside the host workspace to its sandbox mount point."""

    if value.startswith("-") and not Path(value).is_absolute():
        return value
    candidate = Path(value)
    try:
        relative = candidate.resolve().relative_to(root)
    except ValueError:
        return value
    return str(workspace_mount / relative).replace("\\", "/")


def _set_posix_limits(policy: ControlledExecutionPolicy) -> None:
    if os.name != "posix":
        return
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (policy.max_cpu_seconds, policy.max_cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (policy.max_memory_bytes, policy.max_memory_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (policy.max_file_bytes, policy.max_file_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except (ImportError, OSError, ValueError):
        # The external sandbox and wall-clock/output limits remain mandatory;
        # a platform simply lacking optional POSIX limits is not a reason to
        # claim stronger isolation than it provides.
        return


def _capture(stream: object, limit: int, output: bytearray, truncated: list[bool]) -> None:
    reader = stream  # type: ignore[assignment]
    while True:
        chunk = reader.read(8192)
        if not chunk:
            return
        if len(output) < limit:
            output.extend(chunk[: limit - len(output)])
        if len(output) + len(chunk) > limit:
            truncated[0] = True


def run_controlled_command(
    command: Sequence[str] | str,
    *,
    allowed_root: str | Path,
    policy: ControlledExecutionPolicy | None = None,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout_seconds: float | None = None,
) -> ControlledExecutionResult:
    """Run one allowlisted script inside an external OS sandbox.

    This function is intentionally opt-in and raises before spawning a child
    whenever the sandbox or path policy cannot be proven.  It is suitable for
    a caller that has reviewed the source and controls the sandbox binary; it
    does not make arbitrary Python code safe or provide cross-platform kernel
    isolation by itself.
    """

    if os.environ.get("REPROSCOPE_ALLOW_CONTROLLED_EXECUTION") != "1":
        raise ControlledExecutionDenied(
            "set REPROSCOPE_ALLOW_CONTROLLED_EXECUTION=1 for the explicit controlled-execution opt-in"
        )
    policy = policy or ControlledExecutionPolicy()
    root, working = _resolve_root_and_cwd(allowed_root, cwd)
    tokens = _command_tokens(command, max_args=policy.max_args, max_bytes=policy.max_command_bytes)
    normalized_command = "\0".join(tokens)
    command_hash = hashlib.sha256(normalized_command.encode("utf-8")).hexdigest()
    child_command = _resolve_python_command(tokens, root, policy)
    environment = _safe_environment(env, root, policy)
    sandboxed_command = _sandbox_command(child_command, root, working, policy)
    timeout = policy.max_timeout_seconds if timeout_seconds is None else timeout_seconds
    if not 0 < timeout <= policy.max_timeout_seconds:
        raise ControlledExecutionDenied("timeout_seconds exceeds the policy limit")

    creationflags = 0
    preexec_fn = None
    if os.name == "posix":
        preexec_fn = partial(_set_posix_limits, policy)
        start_new_session = True
    else:
        start_new_session = False
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    try:
        process = subprocess.Popen(
            sandboxed_command,
            cwd=str(working),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            start_new_session=start_new_session,
            creationflags=creationflags,
            preexec_fn=preexec_fn,
        )
    except OSError as exc:
        raise ControlledExecutionDenied("external sandbox could not be started") from exc
    stdout = bytearray()
    stderr = bytearray()
    stdout_truncated = [False]
    stderr_truncated = [False]
    stdout_thread = threading.Thread(
        target=_capture,
        args=(process.stdout, policy.max_output_bytes, stdout, stdout_truncated),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_capture,
        args=(process.stderr, policy.max_output_bytes, stderr, stderr_truncated),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        if os.name == "posix":
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()
        raise ControlledExecutionTimeout(f"controlled execution exceeded {timeout:.1f}s") from exc
    finally:
        if process.poll() is None:
            process.kill()
        elif os.name == "posix":
            # A hostile script can fork and exit while descendants retain the
            # pipes. Kill the dedicated process group before returning.
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        stdout_thread.join(timeout=2)
        stderr_thread.join(timeout=2)
    if timed_out:  # pragma: no cover - timeout path raises above.
        raise ControlledExecutionTimeout("controlled execution timed out")
    return ControlledExecutionResult(
        returncode=process.returncode,
        timed_out=False,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        stdout_truncated=stdout_truncated[0],
        stderr_truncated=stderr_truncated[0],
        command_hash=command_hash,
        sandbox=policy.sandbox or "none",
    )


def preflight_third_party_execution(
    command: str | None = None,
    *,
    allowed_root: str | None = None,
) -> ThirdPartyExecutionPreflight:
    """Return a deterministic default-deny preflight without executing anything."""

    normalized = command.strip() if isinstance(command, str) else ""
    if not normalized:
        return ThirdPartyExecutionPreflight(allowed_root=allowed_root)
    return ThirdPartyExecutionPreflight(
        status="denied",
        requested=True,
        command_hash=sha256_text(normalized),
        allowed_root=allowed_root,
    )


__all__ = [
    "ControlledExecutionDenied",
    "ControlledExecutionError",
    "ControlledExecutionPolicy",
    "ControlledExecutionResult",
    "ControlledExecutionTimeout",
    "preflight_third_party_execution",
    "run_controlled_command",
]
