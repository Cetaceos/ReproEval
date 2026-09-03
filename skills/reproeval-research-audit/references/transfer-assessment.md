# Technology-Transfer Assessment

Use this workflow when a paper, patent note, design document, or open-source solution must be assessed under a
different target project's requirements, resources, interfaces, or operating conditions.

## Inputs

Require both sides of the comparison:

- one or more source-solution document paths;
- one or more target-context paths describing constraints and success criteria;
- an optional Python repository path for static dependency and entry-point evidence;
- an optional decision focus such as latency, data availability, hardware, integration effort, or cost.

If the target context omits measurable requirements or available resources, keep the result conditional or
insufficient rather than importing assumptions from the source solution.

## Full MCP sequence

1. If a repository is supplied, call `reproscope_audit_repository`. Keep its `repository_audit.json` artifact path.
2. Call `reproscope_extract_solution_profile` with the source solution paths and optional focus. Keep the returned
   `solution_profile.json` path.
3. Call `reproscope_assess_transfer` with the same source paths, target-context paths, exact profile artifact path,
   focus, and optional repository-audit artifact. Keep `transfer_assessment.json`.
4. Call `reproscope_build_transfer_graph` with the completed profile and assessment paths. Continue only when
   `graph_validated` is `true`; keep `transfer_graph.json`.
5. Call `reproscope_render_transfer_report` with the same profile and assessment paths and the validated graph path.

Every artifact argument must be copied from `artifacts[].relative_path` in an MCP response. Do not infer a path
from the run identifier or search another run's directory for a similarly named file.

## Decision boundary

Summarize the feasibility band and score only when coverage permits. Separate directly reusable components,
required adaptations, unsatisfied dependencies/resources, invalidated assumptions, risks, and validation steps.
Preserve `performance_prediction_provided=false` and `legal_conclusion_provided=false` as hard boundaries.

A high score is not a deployment guarantee. A sparse target context cannot support exact latency, accuracy, cost,
or resource predictions. License signals are prompts for qualified review, not legal conclusions.
