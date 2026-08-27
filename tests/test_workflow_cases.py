from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from hy3_reproscope_mcp.config import Settings
from hy3_reproscope_mcp.errors import ArtifactLineageError
from hy3_reproscope_mcp.models import (
    CompareReproductionResult,
    ExtractClaimsResult,
    ReliabilityScoreResult,
)
from hy3_reproscope_mcp.server import AppContext
from hy3_reproscope_mcp.tools import (
    audit_repository,
    build_evidence_graph,
    compare_results,
    extract_claims,
    render_report,
    score_paper,
)


class SequenceHy3Client:
    def __init__(self, payloads: Mapping[type[BaseModel], Sequence[dict[str, Any]]]) -> None:
        self.payloads = defaultdict(deque)
        for model_type, model_payloads in payloads.items():
            self.payloads[model_type].extend(model_payloads)

    async def complete_structured(
        self,
        messages: Sequence[Mapping[str, str]],
        response_model: type[BaseModel],
        **_: Any,
    ) -> BaseModel:
        del messages
        return response_model.model_validate(self.payloads[response_model].popleft())

    async def close(self) -> None:
        return None


def _settings(tmp_path) -> Settings:
    return Settings(
        REPROSCOPE_ALLOWED_ROOTS=str(tmp_path),
        REPROSCOPE_WORKSPACE=tmp_path / "artifacts",
    )


def _claim_payload(reported_value: str = "0.90") -> dict[str, Any]:
    return {
        "run_id": "model_claims",
        "summary": "One empirical claim was extracted.",
        "core_claims": [
            {
                "claim_id": "claim_main",
                "claim_type": "main_result",
                "statement": f"The reported accuracy is {reported_value}.",
                "reported_value": reported_value,
                "reproducibility_impact": "This is the primary result under review.",
            }
        ],
        "experiment_settings": [
            {
                "name": "epochs",
                "value": "100",
                "disclosed": True,
            }
        ],
    }


def _comparison_payload(
    *,
    paper_value: float,
    setting_differences: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": "model_comparison",
        "summary": "The reproduction result was compared with the paper.",
        "metric_comparisons": [
            {
                "metric": "accuracy",
                "paper_value": paper_value,
                "reproduction_source_id": "repro_1",
                "reproduction_column": "accuracy",
                "severity": "critical",
                "conclusion": "The server must recalculate this comparison.",
            }
        ],
        "setting_differences": setting_differences or [],
        "supported_claim_ids": ["claim_main"],
        "conclusion_stability": "The conclusion depends on the validated reproduction evidence.",
    }


def _score_payload(
    dimensions: list[dict[str, Any]],
    *,
    summary: str,
) -> dict[str, Any]:
    return {
        "run_id": "model_score",
        "overall_score": 95,
        "reliability_band": "strong",
        "conclusion_confidence": 0.7,
        "summary": summary,
        "dimensions": dimensions,
        "reproduction_verdict": "The reproduction evidence requires qualification.",
        "experimental_rigor_verdict": "The available setup evidence is incomplete.",
    }


async def _run_analysis(
    tmp_path,
    *,
    client: SequenceHy3Client,
    paper_text: str,
    result_text: str,
    reproduction_log: str | None = None,
    group_filters: dict[str, str] | None = None,
    include_repository_audit: bool = False,
):
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text(paper_text, encoding="utf-8")
    result_path.write_text(result_text, encoding="utf-8")
    reproduction_paths = [str(result_path)]
    if reproduction_log is not None:
        log_path = tmp_path / "train.log"
        log_path.write_text(reproduction_log, encoding="utf-8")
        reproduction_paths.append(str(log_path))

    app = AppContext(settings=_settings(tmp_path), hy3_client=client)
    repository_audit_path: str | None = None
    if include_repository_audit:
        repository_path = tmp_path / "repository"
        repository_path.mkdir()
        (repository_path / "pyproject.toml").write_text(
            '[project]\nname = "sample"\nversion = "0.1.0"\ndependencies = ["numpy>=2"]\n',
            encoding="utf-8",
        )
        repository_audit = audit_repository(app, repository_path=str(repository_path))
        repository_audit_path = repository_audit.artifacts[0].relative_path
    claims = await extract_claims(app, paper_paths=[str(paper_path)], focus=None)
    comparison = await compare_results(
        app,
        paper_paths=[str(paper_path)],
        reproduction_paths=reproduction_paths,
        metric_hints=["accuracy"],
        group_filters=group_filters,
        claims_artifact_path=claims.artifacts[0].relative_path,
    )
    score = await score_paper(
        app,
        paper_paths=[str(paper_path)],
        reproduction_paths=reproduction_paths,
        rubric_focus=[],
        group_filters=group_filters,
        claims_artifact_path=claims.artifacts[0].relative_path,
        comparison_artifact_path=comparison.artifacts[0].relative_path,
        repository_audit_artifact_path=repository_audit_path,
    )
    return app, claims, comparison, score


@pytest.mark.asyncio
async def test_filtered_group_workflow_keeps_one_scope_through_report(tmp_path) -> None:
    client = SequenceHy3Client(
        {
            ExtractClaimsResult: [_claim_payload()],
            CompareReproductionResult: [_comparison_payload(paper_value=0.90)],
            ReliabilityScoreResult: [
                _score_payload(
                    [
                        {
                            "name": "reproduction_result_agreement",
                            "score": 60,
                            "rationale": "Dataset-A is lower than the paper value.",
                        },
                        {
                            "name": "experiment_setup_transparency",
                            "score": 70,
                            "rationale": "The selected dataset and split are explicit.",
                        },
                    ],
                    summary="The assessment is scoped to Dataset-A/test.",
                )
            ],
        }
    )
    app, claims, comparison, score = await _run_analysis(
        tmp_path,
        client=client,
        paper_text="The paper reports accuracy 0.90 on Dataset-A/test.",
        result_text=("dataset,split,accuracy\nDataset-A,test,0.8\nDataset-A,test,0.9\nDataset-B,test,0.1\n"),
        group_filters={"dataset": "Dataset-A", "split": "test"},
    )
    report = render_report(
        app,
        claims_artifact_path=claims.artifacts[0].relative_path,
        comparison_artifact_path=comparison.artifacts[0].relative_path,
        score_artifact_path=score.artifacts[0].relative_path,
        title="Filtered group case",
    )
    report_text = (app.settings.reproscope_workspace / report.report_path).read_text(encoding="utf-8")

    assert comparison.metric_comparisons[0].reproduced_value == pytest.approx(0.85)
    assert (
        comparison.group_filters
        == score.group_filters
        == {
            "dataset": "Dataset-A",
            "split": "test",
        }
    )
    assert "Experiment group filters: `dataset=Dataset-A, split=test`." in report_text


@pytest.mark.asyncio
async def test_insufficient_evidence_workflow_abstains_in_final_report(tmp_path) -> None:
    client = SequenceHy3Client(
        {
            ExtractClaimsResult: [_claim_payload()],
            CompareReproductionResult: [_comparison_payload(paper_value=0.90)],
            ReliabilityScoreResult: [
                _score_payload(
                    [
                        {
                            "name": "baseline_fairness",
                            "score": 70,
                            "rationale": "Only limited baseline evidence is available.",
                        }
                    ],
                    summary="The available evidence is too sparse for an overall reliability score.",
                )
            ],
        }
    )
    app, claims, comparison, score = await _run_analysis(
        tmp_path,
        client=client,
        paper_text="The paper reports accuracy 0.90 but omits most experimental details.",
        result_text="accuracy\n0.82\n0.84\n",
        include_repository_audit=True,
    )

    graph = build_evidence_graph(
        app,
        claims_artifact_path=claims.artifacts[0].relative_path,
        comparison_artifact_path=comparison.artifacts[0].relative_path,
        score_artifact_path=score.artifacts[0].relative_path,
    )
    report = render_report(
        app,
        claims_artifact_path=claims.artifacts[0].relative_path,
        comparison_artifact_path=comparison.artifacts[0].relative_path,
        score_artifact_path=score.artifacts[0].relative_path,
        evidence_graph_artifact_path=graph.artifacts[0].relative_path,
        title="Insufficient evidence case",
    )
    report_text = (app.settings.reproscope_workspace / report.report_path).read_text(encoding="utf-8")

    assert score.rubric_coverage == 0.15
    assert score.overall_score is None
    assert score.reliability_band.value == "insufficient"
    assert any(warning.code == "RUBRIC_PARTIAL_COVERAGE" for warning in score.warnings)
    assert [parent.role for parent in score.parent_artifacts] == [
        "claims",
        "comparison",
        "repository_audit",
    ]
    assert any(warning.code == "REPOSITORY_AUDIT_CALLER_ASSOCIATED" for warning in score.warnings)
    assert "not assessed" in report_text
    assert "RUBRIC_PARTIAL_COVERAGE" in report_text


@pytest.mark.asyncio
async def test_setting_mismatch_workflow_survives_into_final_report(tmp_path) -> None:
    setting_difference = {
        "setting": "epochs",
        "paper_value": "100",
        "reproduction_value": "50",
        "severity": "critical",
        "likely_effect": "The reduced training budget may explain part of the accuracy gap.",
    }
    client = SequenceHy3Client(
        {
            ExtractClaimsResult: [_claim_payload()],
            CompareReproductionResult: [
                _comparison_payload(
                    paper_value=0.90,
                    setting_differences=[setting_difference],
                )
            ],
            ReliabilityScoreResult: [
                _score_payload(
                    [
                        {
                            "name": "reproduction_result_agreement",
                            "score": 45,
                            "rationale": "The reproduced accuracy is lower.",
                        },
                        {
                            "name": "experiment_setup_transparency",
                            "score": 25,
                            "rationale": "The training budget differs from the paper.",
                        },
                    ],
                    summary="A material setup mismatch weakens direct comparability.",
                )
            ],
        }
    )
    app, claims, comparison, score = await _run_analysis(
        tmp_path,
        client=client,
        paper_text="The paper reports accuracy 0.90 after 100 training epochs.",
        result_text="accuracy\n0.81\n0.83\n",
        reproduction_log="epochs=50 optimizer=AdamW",
    )

    report = render_report(
        app,
        claims_artifact_path=claims.artifacts[0].relative_path,
        comparison_artifact_path=comparison.artifacts[0].relative_path,
        score_artifact_path=score.artifacts[0].relative_path,
        title="Setting mismatch case",
    )
    report_text = (app.settings.reproscope_workspace / report.report_path).read_text(encoding="utf-8")

    assert comparison.setting_differences[0].severity.value == "critical"
    assert score.overall_score == pytest.approx(37)
    assert "| epochs | 100 | 50 | critical |" in report_text
    assert "different training budget can make the reported and reproduced metrics" in report_text
    assert "| epochs | 100 | 50 | mismatch |" in report_text


@pytest.mark.asyncio
async def test_workflow_rejects_score_combined_with_another_comparison_run(tmp_path) -> None:
    client = SequenceHy3Client(
        {
            ExtractClaimsResult: [_claim_payload()],
            CompareReproductionResult: [
                _comparison_payload(paper_value=0.90),
                _comparison_payload(paper_value=0.90),
            ],
            ReliabilityScoreResult: [
                _score_payload(
                    [
                        {
                            "name": "reproduction_result_agreement",
                            "score": 60,
                            "rationale": "The reproduced result is lower.",
                        },
                        {
                            "name": "experiment_setup_transparency",
                            "score": 60,
                            "rationale": "The core setup is described.",
                        },
                    ],
                    summary="The workflow is internally consistent.",
                )
            ],
        }
    )
    paper_path = tmp_path / "paper.md"
    result_path = tmp_path / "results.csv"
    paper_path.write_text("The paper reports accuracy 0.90.", encoding="utf-8")
    result_path.write_text("accuracy\n0.84\n0.86\n", encoding="utf-8")
    app = AppContext(settings=_settings(tmp_path), hy3_client=client)
    claims = await extract_claims(app, paper_paths=[str(paper_path)], focus=None)

    comparisons = []
    for _ in range(2):
        comparisons.append(
            await compare_results(
                app,
                paper_paths=[str(paper_path)],
                reproduction_paths=[str(result_path)],
                metric_hints=["accuracy"],
                claims_artifact_path=claims.artifacts[0].relative_path,
            )
        )
    score = await score_paper(
        app,
        paper_paths=[str(paper_path)],
        reproduction_paths=[str(result_path)],
        rubric_focus=[],
        claims_artifact_path=claims.artifacts[0].relative_path,
        comparison_artifact_path=comparisons[0].artifacts[0].relative_path,
    )

    with pytest.raises(ArtifactLineageError, match="exact supplied comparison artifact"):
        render_report(
            app,
            claims_artifact_path=claims.artifacts[0].relative_path,
            comparison_artifact_path=comparisons[1].artifacts[0].relative_path,
            score_artifact_path=score.artifacts[0].relative_path,
            title="Mixed artifact case",
        )


@pytest.mark.asyncio
async def test_zero_denominator_workflow_keeps_unknown_delta_in_report(tmp_path) -> None:
    client = SequenceHy3Client(
        {
            ExtractClaimsResult: [_claim_payload(reported_value="0")],
            CompareReproductionResult: [_comparison_payload(paper_value=0)],
            ReliabilityScoreResult: [
                _score_payload(
                    [
                        {
                            "name": "reproduction_result_agreement",
                            "score": 50,
                            "rationale": "Absolute values can be compared but relative change is undefined.",
                        },
                        {
                            "name": "experiment_setup_transparency",
                            "score": 60,
                            "rationale": "The basic setup is available.",
                        },
                    ],
                    summary="Relative change cannot be interpreted from a zero paper value.",
                )
            ],
        }
    )
    app, claims, comparison, score = await _run_analysis(
        tmp_path,
        client=client,
        paper_text="The paper reports an accuracy value of 0 for this diagnostic case.",
        result_text="accuracy\n0.20\n0.40\n",
    )
    report = render_report(
        app,
        claims_artifact_path=claims.artifacts[0].relative_path,
        comparison_artifact_path=comparison.artifacts[0].relative_path,
        score_artifact_path=score.artifacts[0].relative_path,
        title="Zero denominator case",
    )
    report_text = (app.settings.reproscope_workspace / report.report_path).read_text(encoding="utf-8")
    metric = comparison.metric_comparisons[0]

    assert metric.absolute_delta == pytest.approx(0.3)
    assert metric.relative_delta_percent is None
    assert metric.severity.value == "unknown"
    assert any(warning.code == "RELATIVE_DELTA_UNDEFINED" for warning in comparison.warnings)
    assert "| accuracy | 0 | - | 0 | 0.3 | fraction |" in report_text
    assert "RELATIVE_DELTA_UNDEFINED" in report_text
