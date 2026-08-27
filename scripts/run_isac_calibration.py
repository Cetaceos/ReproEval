"""Evaluate an explicitly labelled, offline ISAC calibration fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hy3_reproscope_mcp.profiles.isac_phy import (
    ISAC_PROFILE_VERSION,
    apply_activation_threshold,
    evaluate_isac_calibration,
    load_calibration_cases,
    load_expert_calibration_cases,
    select_activation_threshold,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "evals" / "synthetic_isac_calibration.json",
        help="Explicitly labelled ISAC calibration fixture (JSON).",
    )
    parser.add_argument(
        "--require-human-annotations",
        action="store_true",
        help="Require expert/reviewed labels and calibration + held_out splits.",
    )
    parser.add_argument(
        "--select-threshold",
        action="store_true",
        help="Tune activation threshold on calibration only, then apply it to all splits.",
    )
    parser.add_argument(
        "--max-false-activation-rate",
        type=float,
        default=0.05,
        help="Maximum calibration false-activation rate used by --select-threshold.",
    )
    parser.add_argument("--output", type=Path, help="Optional path for the JSON report.")
    return parser


def main() -> None:
    args = _parser().parse_args()
    payload = json.loads(args.fixture.resolve().read_text(encoding="utf-8"))
    cases = (
        load_expert_calibration_cases(payload, require_provenance=True)
        if args.require_human_annotations
        else load_calibration_cases(payload)
    )
    profile_version = payload["profile_version"]
    if profile_version != ISAC_PROFILE_VERSION:
        raise ValueError(
            f"Calibration fixture profile_version {profile_version!r} does not match "
            f"the installed ISAC profile {ISAC_PROFILE_VERSION!r}."
        )
    threshold_selection = None
    if args.select_threshold:
        threshold_selection = select_activation_threshold(
            cases,
            max_false_activation_rate=args.max_false_activation_rate,
        )
        cases = apply_activation_threshold(cases, threshold_selection.selected_threshold)
    report = evaluate_isac_calibration(
        cases,
        profile_version=profile_version,
    )
    if threshold_selection is not None:
        report = report.model_copy(update={"threshold_selection": threshold_selection})
    rendered = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
