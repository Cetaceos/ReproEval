# ReproEval Agent Skill

ReproEval 0.34.0 includes a repository-level Agent Skill that turns the ten low-level ReproScope MCP tools into
two evidence-preserving workflows:

- paper reproducibility review;
- technology-transfer assessment under a supplied target context.

The Skill is an orchestration and safety layer. It does not duplicate application logic, store an API key, call
Hy3 directly, or replace the `hy3-reproscope` MCP server.

## Location

```text
skills/reproeval-research-audit/
  SKILL.md
  agents/openai.yaml
  references/reproduction-review.md
  references/transfer-assessment.md
```

`SKILL.md` contains routing, artifact-lineage rules, failure behavior, and shared claim boundaries. Detailed tool
sequences are loaded only for the selected scenario. `agents/openai.yaml` supplies optional client-facing metadata.

## Install from a source checkout

First configure and validate the MCP server as described in the main README. Then copy the complete Skill folder
to the Skill directory used by an Agent Skills-compatible client.

Codex on Windows:

```powershell
Copy-Item -Recurse `
  .\skills\reproeval-research-audit `
  "$HOME\.codex\skills\reproeval-research-audit"
```

Codex on Linux or macOS:

```bash
cp -R skills/reproeval-research-audit "${CODEX_HOME:-$HOME/.codex}/skills/"
```

Reload the client after installation. A typical explicit invocation is:

```text
Use $reproeval-research-audit to compare this paper with the supplied reproduction CSV and produce a traceable
reliability report.
```

Clients that do not support repository or user Skills can still run the same workflows by calling the documented
MCP tools directly.

## Enforced workflow decisions

- Parent artifacts are taken only from the preceding MCP response's `artifacts[].relative_path`.
- Source paths, group filters, grouping, and decision focus remain consistent across dependent calls.
- Graph and report tools run only after all required parent artifacts complete validation.
- Missing reproduction or target evidence produces a partial or insufficient result instead of invented input.
- Tool failures are surfaced at the MCP boundary and are never hidden by calling internal Python handlers.
- Repository inspection remains static and does not execute discovered code or commands.
- Fraud, legal, deployment, and exact target-performance conclusions remain outside scope.

## Validation

The Skill was checked with the official `skill-creator` `quick_validate.py` utility. Repository tests additionally
parse its metadata and references and compare every documented `reproscope_*` tool name with the live in-memory MCP
`list_tools()` result. This catches stale Skill instructions when the server contract changes.

The validation proves structural compatibility, not that every client follows Skill instructions identically.
End-to-end claims still require observable MCP tool calls and completed ReproScope artifacts.
