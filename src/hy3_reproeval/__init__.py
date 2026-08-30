"""Hy3 ReproEval public package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hy3-reproeval")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.17.0"

from .evaluator import evaluate_case_file, evaluate_case_file_hybrid

__all__ = ["__version__", "evaluate_case_file", "evaluate_case_file_hybrid"]
