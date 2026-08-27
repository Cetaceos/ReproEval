"""Run the checked-in transfer workflow evaluation without an API key."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from hy3_reproscope_mcp.transfer_evaluation import run_transfer_offline_evaluation_suite

DEFAULT_FIXTURES = (
    "synthetic_transfer.json",
    "synthetic_transfer_insufficient_evidence.json",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        type=Path,
        action="append",
        help="Transfer fixture path. Repeat to run multiple cases; defaults to the checked-in suite.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Optional persistent artifact workspace. A temporary directory is used by default.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the machine-readable evaluation result.",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    project_root = Path(__file__).resolve().parents[1]
    fixture_paths = (
        [path.resolve() for path in args.fixture]
        if args.fixture
        else [(project_root / "evals" / name).resolve() for name in DEFAULT_FIXTURES]
    )

    if args.workspace is not None:
        result = asyncio.run(
            run_transfer_offline_evaluation_suite(
                project_root=project_root,
                fixture_paths=fixture_paths,
                workspace_path=args.workspace.resolve(),
            )
        )
    else:
        with tempfile.TemporaryDirectory(prefix="reproscope-transfer-eval-") as temporary_directory:
            result = asyncio.run(
                run_transfer_offline_evaluation_suite(
                    project_root=project_root,
                    fixture_paths=fixture_paths,
                    workspace_path=Path(temporary_directory),
                )
            )

    rendered = json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    raise SystemExit(0 if result.status == "passed" else 1)


if __name__ == "__main__":
    main()
