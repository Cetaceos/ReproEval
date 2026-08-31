"""Backward-compatible Hy3 ReproScope application package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hy3-reproeval")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.21.0"

__all__ = ["__version__"]
