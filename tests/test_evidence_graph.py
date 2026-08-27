from __future__ import annotations

import pytest

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.errors import ArtifactLineageError, EvidenceGraphValidationError
from hy3_reproscope_mcp.evidence_graph import build_graph, validate_evidence_graph
from hy3_reproscope_mcp.lineage import validate_graph_artifact_lineage, validate_report_lineage
from hy3_reproscope_mcp.models import (
    CompareReproductionResult,
    EvidenceGraphEdge,
    ExtractClaimsResult,
    MetricComparisonStatus,
    ReliabilityScoreResult,
)
from hy3_reproscope_mcp.renderer import render_markdown_report
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import build_evidence_graph, render_report
from hy3_reproscope_mcp.workspace import Workspace, parent_artifact_reference


def _source(source_id: str, content_hash: str) -> dict[str, object]:
    is_paper = source_id.startswith("paper_")
    return {
        "source_id": source_id,
        "source_path": "paper.md" if is_paper else "results.csv",
        "source_type": "markdown" if is_paper else "csv",
        "content_hash": content_hash,
        "line_start": 1,
        "line_end": 5,
        "excerpt": "Reported evidence." if is_paper else "accuracy\n0.87",
    }


def _citation(source_id: str, content_hash: str) -> dict[str, object]:
    reference = _source(source_id, content_hash)
    return {
        "source_id": source_id,
        "support": "mentions",
        "locator": "L1-L5",
        "rationale": "Grounded in the supplied source.",
        "source_reference": reference,
    }


def _analysis_results() -> tuple[ExtractClaimsResult, CompareReproductionResult, ReliabilityScoreResult]:
    paper_hash = "a" * 64
    reproduction_hash = "b" * 64
    paper_source = _source("paper_1", paper_hash)
    reproduction_source = _source("repro_1", reproduction_hash)
    paper_citation = _citation("paper_1", paper_hash)
    reproduction_citation = _citation("repro_1", reproduction_hash)
    claims = ExtractClaimsResult.model_validate(
        {
            "run_id": "claims_test",
            "summary": "Three claims were extracted.",
            "sources": [paper_source],
            "core_claims": [
                {
                    "claim_id": "claim_supported",
                    "claim_type": "main_result",
                    "statement": "Accuracy reaches 0.91.",
                    "reported_value": "0.91",
                    "citations": [paper_citation],
                    "reproducibility_impact": "Primary result.",
                },
                {
                    "claim_id": "claim_partial",
                    "claim_type": "ablation",
                    "statement": "The ablation direction and full magnitude are reproduced.",
                    "citations": [paper_citation],
                    "reproducibility_impact": "Ablation magnitude claim.",
                },
                {
                    "claim_id": "claim_contradicted",
                    "claim_type": "baseline",
                    "statement": "The reported gain is fully reproduced.",
                    "citations": [paper_citation],
                    "reproducibility_impact": "Magnitude claim.",
                },
            ],
            "experiment_settings": [
                {
                    "name": "epochs",
                    "value": "100",
                    "disclosed": True,
                    "citations": [paper_citation],
                },
                {
                    "name": "random seed",
                    "value": None,
                    "disclosed": False,
                },
            ],
            "missing_details": [
                {
                    "item": "per-seed scores",
                    "impact": "Variance cannot be independently checked.",
                    "severity": "material",
                    "citations": [paper_citation],
                }
            ],
        }
    )
    comparison = CompareReproductionResult.model_validate(
        {
            "run_id": "compare_test",
            "claims_run_id": "claims_test",
            "summary": "The reproduced result is lower.",
            "sources": [paper_source, reproduction_source],
            "group_by": ["dataset"],
            "metric_comparisons": [
                {
                    "metric": "accuracy",
                    "reproduction_source_id": "repro_1",
                    "reproduction_column": "accuracy",
                    "paper_value": 0.91,
                    "reproduced_value": 0.87,
                    "reproduced_stddev": 0.0,
                    "sample_count": 1,
                    "data_quality": {
                        "total_count": 3,
                        "valid_numeric_count": 1,
                        "missing_count": 1,
                        "non_numeric_count": 1,
                        "non_finite_count": 0,
                        "valid_ratio": 0.333333,
                    },
                    "absolute_delta": -0.04,
                    "relative_delta_percent": -4.3956,
                    "computation_status": "computed",
                    "severity": "material",
                    "conclusion": "The exact magnitude is not reproduced.",
                    "citations": [paper_citation, reproduction_citation],
                }
            ],
            "group_metric_comparisons": [
                {
                    "group": {"dataset": "Dataset-A"},
                    "metric": "accuracy",
                    "reproduction_source_id": "repro_1",
                    "reproduction_column": "accuracy",
                    "paper_value": 0.91,
                    "normalized_paper_value": 0.91,
                    "reproduced_value": 0.86,
                    "reproduced_stddev": 0.01,
                    "sample_count": 2,
                    "data_quality": {
                        "total_count": 2,
                        "valid_numeric_count": 2,
                        "missing_count": 0,
                        "non_numeric_count": 0,
                        "non_finite_count": 0,
                        "valid_ratio": 1,
                    },
                    "absolute_delta": -0.05,
                    "relative_delta_percent": -5.4945,
                    "computation_status": "computed",
                    "severity": "critical",
                    "conclusion": "Dataset-A is below the reported value.",
                },
                {
                    "group": {"dataset": "Dataset-B"},
                    "metric": "accuracy",
                    "reproduction_source_id": "repro_1",
                    "reproduction_column": "accuracy",
                    "paper_value": 0.91,
                    "normalized_paper_value": 0.91,
                    "reproduced_value": 0.82,
                    "reproduced_stddev": 0.02,
                    "sample_count": 2,
                    "data_quality": {
                        "total_count": 3,
                        "valid_numeric_count": 2,
                        "missing_count": 1,
                        "non_numeric_count": 0,
                        "non_finite_count": 0,
                        "valid_ratio": 0.666667,
                    },
                    "absolute_delta": -0.09,
                    "relative_delta_percent": -9.8901,
                    "computation_status": "computed",
                    "severity": "critical",
                    "conclusion": "Dataset-B is further below the reported value.",
                },
            ],
            "group_stability_summaries": [
                {
                    "metric": "accuracy",
                    "reproduction_source_id": "repro_1",
                    "reproduction_column": "accuracy",
                    "group_by": ["dataset"],
                    "group_count": 2,
                    "group_mean": 0.84,
                    "group_mean_stddev": 0.028284,
                    "minimum_group": {"dataset": "Dataset-B"},
                    "minimum_value": 0.82,
                    "maximum_group": {"dataset": "Dataset-A"},
                    "maximum_value": 0.86,
                    "value_range": 0.04,
                    "normalized_paper_value": 0.91,
                    "normalized_scale": "fraction",
                    "range_percent_of_reported": 4.3956,
                    "max_absolute_paper_delta": 0.09,
                    "max_delta_group": {"dataset": "Dataset-B"},
                }
            ],
            "supported_claim_ids": ["claim_supported"],
            "partially_supported_claim_ids": ["claim_partial"],
            "contradicted_claim_ids": ["claim_contradicted"],
            "conclusion_stability": "The direction is supported but the magnitude is weakened.",
        }
    )
    score = ReliabilityScoreResult.model_validate(
        {
            "run_id": "score_test",
            "overall_score": 65,
            "reliability_band": "moderate",
            "conclusion_confidence": 0.7,
            "assessment_scope": "paper_and_reproduction",
            "evidence_coverage": 1,
            "rubric_coverage": 1,
            "summary": "The evidence provides partial reproduction support.",
            "sources": [paper_source, reproduction_source],
            "dimensions": [
                {
                    "name": "reproduction_result_agreement",
                    "score": 65,
                    "weight": 0.3,
                    "rationale": "The direction but not the magnitude is reproduced.",
                    "citations": [paper_citation, reproduction_citation],
                }
            ],
            "reproduction_verdict": "Partially reproduced.",
            "experimental_rigor_verdict": "Some evidence remains missing.",
        }
    )
    return claims, comparison, score


def test_build_graph_connects_claims_and_deterministic_results() -> None:
    claims, comparison, score = _analysis_results()

    graph = build_graph(run_id="graph_test", claims=claims, comparison=comparison, score=score)

    assert graph.graph_validated is True
    serialized_keys = list(graph.model_dump(mode="json"))
    assert serialized_keys.index("graph_validated") < serialized_keys.index("nodes")
    assert graph.model_dump(mode="json")["graph_validated"] is True
    assert graph.source_run_ids == ["claims_test", "compare_test", "score_test"]
    assert graph.metrics.claim_evidence_coverage == 1
    assert graph.metrics.claim_source_coverage == 1
    assert graph.metrics.reproduction_assessment_coverage == 1
    assert graph.metrics.contradiction_ratio == pytest.approx(0.3333)
    assert graph.metrics.reproduction_support_ratio == pytest.approx(0.3333)
    assert graph.metrics.reproduction_partial_support_ratio == pytest.approx(0.3333)
    assert graph.metrics.experiment_setting_coverage == 0.5
    assert graph.metrics.source_closure_ratio == 1
    assert graph.metrics.orphan_claim_count == 0
    reproduced = next(node for node in graph.nodes if node.node_type.value == "reproduction_result")
    grouped = next(node for node in graph.nodes if node.node_id.startswith("group-reproduction-result:"))
    stability = next(node for node in graph.nodes if node.node_id.startswith("assessment:group-stability:"))
    reproduction_run = next(node for node in graph.nodes if node.node_type.value == "reproduction_run")
    assert reproduced.evidence_kind.value == "deterministically_derived"
    assert reproduced.properties["value"] == pytest.approx(0.87)
    assert reproduced.properties["data_total_count"] == 3
    assert reproduced.properties["data_valid_numeric_count"] == 1
    assert reproduced.properties["data_valid_ratio"] == pytest.approx(0.333333)
    assert grouped.properties["group"] == "dataset=Dataset-A"
    assert grouped.properties["group_dataset"] == "Dataset-A"
    assert grouped.properties["value"] == pytest.approx(0.86)
    assert stability.properties["group_count"] == 2
    assert stability.properties["value_range"] == pytest.approx(0.04)
    assert sum(edge.source_node_id == stability.node_id for edge in graph.edges) == 2
    assert reproduction_run.properties["comparison_run_id"] == "compare_test"
    assert any(
        edge.edge_type.value == "derived_from"
        and edge.source_node_id == reproduced.node_id
        and edge.target_node_id == reproduction_run.node_id
        for edge in graph.edges
    )
    assert any(edge.edge_type.value == "contradicts" for edge in graph.edges)
    assert any(edge.edge_type.value == "partially_supports" for edge in graph.edges)
    markdown = render_markdown_report(
        title="Grouped reproduction report",
        claims=claims,
        comparison=comparison,
        score=score,
        graph=graph,
        artifact_inventory=[],
    )
    assert "### Per-group metric comparisons" in markdown
    assert "### Cross-group stability" in markdown
    assert "### Metric data quality" in markdown
    assert "33.33%" in markdown
    assert "dataset=Dataset-A" in markdown


def test_graph_separates_claim_sources_from_reproduction_assessment() -> None:
    claims, comparison, score = _analysis_results()
    for claim in claims.core_claims:
        claim.citations = []

    graph = build_graph(run_id="graph_test", claims=claims, comparison=comparison, score=score)

    assert graph.metrics.claim_source_coverage == 0
    assert graph.metrics.claim_evidence_coverage == 1
    assert graph.metrics.reproduction_assessment_coverage == 1


def test_graph_does_not_count_text_only_claim_relations_as_reproduction_assessment() -> None:
    claims, comparison, score = _analysis_results()
    for metric in comparison.metric_comparisons:
        metric.computation_status = MetricComparisonStatus.UNMATCHED_REPRODUCTION_METRIC
    comparison.group_metric_comparisons = []

    graph = build_graph(run_id="graph_test", claims=claims, comparison=comparison, score=score)

    assert graph.metrics.claim_source_coverage == 1
    assert graph.metrics.claim_evidence_coverage == 1
    assert graph.metrics.reproduction_assessment_coverage == 0


def test_validate_graph_rejects_illegal_edge_endpoints() -> None:
    claims, comparison, score = _analysis_results()
    graph = build_graph(run_id="graph_test", claims=claims, comparison=comparison, score=score)
    graph.edges.append(
        EvidenceGraphEdge(
            edge_id="edge:illegal",
            edge_type="reported_by",
            source_node_id="assessment:comparison",
            target_node_id="artifact:1",
            evidence_kind="inferred",
            rationale="Assessments cannot be reported_by source artifacts.",
        )
    )

    with pytest.raises(EvidenceGraphValidationError, match="Illegal reported_by endpoints"):
        validate_evidence_graph(graph)


def test_validate_graph_rejects_tampered_metrics() -> None:
    claims, comparison, score = _analysis_results()
    graph = build_graph(run_id="graph_test", claims=claims, comparison=comparison, score=score)
    graph.metrics.orphan_claim_count = 99

    with pytest.raises(EvidenceGraphValidationError, match="metrics do not match"):
        validate_evidence_graph(graph)


def test_graph_lineage_rejects_other_analysis_runs() -> None:
    claims, comparison, score = _analysis_results()
    graph = build_graph(run_id="graph_test", claims=claims, comparison=comparison, score=score)
    graph.source_run_ids[0] = "claims_other"

    with pytest.raises(ArtifactLineageError, match="not built from the supplied"):
        validate_graph_artifact_lineage(graph, claims, comparison, score)


def test_report_lineage_rejects_comparison_from_other_claim_run() -> None:
    claims, comparison, score = _analysis_results()
    comparison.claims_run_id = "claims_other"

    with pytest.raises(ArtifactLineageError, match="different claim-analysis run"):
        validate_report_lineage(claims, comparison, score)


def test_graph_tool_writes_artifact_and_report_renders_summary(tmp_path) -> None:
    claims, comparison, score = _analysis_results()
    settings = Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(tmp_path),
        REPROSCOPE_WORKSPACE=tmp_path / "artifacts",
    )
    workspace = Workspace(settings)
    claims_artifact = workspace.write_json_artifact(
        claims.run_id,
        "extract_claims.json",
        claims.model_dump(mode="json"),
    )
    comparison.parent_artifacts = [parent_artifact_reference("claims", claims_artifact)]
    comparison_artifact = workspace.write_json_artifact(
        comparison.run_id,
        "compare_results.json",
        comparison.model_dump(mode="json"),
    )
    score.parent_artifacts = [
        parent_artifact_reference("claims", claims_artifact),
        parent_artifact_reference("comparison", comparison_artifact),
    ]
    score_artifact = workspace.write_json_artifact(
        score.run_id,
        "reliability_score.json",
        score.model_dump(mode="json"),
    )
    app = AppContext(settings=settings)

    graph = build_evidence_graph(
        app,
        claims_artifact_path=claims_artifact.relative_path,
        comparison_artifact_path=comparison_artifact.relative_path,
        score_artifact_path=score_artifact.relative_path,
    )
    report = render_report(
        app,
        claims_artifact_path=claims_artifact.relative_path,
        comparison_artifact_path=comparison_artifact.relative_path,
        score_artifact_path=score_artifact.relative_path,
        evidence_graph_artifact_path=graph.artifacts[0].relative_path,
        title="Evidence graph audit",
    )

    graph_path = settings.reproscope_workspace / graph.artifacts[0].relative_path
    report_text = (settings.reproscope_workspace / report.report_path).read_text(encoding="utf-8")
    assert graph_path.is_file()
    assert report.evidence_graph_run_id == graph.run_id
    assert len(report.artifact_inventory) == 4
    assert report.artifact_inventory[-1].role == "evidence_graph"
    assert graph.artifacts[0].relative_path in report_text
    assert report.manifest_path.endswith("/report_manifest.json")
    assert "## Claim-Evidence-Result graph" in report_text
    assert "Claim evidence coverage" in report_text
    assert "Claim source coverage" in report_text
    assert "Reproduction-assessed claims" in report_text
