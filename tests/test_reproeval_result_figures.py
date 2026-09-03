from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from test_reproeval_stability import _write_stability_runs

from hy3_reproeval.cli import main
from hy3_reproeval.errors import EvaluationInputError
from hy3_reproeval.result_figures import render_results_figures, verify_results_figures
from hy3_reproeval.results_export import export_benchmark_results
from hy3_reproeval.stability import analyze_benchmark_stability


async def _write_results_bundle(tmp_path: Path) -> Path:
    benchmarks = await _write_stability_runs(tmp_path)
    stability = analyze_benchmark_stability(benchmarks)
    stability_path = tmp_path / "stability.json"
    stability_path.write_text(stability.model_dump_json(indent=2) + "\n", encoding="utf-8")
    bundle = tmp_path / "results"
    export_benchmark_results(benchmarks, stability_path, bundle)
    return bundle


async def test_result_figures_are_deterministic_and_bound_to_source(tmp_path: Path) -> None:
    bundle = await _write_results_bundle(tmp_path)
    first = tmp_path / "figures-a"
    second = tmp_path / "figures-b"

    rendered = render_results_figures(bundle, first)
    render_results_figures(bundle, second)

    assert set(rendered.files) == {
        "dimension_stability.svg",
        "figure_manifest.json",
        "score_by_tier.svg",
    }
    for name in rendered.files:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    score_svg = (first / "score_by_tier.svg").read_text(encoding="utf-8")
    dimension_svg = (first / "dimension_stability.svg").read_text(encoding="utf-8")
    assert "Mean report score by quality tier" in score_svg
    assert "High" in score_svg and "Medium" in score_svg and "Low" in score_svg
    assert "Dimension-level repeated-run stability" in dimension_svg
    assert "<script" not in score_svg.lower()
    assert ET.fromstring(score_svg).tag == "{http://www.w3.org/2000/svg}svg"
    assert ET.fromstring(dimension_svg).attrib["viewBox"] == "0 0 960 584"
    verification = verify_results_figures(first, source_bundle=bundle)
    assert verification.valid is True
    assert verification.file_count == 3
    assert verification.source_export_manifest_sha256 == rendered.source_manifest_sha256


async def test_result_figures_reject_nonempty_output(tmp_path: Path) -> None:
    bundle = await _write_results_bundle(tmp_path)
    output = tmp_path / "figures"
    output.mkdir()
    (output / "old.svg").write_text("<svg/>\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="absent or empty"):
        render_results_figures(bundle, output)


async def test_result_figure_verifier_rejects_tamper_and_extra_files(tmp_path: Path) -> None:
    bundle = await _write_results_bundle(tmp_path)
    tampered_figures = tmp_path / "tampered-figures"
    render_results_figures(bundle, tampered_figures)
    score_path = tampered_figures / "score_by_tier.svg"
    score_path.write_text(score_path.read_text(encoding="utf-8") + "<!-- changed -->\n", encoding="utf-8")

    with pytest.raises(EvaluationInputError, match="fingerprint changed"):
        verify_results_figures(tampered_figures)

    extra_figures = tmp_path / "extra-figures"
    render_results_figures(bundle, extra_figures)
    (extra_figures / "extra.txt").write_text("unexpected\n", encoding="utf-8")
    with pytest.raises(EvaluationInputError, match="closed manifest inventory"):
        verify_results_figures(extra_figures)


async def test_result_figures_reject_malformed_verified_csv(tmp_path: Path) -> None:
    bundle = await _write_results_bundle(tmp_path)
    report_path = bundle / "report_stability.csv"
    report_path.write_text("wrong,column\nvalue,row\n", encoding="utf-8")
    _rebind_export_file(bundle, "report_stability.csv")

    with pytest.raises(EvaluationInputError, match="canonical columns"):
        render_results_figures(bundle, tmp_path / "figures")


async def test_result_figure_verifier_rejects_symlinked_bundle_root(tmp_path: Path) -> None:
    bundle = await _write_results_bundle(tmp_path)
    figures = tmp_path / "figures"
    render_results_figures(bundle, figures)
    linked = tmp_path / "linked-figures"
    try:
        linked.symlink_to(figures, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are not available on this host")

    with pytest.raises(EvaluationInputError, match="symbolic link"):
        verify_results_figures(linked)


async def test_result_figures_cli_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = await _write_results_bundle(tmp_path)
    figures = tmp_path / "figures"

    assert main(["render-results-figures", "--bundle", str(bundle), "--output-dir", str(figures)]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["dataset_id"]
    assert (
        main(
            [
                "verify-results-figures",
                "--figures",
                str(figures),
                "--source-bundle",
                str(bundle),
            ]
        )
        == 0
    )
    verified = json.loads(capsys.readouterr().out)
    assert verified["valid"] is True


def _rebind_export_file(bundle: Path, name: str) -> None:
    manifest_path = bundle / "export_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = (bundle / name).read_bytes()
    for item in manifest["outputs"]:
        if item["path"] == name:
            item["bytes"] = len(payload)
            item["sha256"] = hashlib.sha256(payload).hexdigest().upper()
            break
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
