"""Top-level command-line entry point for ReproEval."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from hy3_reproscope_mcp.errors import ReproScopeError

from . import __version__
from .errors import EvaluationInputError
from .evaluator import evaluate_case_file, evaluate_case_file_hybrid
from .judge import write_judge_record
from .pairwise import compare_case_files, write_pairwise_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hy3-reproeval",
        description="Generate and evaluate evidence-grounded research reports with Hy3.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve-mcp", help="Run the migrated ReproScope MCP server over stdio.")
    evaluate_parser = subparsers.add_parser(
        "evaluate-report",
        help="Run deterministic seven-dimension evaluation from a case manifest.",
    )
    evaluate_parser.add_argument("--case", required=True, type=Path, help="Path to an evaluation case JSON file.")
    evaluate_parser.add_argument("--output", type=Path, help="Optional path for the evaluation result JSON.")
    evaluate_parser.add_argument(
        "--judge",
        choices=("none", "online", "replay"),
        default="none",
        help="Semantic Judge mode. The default runs deterministic validators only.",
    )
    evaluate_parser.add_argument(
        "--judge-record",
        type=Path,
        help="Write an online Judge record, or read this record in replay mode.",
    )
    compare_parser = subparsers.add_parser(
        "compare-reports",
        help="Blindly compare two reports under one evaluation contract with repeated Hy3 Judge trials.",
    )
    compare_parser.add_argument("--left-case", required=True, type=Path)
    compare_parser.add_argument("--right-case", required=True, type=Path)
    compare_parser.add_argument("--comparison-id", required=True)
    compare_parser.add_argument("--repeats", type=int, default=3)
    compare_parser.add_argument("--judge", choices=("online", "replay"), required=True)
    compare_parser.add_argument(
        "--judge-record",
        type=Path,
        help="Write an online pairwise Judge bundle, or read this bundle in replay mode.",
    )
    compare_parser.add_argument("--output", type=Path, help="Optional path for the comparison result JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve-mcp":
        from hy3_reproscope_mcp.server import main as run_server

        run_server()
        return 0
    if args.command == "evaluate-report":
        try:
            if args.judge == "none":
                if args.judge_record is not None:
                    parser.error("--judge-record requires --judge online or --judge replay")
                result = evaluate_case_file(args.case)
            elif args.judge == "replay":
                if args.judge_record is None:
                    parser.error("--judge replay requires --judge-record")
                result, _ = asyncio.run(evaluate_case_file_hybrid(args.case, judge_replay_path=args.judge_record))
            else:
                result, judge_record = asyncio.run(evaluate_case_file_hybrid(args.case))
                if args.judge_record is not None:
                    write_judge_record(args.judge_record, judge_record)
        except (EvaluationInputError, ReproScopeError) as exc:
            parser.error(str(exc))
        rendered = result.model_dump_json(indent=2) + "\n"
        if args.output is not None:
            output_path = args.output.expanduser().resolve()
            if not output_path.parent.is_dir():
                parser.error(f"output directory does not exist: {output_path.parent}")
            output_path.write_text(rendered, encoding="utf-8")
            print(output_path.as_posix())
        else:
            print(rendered, end="")
        return 0
    if args.command == "compare-reports":
        if args.judge == "replay" and args.judge_record is None:
            parser.error("--judge replay requires --judge-record")
        try:
            result, bundle = asyncio.run(
                compare_case_files(
                    args.left_case,
                    args.right_case,
                    comparison_id=args.comparison_id,
                    repeats=args.repeats,
                    judge_replay_path=args.judge_record if args.judge == "replay" else None,
                )
            )
            if args.judge == "online" and args.judge_record is not None:
                write_pairwise_bundle(args.judge_record, bundle)
        except (EvaluationInputError, ReproScopeError) as exc:
            parser.error(str(exc))
        rendered = result.model_dump_json(indent=2) + "\n"
        if args.output is not None:
            output_path = args.output.expanduser().resolve()
            if not output_path.parent.is_dir():
                parser.error(f"output directory does not exist: {output_path.parent}")
            output_path.write_text(rendered, encoding="utf-8")
            print(output_path.as_posix())
        else:
            print(rendered, end="")
        return 0
    parser.print_help()
    return 0
