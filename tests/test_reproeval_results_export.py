from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from test_reproeval_stability import _write_stability_runs

from hy3_reproeval.cli import main
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.results_export import export_benchmark_results
from hy3_reproeval.stability import analyze_benchmark_stability


async def test_results_export_writes_verified_markdown_csv_and_manifest(tmp_path: Path) -> None:
    benchmarks = await _write_stability_runs(tmp_path)
    stability = analyze_benchmark_stability(benchmarks)
    stability_path = tmp_path / "stability.json"
    stability_path.write_text(stability.model_dump_json(indent=2) + "\n", encoding="utf-8")
    output_dir = tmp_path / "export"

    result = export_benchmark_results(benchmarks, stability_path, output_dir)

    assert result.run_count == 3
    assert set(result.files) == {
        "benchmark_runs.csv",
        "dimension_stability.csv",
        "export_manifest.json",
        "report_stability.csv",
        "summary.md",
    }
    assert "Repeated-run stability" in (output_dir / "summary.md").read_text(encoding="utf-8")
    with (output_dir / "benchmark_runs.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3
    manifest = json.loads((output_dir / "export_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_count"] == 3
    assert len(manifest["stability_result_sha256"]) == 64
    assert len(manifest["outputs"]) == 4


async def test_results_export_rejects_mismatched_stability(tmp_path: Path) -> None:
    benchmarks = await _write_stability_runs(tmp_path)
    stability = analyze_benchmark_stability(benchmarks)
    stability.overall.quality_band_flip_count = 0
    stability_path = tmp_path / "stability.json"
    stability_path.write_text(stability.model_dump_json(indent=2) + "\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="does not match"):
        export_benchmark_results(benchmarks, stability_path, tmp_path / "export")


async def test_results_export_refuses_nonempty_output_directory(tmp_path: Path) -> None:
    benchmarks = await _write_stability_runs(tmp_path)
    stability = analyze_benchmark_stability(benchmarks)
    stability_path = tmp_path / "stability.json"
    stability_path.write_text(stability.model_dump_json(indent=2) + "\n", encoding="utf-8")
    output_dir = tmp_path / "export"
    output_dir.mkdir()
    (output_dir / "old.txt").write_text("old", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="absent or empty"):
        export_benchmark_results(benchmarks, stability_path, output_dir)


async def test_cli_exports_results_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    benchmarks = await _write_stability_runs(tmp_path)
    stability = analyze_benchmark_stability(benchmarks)
    stability_path = tmp_path / "stability.json"
    stability_path.write_text(stability.model_dump_json(indent=2) + "\n", encoding="utf-8")
    output_dir = tmp_path / "export"
    argv = ["export-benchmark-results"]
    for path in benchmarks:
        argv.extend(["--benchmark", str(path)])
    argv.extend(["--stability", str(stability_path), "--output-dir", str(output_dir)])

    assert main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_count"] == 3
    assert (output_dir / "summary.md").is_file()
