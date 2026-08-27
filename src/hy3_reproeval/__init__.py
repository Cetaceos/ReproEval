"""Hy3 ReproEval public package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hy3-reproeval")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.15.0"

__all__ = ["__version__"]
