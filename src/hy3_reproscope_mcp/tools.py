"""MCP tool registration and business handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Annotated, Any, TypeVar
from uuid import uuid4

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from .errors import GroupFilterError
from .evidence_graph import build_graph, validate_evidence_graph
from .execution import preflight_third_party_execution
from .lineage import (
    merge_sources,
    validate_comparison_context,
    validate_graph_artifact_lineage,
    validate_report_lineage,
    validate_score_context,
    validate_transfer_context,
    validate_transfer_graph_artifact_lineage,
    validate_transfer_report_lineage,
)
from .loaders import load_sources, normalize_group_by, normalize_group_filters
from .metric_registry import metric_registry_payload
from .metrics import (
    compute_group_metric_comparisons,
    compute_metric_differences,
    validate_group_analysis_request,
)
from .models import (
    SCHEMA_VERSION,
    ArtifactAuditEntry,
    ArtifactIntegrity,
    BuildEvidenceGraphResult,
    ClaimRelationDiagnostics,
    CompareReproductionResult,
    DomainFinding,
    DomainFindingStatus,
    DomainProfileMode,
    DomainProfileName,
    EvidenceCitation,
    EvidenceKind,
    ExtractClaimsResult,
    ISACEvidenceLevel,
    ISACProfileAnalysis,
    ISACSystemType,
    ParentArtifactReference,
    ProfileRequestSource,
    ReliabilityDimension,
    ReliabilityScoreResult,
    RenderReportResult,
    ToolResultBase,
    ToolWarning,
)
from .profiles import GENERIC_PROFILE_VERSION
from .profiles import registry as profile_registry
from .profiles.isac_phy import ISAC_PROFILE_VERSION, resolve_profile_activation
from .prompts import build_structured_messages
from .renderer import render_markdown_report
from .repository_models import RepositoryAuditResult
from .repository_scanner import audit_repository as scan_repository
from .rubric import normalize_score, rubric_payload
from .setting_analysis import build_setting_checks, reconcile_setting_differences
from .transfer_graph import build_transfer_graph, require_validated_transfer_graph
from .transfer_models import (
    BuildTransferGraphResult,
    RenderTransferReportResult,
    SolutionProfileResult,
    TransferAssessmentResult,
    TransferDimension,
)
from .transfer_renderer import render_transfer_markdown_report
from .transfer_rubric import normalize_transfer_assessment, transfer_rubric_payload
from .workspace import RunManifestWriter, Workspace, parent_artifact_reference

ResultT = TypeVar("ResultT", bound=ToolResultBase)


def register_tools(server: FastMCP[Any]) -> None:
    """Register all ReproScope MCP tools."""

    @server.tool(
        name="reproscope_extract_claims",
        description=(
            "Load paper text/markdown or structured notes, then use Hy3 to extract reproducibility-relevant "
            "claims, metrics, baselines, assumptions, and missing experimental details."
        ),
    )
    async def reproscope_extract_claims(
        paper_paths: Annotated[
            list[str],
            Field(
                min_length=1,
                description=(
                    "Local paper or note files to inspect. Supported: pdf, md, txt, csv, json, jsonl, yaml, log."
                ),
            ),
        ],
        focus: Annotated[
            str | None,
            Field(description="Optional focus such as dataset shift, benchmark leakage, ablations, or metrics."),
        ] = None,
        domain_profile: Annotated[
            DomainProfileMode,
            Field(
                description=(
                    "Optional domain profile. generic preserves the normal audit, isac_phy explicitly enables "
                    "the ISAC physical-layer audit, and auto enables it only after conservative detection."
                )
            ),
        ] = DomainProfileMode.GENERIC,
        profile_request_source: Annotated[
            ProfileRequestSource,
            Field(
                description=(
                    "Why an explicit profile was selected. Use user_instruction when the MCP client mapped a "
                    "natural-language user request to domain_profile."
                )
            ),
        ] = ProfileRequestSource.TOOL_PARAMETER,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Extract experiment claims and reproducibility signals from paper materials."""

        app = _app_context(ctx)
        result = await extract_claims(
            app,
            paper_paths=paper_paths,
            focus=focus,
            domain_profile=domain_profile,
            profile_request_source=profile_request_source,
        )
        return result.model_dump(mode="json")

    @server.tool(
        name="reproscope_compare_results",
        description=(
            "Load paper claims and reproduction artifacts, then use Hy3 to compare reported results with reproduced "
            "results, identify metric deltas, validate three-way Claim relations, expose unassessed-Claim coverage, "
            "and explain likely causes."
        ),
    )
    async def reproscope_compare_results(
        paper_paths: Annotated[
            list[str],
            Field(min_length=1, description="Local files containing paper claims or experiment descriptions."),
        ],
        reproduction_paths: Annotated[
            list[str],
            Field(min_length=1, description="Local reproduction result files such as CSV, JSON, logs, or markdown."),
        ],
        metric_hints: Annotated[
            list[str] | None,
            Field(description="Optional metric names to prioritize, for example accuracy, F1, BLEU, latency."),
        ] = None,
        group_filters: Annotated[
            dict[str, str] | None,
            Field(
                description=(
                    "Optional local filters for structured experiment groups, "
                    'for example {"dataset": "Dataset-A", "split": "test", "method": "ours"}.'
                )
            ),
        ] = None,
        group_by: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Optional experiment dimensions for deterministic per-group statistics, for example "
                    '["dataset", "method"].'
                )
            ),
        ] = None,
        claims_artifact_path: Annotated[
            str | None,
            Field(description="Optional extract_claims.json path under REPROSCOPE_WORKSPACE."),
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Compare original paper claims against local reproduction evidence."""

        app = _app_context(ctx)
        result = await compare_results(
            app,
            paper_paths=paper_paths,
            reproduction_paths=reproduction_paths,
            metric_hints=metric_hints or [],
            group_filters=group_filters or {},
            group_by=group_by or [],
            claims_artifact_path=claims_artifact_path,
        )
        return result.model_dump(mode="json")

    @server.tool(
        name="reproscope_score_paper",
        description=(
            "Use Hy3 to produce a structured reliability and experimental-rigor score for a paper, combining "
            "paper evidence, reproduction evidence, and methodological risk factors."
        ),
    )
    async def reproscope_score_paper(
        paper_paths: Annotated[
            list[str],
            Field(min_length=1, description="Local files containing paper text, method notes, or experiment sections."),
        ],
        reproduction_paths: Annotated[
            list[str] | None,
            Field(description="Optional local reproduction evidence such as results CSVs, JSON, logs, or notes."),
        ] = None,
        rubric_focus: Annotated[
            list[str] | None,
            Field(description="Optional rubric dimensions to emphasize, such as controls, ablations, or data leakage."),
        ] = None,
        group_filters: Annotated[
            dict[str, str] | None,
            Field(description="The same structured-result group filters used for comparison, if any."),
        ] = None,
        claims_artifact_path: Annotated[
            str | None,
            Field(description="Optional extract_claims.json path under REPROSCOPE_WORKSPACE."),
        ] = None,
        comparison_artifact_path: Annotated[
            str | None,
            Field(description="Optional compare_results.json path under REPROSCOPE_WORKSPACE."),
        ] = None,
        repository_audit_artifact_path: Annotated[
            str | None,
            Field(description="Optional repository_audit.json path under REPROSCOPE_WORKSPACE."),
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Score paper reliability and experimental rigor using evidence-grounded Hy3 analysis."""

        app = _app_context(ctx)
        result = await score_paper(
            app,
            paper_paths=paper_paths,
            reproduction_paths=reproduction_paths or [],
            rubric_focus=rubric_focus or [],
            group_filters=group_filters or {},
            claims_artifact_path=claims_artifact_path,
            comparison_artifact_path=comparison_artifact_path,
            repository_audit_artifact_path=repository_audit_artifact_path,
        )
        return result.model_dump(mode="json")

    @server.tool(
        name="reproscope_build_evidence_graph",
        description=(
            "Read completed claim, comparison, and score artifacts, validate their source lineage, and build a "
            "deterministic Claim-Evidence-Result Graph without making another Hy3 API call. "
            "The returned top-level JSON includes graph_validated=true before the large nodes and edges payload."
        ),
    )
    async def reproscope_build_evidence_graph(
        claims_artifact_path: Annotated[
            str,
            Field(description="Path to an extract_claims.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        comparison_artifact_path: Annotated[
            str,
            Field(description="Path to a compare_results.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        score_artifact_path: Annotated[
            str,
            Field(description="Path to a reliability_score.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Build and persist a validated evidence graph from prior analysis artifacts."""

        app = _app_context(ctx)
        result = build_evidence_graph(
            app,
            claims_artifact_path=claims_artifact_path,
            comparison_artifact_path=comparison_artifact_path,
            score_artifact_path=score_artifact_path,
        )
        return result.model_dump(mode="json")

    @server.tool(
        name="reproscope_render_report",
        description=(
            "Read completed ReproScope claim, comparison, and score JSON artifacts and render a deterministic "
            "Markdown audit report without making another Hy3 API call."
        ),
    )
    async def reproscope_render_report(
        claims_artifact_path: Annotated[
            str,
            Field(description="Path to an extract_claims.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        comparison_artifact_path: Annotated[
            str,
            Field(description="Path to a compare_results.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        score_artifact_path: Annotated[
            str,
            Field(description="Path to a reliability_score.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        evidence_graph_artifact_path: Annotated[
            str | None,
            Field(description="Optional evidence_graph.json path under REPROSCOPE_WORKSPACE."),
        ] = None,
        title: Annotated[
            str,
            Field(min_length=1, max_length=200, description="Report title."),
        ] = "ReproScope paper reliability audit",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Render a final Markdown report from validated ReproScope artifacts."""

        app = _app_context(ctx)
        result = render_report(
            app,
            claims_artifact_path=claims_artifact_path,
            comparison_artifact_path=comparison_artifact_path,
            score_artifact_path=score_artifact_path,
            evidence_graph_artifact_path=evidence_graph_artifact_path,
            title=title,
        )
        return result.model_dump(mode="json")

    @server.tool(
        name="reproscope_extract_solution_profile",
        description=(
            "Load papers, patents, design notes, or open-source documentation and use Hy3 to extract a "
            "source-grounded profile of objectives, components, dependencies, assumptions, resources, and gaps."
        ),
    )
    async def reproscope_extract_solution_profile(
        solution_paths: Annotated[
            list[str],
            Field(
                min_length=1,
                description=(
                    "Local source-solution files to inspect. Supported: pdf, md, txt, csv, json, jsonl, yaml, log."
                ),
            ),
        ],
        focus: Annotated[
            str | None,
            Field(description="Optional focus such as interfaces, deployment dependencies, data, or implementation."),
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Extract a reusable, evidence-linked profile of an existing technical solution."""

        app = _app_context(ctx)
        result = await extract_solution_profile(app, solution_paths=solution_paths, focus=focus)
        return result.model_dump(mode="json")

    @server.tool(
        name="reproscope_assess_transfer",
        description=(
            "Compare a validated source-solution profile with a supplied target project context, then use Hy3 and "
            "a fixed local rubric to assess compatibility, reusable components, adaptations, risks, and validation."
        ),
    )
    async def reproscope_assess_transfer(
        solution_paths: Annotated[
            list[str],
            Field(min_length=1, description="The same source-solution files used to create the profile artifact."),
        ],
        target_context_paths: Annotated[
            list[str],
            Field(
                min_length=1,
                description="Local files describing target requirements, constraints, resources, and success criteria.",
            ),
        ],
        solution_profile_artifact_path: Annotated[
            str,
            Field(description="Path to a solution_profile.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        focus: Annotated[
            str | None,
            Field(description="Optional decision focus such as latency, data availability, cost, or integration."),
        ] = None,
        repository_audit_artifact_path: Annotated[
            str | None,
            Field(description="Optional repository_audit.json path under REPROSCOPE_WORKSPACE."),
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Assess conditional transfer feasibility without predicting unsupported target performance."""

        app = _app_context(ctx)
        result = await assess_transfer(
            app,
            solution_paths=solution_paths,
            target_context_paths=target_context_paths,
            solution_profile_artifact_path=solution_profile_artifact_path,
            focus=focus,
            repository_audit_artifact_path=repository_audit_artifact_path,
        )
        return result.model_dump(mode="json")

    @server.tool(
        name="reproscope_build_transfer_graph",
        description=(
            "Read completed solution-profile and transfer-assessment artifacts, validate their exact lineage, and "
            "build a deterministic graph of assumptions, target constraints, component transfer, adaptations, "
            "risks, and validation steps without another Hy3 API call. "
            "The returned top-level JSON includes graph_validated=true before the large nodes and edges payload."
        ),
    )
    async def reproscope_build_transfer_graph(
        solution_profile_artifact_path: Annotated[
            str,
            Field(description="Path to a solution_profile.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        transfer_assessment_artifact_path: Annotated[
            str,
            Field(description="Path to a transfer_assessment.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Build and persist a validated transfer evidence graph."""

        app = _app_context(ctx)
        result = build_transfer_evidence_graph(
            app,
            solution_profile_artifact_path=solution_profile_artifact_path,
            transfer_assessment_artifact_path=transfer_assessment_artifact_path,
        )
        return result.model_dump(mode="json")

    @server.tool(
        name="reproscope_render_transfer_report",
        description=(
            "Validate completed solution-profile and transfer-assessment artifacts, then render a deterministic "
            "Markdown decision report without making another Hy3 API call."
        ),
    )
    async def reproscope_render_transfer_report(
        solution_profile_artifact_path: Annotated[
            str,
            Field(description="Path to a solution_profile.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        transfer_assessment_artifact_path: Annotated[
            str,
            Field(description="Path to a transfer_assessment.json artifact under REPROSCOPE_WORKSPACE."),
        ],
        transfer_graph_artifact_path: Annotated[
            str | None,
            Field(description="Optional transfer_graph.json path under REPROSCOPE_WORKSPACE."),
        ] = None,
        title: Annotated[
            str,
            Field(min_length=1, max_length=200, description="Transfer assessment report title."),
        ] = "ReproScope technology transfer assessment",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Render a transfer decision report from lineage-validated artifacts."""

        app = _app_context(ctx)
        result = render_transfer_report(
            app,
            solution_profile_artifact_path=solution_profile_artifact_path,
            transfer_assessment_artifact_path=transfer_assessment_artifact_path,
            transfer_graph_artifact_path=transfer_graph_artifact_path,
            title=title,
        )
        return result.model_dump(mode="json")

    @server.tool(
        name="reproscope_audit_repository",
        description=(
            "Statically inspect bounded Python repository metadata, dependencies, entrypoints, test instructions, "
            "and environment-variable names without executing repository code or discovered commands."
        ),
    )
    async def reproscope_audit_repository(
        repository_path: Annotated[
            str,
            Field(description="Local repository directory under REPROSCOPE_ALLOWED_ROOTS."),
        ],
        max_python_files: Annotated[
            int,
            Field(
                ge=1,
                le=500,
                description="Maximum number of Python source files to parse statically; defaults to 200.",
            ),
        ] = 200,
        execution_command: Annotated[
            str | None,
            Field(
                max_length=4000,
                description=(
                    "Optional command to record for a non-executing third-party preflight. The command is hashed "
                    "and refused; repository code is never started by this tool."
                ),
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Audit static repository reproducibility conditions without running repository code."""

        app = _app_context(ctx)
        result = audit_repository(
            app,
            repository_path=repository_path,
            max_python_files=max_python_files,
            execution_command=execution_command,
        )
        return result.model_dump(mode="json")


async def extract_solution_profile(
    app_context: Any,
    *,
    solution_paths: list[str],
    focus: str | None,
) -> SolutionProfileResult:
    return await _run_async_tool(
        app_context,
        prefix="solution",
        tool_name="reproscope_extract_solution_profile",
        operation=lambda run_id: _extract_solution_profile(
            app_context,
            run_id=run_id,
            solution_paths=solution_paths,
            focus=focus,
        ),
    )


async def _extract_solution_profile(
    app_context: Any,
    *,
    run_id: str,
    solution_paths: list[str],
    focus: str | None,
) -> SolutionProfileResult:
    solution_bundle = load_sources(
        solution_paths,
        role="solution",
        settings=app_context.settings,
        source_id_prefix="solution",
    )
    payload = {
        "run_id": run_id,
        "focus": focus,
        "solution_sources": solution_bundle.prompt_sources(),
    }
    messages = build_structured_messages(
        task="extract_solution_profile",
        instructions=(
            "Extract only evidence-supported objectives, success criteria, components, interfaces, dependencies, "
            "assumptions, resource requirements, implementation signals, license signals, provenance signals, and "
            "evidence gaps. Assign stable IDs within this response, for example objective_1, component_1, "
            "dependency_1, assumption_1, and resource_1. A license or provenance signal records only what the source "
            "states and must not become a legal conclusion. Every citation must copy both source_id and one exact "
            "locator from that source's segments; omit source_reference because the server validates and attaches it."
        ),
        payload=payload,
        response_model=SolutionProfileResult,
    )
    result = await app_context.get_hy3_client().complete_structured(messages, SolutionProfileResult)
    result.run_id = run_id
    result.sources = solution_bundle.source_references()
    _sanitize_solution_profile_ids(result)
    _sanitize_citations(result, solution_bundle.citation_references())
    if result.license_signals or result.provenance_signals:
        result.warnings.append(
            ToolWarning(
                code="LICENSE_SIGNALS_NOT_LEGAL_ADVICE",
                message="License and provenance signals are screening evidence, not a legal conclusion.",
            )
        )
    result.warnings.extend(solution_bundle.warnings)
    result.artifacts.append(_write_artifact(app_context, run_id, "solution_profile.json", result))
    return result


async def assess_transfer(
    app_context: Any,
    *,
    solution_paths: list[str],
    target_context_paths: list[str],
    solution_profile_artifact_path: str,
    focus: str | None,
    repository_audit_artifact_path: str | None = None,
) -> TransferAssessmentResult:
    return await _run_async_tool(
        app_context,
        prefix="transfer",
        tool_name="reproscope_assess_transfer",
        operation=lambda run_id: _assess_transfer(
            app_context,
            run_id=run_id,
            solution_paths=solution_paths,
            target_context_paths=target_context_paths,
            solution_profile_artifact_path=solution_profile_artifact_path,
            focus=focus,
            repository_audit_artifact_path=repository_audit_artifact_path,
        ),
    )


async def _assess_transfer(
    app_context: Any,
    *,
    run_id: str,
    solution_paths: list[str],
    target_context_paths: list[str],
    solution_profile_artifact_path: str,
    focus: str | None,
    repository_audit_artifact_path: str | None,
) -> TransferAssessmentResult:
    solution_bundle = load_sources(
        solution_paths,
        role="solution",
        settings=app_context.settings,
        source_id_prefix="solution",
    )
    target_bundle = load_sources(
        target_context_paths,
        role="target",
        settings=app_context.settings,
        source_id_prefix="target",
    )
    workspace = Workspace(app_context.settings)
    profile, profile_parent = _read_result_artifact(
        workspace,
        solution_profile_artifact_path,
        SolutionProfileResult,
        "solution_profile",
    )
    repository_audit: RepositoryAuditResult | None = None
    repository_parent: ParentArtifactReference | None = None
    if repository_audit_artifact_path:
        repository_audit, repository_parent = _read_result_artifact(
            workspace,
            repository_audit_artifact_path,
            RepositoryAuditResult,
            "repository_audit",
        )
    validate_transfer_context(
        solution_sources=solution_bundle.source_references(),
        profile=profile,
    )
    payload = {
        "run_id": run_id,
        "focus": focus,
        "fixed_transfer_rubric": transfer_rubric_payload(),
        "solution_profile": profile.model_dump(mode="json"),
        "solution_sources": solution_bundle.prompt_sources(),
        "target_context_sources": target_bundle.prompt_sources(),
        "repository_audit": (
            _repository_audit_prompt_payload(repository_audit) if repository_audit is not None else None
        ),
    }
    messages = build_structured_messages(
        task="assess_solution_transfer",
        instructions=(
            "Compare the source solution's stated conditions with the supplied target context. Assess every dimension "
            "in fixed_transfer_rubric using exactly its supplied name. Use assessment_status=assessed and a score from "
            "0 to 100 only when the evidence supports it; otherwise use insufficient_evidence and score=null. The "
            "server owns weights and the aggregate, so omit weight or set it to 0. Reuse only assumption_id and "
            "component_id, dependency_id, and resource_id values present in solution_profile. Identify compatible "
            "and invalid assumptions, directly reusable or adaptable components, dependency and resource status, "
            "required changes, risks, and a staged validation plan. Do not provide "
            "a point estimate of target performance without target measurements. Do not issue patent validity, "
            "infringement, or other legal conclusions. Set performance_prediction_provided=false and "
            "legal_conclusion_provided=false. Every citation must copy both source_id and one exact locator from the "
            "solution or target sources; omit source_reference because the server validates and attaches it. A "
            "repository_audit, when supplied, is a caller-associated static scan: use it only as implementation and "
            "validation-condition evidence, do not assume it proves correspondence to the source solution, and do "
            "not treat discovered commands or declarations as executed successfully."
        ),
        payload=payload,
        response_model=TransferAssessmentResult,
    )
    result = await app_context.get_hy3_client().complete_structured(messages, TransferAssessmentResult)
    result.run_id = run_id
    result.solution_profile_run_id = profile.run_id
    result.repository_audit_run_id = repository_audit.run_id if repository_audit else None
    result.parent_artifacts = [artifact for artifact in (profile_parent, repository_parent) if artifact is not None]
    result.sources = merge_sources(
        solution_bundle.source_references(),
        target_bundle.source_references(),
        repository_audit.sources if repository_audit else [],
    )
    _sanitize_transfer_relations(result, profile)
    _sanitize_citations(
        result,
        solution_bundle.citation_references() | target_bundle.citation_references(),
    )
    normalize_transfer_assessment(result)
    result.warnings.extend([*solution_bundle.warnings, *target_bundle.warnings])
    if repository_audit is not None:
        _attach_repository_audit_to_transfer(result, repository_audit)
    result.artifacts.append(_write_artifact(app_context, run_id, "transfer_assessment.json", result))
    return result


def _sanitize_transfer_relations(
    result: TransferAssessmentResult,
    profile: SolutionProfileResult,
) -> None:
    valid_assumptions = {assumption.assumption_id for assumption in profile.assumptions}
    valid_components = {component.component_id for component in profile.components}
    valid_dependencies = {dependency.dependency_id for dependency in profile.dependencies}
    valid_resources = {resource.resource_id for resource in profile.resource_requirements}
    unknown_assumptions = sorted(
        {item.assumption_id for item in result.assumption_assessments if item.assumption_id not in valid_assumptions}
    )
    unknown_components = {
        item.component_id for item in result.component_assessments if item.component_id not in valid_components
    }
    unknown_dependencies = sorted(
        {item.dependency_id for item in result.dependency_assessments if item.dependency_id not in valid_dependencies}
    )
    unknown_resources = sorted(
        {item.resource_id for item in result.resource_assessments if item.resource_id not in valid_resources}
    )
    for adaptation in result.required_adaptations:
        unknown_components.update(
            component_id for component_id in adaptation.affected_component_ids if component_id not in valid_components
        )
        adaptation.affected_component_ids = [
            component_id for component_id in adaptation.affected_component_ids if component_id in valid_components
        ]
    result.assumption_assessments = [
        item for item in result.assumption_assessments if item.assumption_id in valid_assumptions
    ]
    result.component_assessments = [
        item for item in result.component_assessments if item.component_id in valid_components
    ]
    result.dependency_assessments = [
        item for item in result.dependency_assessments if item.dependency_id in valid_dependencies
    ]
    result.resource_assessments = [item for item in result.resource_assessments if item.resource_id in valid_resources]
    if unknown_assumptions:
        result.warnings.append(
            ToolWarning(
                code="UNKNOWN_TRANSFER_ASSUMPTION_ID",
                message="Unknown assumption IDs were removed from the transfer assessment: "
                + ", ".join(unknown_assumptions),
            )
        )
    if unknown_components:
        result.warnings.append(
            ToolWarning(
                code="UNKNOWN_TRANSFER_COMPONENT_ID",
                message="Unknown component IDs were removed from transfer relations: "
                + ", ".join(sorted(unknown_components)),
            )
        )
    if unknown_dependencies:
        result.warnings.append(
            ToolWarning(
                code="UNKNOWN_TRANSFER_DEPENDENCY_ID",
                message="Unknown dependency IDs were removed from the transfer assessment: "
                + ", ".join(unknown_dependencies),
            )
        )
    if unknown_resources:
        result.warnings.append(
            ToolWarning(
                code="UNKNOWN_TRANSFER_RESOURCE_ID",
                message=(
                    "Unknown resource IDs were removed from the transfer assessment: " + ", ".join(unknown_resources)
                ),
            )
        )


def _sanitize_solution_profile_ids(result: SolutionProfileResult) -> None:
    collections = (
        ("objective_id", result.objectives),
        ("component_id", result.components),
        ("dependency_id", result.dependencies),
        ("assumption_id", result.assumptions),
        ("resource_id", result.resource_requirements),
    )
    duplicate_ids: set[str] = set()
    for field_name, items in collections:
        unique: list[Any] = []
        seen: set[str] = set()
        for item in items:
            item_id = getattr(item, field_name)
            if item_id in seen:
                duplicate_ids.add(item_id)
                continue
            seen.add(item_id)
            unique.append(item)
        items[:] = unique
    if duplicate_ids:
        result.warnings.append(
            ToolWarning(
                code="DUPLICATE_SOLUTION_PROFILE_ID",
                message="Only the first entity was kept for duplicated solution-profile IDs: "
                + ", ".join(sorted(duplicate_ids)),
            )
        )


def audit_repository(
    app_context: Any,
    *,
    repository_path: str,
    max_python_files: int = 200,
    execution_command: str | None = None,
) -> RepositoryAuditResult:
    return _run_sync_tool(
        app_context,
        prefix="repository",
        tool_name="reproscope_audit_repository",
        operation=lambda run_id: _audit_repository(
            app_context,
            run_id=run_id,
            repository_path=repository_path,
            max_python_files=max_python_files,
            execution_command=execution_command,
        ),
    )


def _audit_repository(
    app_context: Any,
    *,
    run_id: str,
    repository_path: str,
    max_python_files: int,
    execution_command: str | None,
) -> RepositoryAuditResult:
    result = scan_repository(
        run_id=run_id,
        repository_path=repository_path,
        settings=app_context.settings,
        max_python_files=max_python_files,
    )
    result.execution_preflight = preflight_third_party_execution(
        execution_command,
        allowed_root=result.repository_root,
    )
    result.artifacts.append(_write_artifact(app_context, run_id, "repository_audit.json", result))
    return result


def _repository_audit_prompt_payload(audit: RepositoryAuditResult) -> dict[str, Any]:
    return {
        "run_id": audit.run_id,
        "association": (
            "Caller supplied; the server does not independently prove that this repository corresponds to the "
            "paper or source solution."
        ),
        "analysis_scope": "Bounded static inspection only; no repository code or discovered command was executed.",
        "summary": audit.summary,
        "metrics": audit.metrics.model_dump(mode="json"),
        "gaps": [gap.model_dump(mode="json") for gap in audit.gaps[:50]],
        "dependencies": [
            dependency.model_dump(mode="json", exclude={"source_path"}) for dependency in audit.dependencies[:50]
        ],
        "entrypoints": [
            entrypoint.model_dump(mode="json", exclude={"source_path"}) for entrypoint in audit.entrypoints[:25]
        ],
        "environment_variable_names": [signal.name for signal in audit.environment_variables[:50]],
        "documented_install_commands": audit.install_commands[:20],
        "documented_test_commands": audit.test_commands[:20],
        "execution_policy": audit.execution_policy,
        "execution_preflight": audit.execution_preflight.model_dump(mode="json"),
        "executed_repository_code": audit.executed_repository_code,
    }


def _repository_gap_texts(audit: RepositoryAuditResult) -> list[str]:
    return [f"[repository audit:{gap.severity.value}] {gap.code}: {gap.message}" for gap in audit.gaps]


def _append_evidence_gaps(dimension: Any, gaps: list[str]) -> None:
    for gap in gaps:
        if gap not in dimension.evidence_gaps:
            dimension.evidence_gaps.append(gap)


def _attach_repository_audit_warnings(result: ToolResultBase, audit: RepositoryAuditResult) -> None:
    result.warnings.extend(audit.warnings)
    result.warnings.append(
        ToolWarning(
            code="REPOSITORY_AUDIT_CALLER_ASSOCIATED",
            message=(
                "The repository audit was supplied by the caller; ReproScope did not independently prove that the "
                "repository corresponds to the paper or source solution, and the static scan did not execute code."
            ),
        )
    )


def _attach_repository_audit_to_score(
    result: ReliabilityScoreResult,
    audit: RepositoryAuditResult,
) -> None:
    gaps = _repository_gap_texts(audit)
    for dimension in result.dimensions:
        if dimension.name is ReliabilityDimension.DATA_IMPLEMENTATION_AVAILABILITY:
            _append_evidence_gaps(dimension, gaps)
    _attach_repository_audit_warnings(result, audit)


def _attach_repository_audit_to_transfer(
    result: TransferAssessmentResult,
    audit: RepositoryAuditResult,
) -> None:
    all_gaps = _repository_gap_texts(audit)
    dependency_codes = {
        "DEPENDENCIES_NOT_DECLARED",
        "DEPENDENCIES_NOT_FULLY_PINNED",
        "ENVIRONMENT_EXAMPLE_NOT_FOUND",
        "INSTALL_COMMAND_NOT_DOCUMENTED",
        "LOCKFILE_NOT_FOUND",
        "MISSING_PROJECT_METADATA",
        "PYTHON_VERSION_UNSPECIFIED",
    }
    validation_codes = {
        "ENTRYPOINT_NOT_FOUND",
        "REPOSITORY_SCAN_INCOMPLETE",
        "TEST_PROCEDURE_NOT_FOUND",
    }
    dependency_gaps = [text for text, gap in zip(all_gaps, audit.gaps, strict=True) if gap.code in dependency_codes]
    validation_gaps = [text for text, gap in zip(all_gaps, audit.gaps, strict=True) if gap.code in validation_codes]
    for dimension in result.dimensions:
        if dimension.name is TransferDimension.EVIDENCE_RELIABILITY:
            _append_evidence_gaps(dimension, all_gaps)
        elif dimension.name is TransferDimension.DEPENDENCY_FEASIBILITY:
            _append_evidence_gaps(dimension, dependency_gaps)
        elif dimension.name is TransferDimension.VALIDATION_READINESS:
            _append_evidence_gaps(dimension, validation_gaps)
    _attach_repository_audit_warnings(result, audit)


def build_transfer_evidence_graph(
    app_context: Any,
    *,
    solution_profile_artifact_path: str,
    transfer_assessment_artifact_path: str,
) -> BuildTransferGraphResult:
    return _run_sync_tool(
        app_context,
        prefix="transfer_graph",
        tool_name="reproscope_build_transfer_graph",
        operation=lambda run_id: _build_transfer_evidence_graph(
            app_context,
            run_id=run_id,
            solution_profile_artifact_path=solution_profile_artifact_path,
            transfer_assessment_artifact_path=transfer_assessment_artifact_path,
        ),
    )


def _build_transfer_evidence_graph(
    app_context: Any,
    *,
    run_id: str,
    solution_profile_artifact_path: str,
    transfer_assessment_artifact_path: str,
) -> BuildTransferGraphResult:
    workspace = Workspace(app_context.settings)
    profile, profile_parent = _read_result_artifact(
        workspace,
        solution_profile_artifact_path,
        SolutionProfileResult,
        "solution_profile",
    )
    assessment, assessment_parent = _read_result_artifact(
        workspace,
        transfer_assessment_artifact_path,
        TransferAssessmentResult,
        "transfer_assessment",
    )
    validate_transfer_report_lineage(
        profile,
        assessment,
        profile_artifact=profile_parent,
    )
    result = build_transfer_graph(
        run_id=run_id,
        profile=profile,
        assessment=assessment,
    )
    result.parent_artifacts = [profile_parent, assessment_parent]
    result.artifacts.append(_write_artifact(app_context, run_id, "transfer_graph.json", result))
    return result


def render_transfer_report(
    app_context: Any,
    *,
    solution_profile_artifact_path: str,
    transfer_assessment_artifact_path: str,
    title: str,
    transfer_graph_artifact_path: str | None = None,
) -> RenderTransferReportResult:
    return _run_sync_tool(
        app_context,
        prefix="transfer_report",
        tool_name="reproscope_render_transfer_report",
        operation=lambda run_id: _render_transfer_report(
            app_context,
            run_id=run_id,
            solution_profile_artifact_path=solution_profile_artifact_path,
            transfer_assessment_artifact_path=transfer_assessment_artifact_path,
            transfer_graph_artifact_path=transfer_graph_artifact_path,
            title=title,
        ),
    )


def _render_transfer_report(
    app_context: Any,
    *,
    run_id: str,
    solution_profile_artifact_path: str,
    transfer_assessment_artifact_path: str,
    transfer_graph_artifact_path: str | None,
    title: str,
) -> RenderTransferReportResult:
    workspace = Workspace(app_context.settings)
    profile, profile_parent = _read_result_artifact(
        workspace,
        solution_profile_artifact_path,
        SolutionProfileResult,
        "solution_profile",
    )
    assessment, assessment_parent = _read_result_artifact(
        workspace,
        transfer_assessment_artifact_path,
        TransferAssessmentResult,
        "transfer_assessment",
    )
    validate_transfer_report_lineage(
        profile,
        assessment,
        profile_artifact=profile_parent,
    )
    graph: BuildTransferGraphResult | None = None
    graph_parent: ParentArtifactReference | None = None
    if transfer_graph_artifact_path:
        graph, graph_parent = _read_result_artifact(
            workspace,
            transfer_graph_artifact_path,
            BuildTransferGraphResult,
            "transfer_graph",
        )
    if graph is not None and graph_parent is not None:
        validate_transfer_graph_artifact_lineage(
            graph,
            profile,
            assessment,
            profile_artifact=profile_parent,
            assessment_artifact=assessment_parent,
        )
        require_validated_transfer_graph(graph)
    artifact_inventory = [
        _artifact_audit_entry(profile_parent, profile),
        _artifact_audit_entry(assessment_parent, assessment),
    ]
    if graph is not None and graph_parent is not None:
        artifact_inventory.append(_artifact_audit_entry(graph_parent, graph))
    markdown = render_transfer_markdown_report(
        title=title,
        profile=profile,
        assessment=assessment,
        graph=graph,
        artifact_inventory=artifact_inventory,
    )
    report_artifact = workspace.write_text_artifact(
        run_id,
        "transfer_report.md",
        markdown,
        artifact_type="markdown",
    )
    manifest_path = f"{run_id}/transfer_report_manifest.json"
    result = RenderTransferReportResult(
        run_id=run_id,
        title=title,
        summary=assessment.summary,
        report_path=report_artifact.relative_path,
        manifest_path=manifest_path,
        source_run_ids=[profile.run_id, assessment.run_id],
        transfer_graph_run_id=graph.run_id if graph else None,
        graph_validated=graph.graph_validated if graph else None,
        artifact_inventory=artifact_inventory,
        parent_artifacts=[
            profile_parent,
            assessment_parent,
            *([graph_parent] if graph_parent else []),
        ],
        sources=assessment.sources,
        artifacts=[report_artifact],
    )
    manifest_artifact = workspace.write_json_artifact(
        run_id,
        "transfer_report_manifest.json",
        result.model_dump(mode="json"),
    )
    if manifest_artifact.payload_hash is not None:
        result.artifact_integrity = ArtifactIntegrity(payload_hash=manifest_artifact.payload_hash)
    result.artifacts.append(manifest_artifact)
    return result


async def extract_claims(
    app_context: Any,
    *,
    paper_paths: list[str],
    focus: str | None,
    domain_profile: DomainProfileMode = DomainProfileMode.GENERIC,
    profile_request_source: ProfileRequestSource = ProfileRequestSource.TOOL_PARAMETER,
) -> ExtractClaimsResult:
    return await _run_async_tool(
        app_context,
        prefix="claims",
        tool_name="reproscope_extract_claims",
        operation=lambda run_id: _extract_claims(
            app_context,
            run_id=run_id,
            paper_paths=paper_paths,
            focus=focus,
            domain_profile=domain_profile,
            profile_request_source=profile_request_source,
        ),
    )


async def _extract_claims(
    app_context: Any,
    *,
    run_id: str,
    paper_paths: list[str],
    focus: str | None,
    domain_profile: DomainProfileMode,
    profile_request_source: ProfileRequestSource,
) -> ExtractClaimsResult:
    paper_bundle = load_sources(
        paper_paths,
        role="paper",
        settings=app_context.settings,
        source_id_prefix="paper",
    )
    activation = resolve_profile_activation(
        requested_profile=DomainProfileMode(domain_profile),
        request_source=ProfileRequestSource(profile_request_source),
        bundle=paper_bundle,
    )
    isac_enabled = activation.effective_profile is DomainProfileName.ISAC_PHY
    isac_context = profile_registry.isac_prompt_payload() if isac_enabled else None
    payload = {
        "run_id": run_id,
        "focus": focus,
        "domain_profile_activation": activation.model_dump(mode="json"),
        "isac_profile_context": isac_context,
        "paper_sources": paper_bundle.prompt_sources(),
    }
    messages = build_structured_messages(
        task="extract_reproducibility_claims",
        instructions=(
            "Identify core empirical claims, reported metrics, datasets, baselines, ablations, environment details, "
            "and missing details that would block reproduction. Every citation must copy both source_id and one "
            "exact locator from that source's segments. The server, not the model, owns domain_profile_activation. "
            "When isac_profile_context is null, set isac_analysis to null. When it is present, fill isac_analysis "
            "using only the supplied paper sources. Use registry canonical names exactly, classify conservatively, "
            "and use unknown when evidence is insufficient. Evaluate every supplied ISAC risk rule once. A registry "
            "defines what to inspect but is not evidence about this paper, so every pass, warning, or risk must cite "
            "the current paper evidence that supports it or state missing_evidence. Domain findings never affect "
            "the generic score and must set affects_score=false. Do not call a paper fraudulent and do not infer "
            "precise deployment performance from simulation."
        ),
        payload=payload,
        response_model=ExtractClaimsResult,
    )
    result = await app_context.get_hy3_client().complete_structured(messages, ExtractClaimsResult)
    result.run_id = run_id
    result.sources = paper_bundle.source_references()
    _sanitize_citations(result, paper_bundle.citation_references())
    result.domain_profile_activation = activation
    result.profile_versions = {"generic_profile": GENERIC_PROFILE_VERSION}
    if isac_enabled:
        result.profile_versions.update(
            {
                "isac_profile": ISAC_PROFILE_VERSION,
                **profile_registry.isac_versions(),
            }
        )
        result.registry_hashes = profile_registry.isac_hashes()
        _normalize_isac_analysis(result)
    else:
        result.isac_analysis = None
    for warning in activation.warnings:
        result.warnings.append(
            ToolWarning(
                code="DOMAIN_PROFILE_ACTIVATION_NOTICE",
                message=warning,
                source_references=activation.source_references,
            )
        )
    result.warnings.extend(paper_bundle.warnings)
    result.artifacts.append(_write_artifact(app_context, run_id, "extract_claims.json", result))
    return result


def _normalize_isac_analysis(result: ExtractClaimsResult) -> None:
    metric_document = profile_registry.isac_document("metrics").payload
    assumption_document = profile_registry.isac_document("assumptions").payload
    rule_document = profile_registry.isac_document("risk_rules").payload
    metric_names = {item["canonical_name"] for item in metric_document["metrics"]}
    assumption_names = {item["name"] for item in assumption_document["assumptions"]}
    rule_ids = [item["rule_id"] for item in rule_document["rules"]]
    rule_id_set = set(rule_ids)

    if result.isac_analysis is None:
        result.isac_analysis = ISACProfileAnalysis(
            findings=[
                _unknown_domain_finding(rule_id, "Hy3 returned no ISAC analysis for the active profile.")
                for rule_id in rule_ids
            ],
            limitations=["The active ISAC profile produced no structured domain analysis."],
        )
        result.warnings.append(
            ToolWarning(
                code="ISAC_ANALYSIS_MISSING",
                message="Hy3 returned no ISAC analysis; all domain rules were recorded as unknown.",
            )
        )
        return

    analysis = result.isac_analysis
    has_classification = (
        analysis.system_type is not ISACSystemType.UNKNOWN
        or bool(analysis.sensing_topologies)
        or bool(analysis.waveforms)
        or bool(analysis.research_methods)
        or analysis.evidence_level is not ISACEvidenceLevel.UNKNOWN
    )
    if has_classification and not analysis.classification_citations:
        analysis.system_type = ISACSystemType.UNKNOWN
        analysis.sensing_topologies = []
        analysis.waveforms = []
        analysis.research_methods = []
        analysis.evidence_level = ISACEvidenceLevel.UNKNOWN
        result.warnings.append(
            ToolWarning(
                code="UNSUPPORTED_ISAC_CLASSIFICATION",
                message="Removed ISAC classifications without a validated current-paper citation.",
            )
        )

    unknown_metrics = sorted(
        {metric.canonical_name for metric in analysis.metrics if metric.canonical_name not in metric_names}
    )
    unsupported_metrics = sorted(
        {
            metric.canonical_name
            for metric in analysis.metrics
            if metric.canonical_name in metric_names and not metric.citations
        }
    )
    analysis.metrics = [
        metric for metric in analysis.metrics if metric.canonical_name in metric_names and bool(metric.citations)
    ]
    if unknown_metrics:
        result.warnings.append(
            ToolWarning(
                code="UNKNOWN_ISAC_METRIC",
                message="Removed metrics not present in the active ISAC registry: " + ", ".join(unknown_metrics),
            )
        )
    if unsupported_metrics:
        result.warnings.append(
            ToolWarning(
                code="UNSUPPORTED_ISAC_METRIC",
                message=(
                    "Removed ISAC metric observations without a validated current-paper citation: "
                    + ", ".join(unsupported_metrics)
                ),
            )
        )

    unknown_assumptions = sorted(
        {assumption.name for assumption in analysis.assumptions if assumption.name not in assumption_names}
    )
    unsupported_assumptions = sorted(
        {
            assumption.name
            for assumption in analysis.assumptions
            if assumption.name in assumption_names and not assumption.citations
        }
    )
    analysis.assumptions = [
        assumption
        for assumption in analysis.assumptions
        if assumption.name in assumption_names and bool(assumption.citations)
    ]
    if unknown_assumptions:
        result.warnings.append(
            ToolWarning(
                code="UNKNOWN_ISAC_ASSUMPTION",
                message=(
                    "Removed assumptions not present in the active ISAC registry: " + ", ".join(unknown_assumptions)
                ),
            )
        )
    if unsupported_assumptions:
        result.warnings.append(
            ToolWarning(
                code="UNSUPPORTED_ISAC_ASSUMPTION",
                message=(
                    "Removed ISAC assumption observations without a validated current-paper citation: "
                    + ", ".join(unsupported_assumptions)
                ),
            )
        )

    normalized_findings: dict[str, DomainFinding] = {}
    unknown_rule_ids: set[str] = set()
    duplicate_rule_ids: set[str] = set()
    for finding in analysis.findings:
        if finding.rule_id not in rule_id_set:
            unknown_rule_ids.add(finding.rule_id)
            continue
        if finding.rule_id in normalized_findings:
            duplicate_rule_ids.add(finding.rule_id)
            continue
        finding.affects_score = False
        if finding.citations:
            finding.evidence_kind = EvidenceKind.INFERRED
        elif finding.status in {
            DomainFindingStatus.PASS,
            DomainFindingStatus.RISK,
        }:
            finding.status = DomainFindingStatus.UNKNOWN
            finding.evidence_kind = EvidenceKind.UNKNOWN
            finding.missing_evidence.append(
                "The model supplied no validated current-paper citation for this assertion."
            )
        elif finding.status is DomainFindingStatus.WARNING and not finding.missing_evidence:
            finding.status = DomainFindingStatus.UNKNOWN
            finding.evidence_kind = EvidenceKind.UNKNOWN
            finding.missing_evidence.append(
                "The warning had neither a validated citation nor an explicit missing-evidence basis."
            )
        normalized_findings[finding.rule_id] = finding

    analysis.findings = [
        normalized_findings.get(
            rule_id,
            _unknown_domain_finding(rule_id, "The active profile returned no finding for this rule."),
        )
        for rule_id in rule_ids
    ]
    if unknown_rule_ids:
        result.warnings.append(
            ToolWarning(
                code="UNKNOWN_ISAC_RULE",
                message="Removed findings for unknown ISAC rules: " + ", ".join(sorted(unknown_rule_ids)),
            )
        )
    if duplicate_rule_ids:
        result.warnings.append(
            ToolWarning(
                code="DUPLICATE_ISAC_RULE",
                message="Only the first finding was kept for ISAC rules: " + ", ".join(sorted(duplicate_rule_ids)),
            )
        )


def _unknown_domain_finding(rule_id: str, reason: str) -> DomainFinding:
    return DomainFinding(
        rule_id=rule_id,
        status=DomainFindingStatus.UNKNOWN,
        summary="Insufficient evidence for this ISAC check.",
        rationale=reason,
        evidence_kind=EvidenceKind.UNKNOWN,
        missing_evidence=[reason],
    )


async def compare_results(
    app_context: Any,
    *,
    paper_paths: list[str],
    reproduction_paths: list[str],
    metric_hints: list[str],
    group_filters: dict[str, str] | None = None,
    group_by: list[str] | None = None,
    claims_artifact_path: str | None = None,
) -> CompareReproductionResult:
    return await _run_async_tool(
        app_context,
        prefix="compare",
        tool_name="reproscope_compare_results",
        operation=lambda run_id: _compare_results(
            app_context,
            run_id=run_id,
            paper_paths=paper_paths,
            reproduction_paths=reproduction_paths,
            metric_hints=metric_hints,
            group_filters=group_filters,
            group_by=group_by,
            claims_artifact_path=claims_artifact_path,
        ),
    )


async def _compare_results(
    app_context: Any,
    *,
    run_id: str,
    paper_paths: list[str],
    reproduction_paths: list[str],
    metric_hints: list[str],
    group_filters: dict[str, str] | None,
    group_by: list[str] | None,
    claims_artifact_path: str | None,
) -> CompareReproductionResult:
    normalized_group_filters = normalize_group_filters(group_filters or {})
    normalized_group_by = normalize_group_by(group_by or [])
    paper_bundle = load_sources(
        paper_paths,
        role="paper",
        settings=app_context.settings,
        source_id_prefix="paper",
    )
    reproduction_bundle = load_sources(
        reproduction_paths,
        role="reproduction",
        settings=app_context.settings,
        source_id_prefix="repro",
        group_filters=normalized_group_filters,
    )
    validate_group_analysis_request(
        reproduction_bundle,
        group_by=normalized_group_by,
        group_filters=normalized_group_filters,
    )
    workspace = Workspace(app_context.settings)
    claims_context: ExtractClaimsResult | None = None
    claims_parent: ParentArtifactReference | None = None
    if claims_artifact_path:
        claims_context, claims_parent = _read_result_artifact(
            workspace,
            claims_artifact_path,
            ExtractClaimsResult,
            "claims",
        )
    if claims_context is not None:
        validate_comparison_context(
            paper_sources=paper_bundle.source_references(),
            claims=claims_context,
        )
    deterministic_setting_checks = build_setting_checks(paper_bundle, reproduction_bundle)
    payload = {
        "run_id": run_id,
        "metric_hints": metric_hints,
        "group_filters": normalized_group_filters,
        "group_by": normalized_group_by,
        "metric_registry": metric_registry_payload(),
        "deterministic_setting_checks": [check.model_dump(mode="json") for check in deterministic_setting_checks],
        "prior_claim_analysis": claims_context.model_dump(mode="json") if claims_context else None,
        "paper_sources": paper_bundle.prompt_sources(),
        "reproduction_sources": reproduction_bundle.prompt_sources(),
    }
    messages = build_structured_messages(
        task="compare_reproduction_results",
        instructions=(
            "Map reported paper metrics to reproduction metrics when possible. For every mapped metric, copy the "
            "exact reproduction source_id and CSV column name into reproduction_source_id and reproduction_column. "
            "Return paper_value exactly as reported by the paper, without silently rescaling it. Set unit and "
            "paper_scale to fraction, percentage, linear, decibel, or unknown when the source supports that choice. "
            "Set reproduction_scale when the column name or source makes it explicit. The server owns canonical "
            "metric aliases, safe percentage/fraction conversion, and all aggregate and delta calculations. "
            "If prior_claim_analysis is supplied, supported_claim_ids, partially_supported_claim_ids, and "
            "contradicted_claim_ids may only contain claim IDs from that artifact. Use partial support when the "
            "direction, a subset of conditions, or only part of the stated magnitude is reproduced. Place each "
            "Claim in at most one relation list. Otherwise leave all three lists empty. The server recalculates "
            "claim_relation_diagnostics locally; do not use it to infer or change any relation. "
            "Treat deterministic_setting_checks as authoritative for the listed settings. Do not claim a difference "
            "when a check is match, and do not override a locally detected mismatch. "
            "Do not calculate the reproduction aggregate or delta because the server will replace those fields "
            "locally. Explain exact "
            "matches, material differences, missing metrics, changed settings, and uncertainty. Avoid inventing "
            "numbers. If a reproduction source has aggregation_safe=false, treat its global numeric statistics as "
            "unsafe and explain that the file must be filtered to one experiment group. "
            "When group_by is non-empty, the server will compute group_metric_comparisons locally after your metric "
            "mapping; do not invent per-group aggregates. "
            "Every citation must copy both source_id and one exact locator from that source's segments."
        ),
        payload=payload,
        response_model=CompareReproductionResult,
    )
    result = await app_context.get_hy3_client().complete_structured(messages, CompareReproductionResult)
    result.run_id = run_id
    result.claims_run_id = claims_context.run_id if claims_context else None
    result.group_filters = normalized_group_filters
    result.group_by = normalized_group_by
    result.parent_artifacts = [claims_parent] if claims_parent else []
    if claims_context is not None:
        result.profile_versions = dict(claims_context.profile_versions)
        result.registry_hashes = dict(claims_context.registry_hashes)
    result.sources = merge_sources(
        paper_bundle.source_references(),
        reproduction_bundle.source_references(),
    )
    compute_metric_differences(result, reproduction_bundle)
    compute_group_metric_comparisons(
        result,
        reproduction_paths=reproduction_paths,
        reproduction_bundle=reproduction_bundle,
        group_by=normalized_group_by,
        settings=app_context.settings,
    )
    reconcile_setting_differences(result, deterministic_setting_checks)
    _sanitize_claim_relations(result, claims_context)
    _sanitize_citations(
        result,
        paper_bundle.citation_references() | reproduction_bundle.citation_references(),
    )
    result.warnings.extend([*paper_bundle.warnings, *reproduction_bundle.warnings])
    result.artifacts.append(_write_artifact(app_context, run_id, "compare_results.json", result))
    return result


def _sanitize_claim_relations(
    result: CompareReproductionResult,
    claims_context: ExtractClaimsResult | None,
) -> None:
    supplied_ids = [
        *result.supported_claim_ids,
        *result.partially_supported_claim_ids,
        *result.contradicted_claim_ids,
    ]
    if claims_context is None:
        result.claim_relation_diagnostics = ClaimRelationDiagnostics()
        if supplied_ids:
            result.supported_claim_ids = []
            result.partially_supported_claim_ids = []
            result.contradicted_claim_ids = []
            result.warnings.append(
                ToolWarning(
                    code="CLAIM_LINKAGE_UNAVAILABLE",
                    message="Claim relations were removed because no extract_claims artifact was supplied.",
                )
            )
        return

    ordered_valid_ids = list(dict.fromkeys(claim.claim_id for claim in claims_context.core_claims))
    valid_ids = set(ordered_valid_ids)
    unknown_ids = sorted(set(supplied_ids) - valid_ids)
    supported = list(dict.fromkeys(claim_id for claim_id in result.supported_claim_ids if claim_id in valid_ids))
    partially_supported = list(
        dict.fromkeys(claim_id for claim_id in result.partially_supported_claim_ids if claim_id in valid_ids)
    )
    contradicted = list(dict.fromkeys(claim_id for claim_id in result.contradicted_claim_ids if claim_id in valid_ids))
    relation_counts: dict[str, int] = {}
    for relation in (supported, partially_supported, contradicted):
        for claim_id in relation:
            relation_counts[claim_id] = relation_counts.get(claim_id, 0) + 1
    overlaps = sorted(claim_id for claim_id, count in relation_counts.items() if count > 1)
    if overlaps:
        supported = [claim_id for claim_id in supported if claim_id not in overlaps]
        partially_supported = [claim_id for claim_id in partially_supported if claim_id not in overlaps]
        contradicted = [claim_id for claim_id in contradicted if claim_id not in overlaps]
        result.warnings.append(
            ToolWarning(
                code="AMBIGUOUS_CLAIM_RELATION",
                message=(
                    "Claim IDs returned in multiple support/partial-support/contradiction categories were removed: "
                    + ", ".join(overlaps)
                ),
            )
        )
    if unknown_ids:
        result.warnings.append(
            ToolWarning(
                code="UNKNOWN_COMPARISON_CLAIM_ID",
                message="Unknown claim IDs were removed from comparison relations: " + ", ".join(unknown_ids),
            )
        )
    result.supported_claim_ids = supported
    result.partially_supported_claim_ids = partially_supported
    result.contradicted_claim_ids = contradicted
    assessed_ids = set(supported) | set(partially_supported) | set(contradicted)
    unassessed_ids = [claim_id for claim_id in ordered_valid_ids if claim_id not in assessed_ids]
    total_claim_count = len(ordered_valid_ids)
    result.claim_relation_diagnostics = ClaimRelationDiagnostics(
        total_claim_count=total_claim_count,
        assessed_claim_count=len(assessed_ids),
        fully_supported_count=len(supported),
        partially_supported_count=len(partially_supported),
        contradicted_count=len(contradicted),
        unassessed_claim_count=len(unassessed_ids),
        claim_relation_coverage=(len(assessed_ids) / total_claim_count if total_claim_count else None),
        unassessed_claim_ids=unassessed_ids,
    )
    if unassessed_ids:
        result.warnings.append(
            ToolWarning(
                code="CLAIM_RELATION_COVERAGE_INCOMPLETE",
                message=(
                    f"{len(unassessed_ids)} of {total_claim_count} claims received no validated full-support, "
                    "partial-support, or contradiction relation."
                ),
            )
        )


async def score_paper(
    app_context: Any,
    *,
    paper_paths: list[str],
    reproduction_paths: list[str],
    rubric_focus: list[str],
    group_filters: dict[str, str] | None = None,
    claims_artifact_path: str | None = None,
    comparison_artifact_path: str | None = None,
    repository_audit_artifact_path: str | None = None,
) -> ReliabilityScoreResult:
    return await _run_async_tool(
        app_context,
        prefix="score",
        tool_name="reproscope_score_paper",
        operation=lambda run_id: _score_paper(
            app_context,
            run_id=run_id,
            paper_paths=paper_paths,
            reproduction_paths=reproduction_paths,
            rubric_focus=rubric_focus,
            group_filters=group_filters,
            claims_artifact_path=claims_artifact_path,
            comparison_artifact_path=comparison_artifact_path,
            repository_audit_artifact_path=repository_audit_artifact_path,
        ),
    )


async def _score_paper(
    app_context: Any,
    *,
    run_id: str,
    paper_paths: list[str],
    reproduction_paths: list[str],
    rubric_focus: list[str],
    group_filters: dict[str, str] | None,
    claims_artifact_path: str | None,
    comparison_artifact_path: str | None,
    repository_audit_artifact_path: str | None,
) -> ReliabilityScoreResult:
    normalized_group_filters = normalize_group_filters(group_filters or {})
    if normalized_group_filters and not reproduction_paths:
        raise GroupFilterError(
            "group_filters require at least one reproduction path when scoring.",
            hint="Pass the structured result files used for comparison or remove group_filters.",
        )
    paper_bundle = load_sources(
        paper_paths,
        role="paper",
        settings=app_context.settings,
        source_id_prefix="paper",
    )
    reproduction_bundle = (
        load_sources(
            reproduction_paths,
            role="reproduction",
            settings=app_context.settings,
            source_id_prefix="repro",
            group_filters=normalized_group_filters,
        )
        if reproduction_paths
        else None
    )
    workspace = Workspace(app_context.settings)
    claims_context: ExtractClaimsResult | None = None
    claims_parent: ParentArtifactReference | None = None
    if claims_artifact_path:
        claims_context, claims_parent = _read_result_artifact(
            workspace,
            claims_artifact_path,
            ExtractClaimsResult,
            "claims",
        )
    comparison_context: CompareReproductionResult | None = None
    comparison_parent: ParentArtifactReference | None = None
    if comparison_artifact_path:
        comparison_context, comparison_parent = _read_result_artifact(
            workspace,
            comparison_artifact_path,
            CompareReproductionResult,
            "comparison",
        )
    repository_audit: RepositoryAuditResult | None = None
    repository_parent: ParentArtifactReference | None = None
    if repository_audit_artifact_path:
        repository_audit, repository_parent = _read_result_artifact(
            workspace,
            repository_audit_artifact_path,
            RepositoryAuditResult,
            "repository_audit",
        )
    validate_score_context(
        paper_sources=paper_bundle.source_references(),
        reproduction_sources=(reproduction_bundle.source_references() if reproduction_bundle else []),
        claims=claims_context,
        comparison=comparison_context,
        group_filters=normalized_group_filters,
        claims_artifact=claims_parent,
        comparison_artifact=comparison_parent,
    )
    payload = {
        "run_id": run_id,
        "rubric_focus": rubric_focus,
        "group_filters": normalized_group_filters,
        "fixed_rubric": rubric_payload(),
        "paper_sources": paper_bundle.prompt_sources(),
        "reproduction_sources": reproduction_bundle.prompt_sources() if reproduction_bundle else [],
        "prior_claim_analysis": claims_context.model_dump(mode="json") if claims_context else None,
        "prior_reproduction_comparison": (comparison_context.model_dump(mode="json") if comparison_context else None),
        "repository_audit": (
            _repository_audit_prompt_payload(repository_audit) if repository_audit is not None else None
        ),
    }
    messages = build_structured_messages(
        task="score_paper_reliability",
        instructions=(
            "Assess every dimension in fixed_rubric using exactly its supplied name. Use assessment_status=assessed "
            "and a score from 0 to 100 only when the supplied evidence supports an assessment. Otherwise use "
            "assessment_status=insufficient_evidence and score=null; unknown is not zero. The server owns weights, "
            "so omit weight or set it to 0. rubric_focus changes narrative emphasis only. Every citation must copy "
            "both source_id and one exact locator from that source's segments; omit source_reference because the "
            "server attaches it after validation. Treat prior analyses as structured context but verify them against "
            "the supplied sources. Missing independent reproduction evidence must not be treated as agreement. A "
            "repository_audit, when supplied, is a caller-associated static scan: use it only as implementation and "
            "reproducibility-condition evidence, do not assume it proves correspondence to the paper, and do not "
            "treat discovered commands or declarations as executed successfully."
        ),
        payload=payload,
        response_model=ReliabilityScoreResult,
    )
    result = await app_context.get_hy3_client().complete_structured(messages, ReliabilityScoreResult)
    result.run_id = run_id
    result.repository_audit_run_id = repository_audit.run_id if repository_audit else None
    result.group_filters = normalized_group_filters
    result.parent_artifacts = [
        artifact for artifact in (claims_parent, comparison_parent, repository_parent) if artifact is not None
    ]
    profile_context = claims_context or comparison_context
    if profile_context is not None:
        result.profile_versions = dict(profile_context.profile_versions)
        result.registry_hashes = dict(profile_context.registry_hashes)
    result.sources = merge_sources(
        paper_bundle.source_references(),
        reproduction_bundle.source_references() if reproduction_bundle else [],
        repository_audit.sources if repository_audit else [],
    )
    citation_references = paper_bundle.citation_references()
    if reproduction_bundle:
        citation_references.update(reproduction_bundle.citation_references())
    _sanitize_citations(result, citation_references)
    normalize_score(result, has_reproduction=bool(reproduction_bundle))
    if reproduction_bundle:
        result.warnings.extend([*paper_bundle.warnings, *reproduction_bundle.warnings])
    else:
        result.warnings.extend(paper_bundle.warnings)
    if repository_audit is not None:
        _attach_repository_audit_to_score(result, repository_audit)
    result.artifacts.append(_write_artifact(app_context, run_id, "reliability_score.json", result))
    return result


def render_report(
    app_context: Any,
    *,
    claims_artifact_path: str,
    comparison_artifact_path: str,
    score_artifact_path: str,
    title: str,
    evidence_graph_artifact_path: str | None = None,
) -> RenderReportResult:
    return _run_sync_tool(
        app_context,
        prefix="report",
        tool_name="reproscope_render_report",
        operation=lambda run_id: _render_report(
            app_context,
            run_id=run_id,
            claims_artifact_path=claims_artifact_path,
            comparison_artifact_path=comparison_artifact_path,
            score_artifact_path=score_artifact_path,
            title=title,
            evidence_graph_artifact_path=evidence_graph_artifact_path,
        ),
    )


def _render_report(
    app_context: Any,
    *,
    run_id: str,
    claims_artifact_path: str,
    comparison_artifact_path: str,
    score_artifact_path: str,
    title: str,
    evidence_graph_artifact_path: str | None,
) -> RenderReportResult:
    workspace = Workspace(app_context.settings)
    claims, claims_parent = _read_result_artifact(
        workspace,
        claims_artifact_path,
        ExtractClaimsResult,
        "claims",
    )
    comparison, comparison_parent = _read_result_artifact(
        workspace,
        comparison_artifact_path,
        CompareReproductionResult,
        "comparison",
    )
    score, score_parent = _read_result_artifact(
        workspace,
        score_artifact_path,
        ReliabilityScoreResult,
        "score",
    )
    validate_report_lineage(
        claims,
        comparison,
        score,
        claims_artifact=claims_parent,
        comparison_artifact=comparison_parent,
    )
    graph: BuildEvidenceGraphResult | None = None
    graph_parent: ParentArtifactReference | None = None
    if evidence_graph_artifact_path:
        graph, graph_parent = _read_result_artifact(
            workspace,
            evidence_graph_artifact_path,
            BuildEvidenceGraphResult,
            "evidence_graph",
        )
    if graph is not None:
        validate_graph_artifact_lineage(
            graph,
            claims,
            comparison,
            score,
            claims_artifact=claims_parent,
            comparison_artifact=comparison_parent,
            score_artifact=score_parent,
        )
        validate_evidence_graph(graph)
    artifact_inventory = [
        _artifact_audit_entry(claims_parent, claims),
        _artifact_audit_entry(comparison_parent, comparison),
        _artifact_audit_entry(score_parent, score),
    ]
    if graph is not None and graph_parent is not None:
        artifact_inventory.append(_artifact_audit_entry(graph_parent, graph))
    markdown = render_markdown_report(
        title=title,
        claims=claims,
        comparison=comparison,
        score=score,
        graph=graph,
        artifact_inventory=artifact_inventory,
    )
    report_artifact = workspace.write_text_artifact(
        run_id,
        "reproscope_report.md",
        markdown,
        artifact_type="markdown",
    )
    manifest_path = f"{run_id}/report_manifest.json"
    result = RenderReportResult(
        run_id=run_id,
        title=title,
        summary=score.summary,
        report_path=report_artifact.relative_path,
        manifest_path=manifest_path,
        source_run_ids=[claims.run_id, comparison.run_id, score.run_id],
        evidence_graph_run_id=graph.run_id if graph else None,
        artifact_inventory=artifact_inventory,
        parent_artifacts=[
            claims_parent,
            comparison_parent,
            score_parent,
            *([graph_parent] if graph_parent else []),
        ],
        sources=merge_sources(claims.sources, comparison.sources, score.sources),
        artifacts=[report_artifact],
        profile_versions=dict(claims.profile_versions),
        registry_hashes=dict(claims.registry_hashes),
    )
    manifest_artifact = workspace.write_json_artifact(
        run_id,
        "report_manifest.json",
        result.model_dump(mode="json"),
    )
    if manifest_artifact.payload_hash is not None:
        result.artifact_integrity = ArtifactIntegrity(payload_hash=manifest_artifact.payload_hash)
    result.artifacts.append(manifest_artifact)
    return result


def build_evidence_graph(
    app_context: Any,
    *,
    claims_artifact_path: str,
    comparison_artifact_path: str,
    score_artifact_path: str,
) -> BuildEvidenceGraphResult:
    return _run_sync_tool(
        app_context,
        prefix="graph",
        tool_name="reproscope_build_evidence_graph",
        operation=lambda run_id: _build_evidence_graph(
            app_context,
            run_id=run_id,
            claims_artifact_path=claims_artifact_path,
            comparison_artifact_path=comparison_artifact_path,
            score_artifact_path=score_artifact_path,
        ),
    )


def _build_evidence_graph(
    app_context: Any,
    *,
    run_id: str,
    claims_artifact_path: str,
    comparison_artifact_path: str,
    score_artifact_path: str,
) -> BuildEvidenceGraphResult:
    workspace = Workspace(app_context.settings)
    claims, claims_parent = _read_result_artifact(
        workspace,
        claims_artifact_path,
        ExtractClaimsResult,
        "claims",
    )
    comparison, comparison_parent = _read_result_artifact(
        workspace,
        comparison_artifact_path,
        CompareReproductionResult,
        "comparison",
    )
    score, score_parent = _read_result_artifact(
        workspace,
        score_artifact_path,
        ReliabilityScoreResult,
        "score",
    )
    validate_report_lineage(
        claims,
        comparison,
        score,
        claims_artifact=claims_parent,
        comparison_artifact=comparison_parent,
    )
    result = build_graph(run_id=run_id, claims=claims, comparison=comparison, score=score)
    result.parent_artifacts = [claims_parent, comparison_parent, score_parent]
    result.profile_versions = dict(claims.profile_versions)
    result.registry_hashes = dict(claims.registry_hashes)
    result.artifacts.append(_write_artifact(app_context, run_id, "evidence_graph.json", result))
    return result


def _app_context(ctx: Context | None) -> Any:
    if ctx is None:
        raise ValueError("MCP request context is required.")
    return ctx.request_context.lifespan_context


def _new_run_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


async def _run_async_tool(
    app_context: Any,
    *,
    prefix: str,
    tool_name: str,
    operation: Callable[[str], Awaitable[ResultT]],
) -> ResultT:
    run_id = _new_run_id(prefix)
    lifecycle = RunManifestWriter(
        Workspace(app_context.settings),
        run_id=run_id,
        tool_name=tool_name,
    )
    lifecycle.mark_running()
    try:
        result = await operation(run_id)
        manifest_artifact = lifecycle.mark_completed(result)
    except Exception as exc:
        _mark_failed_safely(lifecycle, exc)
        raise
    result.artifacts.append(manifest_artifact)
    return result


def _run_sync_tool(
    app_context: Any,
    *,
    prefix: str,
    tool_name: str,
    operation: Callable[[str], ResultT],
) -> ResultT:
    run_id = _new_run_id(prefix)
    lifecycle = RunManifestWriter(
        Workspace(app_context.settings),
        run_id=run_id,
        tool_name=tool_name,
    )
    lifecycle.mark_running()
    try:
        result = operation(run_id)
        manifest_artifact = lifecycle.mark_completed(result)
    except Exception as exc:
        _mark_failed_safely(lifecycle, exc)
        raise
    result.artifacts.append(manifest_artifact)
    return result


def _mark_failed_safely(lifecycle: RunManifestWriter, error: Exception) -> None:
    # Preserve the original tool error when the workspace itself is unavailable.
    with suppress(Exception):
        lifecycle.mark_failed(error)


def _write_artifact(app_context: Any, run_id: str, name: str, result: Any) -> Any:
    workspace = Workspace(app_context.settings)
    payload = result.model_dump(mode="json", exclude={"artifacts"})
    artifact = workspace.write_json_artifact(run_id, name, payload)
    if artifact.payload_hash is not None:
        result.artifact_integrity = ArtifactIntegrity(payload_hash=artifact.payload_hash)
    return artifact


def _read_result_artifact(
    workspace: Workspace,
    raw_path: str,
    model_type: type[ToolResultBase],
    role: str,
) -> tuple[Any, ParentArtifactReference]:
    payload, artifact = workspace.read_json_artifact_with_reference(raw_path, expected_schema=SCHEMA_VERSION)
    result = model_type.model_validate(payload)
    return result, parent_artifact_reference(role, artifact)


def _artifact_audit_entry(
    artifact: ParentArtifactReference,
    result: ToolResultBase,
) -> ArtifactAuditEntry:
    return ArtifactAuditEntry(
        **artifact.model_dump(mode="python"),
        direct_parents=result.parent_artifacts,
    )


def _sanitize_citations(
    result: BaseModel,
    citation_references: dict[str, dict[str, Any]],
) -> None:
    unknown_source_ids: set[str] = set()
    unknown_locators: set[str] = set()

    def visit(model: BaseModel) -> None:
        for field_name in type(model).model_fields:
            value = getattr(model, field_name)
            if isinstance(value, list):
                sanitized: list[Any] = []
                for item in value:
                    if isinstance(item, EvidenceCitation):
                        if item.source_id not in citation_references:
                            unknown_source_ids.add(item.source_id)
                            continue
                        reference = citation_references[item.source_id].get(item.locator)
                        if reference is None:
                            unknown_locators.add(f"{item.source_id}:{item.locator}")
                            continue
                        item.source_reference = reference
                    if isinstance(item, BaseModel):
                        visit(item)
                    sanitized.append(item)
                if len(sanitized) != len(value):
                    setattr(model, field_name, sanitized)
            elif isinstance(value, BaseModel):
                visit(value)

    visit(result)
    if unknown_source_ids and isinstance(result, ToolResultBase):
        result.warnings.append(
            ToolWarning(
                code="UNKNOWN_SOURCE_CITATION",
                message="Removed citations to unknown source IDs: " + ", ".join(sorted(unknown_source_ids)),
            )
        )
    if unknown_locators and isinstance(result, ToolResultBase):
        result.warnings.append(
            ToolWarning(
                code="UNKNOWN_EVIDENCE_LOCATOR",
                message="Removed citations with unknown locators: " + ", ".join(sorted(unknown_locators)),
            )
        )
