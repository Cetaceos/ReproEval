"""Hy3 ReproEval public package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hy3-reproeval")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.38.0"

from .adjudication_packet import finalize_adjudication_packet, prepare_adjudication_packet
from .agreement import analyze_annotation_agreement
from .annotation_packet import finalize_annotation_packet, prepare_annotation_packet
from .annotations import validate_annotation_bundles
from .benchmark import run_dataset_benchmark
from .consensus import finalize_annotation_consensus
from .dataset import replay_mutation_manifest, validate_dataset_manifest
from .evaluator import evaluate_case_file, evaluate_case_file_hybrid
from .freeze import create_dataset_freeze, verify_dataset_freeze
from .human_results_export import export_human_consensus_results, verify_human_consensus_results
from .judge_batch import generate_dataset_judge_records
from .judge_experiment import run_judge_experiment
from .p0_dataset import materialize_p0_dataset
from .p1_transfer_dataset import materialize_p1_transfer_dataset
from .pairwise import compare_case_files
from .real_pilot import materialize_real_pilot, verify_real_pilot_source_cache
from .reference_generation import generate_reference_candidates, validate_reference_reviews
from .result_figures import render_results_figures, verify_results_figures
from .results_export import export_benchmark_results, verify_results_export
from .stability import analyze_benchmark_stability

__all__ = [
    "__version__",
    "analyze_annotation_agreement",
    "analyze_benchmark_stability",
    "compare_case_files",
    "create_dataset_freeze",
    "evaluate_case_file",
    "evaluate_case_file_hybrid",
    "export_benchmark_results",
    "export_human_consensus_results",
    "finalize_adjudication_packet",
    "finalize_annotation_consensus",
    "finalize_annotation_packet",
    "generate_dataset_judge_records",
    "generate_reference_candidates",
    "materialize_p0_dataset",
    "materialize_p1_transfer_dataset",
    "materialize_real_pilot",
    "prepare_adjudication_packet",
    "prepare_annotation_packet",
    "render_results_figures",
    "replay_mutation_manifest",
    "run_dataset_benchmark",
    "run_judge_experiment",
    "validate_annotation_bundles",
    "validate_dataset_manifest",
    "validate_reference_reviews",
    "verify_dataset_freeze",
    "verify_human_consensus_results",
    "verify_real_pilot_source_cache",
    "verify_results_export",
    "verify_results_figures",
]
