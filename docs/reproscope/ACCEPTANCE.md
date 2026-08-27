# MCP Client Acceptance

Do not mark a client as passed until the exact packaged server, endpoint configuration, and demo inputs have been
tested. Never capture an API key in screenshots or recordings.

## Current Matrix

| Client or path | Tool discovery | Live Hy3 call | Artifact written | Status |
| --- | --- | --- | --- | --- |
| Local 0.15.0 wheel | Final `76A3F8...` wheel installed successfully; ten tools discovered from both module and console-script stdio entrypoints | Latest live-tested `3C940...` wheel completed paper, transfer, and ISAC explicit/auto chains; exact `76A3F8...` online Hy3 repeat was not run | 13 completed runs and 28 hash-verified artifacts retained in a sanitized index; one empty-completion retry is recorded separately | Final candidate passes build, distribution, installation, dependency, and stdio gates; exact-candidate online repeat and new remote CI remain pending |
| Historical TokenHub 0.5.0 | Five tools | Complete paper workflow passed, including two repairs | Five primary artifacts and completed manifests verified | Historical evidence only |
| CodeBuddy | Current 0.15.0 ten-tool screenshot | Current stdio report calls, artifact-lineage rejection, and completed transfer-report rendering | Final MP4 plus persisted report artifacts; artifact hashes remain authoritative | Final demo recorded; the video does not independently prove a fresh full Hy3 chain |
| Visual Studio Code 1.131.0 | Current 0.15.0 ten-tool screenshot | Runtime-equivalent prior `61F776...` wheel completed `reproscope_audit_repository` without Hy3 | `repository_8246ee4f34e0` plus machine-checkable content/payload hashes | Real MCP call passed; exact `76A3F8...` GUI repeat was not run |
| Cursor or Cline | Not required | Not run | Not run | Optional additional client |

Automated tests additionally initialize the server through both an in-memory MCP session and a real stdio subprocess.
They are protocol regression tests, not substitutes for the second GUI client requirement.

Synthetic workflow tests also run the persisted claim, comparison, score, graph, report, and run-manifest chain. They cover
insufficient-evidence abstention, deterministic extraction of a training-budget mismatch, rejection of a score combined
with a different comparison run, and undefined relative change when the paper value is zero. Hy3 responses are
deterministic fixtures in these tests; they validate server orchestration and safeguards, not model quality.

`python scripts/run_offline_eval.py` is the repeatable acceptance baseline for the complete five-tool chain. It runs a
normal scoring case and an insufficient-evidence case, checks 49 claim, statistic, setting, score, abstention, graph,
report, and lifecycle invariants, and exits nonzero on failure. The suite reports Correct Abstention Rate and its JSON
output follows `evals/offline_evaluation_suite.schema.json`. This is an orchestration evaluation and does not replace
live Hy3 or GUI-client validation.

The four-tool transfer suite performs 67 checks across normal and insufficient-target-context cases. ISAC profile
regressions use `evals/synthetic_isac_profile.json` and `evals/synthetic_isac_insufficient_evidence.json` to cover
generic-default behavior, conservative auto detection, explicit activation, registry bounds, unsupported-output
cleanup, graph integration, and report rendering. These are synthetic replay fixtures, not domain-quality calibration.

Group-filter regressions cover CSV, JSON, and JSONL. `examples/sample_mixed_results.csv` can be used for a manual check:
without filters, aggregation is blocked; with `{"dataset":"Dataset-A","split":"test","method":"proposed"}`, the selected
accuracy mean is `0.88` with `sample_count=2`. Pass the same filters to scoring.

The latest sanitized historical TokenHub record is in [LIVE_VALIDATION_0_5_CN.md](LIVE_VALIDATION_0_5_CN.md); the
[0.4.0 record](LIVE_VALIDATION_CN.md) is an earlier immutable snapshot. These records distinguish direct API
validation from user-reported CodeBuddy validation and do not treat a GUI-client configuration file as proof of a
client run. Neither record proves current 0.15.0 behavior.

The two-client evidence record is in [CLIENT_VALIDATION_CN.md](CLIENT_VALIDATION_CN.md). The current screenshots prove
0.15.0 ten-tool discovery in both clients. CodeBuddy additionally has user-provided current-version pipeline evidence;
Visual Studio Code 1.131.0 completed a prior-build static-audit Tool call recorded in
`CLIENT_VALIDATION_0_15_INDEX.json`. The older Visual Studio Code comparison remains explicitly labelled 0.5.0 history.

## Machine-checkable evidence

Validate the checked-in credential-free current-wheel evidence with:

```bash
python scripts/validate_client_evidence.py docs/CLIENT_VALIDATION_0_15_INDEX.json
```

The validator requires the canonical ten-tool list, Schema 1.21, server 0.15.0, completed run IDs, relative artifact
paths, SHA-256 content/payload hashes, and `secrets_redacted=true`. It does not claim that a screenshot or record is
an independent proof of model quality.

For the exact wheel used by a live run, first run `python scripts/run_live_wheel_validation.py` to record its digest.
The `--execute` path is intentionally opt-in and requires both `REPROSCOPE_RUN_LIVE=1` and
`REPROSCOPE_ALLOW_CONTROLLED_EXECUTION=1`; it is a runner for this package, not a sandbox for arbitrary repositories.

## Shared Preparation

1. For development and CI, install `requirements.lock` first and then use `python -m pip install -e . --no-deps`; final acceptance must use the newly built 0.15.0 wheel.
2. Configure TokenHub using `.mcp.json`; keep the API key in private client settings only.
3. On Windows, replace `command` with the absolute `.venv/Scripts/python.exe` path.
4. Set `REPROSCOPE_ALLOWED_ROOTS` to the absolute `mcp_servers/reproscope` directory.
5. Restart the client and verify all ten tools are listed.

## CodeBuddy Check

1. Select **Try to Run** in the MCP settings.
2. Confirm all ten tools and their current parameter schemas are visible.
3. Run `reproscope_extract_claims` on `examples/sample_paper.md`.
4. Confirm the output includes the reported `0.91` accuracy, `0.86` baseline, `0.88` ablation, and missing package
   versions/per-seed statistics.
5. Confirm citations contain both `paper_1` and a non-empty locator such as `L1-L10`.
6. Confirm `extract_claims.json` exists below `REPROSCOPE_WORKSPACE`.
7. Run `reproscope_compare_results` with `examples/sample_results.csv` and the claim artifact from step 6; confirm
   the locally calculated values below and that returned claim IDs exist in the claim artifact.
8. Run `reproscope_score_paper` with the claim and comparison artifacts.
9. Run `reproscope_build_evidence_graph` with all three analysis artifacts and confirm `graph_validated=true`.
10. Run `reproscope_render_report` with the graph artifact and confirm the Markdown report contains a graph summary,
   an upstream artifact inventory, and direct-parent lineage.
11. Run `reproscope_extract_claims` on `examples/sample_isac_paper.md` with `domain_profile="auto"`; confirm the active
    profile, version/registry hashes, citation-gated observations, 12 advisory findings, and `affects_score=false`.
12. Run `reproscope_extract_solution_profile` on `examples/sample_solution.md`; confirm the solution-profile artifact and
    its source hash are persisted below `REPROSCOPE_WORKSPACE`.
13. Run `reproscope_assess_transfer` on `examples/sample_solution.md` and `examples/sample_target_context.md` using
    the generated solution-profile artifact; confirm the six fixed dimensions, conditional status, and no unsupported
    target-performance point prediction.
14. Run `reproscope_build_transfer_graph` and `reproscope_render_transfer_report` from the exact profile and assessment
    artifacts; confirm graph lineage, report manifest lineage, and the conditional-transfer boundary.
15. Run `reproscope_audit_repository` on the local `mcp_servers/reproscope` directory; confirm the static audit is
    bounded, records its run manifest, reports download-hash coverage, and does not execute repository code. A
    repository without per-download hashes should show `DOWNLOAD_HASHES_NOT_LOCKED` rather than implying a secure
    install. To exercise the explicit execution boundary, pass an `execution_command` and verify that only its
    SHA-256 digest is recorded with `status=denied` and `executed=false`.
16. Confirm `report_manifest.json` exists, lists the Markdown artifact with its file hash, and does not list itself.
17. Confirm each Tool run directory contains `run_manifest.json` with a completed status and ordered status history.
18. Confirm the final MP4 shows the MCP Tool card, completed status, Schema 1.21, `graph_validated=true`, and relative
    artifact paths without exposing credentials.

For adversarial evidence-input checks, set `REPROSCOPE_PROMPT_INJECTION_POLICY=reject` and confirm a source matching
the detector is refused before any Hy3 request. The detector is best-effort; an empty signal is not a safety proof.

## Visual Studio Code Check

The 2026-07-28 record used VS Code 1.129.1 and 0.5.0 with workspace `.vscode/mcp.json`. It is historical. Repeat the
following against the final 0.15.0 wheel before marking the PR ready:

1. Confirm `hy3Reproscope` is running in `MCP: List Servers`.
2. Confirm all ten ReproScope tools are enabled in Configure Tools.
3. Run `reproscope_compare_results` with the synthetic paper, CSV, and log inputs.
4. Confirm `accuracy` has `sample_count=5`, `reproduced_value=0.876`, and `absolute_delta=-0.034`.
5. Confirm the new comparison `run_manifest.json` is completed and records Schema 1.21.
6. Run `reproscope_audit_repository` on the opened project; confirm a bounded static audit result and completed
   `run_manifest.json`, with no repository code execution.
7. Preserve credential-free current-version screenshots under `docs/assets/`; do not overwrite the historical record
   without documenting the replacement.

### Visual Studio Code direct-call prompt

The supplied VS Code screenshot shows tool discovery and an agent-generated plan, not a completed MCP call. Use a
fresh chat with the following instruction to force auditable, one-tool-at-a-time execution:

```text
Use the connected hy3Reproscope MCP server directly. Do not create a plan, todo list, or prose-only simulation.
Execute exactly one tool call, wait for its raw JSON result, then stop and show that result. Continue only after I say
"next". Do not infer fields from an artifact or from earlier messages.

Start with reproscope_extract_claims on examples/sample_paper.md. For every call, preserve the raw top-level JSON,
including run_id, schema_version, completed artifact path, content/payload hashes, and warnings. For
reproscope_build_evidence_graph and reproscope_build_transfer_graph, verify the returned top-level
graph_validated=true before reading nodes or edges. A planning message, a tool list, or a claim that a call completed
without raw JSON is not evidence; report it as "no call executed" and stop.
```

After the final call, export only a credential-free JSON record using the exact returned run IDs and relative artifact
paths. Validate that record with `python scripts/validate_client_evidence.py`. The screenshot may document the GUI, but
the persisted artifact and its SHA-256 hashes are the acceptance authority.

## Cursor Check

Use Cursor only as an optional additional client:

1. Create `.cursor/mcp.json` in the opened project and paste the `mcpServers` object from `.mcp.json`.
2. Replace `command`, `HY3_API_KEY`, and `REPROSCOPE_ALLOWED_ROOTS` with private absolute values.
3. Restart Cursor and open MCP settings; confirm `hy3-reproscope` is connected and lists ten tools.
4. Run `reproscope_compare_results` with `examples/sample_paper.md` and `examples/sample_results.csv`.
5. Confirm `accuracy` has `sample_count=5`, `reproduced_value=0.876`, and a locally computed delta of `-0.034`.
6. Save a screenshot showing the tool name, success state, and computed fields, with credentials excluded.

## Cline Check

Use Cline as the alternative if Cursor is unavailable:

1. Install Cline in VS Code and open MCP Servers settings.
2. Add the same stdio object and restart the MCP server.
3. Confirm ten tools are visible.
4. Run the same comparison call and verify the deterministic values listed above.
5. Save a credential-free screenshot for the PR description.

## Final Evidence

The final CodeBuddy recording is stored as `docs/assets/demo-0.15.0-codebuddy-mcp.mp4`; current ten-tool discovery
screenshots and the evidence montage are stored in the same directory. The MP4 shows real stdio report calls,
artifact validation, and a completed transfer report. It contains local paths and preceding rejected calls, so its
scope must not be expanded into a claim that every Hy3 workflow was freshly executed in the recording. Historical
0.5.0 evidence remains useful context but cannot satisfy current-version claims.
