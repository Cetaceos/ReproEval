# ruff: noqa: RUF001
from __future__ import annotations

import json

from hy3_reproscope_mcp.models import (
    CompareReproductionResult,
    ExtractClaimsResult,
    ReliabilityScoreResult,
    ToolWarning,
)
from hy3_reproscope_mcp.prompts import build_structured_messages
from hy3_reproscope_mcp.renderer import render_markdown_report
from hy3_reproscope_mcp.report_localization import localize_report
from hy3_reproscope_mcp.transfer_models import SolutionProfileResult, TransferAssessmentResult
from hy3_reproscope_mcp.transfer_renderer import render_transfer_markdown_report


def test_chinese_report_localizes_fixed_text_and_engineering_terms() -> None:
    markdown = "\n".join(
        [
            "# Demo",
            "## Audit trail",
            "### Upstream artifact inventory",
            "### Direct parent lineage",
            "| Dimension | Weight | Status | Score | Rationale | Evidence gaps | Evidence |",
            "| reproduction_result_agreement | 30% | insufficient_evidence | - | - | - | - |",
            "Graph relations are constructed and validated locally from the supplied profile and assessment. "
            "Inferred transfer relations remain conditional evidence, not measured target performance.",
        ]
    )

    localized = localize_report(markdown, language="zh-CN")

    assert "## 运行追踪" in localized
    assert "### 上游结果文件清单" in localized
    assert "### 直接输入输出关系" in localized
    assert "| 评估维度 | 权重 | 状态 | 得分 | 判断依据 | 证据缺口 | 证据 |" in localized
    assert "| 复现结果一致性 | 30% | 证据不足 |" in localized
    assert "不代表目标环境中的实测性能" in localized
    assert "工件血缘" not in localized


def test_english_report_is_unchanged() -> None:
    markdown = "## Audit trail\n### Direct parent lineage"

    assert localize_report(markdown, language="en") == markdown


def test_chinese_prompt_requests_natural_chinese_without_changing_schema_tokens() -> None:
    messages = build_structured_messages(
        task="extract",
        instructions="Return evidence-grounded claims.",
        payload={"sources": []},
        response_model=ExtractClaimsResult,
        output_language="zh-CN",
    )
    payload = json.loads(messages[1]["content"])

    assert "natural Simplified Chinese" in payload["instructions"]
    assert "JSON field names" in payload["instructions"]
    assert "输入输出链路校验" in payload["instructions"]


def test_paper_renderer_emits_chinese_fixed_structure() -> None:
    markdown = render_markdown_report(
        title="论文复现审查",
        claims=ExtractClaimsResult(run_id="claims", summary="已提取论文主张。"),
        comparison=CompareReproductionResult(
            run_id="comparison",
            summary="复现证据不足。",
            conclusion_stability="需要更多实验。",
        ),
        score=ReliabilityScoreResult(
            run_id="score",
            reliability_band="insufficient",
            conclusion_confidence=0.2,
            summary="现有证据不足以形成完整结论。",
            dimensions=[
                {
                    "name": "reproduction_result_agreement",
                    "assessment_status": "insufficient_evidence",
                    "rationale": "缺少独立复现结果。",
                }
            ],
            reproduction_verdict="证据不足。",
            experimental_rigor_verdict="仍需补充实验设置。",
        ),
        artifact_inventory=[],
        language="zh-CN",
    )

    assert "## 执行摘要" in markdown
    assert "## 复现结果对比" in markdown
    assert "### 上游结果文件清单" in markdown
    assert "复现结果一致性" in markdown
    assert "## Executive summary" not in markdown


def test_transfer_renderer_emits_chinese_fixed_structure() -> None:
    markdown = render_transfer_markdown_report(
        title="方案迁移评估",
        profile=SolutionProfileResult(
            run_id="profile",
            summary="已提取源方案。",
            warnings=[ToolWarning(code="LICENSE_SIGNALS_NOT_LEGAL_ADVICE", message="first")],
        ),
        assessment=TransferAssessmentResult(
            run_id="assessment",
            solution_profile_run_id="profile",
            summary="当前只能形成条件化结论。",
            target_context_summary="三维移动通信与感知环境。",
            feasibility_band="conditional",
            conclusion_confidence=0.5,
            dimensions=[
                {
                    "name": "assumption_compatibility",
                    "assessment_status": "assessed",
                    "score": 60,
                    "rationale": "部分前提条件需要重新验证。",
                }
            ],
            warnings=[ToolWarning(code="LICENSE_SIGNALS_NOT_LEGAL_ADVICE", message="second")],
        ),
        artifact_inventory=[],
        language="zh-CN",
    )

    assert "## 决策摘要" in markdown
    assert "## 迁移可行性评估" in markdown
    assert "不预测目标环境中的具体性能" in markdown
    assert markdown.count("LICENSE_SIGNALS_NOT_LEGAL_ADVICE") == 1
    assert "许可证和来源信息仅用于初步检查，不构成法律结论。" in markdown
    assert "## Decision summary" not in markdown
