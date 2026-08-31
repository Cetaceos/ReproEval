"""Hy3 ReproEval public package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hy3-reproeval")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.21.0"

from .annotations import validate_annotation_bundles
from .benchmark import run_dataset_benchmark
from .dataset import replay_mutation_manifest, validate_dataset_manifest
from .evaluator import evaluate_case_file, evaluate_case_file_hybrid
from .judge_batch import generate_dataset_judge_records
from .pairwise import compare_case_files

__all__ = [
    "__version__",
    "compare_case_files",
    "evaluate_case_file",
    "evaluate_case_file_hybrid",
    "generate_dataset_judge_records",
    "replay_mutation_manifest",
    "run_dataset_benchmark",
    "validate_annotation_bundles",
    "validate_dataset_manifest",
]
