from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path

import pytest
from test_reproeval_agreement import _two_bundles

from hy3_reproeval.benchmark import BenchmarkMode, run_dataset_benchmark
from hy3_reproeval.cli import main
from hy3_reproeval.consensus import finalize_annotation_consensus
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.human_results_export import (
    export_human_consensus_results,
    verify_human_consensus_results,
)

_FREEZE_SHA256 = "A" * 64


def _inputs(tmp_path: Path) -> tuple[Path, list[Path]]:
    manifest_path, _, first, second = _two_bundles(tmp_path)
    consensus = finalize_annotation_consensus(manifest_path, [first, second])
    consensus_payload = consensus.model_dump(mode="json")
    consensus_payload["dataset_freeze_sha256"] = _FREEZE_SHA256
    consensus_path = tmp_path / "consensus.json"
    consensus_path.write_text(json.dumps(consensus_payload, indent=2) + "\n", encoding="utf-8")

    base = asyncio.run(run_dataset_benchmark(manifest_path, mode=BenchmarkMode.REPLAY))
    benchmarks: list[Path] = []
    for index in range(3):
        payload = base.model_dump(mode="json")
        payload.update(
            dataset_freeze_sha256=_FREEZE_SHA256,
            judge_run_id=f"{index + 1:032x}",
            judge_record_index_sha256=f"{index + 1:064X}",
        )
        path = tmp_path / f"benchmark-{index + 1}.json"
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        benchmarks.append(path)
    return consensus_path, benchmarks


def test_human_results_export_is_closed_deidentified_and_verified(tmp_path: Path) -> None:
    consensus, benchmarks = _inputs(tmp_path)
    output = tmp_path / "public-human-results"

    result = export_human_consensus_results(consensus, benchmarks, output)

    assert result.run_count == 3
    assert result.report_count == 3
    assert set(result.files) == {
        "consensus_dimensions.csv",
        "consensus_reports.csv",
        "export_manifest.json",
        "run_metrics.csv",
        "summary.md",
        "system_human_comparison.csv",
        "tier_metrics.csv",
    }
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    assert "annotator-a" not in public_text
    assert "annotator-b" not in public_text
    assert "bundle-a" not in public_text
    assert "bundle-b" not in public_text
    with (output / "consensus_dimensions.csv").open(encoding="utf-8", newline="") as stream:
        dimensions = list(csv.DictReader(stream))
    assert len(dimensions) == 21
    with (output / "system_human_comparison.csv").open(encoding="utf-8", newline="") as stream:
        comparisons = list(csv.DictReader(stream))
    assert len(comparisons) == 9
    verification = verify_human_consensus_results(output)
    assert verification.valid is True
    with (output / "tier_metrics.csv").open(encoding="utf-8", newline="") as stream:
        tiers = list(csv.DictReader(stream))
    assert len(tiers) == 9
    assert verification.file_count == 7


def test_human_results_export_cli_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    consensus, benchmarks = _inputs(tmp_path)
    output = tmp_path / "public-human-results"
    argv = ["export-human-consensus-results", "--consensus", str(consensus)]
    for benchmark in benchmarks:
        argv.extend(["--benchmark", str(benchmark)])
    argv.extend(["--output-dir", str(output)])

    assert main(argv) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["report_count"] == 3
    assert main(["verify-human-consensus-results", "--bundle", str(output)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True


def test_human_results_verifier_rejects_tampering(tmp_path: Path) -> None:
    consensus, benchmarks = _inputs(tmp_path)
    output = tmp_path / "public-human-results"
    export_human_consensus_results(consensus, benchmarks, output)
    report_path = output / "consensus_reports.csv"
    report_path.write_text(report_path.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="fingerprint changed"):
        verify_human_consensus_results(output)


def test_human_results_export_rejects_unready_consensus(tmp_path: Path) -> None:
    consensus, benchmarks = _inputs(tmp_path)
    payload = json.loads(consensus.read_text(encoding="utf-8"))
    payload["consensus_ready"] = False
    consensus.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="not ready"):
        export_human_consensus_results(consensus, benchmarks, tmp_path / "public-human-results")


def test_human_results_export_rejects_tier_drift_across_runs(tmp_path: Path) -> None:
    consensus, benchmarks = _inputs(tmp_path)
    payload = json.loads(benchmarks[1].read_text(encoding="utf-8"))
    payload["groups"][0]["reports"][0]["quality_tier"] = "low"
    benchmarks[1].write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="quality tiers changed"):
        export_human_consensus_results(consensus, benchmarks, tmp_path / "public-human-results")
