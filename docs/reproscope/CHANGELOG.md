# Changelog

## 0.15.0 - 2026-07-31

- Add an experimental ISAC physical-layer profile to `reproscope_extract_claims` while preserving the generic profile
  as the default.
- Support explicit `isac_phy` activation and conservative `auto` detection based on joint communication-and-sensing
  evidence, with activation reasons and source references recorded in artifacts.
- Bundle versioned JSON registries for ISAC taxonomy, 24 metrics, 28 assumptions, and 12 risk rules, and persist their
  content hashes and versions in artifacts and run manifests.
- Protect cached registry payloads from caller mutation and validate registry versions, required collections, and
  unique canonical identifiers when package data is loaded.
- Remove unknown or unsupported ISAC classifications, metrics, assumptions, and rules locally after citation
  validation; downgrade unsupported strong findings to `unknown` and keep all domain findings advisory.
- Add ISAC profile and finding nodes to the existing evidence graph and a dedicated section to the deterministic
  Markdown report without changing the generic reliability score.
- Add checked-in positive and insufficient-evidence ISAC fixtures covering conservative activation, explicit
  activation, unsupported-output cleanup, registry bounds, graph integration, and report rendering.
- Bump the structured artifact schema to 1.21 while keeping MCP discovery at ten tools.
- Add an offline, explicitly labelled ISAC calibration helper with split-aware Evidence Cards, descriptive activation
  and risk-rule metrics, correct-abstention reporting, and inter-run stability checks. Synthetic fixtures remain
  regression data only and do not establish an expert or held-out benchmark.
- Extend ISAC calibration reports with per-rule metrics, exact citation-set accuracy, explicit UAR/CAR fields,
  calibration-only threshold selection, frozen held-out application, and group/content-hash leakage checks. Add a
  strict external-human import template that requires provenance before benchmark evaluation.
- Add bounded alias-free YAML parsing, nested scalar summaries for configuration reconciliation, and bounded key/value
  summaries for logs while retaining original line-addressable evidence.
- Add best-effort prompt-injection signals with NFKC/zero-width normalization, quoted-data handling, and an optional
  fail-closed `REPROSCOPE_PROMPT_INJECTION_POLICY=reject` ingestion boundary. This is not an absolute protection.
- Add dependency download-hash coverage diagnostics and a default-deny third-party execution preflight that records
  only a command digest; repository audit remains static read-only and never starts discovered code.
- Expose `graph_validated=true` consistently on transfer reports, manifests, Markdown, and downstream validation.
- Add read-only MCP resources for server metadata, ISAC registry summaries, validated run manifests, and recovery
  guidance; resources never resume runs or execute repository code.
- Add conservative metric-specific conversions for latency, throughput, and spectral-efficiency units, including
  explicit unit suffixes in metric names. Unknown and one-sided units now produce `unresolved_metric_unit` instead of
  a raw delta; dB conversions remain a manual-review boundary.
- Require ISAC calibration fixtures to match the installed profile version when loaded through the library API, not
  only through the command-line harness.
- Keep the local takeover ledger out of source distributions while requiring the public release evidence documents;
  distribution checks now emit archive SHA-256 values for handoff records.
- Add a checked-in `requirements.lock` for the verified development/CI dependency graph and recognize it in bounded
  repository audits; the lockfile pins versions but intentionally does not claim download-hash reproducibility yet.
- Add opt-in 0.15.0 live validators for the transfer and ISAC workflows, with sanitized run/artifact hash summaries and
  explicit failure boundaries; the ISAC validator records activation source from the typed profile model.
- Keep wheel-based live scripts under Python isolated mode while bootstrapping only the fixed repository script
  allowlist, with path-escape and real sibling-import regression coverage.
- Record the direct 0.15.0 Hy3 paper, transfer, and ISAC validation evidence in a machine-readable sanitized index;
  repository-owned examples remain clearly labelled synthetic inputs.
- Revalidate the exact final 0.15.0 wheel through all three live Hy3 workflows, retaining a sanitized summary for 13
  completed runs and 28 independently hash-verified artifacts while preserving earlier quota failures as history.
- Harden the wheel validator with bounded command timeouts, persistent in-project workspaces, per-workflow retries,
  and artifact-type-aware content/payload hash checks.
- Accept a single schema-valid JSON value wrapped in model commentary, make the bounded repair request deterministic,
  and expose exhausted structured-output repair as an explicitly retryable domain error.
- Add the final CodeBuddy MCP MP4 and document its evidence boundary while excluding repository-only video media from
  Python wheel/sdist archives.

## 0.14.0 - 2026-07-30

- Add deterministic `claim_relation_diagnostics` to reproduction comparisons with validated counts for full support,
  partial support, contradiction, and unassessed Claims.
- Calculate Claim relation coverage locally from the supplied claim artifact after unknown and conflicting IDs are
  removed.
- Preserve unassessed Claim IDs in source order and emit an explicit incomplete-coverage warning without modifying
  reliability scores.
- Render the coverage partition and unassessed IDs in paper reproduction reports.
- Extend the paper offline evaluation to 49 deterministic checks and bump the structured artifact schema to 1.20.

## 0.13.0 - 2026-07-30

- Add `partially_supported_claim_ids` to reproduction comparisons for claims whose direction, conditions, or
  magnitude are only partly reproduced.
- Constrain Hy3 to the Claim IDs in the supplied claim artifact and locally enforce mutual exclusivity across full
  support, partial support, and contradiction categories.
- Remove unknown or cross-category Claim IDs with explicit warnings instead of selecting one model-proposed label.
- Emit validated `partially_supports` graph edges and a deterministic partial-support ratio alongside full-support
  and contradiction ratios.
- Bump the structured artifact schema to 1.19 while keeping MCP discovery at ten tools.

## 0.12.0 - 2026-07-30

- Separate direct Claim source coverage from coverage by relations tied to locally recalculated reproduction results.
- Add deterministic `claim_source_coverage` and `reproduction_assessment_coverage` graph metrics while retaining
  combined Claim evidence coverage and the support direction ratio.
- Count a Claim as reproduction-assessed only when its relation originates from an assessment that directly depends
  on a reproduction-result node; text-only Claim relations do not qualify.
- Explain the four coverage semantics in Markdown reports and explicitly avoid treating supplied reproduction
  material as proof of independent reproduction.
- Bump the structured artifact schema to 1.18 while keeping MCP discovery at ten tools.

## 0.11.0 - 2026-07-30

- Add deterministic metric data-quality diagnostics for CSV, JSON, and JSONL result columns.
- Distinguish valid numeric, missing, non-numeric, and non-finite values and record their exact partition and valid
  ratio after group filtering.
- Attach diagnostics to global and group-scoped metric comparisons, with explicit warnings whenever values are
  excluded from statistics.
- Validate data-quality count and ratio invariants when artifacts are loaded, and expose the diagnostics in Markdown
  reports, score context, and evidence-graph result nodes.
- Keep the diagnostics descriptive: missingness does not automatically change reliability scores.
- Bump the structured artifact schema to 1.17 while keeping MCP discovery at ten tools.

## 0.10.0 - 2026-07-30

- Derive descriptive cross-group stability summaries when at least two `group_by` results exist for the same
  metric, source, and column.
- Report the mean and sample standard deviation of group means, observed range, endpoint groups, and the largest
  absolute paper delta without labeling groups as best or worst.
- Suppress range-to-reported percentages for decibel metrics and avoid changing reliability scores from these
  descriptive summaries.
- Include stability summaries in `compare_results.json`, score context, Markdown reports, and evidence graphs.
- Bump the structured artifact schema to 1.16 while keeping MCP discovery at ten tools.

## 0.9.0 - 2026-07-30

- Add optional `group_by` dimensions to `reproscope_compare_results` for bounded, deterministic per-group analysis
  across CSV, JSON, and JSONL reproduction sources.
- Normalize dataset, split, scenario, method, and model aliases, preserve global mixed-group aggregation blocking,
  and reject redundant, missing, truncated, or more than 100 candidate group combinations before calling Hy3.
- Recalculate count, mean, sample standard deviation, metric scale, and paper-relative deltas for
  each real group after Hy3 maps the metric and source column.
- Persist group-scoped comparisons in `compare_results.json` and expose them in Markdown reports and evidence graphs.
- Bump the structured artifact schema to 1.15 while keeping MCP discovery at ten tools.

## 0.8.0 - 2026-07-30

- Allow `reproscope_score_paper` and `reproscope_assess_transfer` to consume an optional, integrity-checked
  `repository_audit.json` artifact.
- Add the repository audit as an exact parent artifact, expose its run ID in downstream results, and merge its
  source inventory into the evidence chain.
- Provide bounded audit context to Hy3 and deterministically append static repository gaps to the relevant paper
  reliability and transfer-feasibility dimensions without overriding scores.
- Warn that repository-to-paper or repository-to-solution association is caller supplied and that discovered
  declarations and commands were not executed.
- Bump the structured artifact schema to 1.14 while keeping MCP discovery at ten tools.

## 0.7.0 - 2026-07-30

- Add `reproscope_audit_repository` for bounded, deterministic inspection of Python repository reproducibility
  conditions without executing repository code or discovered commands.
- Parse root `pyproject.toml`, `setup.cfg`, requirements files, Conda environment files, supported lockfiles,
  shell code blocks in README files, and a bounded set of Python files using structured standard-library parsers.
- Extract declared dependencies, direct-spec pinning, Python constraints, console and module entrypoints,
  installation and test commands, and environment-variable names while ignoring `.env` contents.
- Enforce allowed-root, symlink, per-file, total-byte, and Python-file-count boundaries and report incomplete scans.
- Emit `repository_audit.json` with source hashes, inspected-file inventory, readiness metrics, explicit gaps,
  lifecycle manifest, and `executed_repository_code=false`.
- Bump the structured artifact schema to 1.13 and expand MCP discovery to ten tools.

## 0.6.0 - 2026-07-29

- Add a second end-to-end application for conditional assessment of papers, patents, design notes, and open-source
  solutions against a supplied target project context.
- Add `reproscope_extract_solution_profile` for evidence-linked objectives, components, dependencies, assumptions,
  resources, implementation signals, license signals, provenance signals, and evidence gaps.
- Add `reproscope_assess_transfer` with a fixed six-dimension local rubric for assumption compatibility, reusable
  components, required adaptations, risks, and staged validation planning.
- Add `reproscope_build_transfer_graph` for deterministic assumption invalidation, condition compatibility,
  component transfer, adaptation, risk, validation, source-closure, and coverage relations.
- Add `reproscope_render_transfer_report` for deterministic Markdown and manifest generation without another Hy3 call.
- Reject stale solution profiles by source content hash and require exact profile-parent lineage in downstream
  transfer artifacts.
- Remove model-proposed relations to unknown assumption or component IDs before writing artifacts.
- Treat insufficient transfer evidence as unassessed instead of zero, suppress point performance predictions without
  target measurements, and label license or provenance output as non-legal screening evidence.
- Add a no-key, two-case transfer evaluation suite with 67 deterministic checks and correct-abstention measurement,
  and run it in CI alongside the paper-workflow evaluation.
- Bump the structured artifact schema to 1.12 and add synthetic transfer examples and regression tests.

## 0.5.0 - 2026-07-26

- Detect mixed dataset, split, scenario, and method groups in tabular reproduction results.
- Block unsafe whole-column metric aggregation with an explicit ambiguous-group status and actionable warnings.
- Add a deterministic metric alias registry and explicit fraction, percentage, linear, and decibel scales.
- Convert percentage and fraction values when safe, while rejecting alias conflicts and unsafe linear/dB conversion.
- Allow comparisons to consume a validated claim artifact and sanitize supported/contradicted claim IDs locally.
- Embed canonical payload hashes in JSON artifacts and reject modified schema 1.6 artifacts.
- Record exact parent artifact roles, run IDs, paths, and hashes across comparison, score, graph, and report workflows.
- Use byte-stable UTF-8 artifact writes so file hashes remain identical across Windows, Linux, and macOS.
- Add local dataset, split, scenario, and method filters for CSV, JSON, and JSONL experiment groups.
- Require comparison and scoring artifacts to use the same normalized group-filter contract.
- Extract and normalize common experiment settings locally from paper text, logs, YAML-like text, and structured data.
- Reconcile epochs, optimizer, learning rate, batch size, weight decay, scheduler, and explicit seed values before
  accepting model-proposed setting differences.
- Add a report artifact inventory with exact paths, file hashes, payload hashes, schemas, and direct-parent lineage.
- Write `report_manifest.json` with the Markdown report hash while deliberately excluding a self-reference.
- Persist `run_manifest.json` for every tool with created, running, completed, or failed status history and redacted
  unexpected errors.
- Add a no-key, two-case offline evaluation suite that replays the complete five-tool workflow, checks 45 deterministic
  invariants, measures correct abstention under insufficient evidence, emits schema-defined JSON, and runs in CI.
- Validate the 0.5.0 five-tool workflow against TokenHub, including two real structured-output repair requests and
  completed lifecycle manifests for every tool.
- Make the live validator recover a sanitized summary from completed artifacts and reject source/distribution version
  mismatches before issuing API requests.
- Validate Visual Studio Code 1.129.1 as the second MCP client with five-tool discovery, a real comparison call,
  deterministic result checks, stored screenshots, and a completed local run manifest.
- Prevent decimal tails such as the `0003` in `learning_rate=0.0003 epochs=100` from being extracted as epoch values.
- Bump the structured artifact schema to 1.10 for grouping, metric-scale, claim-run, integrity, parent-lineage,
  group-filter, deterministic-setting, report-manifest, and run-lifecycle metadata.
- Add full synthetic workflows for insufficient-evidence abstention, setting-difference reporting, cross-run artifact
  rejection, and zero-denominator uncertainty.
- Ignore non-finite values in deterministic CSV/JSON/JSONL statistics and reject non-finite model fields.
- Mark relative delta and difference severity as unknown when the reported paper value is zero.
- Add repeatable stdio entrypoint smoke checks and an explicit opt-in real Hy3 workflow validator.
- Document the 0.4.0 TokenHub validation, current client evidence, and public Rhino-Bird MCP PR research.

## 0.4.0 - 2026-07-19

- Add a deterministic Claim-Evidence-Result Graph built from validated claim, comparison, and score artifacts.
- Distinguish observed, deterministically derived, inferred, speculative, and unknown graph evidence.
- Validate graph endpoints, source closure, metrics, source hashes, and upstream run lineage.
- Add graph coverage, contradiction, orphan-claim, setting-coverage, and reproduction-support metrics.
- Optionally include a validated evidence-graph summary in deterministic Markdown reports.
- Add Python 3.11-3.13 CI with tests, builds, and isolated wheel installation.

## 0.3.0 - 2026-07-16

- Preserve complete source inventories and attach validated full references to model citations.
- Reject stale or unrelated prior-analysis and report artifacts through SHA-256 lineage checks.
- Distinguish insufficient evidence from a zero score and report fixed-rubric coverage separately.
- Calculate deterministic numeric summaries for tabular JSON and JSONL reproduction results.
- Include source hashes, rubric coverage, and unassessed dimensions in deterministic reports.

## 0.2.0 - 2026-07-15

- Add Tencent Cloud TokenHub request adaptation for `hy3` and `hy3-preview`.
- Add stable page/line evidence segments and reject unknown citation locators.
- Calculate CSV mean, sample standard deviation, sample count, and metric deltas locally.
- Replace model-selected score weights with a fixed six-dimension reliability rubric.
- Add paper-only assessment safeguards and evidence coverage reporting.
- Add `reproscope_render_report` for deterministic Markdown report generation.
- Add CodeBuddy/Cursor acceptance and demo recording procedures.

## 0.1.0 - 2026-07-14

- Initial FastMCP stdio server, safe local loaders, Hy3 client, three analysis tools, artifacts, and tests.
