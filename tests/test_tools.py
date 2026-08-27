from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

import pytest
from pydantic import BaseModel

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.errors import ArtifactLineageError, GroupFilterError
from hy3_reproscope_mcp.models import CompareReproductionResult, ExtractClaimsResult, ReliabilityScoreResult
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import audit_repository, compare_results, extract_claims, score_paper
from hy3_reproscope_mcp.workspace import Workspace


class FakeHy3Client:
    def __init__(self, payloads: dict[type[BaseModel], dict[str, Any]]) -> None:
        self.payloads = payloads
        self.calls: list[tuple[Sequence[Mapping[str, str]], type[BaseModel]]] = []
        self.closed = False

    async def complete_structured(
        self,
        messages: Sequence[Mapping[str, str]],
        response_model: type[BaseModel],
        **_: Any,
    ) -> BaseModel:
        self.calls.append((messages, response_model))
        return response_model.model_validate(self.payloads[response_model])

    async def close(self) -> None:
        self.closed = True


def _settings(tmp_path) -> Settings:
    return Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(tmp_path),
        REPROSCOPE_WORKSPACE=tmp_path / "artifacts",
    )


def _citation(source_id: str) -> dict[str, str]:
    return {
        "source_id": source_id,
        "support": "mentions",
        "locator": "L1",
        "rationale": "The supplied source reports this value.",
    }


@pytest.mark.asyncio
async def test_extract_claims_uses_loaded_source_and_writes_artifact(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    paper_path.write_text("The method reports accuracy 0.91 on Dataset-A.", encoding="utf-8")
    fake = FakeHy3Client(
        {
            ExtractClaimsResult: {
                "run_id": "model_run",
                "summary": "One reproducibility-relevant claim was found.",
                "core_claims": [
                    {
                        "claim_id": "claim_1",
                        "claim_type": "main_result",
                        "statement": "Accuracy reaches 0.91.",
                        "reported_value": "0.91",
                        "citations": [
                            _citation("paper_1"),
                            _citation("invented_source"),
                            {**_citation("paper_1"), "locator": "L999"},
                        ],
                        "reproducibility_impact": "This is the primary result to reproduce.",
                    }
                ],
            }
        }
    )
    app = AppContext(settings=_settings(tmp_path), hy3_client=fake)

    result = await extract_claims(app, paper_paths=[str(paper_path)], focus="primary metric")

    assert result.run_id.startswith("claims_")
    assert "accuracy 0.91" in fake.calls[0][0][-1]["content"]
    assert [citation.source_id for citation in result.core_claims[0].citations] == ["paper_1"]
    assert result.core_claims[0].citations[0].source_reference is not None
    assert result.sources[0].content_hash == sha256(paper_path.read_bytes()).hexdigest()
    assert any(warning.code == "UNKNOWN_SOURCE_CITATION" for warning in result.warnings)
    assert any(warning.code == "UNKNOWN_EVIDENCE_LOCATOR" for warning in result.warnings)
    assert result.artifact_integrity is not None
    assert result.artifact_integrity.payload_hash == result.artifacts[0].payload_hash
    assert (tmp_path / "artifacts" / result.artifacts[0].relative_path).is_file()


@pytest.mark.asyncio
async def test_compare_results_maps_metric_difference(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text("Reported accuracy: 0.91", encoding="utf-8")
    result_path.write_text("accuracy\n0.87\n", encoding="utf-8")
    fake = FakeHy3Client(
        {
            CompareReproductionResult: {
                "run_id": "model_run",
                "summary": "The reproduction is lower.",
                "metric_comparisons": [
                    {
                        "metric": "accuracy",
                        "paper_value": 0.91,
                        "reproduction_source_id": "repro_1",
                        "reproduction_column": "accuracy",
                        "severity": "material",
                        "conclusion": "The result is not fully reproduced.",
                        "citations": [
                            _citation("paper_1"),
                            {**_citation("repro_1"), "locator": "L1-L20"},
                        ],
                    }
                ],
                "supported_claim_ids": ["invented_claim"],
                "conclusion_stability": "The main conclusion is weakened but not disproved.",
            }
        }
    )
    app = AppContext(settings=_settings(tmp_path), hy3_client=fake)

    result = await compare_results(
        app,
        paper_paths=[str(paper_path)],
        reproduction_paths=[str(result_path)],
        metric_hints=["accuracy"],
    )

    comparison = result.metric_comparisons[0]
    prompt = fake.calls[0][0][-1]["content"]
    assert '"canonical_name": "accuracy"' in prompt
    assert comparison.reproduced_value == pytest.approx(0.87)
    assert comparison.reproduced_stddev == 0
    assert comparison.sample_count == 1
    assert comparison.absolute_delta == pytest.approx(-0.04)
    assert comparison.relative_delta_percent == pytest.approx(-4.3956)
    assert comparison.canonical_metric == "accuracy"
    assert comparison.normalized_paper_value == pytest.approx(0.91)
    assert comparison.normalized_scale.value == "fraction"
    assert comparison.computation_status.value == "computed"
    assert comparison.severity.value == "material"
    assert result.supported_claim_ids == []
    assert result.claim_relation_diagnostics.total_claim_count == 0
    assert result.claim_relation_diagnostics.claim_relation_coverage is None
    assert any(warning.code == "CLAIM_LINKAGE_UNAVAILABLE" for warning in result.warnings)
    assert any(warning.code == "METRIC_VALUES_RECALCULATED" for warning in result.warnings)
    assert result.artifacts[0].relative_path.endswith("compare_results.json")


@pytest.mark.asyncio
async def test_compare_results_blocks_mixed_experiment_groups(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text("Reported accuracy: 0.91 on Dataset-A.", encoding="utf-8")
    result_path.write_text(
        "dataset,split,accuracy\nDataset-A,test,0.87\nDataset-B,test,0.93\n",
        encoding="utf-8",
    )
    fake = FakeHy3Client(
        {
            CompareReproductionResult: {
                "run_id": "model_run",
                "summary": "The global result appears close to the paper.",
                "metric_comparisons": [
                    {
                        "metric": "accuracy",
                        "paper_value": 0.91,
                        "reproduction_source_id": "repro_1",
                        "reproduction_column": "accuracy",
                        "reproduced_value": 0.90,
                        "severity": "minor",
                        "conclusion": "The global average is close.",
                        "citations": [_citation("paper_1")],
                    }
                ],
                "conclusion_stability": "The conclusion depends on a global average.",
            }
        }
    )
    app = AppContext(settings=_settings(tmp_path), hy3_client=fake)

    result = await compare_results(
        app,
        paper_paths=[str(paper_path)],
        reproduction_paths=[str(result_path)],
        metric_hints=["accuracy"],
    )

    prompt = fake.calls[0][0][-1]["content"]
    comparison = result.metric_comparisons[0]
    assert '"aggregation_safe": false' in prompt
    assert comparison.computation_status.value == "ambiguous_reproduction_group"
    assert comparison.reproduced_value is None
    assert comparison.severity.value == "unknown"
    assert any(warning.code == "MIXED_EXPERIMENT_GROUPS" for warning in result.warnings)
    assert any(warning.code == "UNSAFE_METRIC_AGGREGATION_BLOCKED" for warning in result.warnings)
    assert result.artifacts[0].relative_path.endswith("compare_results.json")


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        (
            "results.csv",
            (
                "dataset_name,method_name,accuracy\nDataset-A,ours,0.8\nDataset-A,ours,0.9\n"
                "dataset-a,OURS,0.85\nDataset-B,base,0.7\nDataset-B,base,\n"
            ),
        ),
        (
            "results.json",
            (
                '[{"dataset_name":"Dataset-A","method_name":"ours","accuracy":0.8},'
                '{"dataset_name":"Dataset-A","method_name":"ours","accuracy":0.9},'
                '{"dataset_name":"dataset-a","method_name":"OURS","accuracy":0.85},'
                '{"dataset_name":"Dataset-B","method_name":"base","accuracy":0.7},'
                '{"dataset_name":"Dataset-B","method_name":"base"}]'
            ),
        ),
        (
            "results.jsonl",
            (
                '{"dataset_name":"Dataset-A","method_name":"ours","accuracy":0.8}\n'
                '{"dataset_name":"Dataset-A","method_name":"ours","accuracy":0.9}\n'
                '{"dataset_name":"dataset-a","method_name":"OURS","accuracy":0.85}\n'
                '{"dataset_name":"Dataset-B","method_name":"base","accuracy":0.7}\n'
                '{"dataset_name":"Dataset-B","method_name":"base"}\n'
            ),
        ),
    ],
)
@pytest.mark.asyncio
async def test_compare_results_computes_group_metrics_for_structured_sources(
    tmp_path,
    filename: str,
    content: str,
) -> None:
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / filename
    paper_path.write_text("Reported accuracy: 0.90.", encoding="utf-8")
    result_path.write_text(content, encoding="utf-8")
    fake = FakeHy3Client(
        {
            CompareReproductionResult: {
                "run_id": "model_run",
                "summary": "The source contains multiple experiment groups.",
                "metric_comparisons": [
                    {
                        "metric": "accuracy",
                        "paper_value": 0.90,
                        "reproduction_source_id": "repro_1",
                        "reproduction_column": "accuracy",
                        "severity": "unknown",
                        "conclusion": "Group-scoped calculations are required.",
                    }
                ],
                "conclusion_stability": "The conclusion varies by experiment group.",
            }
        }
    )

    result = await compare_results(
        AppContext(settings=_settings(tmp_path), hy3_client=fake),
        paper_paths=[str(paper_path)],
        reproduction_paths=[str(result_path)],
        metric_hints=["accuracy"],
        group_by=["dataset_name", "model"],
    )

    assert result.group_by == ["dataset", "method"]
    assert result.metric_comparisons[0].computation_status.value == "ambiguous_reproduction_group"
    assert [comparison.group for comparison in result.group_metric_comparisons] == [
        {"dataset": "Dataset-A", "method": "ours"},
        {"dataset": "Dataset-B", "method": "base"},
    ]
    first, second = result.group_metric_comparisons
    assert first.reproduced_value == pytest.approx(0.85)
    assert first.reproduced_stddev == pytest.approx(0.05)
    assert first.sample_count == 3
    assert first.absolute_delta == pytest.approx(-0.05)
    assert first.relative_delta_percent == pytest.approx(-5.5556)
    assert second.reproduced_value == pytest.approx(0.7)
    assert second.sample_count == 1
    assert second.data_quality is not None
    assert second.data_quality.total_count == 2
    assert second.data_quality.valid_numeric_count == 1
    assert second.data_quality.missing_count == 1
    assert second.data_quality.valid_ratio == pytest.approx(0.5)
    assert len(result.group_stability_summaries) == 1
    stability = result.group_stability_summaries[0]
    assert stability.group_count == 2
    assert stability.group_mean == pytest.approx(0.775)
    assert stability.group_mean_stddev == pytest.approx(0.106066)
    assert stability.minimum_group == {"dataset": "Dataset-B", "method": "base"}
    assert stability.minimum_value == pytest.approx(0.7)
    assert stability.maximum_group == {"dataset": "Dataset-A", "method": "ours"}
    assert stability.maximum_value == pytest.approx(0.85)
    assert stability.value_range == pytest.approx(0.15)
    assert stability.range_percent_of_reported == pytest.approx(16.6667)
    assert stability.max_absolute_paper_delta == pytest.approx(0.2)
    assert stability.max_delta_group == {"dataset": "Dataset-B", "method": "base"}
    warning_codes = {warning.code for warning in result.warnings}
    assert "UNSAFE_METRIC_AGGREGATION_BLOCKED" in warning_codes
    assert "GROUP_METRIC_COMPARISONS_COMPUTED" in warning_codes
    assert "GROUP_METRIC_VALUES_EXCLUDED" in warning_codes
    assert "GROUP_STABILITY_SUMMARIES_COMPUTED" in warning_codes
    assert result.unresolved_questions == [
        "Review group_metric_comparisons; global aggregation remains intentionally blocked for mixed sources."
    ]


@pytest.mark.asyncio
async def test_compare_results_rejects_group_by_dimension_already_filtered(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text("Reported accuracy: 0.90.", encoding="utf-8")
    result_path.write_text(
        "dataset_name,accuracy\nDataset-A,0.8\nDataset-B,0.9\n",
        encoding="utf-8",
    )
    fake = FakeHy3Client({})

    with pytest.raises(GroupFilterError, match="repeats dimensions"):
        await compare_results(
            AppContext(settings=_settings(tmp_path), hy3_client=fake),
            paper_paths=[str(paper_path)],
            reproduction_paths=[str(result_path)],
            metric_hints=["accuracy"],
            group_filters={"dataset_name": "Dataset-A"},
            group_by=["dataset"],
        )

    assert fake.calls == []


@pytest.mark.asyncio
async def test_group_stability_avoids_relative_range_for_decibels(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text("Reported SNR: 10 dB.", encoding="utf-8")
    result_path.write_text(
        "scenario,snr_db\nurban,9\nrural,12\n",
        encoding="utf-8",
    )
    fake = FakeHy3Client(
        {
            CompareReproductionResult: {
                "run_id": "model_run",
                "summary": "SNR differs across scenarios.",
                "metric_comparisons": [
                    {
                        "metric": "snr_db",
                        "paper_value": 10,
                        "unit": "dB",
                        "paper_scale": "decibel",
                        "reproduction_source_id": "repro_1",
                        "reproduction_column": "snr_db",
                        "severity": "unknown",
                        "conclusion": "Scenario-scoped calculations are required.",
                    }
                ],
                "conclusion_stability": "SNR varies by scenario.",
            }
        }
    )

    result = await compare_results(
        AppContext(settings=_settings(tmp_path), hy3_client=fake),
        paper_paths=[str(paper_path)],
        reproduction_paths=[str(result_path)],
        metric_hints=["snr_db"],
        group_by=["scenario"],
    )

    stability = result.group_stability_summaries[0]
    assert stability.normalized_scale.value == "decibel"
    assert stability.value_range == pytest.approx(3)
    assert stability.range_percent_of_reported is None


@pytest.mark.asyncio
async def test_compare_results_rejects_excessive_group_combinations(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text("Reported accuracy: 0.90.", encoding="utf-8")
    rows = [f"Dataset-{dataset},Method-{method},0.8" for dataset in range(11) for method in range(10)]
    result_path.write_text(
        "dataset,method,accuracy\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    fake = FakeHy3Client({})

    with pytest.raises(GroupFilterError, match="110 candidate combinations"):
        await compare_results(
            AppContext(settings=_settings(tmp_path), hy3_client=fake),
            paper_paths=[str(paper_path)],
            reproduction_paths=[str(result_path)],
            metric_hints=["accuracy"],
            group_by=["dataset", "method"],
        )

    assert fake.calls == []


@pytest.mark.asyncio
async def test_compare_results_filters_mixed_experiment_group_before_aggregation(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text("Reported accuracy: 0.90 on Dataset-A.", encoding="utf-8")
    result_path.write_text(
        "dataset,split,accuracy\nDataset-A,test,0.8\nDataset-A,test,0.9\nDataset-B,test,0.1\n",
        encoding="utf-8",
    )
    fake = FakeHy3Client(
        {
            CompareReproductionResult: {
                "run_id": "model_run",
                "summary": "Dataset-A was compared separately.",
                "metric_comparisons": [
                    {
                        "metric": "accuracy",
                        "paper_value": 0.90,
                        "reproduction_source_id": "repro_1",
                        "reproduction_column": "accuracy",
                        "severity": "critical",
                        "conclusion": "The selected group is lower.",
                    }
                ],
                "conclusion_stability": "The comparison is scoped to Dataset-A/test.",
            }
        }
    )

    result = await compare_results(
        AppContext(settings=_settings(tmp_path), hy3_client=fake),
        paper_paths=[str(paper_path)],
        reproduction_paths=[str(result_path)],
        metric_hints=["accuracy"],
        group_filters={"dataset": "Dataset-A", "split": "test"},
    )

    comparison = result.metric_comparisons[0]
    prompt = fake.calls[0][0][-1]["content"]
    assert comparison.reproduced_value == pytest.approx(0.85)
    assert comparison.sample_count == 2
    assert comparison.computation_status.value == "computed"
    assert result.group_filters == {"dataset": "Dataset-A", "split": "test"}
    assert '"applied_group_filters"' in prompt
    assert "row_count" in prompt
    assert any(warning.code == "GROUP_FILTER_APPLIED" for warning in result.warnings)
    assert not any(warning.code == "UNSAFE_METRIC_AGGREGATION_BLOCKED" for warning in result.warnings)


@pytest.mark.asyncio
async def test_compare_results_validates_claim_relations_against_prior_artifact(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text("Reported accuracy: 0.91.", encoding="utf-8")
    result_path.write_text("accuracy\n0.87\n", encoding="utf-8")
    settings = _settings(tmp_path)
    claims_artifact = Workspace(settings).write_json_artifact(
        "claims_context",
        "extract_claims.json",
        {
            "run_id": "claims_context",
            "summary": "Three claims were extracted.",
            "sources": [
                {
                    "source_id": "paper_1",
                    "source_path": "paper.md",
                    "source_type": "markdown",
                    "content_hash": sha256(paper_path.read_bytes()).hexdigest(),
                }
            ],
            "core_claims": [
                {
                    "claim_id": claim_id,
                    "claim_type": "main_result",
                    "statement": f"Statement for {claim_id}.",
                    "reproducibility_impact": "Relevant to the comparison.",
                }
                for claim_id in ("claim_1", "claim_2", "claim_3", "claim_4")
            ],
        },
    )
    fake = FakeHy3Client(
        {
            CompareReproductionResult: {
                "run_id": "model_run",
                "summary": "Claim relations were proposed.",
                "metric_comparisons": [
                    {
                        "metric": "accuracy",
                        "paper_value": 0.91,
                        "reproduction_source_id": "repro_1",
                        "reproduction_column": "accuracy",
                        "severity": "material",
                        "conclusion": "The result is lower.",
                    }
                ],
                "supported_claim_ids": ["claim_1", "claim_2", "invented_claim"],
                "partially_supported_claim_ids": ["claim_2", "claim_4"],
                "contradicted_claim_ids": ["claim_2", "claim_3"],
                "conclusion_stability": "Relations require local ID validation.",
            }
        }
    )

    result = await compare_results(
        AppContext(settings=settings, hy3_client=fake),
        paper_paths=[str(paper_path)],
        reproduction_paths=[str(result_path)],
        metric_hints=["accuracy"],
        claims_artifact_path=claims_artifact.relative_path,
    )

    prompt = fake.calls[0][0][-1]["content"]
    assert '"prior_claim_analysis"' in prompt
    assert '"claim_id": "claim_1"' in prompt
    assert result.claims_run_id == "claims_context"
    assert [parent.role for parent in result.parent_artifacts] == ["claims"]
    assert result.parent_artifacts[0].content_hash == claims_artifact.content_hash
    assert result.supported_claim_ids == ["claim_1"]
    assert result.partially_supported_claim_ids == ["claim_4"]
    assert result.contradicted_claim_ids == ["claim_3"]
    diagnostics = result.claim_relation_diagnostics
    assert diagnostics.total_claim_count == 4
    assert diagnostics.assessed_claim_count == 3
    assert diagnostics.fully_supported_count == 1
    assert diagnostics.partially_supported_count == 1
    assert diagnostics.contradicted_count == 1
    assert diagnostics.unassessed_claim_count == 1
    assert diagnostics.unassessed_claim_ids == ["claim_2"]
    assert diagnostics.claim_relation_coverage == pytest.approx(0.75)
    assert any(warning.code == "UNKNOWN_COMPARISON_CLAIM_ID" for warning in result.warnings)
    assert any(warning.code == "AMBIGUOUS_CLAIM_RELATION" for warning in result.warnings)
    assert any(warning.code == "CLAIM_RELATION_COVERAGE_INCOMPLETE" for warning in result.warnings)


@pytest.mark.asyncio
async def test_compare_results_rejects_stale_claim_artifact_before_hy3_call(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text("Current paper bytes.", encoding="utf-8")
    result_path.write_text("accuracy\n0.87\n", encoding="utf-8")
    settings = _settings(tmp_path)
    claims_artifact = Workspace(settings).write_json_artifact(
        "claims_stale",
        "extract_claims.json",
        {
            "run_id": "claims_stale",
            "summary": "Analysis of an older paper version.",
            "sources": [
                {
                    "source_id": "paper_1",
                    "source_path": "paper.md",
                    "source_type": "markdown",
                    "content_hash": "a" * 64,
                }
            ],
        },
    )
    fake = FakeHy3Client({})

    with pytest.raises(ArtifactLineageError, match="does not match"):
        await compare_results(
            AppContext(settings=settings, hy3_client=fake),
            paper_paths=[str(paper_path)],
            reproduction_paths=[str(result_path)],
            metric_hints=["accuracy"],
            claims_artifact_path=claims_artifact.relative_path,
        )

    assert fake.calls == []


@pytest.mark.asyncio
async def test_score_paper_recalculates_weighted_score(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    repository_path = tmp_path / "repository"
    paper_path.write_text("The paper includes controlled baselines and ablations.", encoding="utf-8")
    repository_path.mkdir()
    (repository_path / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "0.1.0"\ndependencies = ["httpx>=0.27"]\n',
        encoding="utf-8",
    )
    fake = FakeHy3Client(
        {
            ReliabilityScoreResult: {
                "run_id": "model_run",
                "overall_score": 99,
                "reliability_band": "strong",
                "conclusion_confidence": 0.7,
                "summary": "The evidence is mixed.",
                "dimensions": [
                    {
                        "name": "baseline_fairness",
                        "score": 80,
                        "rationale": "Baselines are controlled.",
                        "citations": [_citation("paper_1")],
                    },
                    {
                        "name": "reproduction_result_agreement",
                        "score": 40,
                        "rationale": "No independent reproduction evidence was supplied.",
                        "evidence_gaps": ["reproduction results"],
                    },
                    {
                        "name": "experiment_setup_transparency",
                        "score": 70,
                        "rationale": "Most settings are disclosed.",
                    },
                    {
                        "name": "ablation_quality",
                        "score": 60,
                        "rationale": "One useful ablation is present.",
                    },
                    {
                        "name": "statistical_reporting",
                        "score": 50,
                        "rationale": "Variance reporting is incomplete.",
                    },
                    {
                        "name": "data_implementation_availability",
                        "score": 70,
                        "rationale": "Implementation details are partially available.",
                    },
                ],
                "reproduction_verdict": "Insufficient independent evidence.",
                "experimental_rigor_verdict": "The reported setup is moderately rigorous.",
            }
        }
    )
    settings = _settings(tmp_path)
    workspace = Workspace(settings)
    claims_artifact = workspace.write_json_artifact(
        "claims_prior",
        "extract_claims.json",
        {
            "run_id": "claims_prior",
            "summary": "Prior claim analysis.",
            "sources": [
                {
                    "source_id": "paper_1",
                    "source_path": "paper.md",
                    "source_type": "markdown",
                    "content_hash": sha256(paper_path.read_bytes()).hexdigest(),
                }
            ],
        },
    )
    app = AppContext(settings=settings, hy3_client=fake)
    repository_audit = audit_repository(app, repository_path=str(repository_path))

    result = await score_paper(
        app,
        paper_paths=[str(paper_path)],
        reproduction_paths=[],
        rubric_focus=["baseline fairness"],
        claims_artifact_path=claims_artifact.relative_path,
        comparison_artifact_path=None,
        repository_audit_artifact_path=repository_audit.artifacts[0].relative_path,
    )

    assert result.overall_score == pytest.approx(67.14)
    assert result.reliability_band.value == "moderate"
    assert result.assessment_scope.value == "paper_only"
    assert result.conclusion_confidence == 0.5
    assert result.rubric_coverage == 0.7
    assert result.evidence_coverage == 0.15
    assert [dimension.weight for dimension in result.dimensions] == [0.3, 0.2, 0.15, 0.15, 0.1, 0.1]
    assert result.dimensions[0].score is None
    assert result.dimensions[0].assessment_status.value == "insufficient_evidence"
    prompt = fake.calls[0][0][-1]["content"]
    assert "prior_claim_analysis" in prompt
    assert "repository_audit" in prompt
    assert "LOCKFILE_NOT_FOUND" in prompt
    assert result.repository_audit_run_id == repository_audit.run_id
    assert [parent.role for parent in result.parent_artifacts] == ["claims", "repository_audit"]
    implementation_dimension = next(
        dimension for dimension in result.dimensions if dimension.name.value == "data_implementation_availability"
    )
    assert any("LOCKFILE_NOT_FOUND" in gap for gap in implementation_dimension.evidence_gaps)
    assert any(warning.code == "REPOSITORY_AUDIT_CALLER_ASSOCIATED" for warning in result.warnings)
    assert any(warning.code == "PAPER_ONLY_ASSESSMENT" for warning in result.warnings)
    assert any(warning.code == "RUBRIC_PARTIAL_COVERAGE" for warning in result.warnings)
    assert any(warning.code == "SCORE_NORMALIZED" for warning in result.warnings)


@pytest.mark.asyncio
async def test_score_paper_rejects_stale_claim_artifact_before_hy3_call(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    paper_path.write_text("Current paper bytes.", encoding="utf-8")
    settings = _settings(tmp_path)
    workspace = Workspace(settings)
    claims_artifact = workspace.write_json_artifact(
        "claims_stale",
        "extract_claims.json",
        {
            "run_id": "claims_stale",
            "summary": "Analysis of an older paper version.",
            "sources": [
                {
                    "source_id": "paper_1",
                    "source_path": "paper.md",
                    "source_type": "markdown",
                    "content_hash": "a" * 64,
                }
            ],
        },
    )
    fake = FakeHy3Client({})

    with pytest.raises(ArtifactLineageError, match="does not match"):
        await score_paper(
            AppContext(settings=settings, hy3_client=fake),
            paper_paths=[str(paper_path)],
            reproduction_paths=[],
            rubric_focus=[],
            claims_artifact_path=claims_artifact.relative_path,
        )

    assert fake.calls == []


@pytest.mark.asyncio
async def test_score_paper_rejects_comparison_with_different_group_filters_before_hy3_call(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text("Reported accuracy: 0.90.", encoding="utf-8")
    result_path.write_text(
        "dataset,accuracy\nDataset-A,0.8\nDataset-B,0.9\n",
        encoding="utf-8",
    )
    settings = _settings(tmp_path)
    comparison_artifact = Workspace(settings).write_json_artifact(
        "compare_prior",
        "compare_results.json",
        {
            "run_id": "compare_prior",
            "group_filters": {"dataset": "Dataset-A"},
            "summary": "Dataset-A comparison.",
            "conclusion_stability": "Scoped to Dataset-A.",
            "sources": [
                {
                    "source_id": "paper_1",
                    "source_path": "paper.md",
                    "source_type": "markdown",
                    "content_hash": sha256(paper_path.read_bytes()).hexdigest(),
                },
                {
                    "source_id": "repro_1",
                    "source_path": "results.csv",
                    "source_type": "csv",
                    "content_hash": sha256(result_path.read_bytes()).hexdigest(),
                },
            ],
        },
    )
    fake = FakeHy3Client({})

    with pytest.raises(ArtifactLineageError, match="different experiment group filters"):
        await score_paper(
            AppContext(settings=settings, hy3_client=fake),
            paper_paths=[str(paper_path)],
            reproduction_paths=[str(result_path)],
            rubric_focus=[],
            group_filters={"dataset": "Dataset-B"},
            comparison_artifact_path=comparison_artifact.relative_path,
        )

    assert fake.calls == []


@pytest.mark.asyncio
async def test_score_paper_rejects_group_filters_without_reproduction_paths(tmp_path) -> None:
    paper_path = tmp_path / "paper.md"
    paper_path.write_text("Reported accuracy: 0.90.", encoding="utf-8")
    fake = FakeHy3Client({})

    with pytest.raises(GroupFilterError, match="require at least one reproduction path"):
        await score_paper(
            AppContext(settings=_settings(tmp_path), hy3_client=fake),
            paper_paths=[str(paper_path)],
            reproduction_paths=[],
            rubric_focus=[],
            group_filters={"dataset": "Dataset-A"},
        )

    assert fake.calls == []
