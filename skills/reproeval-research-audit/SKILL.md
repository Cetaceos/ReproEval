---
name: reproeval-research-audit
description: Orchestrate evidence-grounded paper reproducibility reviews and technology-transfer assessments through the Hy3 ReproScope MCP tools. Use when a user wants claims, reproduced results, repository signals, transfer constraints, evidence graphs, or final audit reports analyzed without unsupported conclusions.
---

# Hy3 ReproEval Research Audit

Use the connected `hy3-reproscope` MCP server as the application boundary. Do not substitute direct calls to
internal Python handlers and do not describe a workflow as MCP-validated unless every required step actually ran
through the MCP tools.

## Route the request

- For a paper and reproduction evidence, read [references/reproduction-review.md](references/reproduction-review.md).
- For an existing solution and a different target context, read
  [references/transfer-assessment.md](references/transfer-assessment.md).
- If the user supplies a Python repository, include the read-only repository audit in the selected workflow.
- If essential files are missing, identify the missing evidence and run only the supported partial steps.

## Preserve the evidence contract

1. Use only paths the user supplied or paths already present under `REPROSCOPE_ALLOWED_ROOTS`.
2. Keep the same source paths, filters, grouping choices, and focus across dependent calls.
3. Take each parent path from the preceding response's `artifacts[].relative_path`; never derive it from a
   `run_id`, filename guess, or previous conversation.
4. Do not call a graph or renderer until all required parent tools returned completed artifacts.
5. Surface warning codes, insufficient-evidence states, coverage values, and validation markers in the answer.
6. Treat local recomputation, hashes, lineage checks, and hard caps as authoritative over model prose.

## Safety boundaries

- Never execute third-party repository code, install its dependencies, or run commands discovered by the audit.
- Do not infer absent experimental settings, target constraints, licenses, measurements, or citations.
- Do not label a paper fraudulent or treat missing evidence as proof of misconduct.
- Do not present transfer scores as deployment guarantees, legal advice, or point performance predictions.
- Keep `insufficient` or conditional outcomes intact; do not convert them to zero scores or confident conclusions.
- On a tool failure, report the failed MCP step and its error. Do not bypass it with an internal pipeline.

## Return the result

Lead with the decision and evidence coverage, then summarize the strongest supporting and contradicting evidence,
material gaps, warning codes, and recommended verification steps. Include the final report path and relevant
`run_id` values so the user can inspect the traceable artifacts.
