# Changelog

All notable ReproEval changes are documented in this file.

## 0.38.0 - 2026-09-07

### Added

- Dataset schema 1.2 source inventories that bind paper PDFs, journal records, software repositories, release
  archives, and local evidence packets through typed provenance and SHA-256 fingerprints.
- `verify-real-paper-sources` for checking all six cached open-access PDFs, page counts, hashes, and 30 registered
  evidence excerpts without committing copyrighted PDF bytes.
- A source-bounded Hy3 workflow that generates one traceable high-tier candidate per real-paper group and records
  prompt, response, Dataset, source, and output fingerprints in a private review bundle.
- `validate-reference-reviews` and explicit review forms that keep every generated candidate pending until a named
  human reviewer completes the evidence, numerical, limitation, wording, and scientific-boundary checklist.
- A three-run TokenHub `hy3` Judge experiment over the frozen real-paper Pilot, with 54 completed calls and a
  public aggregate result bundle that excludes raw requests, responses, records, and credentials.
- Human-response import compatibility for canonical `L000001` line labels, the `lines` source-reference alias,
  longer expertise declarations, and up to 16 evidence lines without changing finalized integer-only Bundles.
- Two independently completed blind-review Bundles for all 12 validation/test reports, human-human agreement
  analysis, three system-human comparisons, and a fail-closed four-item adjudication queue.
- A third-reviewer packet workflow that exports only queued disputes with anonymous parent evidence traces,
  verifies all frozen copies on return, and binds adjudication output to both parent Bundle hashes.
- Completed third-reviewer resolution of all four queued factual-accuracy disputes, yielding 12/12 final consensus
  reports with `consensus_ready=true` and an updated system-consensus calibration analysis.
- Added a closed, de-identified human-consensus export with report, dimension, and per-run system-human tables,
  plus CLI verification and CI coverage for the real-paper Dataset and all published Pilot result bundles.

### Scientific boundary

- Generated candidates are not Dataset labels, expert ground truth, or independent reproduction results.
- The real-paper Dataset still contains curator drafts; blind report scoring does not promote separately generated
  Hy3 reference candidates, whose six sign-off forms remain pending.
- Human provenance and expertise remain self-attested even though all queued disputes are now resolved; consensus
  does not establish external expert identity, successful software reproduction, or scientific ground truth.

## 0.37.0 - 2026-09-07

### Added

- A six-group real-paper Pilot grounded in attributed CC BY JOSS papers and publication-time software archives,
  with balanced development, validation, and test splits and four declared hard cases.
- Dataset schema fields for open-access publication provenance, paper PDF hashes, study mode, and case difficulty.
- `build-real-paper-pilot` for deterministic materialization and byte verification of the 18-report Pilot.

### Scientific boundary

- Real-paper cases are explicitly classified as reproducibility-readiness reviews because ReproEval has not run the
  third-party software or generated independent measurements.
- High-tier reports use `curator_draft`; validation and Benchmark output warn that these tiers remain construction
  hypotheses until blinded human review is complete.

## 0.36.0 - 2026-09-06

### Added

- Annotation packet schema `1.1`, with a de-identified source-material inventory for every blind-review item.
- Canonical `L000001 | ...` identifiers for report and source copies, raw/copy SHA-256 fingerprints, and
  machine-readable source-line references in finalized human Annotation Bundles.
- Tamper tests for report copies, source copies, private source mappings, assignments, and out-of-range source
  evidence.

### Security

- Reviewer directories retain neutral item and source IDs and exclude quality tiers, Mutation metadata, expected
  errors, system scores, and private Dataset mappings.
- Finalization reconstructs packet files from the frozen Dataset and fails closed on changed source bytes,
  fingerprints, paths, line counts, or evidence references.

## 0.35.0 - 2026-09-03

### Added

- Dependency-free deterministic SVG rendering for quality-tier scores and dimension-level repeated-run stability.
- A closed Figure Manifest that binds every figure to the verified source result manifest and records byte sizes
  and SHA-256 fingerprints.
- `render-results-figures` and `verify-results-figures` CLI workflows, a tracked P1 figure bundle, CI verification,
  protocol documentation, and tamper-focused tests.

### Safety

- Figure rendering consumes verified aggregate CSV artifacts only and never reads raw Judge responses or calls
  Hy3; self-contained SVG output cannot load scripts or external resources.
- Visualization does not create new evidence or expand the scientific claims supported by the source experiment.

## 0.34.0 - 2026-09-03

### Added

- A repository-level `reproeval-research-audit` Agent Skill that routes paper-reproduction and technology-transfer
  requests through the existing ten-tool Hy3 ReproScope MCP boundary.
- Progressive workflow references for exact artifact chaining, partial-evidence behavior, report completion, and
  research-specific claim boundaries.
- Structural tests that validate Skill metadata and references and require its documented tool inventory to match
  the live MCP `list_tools()` contract exactly.

### Safety

- The Skill forbids internal-handler fallbacks, third-party code execution, invented evidence, fraud findings,
  legal conclusions, deployment guarantees, and unsupported target-performance predictions.

## 0.33.0 - 2026-09-03

### Added

- A strict standalone verifier for published Benchmark review bundles, including manifest schema, closed inventory,
  byte-size, SHA-256, symlink, extra-file, lineage-list, and duplicate-run checks.
- A tracked aggregate result bundle from three completed online Hy3 runs over the synthetic P1 transfer Dataset.
- A P1 experiment report covering discrimination, repeated-run stability, unexpected semantic findings, typical
  failure modes, and explicit scientific claim boundaries.

### Security

- Published results contain aggregate Markdown/CSV artifacts and cryptographic lineage only; raw Hy3 requests,
  responses, private experiment state, and credentials remain outside version control.

## 0.32.0 - 2026-09-02

### Added

- Randomized, neutral-ID annotation work packets containing the public Rubric, blank response forms, and copied
  validation/test reports without registered tiers, mutation metadata, expected errors, or system scores.
- A private coordinator manifest that binds every neutral item to its original report and verifies Dataset Freeze,
  Rubric, assignment, report-copy, item-inventory, and evidence-line integrity during finalization.
- `prepare-annotation-packet` and `finalize-annotation-packet` CLI workflows that emit existing strict independent
  human Annotation Bundles for downstream validation, agreement analysis, and consensus.

### Security

- Development reports are excluded, separate annotators receive independently randomized packets, and the
  documentation defines a two-directory trust boundary so the private item mapping is never sent to reviewers.
- Packet preparation does not execute Dataset content or call Hy3; packet outputs and human records remain private
  and ignored by repository defaults.

## 0.31.0 - 2026-09-02

### Added

- A one-command repeated-Judge experiment orchestrator that creates one Dataset Freeze, independent resumable
  Judge runs, replay Benchmarks, Stability output, and a verified Markdown/CSV review bundle.
- An experiment manifest with run state, model/provider provenance, relative artifact paths, Judge run IDs, and
  Judge Record Index fingerprints.
- CLI, protocol documentation, and tests for interruption recovery, completed-run verification, tamper rejection,
  experiment locking, and no-call replay of completed experiments.

### Security

- Experiment output roots reject concurrent writers, changed Dataset/Freeze lineage, changed completed
  Benchmarks, and changed exported review files without storing API credentials.

## 0.30.0 - 2026-09-01

### Added

- A deterministic five-group P1 transfer-generalization Dataset with 15 high/medium/low reports, 10 replayable
  Mutation Manifests, and isolated development/validation/test source groups.
- Transfer cases covering edge inference, UAV federated learning, antenna-array migration, ISAC bandwidth, and
  embedded semantic communication constraints.
- CLI, CI, byte-verification, Dataset validation, Freeze, and test coverage for the canonical P1 inventory.

### Fixed

- Reproduction-specific P0 scale and adversarial warnings no longer appear on transfer-only Datasets.

## 0.29.0 - 2026-09-01

### Added

- A fail-closed Benchmark result exporter that recomputes and verifies the supplied repeated-run Stability lineage.
- Deterministic Markdown, run-level CSV, report-level CSV, dimension-level CSV, and SHA-256 export manifest outputs.
- A CLI workflow for creating review-ready result bundles without exposing Judge response bodies.

## 0.28.1 - 2026-09-01

### Fixed

- Judge batch generation now acquires an exclusive output-directory lock before inspecting or writing records,
  preventing concurrent generators from invalidating index file hashes.
- The lock is released after both successful and failed API runs; an existing lock fails closed with recovery guidance.

## 0.28.0 - 2026-09-01

### Added

- Dataset-wide repeated Benchmark stability analysis with report- and dimension-level score dispersion,
  quality-band flips, coverage gates, and the preregistered maximum-standard-deviation target.
- Independent `run_id` and UTC start-time provenance for resumable Judge Record indexes, propagated into
  Dataset Benchmark results alongside per-report Judge Record hashes.
- A fail-closed CLI protocol requiring replay mode, one Dataset Freeze, one Rubric, matching report inventories,
  and distinct Judge runs and indexes.

### Compatibility

- Older Judge Record indexes and Benchmark results remain readable, but lack the run identity required to make
  an independent repeated-run stability claim.

## 0.27.0 - 2026-09-01

### Added

- A deterministic P0 Dataset builder with byte-exact write and verification modes.
- A tracked synthetic benchmark candidate containing 12 isolated source groups, 44 reports, balanced
  development/validation/test splits, and 8 adversarial reports spanning all seven registered attack types.
- CLI, CI, Freeze-readiness, tamper-detection, packaging, and documentation coverage for the P0 Dataset.

### Boundaries

- P0 structural readiness does not establish expert-label quality, Hy3 performance, model-human agreement,
  or held-out generalization; those claims require the planned blinded annotation and online Judge experiments.

## 0.26.0 - 2026-09-01

### Added

- Optional `dataset_freeze_sha256` lineage on Judge Record indexes, Dataset Benchmark results, Annotation Bundles, annotation validation, agreement analysis, and consensus outputs.
- A shared `--dataset-freeze` option for Judge generation, benchmarking, annotation validation, agreement analysis, and consensus finalization.
- Cross-artifact tests proving one verified Freeze fingerprint flows through machine and human evaluation outputs.

### Safety

- Supplying a Dataset Freeze requires Judge indexes and Annotation Bundles to carry its exact verified fingerprint; unbound and mismatched artifacts fail closed.
- Freeze-bound Judge indexes and Annotation Bundles cannot be consumed or resumed without explicitly verifying their Freeze again.
- System-human comparison rejects Benchmark and annotation lineages that do not use the same Dataset Freeze fingerprint.
- Existing development fixtures remain readable without strict Freeze binding, while controlled experiments can opt into the stronger contract.

## 0.25.0 - 2026-08-31

### Added

- Deterministic Dataset Freeze artifacts binding the Dataset Manifest, public Rubric, Case Manifests, reports, evidence attachments, Mutation Manifests, and registered Judge Records.
- Canonically ordered file inventories with path, role, byte size, SHA-256, and a self-digest over the complete Freeze payload.
- Explicit P0 Dataset readiness checks for source-group scale, validation/test presence, and adversarial-report coverage.
- `freeze-dataset` and `verify-dataset-freeze` CLI commands, including an optional fail-closed `--require-p0-ready` gate.
- A versioned Dataset Freeze protocol and tests for payload tampering, post-freeze input changes, evidence attachments, and development-only readiness refusal.

### Safety

- Every frozen path must remain inside the Dataset root, and duplicate paths or roles are rejected.
- Freeze verification revalidates the Dataset before comparing its identity, Rubric, complete file inventory, and readiness state.
- Meeting Dataset targets does not claim Judge completeness, human annotation coverage, agreement, consensus, held-out performance, or adversarial robustness.

## 0.24.0 - 2026-08-31

### Added

- A versioned adversarial attack contract covering length inflation, terminology stuffing, conclusion repetition, fabricated authority, calculation corruption, limitation suppression, and unsupported overconfidence.
- Per-attack bindings to target Rubric dimensions, expected error labels, mutation operations, and globally unique attack IDs.
- Per-report, per-group, per-split, aggregate, and per-attack-type detection metrics.
- Attack detection rate, attack false-acceptance rate, report-level complete detection, and adversarial error-label recall.
- A public synthetic adversarial development fixture for credential-free deterministic protocol checks.

### Safety

- Adversarial reports require an explicit attack specification and cannot be labeled as reference revisions.
- Attack labels must be a subset of report labels, and synthetic attack dimensions must be covered by registered Mutation operations.
- Adversarial reports remain outside the high/medium/low quality order; attack metrics do not alter ranking scores.
- Public attack metrics are synthetic development checks, so this release establishes the protocol but makes no robustness claim.

## 0.23.0 - 2026-08-31

### Added

- Parent-bound Annotation Bundle lineage for independent, repeat, and adjudication rounds.
- Same-annotator repeat stability with pooled and per-dimension agreement metrics, kept separate from human-human agreement.
- Error-code disagreement detection in addition to status mismatch and score-gap adjudication triggers.
- Fail-closed human consensus aggregation with independent score means, Rubric weighting, minimum coverage, and declared hard caps.
- `finalize-annotations` CLI command with resolved/unresolved dispute inventories and consensus report scores.

### Safety

- Repeat Bundles must reference one independent Bundle from the same annotator; adjudication Bundles must reference at least two distinct independent annotators and use a separate adjudicator.
- Missing adjudication keeps a dimension unresolved, while duplicate, unrelated, or unused adjudication Bundles are rejected.
- Repeat stability is never presented as multi-annotator agreement, and incomplete consensus cannot enter benchmark use.

## 0.22.0 - 2026-08-31

### Added

- Human-human agreement analysis over eligible independent Annotation Bundles.
- Pooled, per-dimension, and per-annotator-pair status agreement, exact score agreement, within-one-point agreement, mean absolute difference, error-code agreement, and quadratic weighted Cohen's Kappa.
- Deterministic adjudication queues for status mismatches and dimension score gaps greater than one point.
- Optional system-human Spearman correlation and mean absolute error from a bound Dataset Benchmark result.
- `analyze-annotations` CLI command with machine-readable coverage, denominators, warnings, and fingerprints.

### Safety

- Synthetic fixtures and development-only reports never contribute to agreement metrics.
- Undefined Kappa or correlation values remain `null`; missing variance or coverage is not rewritten as zero.
- System-human analysis rejects mismatched Dataset, Rubric, group, report, split, or report-content fingerprints.
- Agreement readiness establishes annotation coverage only and does not prove annotator identity, expertise, or label quality.

## 0.21.0 - 2026-08-31

### Added

- Resumable online Hy3 Judge Record generation for every report in a versioned Dataset Manifest.
- Tamper-evident Judge Record indexes that bind model, provider, Dataset, Rubric, requests, responses, and files.
- Direct replay benchmarking from a complete Judge Record index without mutating the Dataset Manifest.
- A strict de-identified annotation Bundle schema with report-line evidence, eligibility checks, and validation/test double-annotation coverage gates.
- Public synthetic annotation fixture and protocol documentation that cannot be counted as human ground truth.

### Safety

- Partial online runs remain explicitly incomplete and cannot enter replay benchmarks.
- Existing record directories require explicit resume mode, and every resumed record is revalidated before reuse.
- Human identity and expertise metadata remain self-attested; this release validates annotation inputs but does not report agreement or adjudication metrics.

## 0.20.0 - 2026-08-31

### Added

- Group-isolated batch evaluation for versioned ReproEval datasets.
- Deterministic and registered Judge replay modes with explicit ranking eligibility.
- Pairwise ordering accuracy, complete-order coverage/accuracy, macro group Spearman correlation, and error-label recall.
- Per-report expected, detected, missing, and unexpected error inventories.
- Tamper-evident Judge Record registration in Dataset Manifests and a public three-tier synthetic replay fixture.
- `benchmark-dataset` CLI command and a versioned Benchmark protocol document.

### Safety

- Provisional deterministic-only scores are excluded from ranking metrics.
- Adversarial reports are excluded from high/medium/low ordering until an explicit attack label contract is available.
- Synthetic replay metrics are identified as protocol checks, not model-human benchmark evidence.

## 0.19.0 - 2026-08-30

### Added

- Versioned dataset, provenance, report-tier, and literal Mutation Manifest schemas.
- Deterministic mutation replay with parent/output hashes and exact operation cardinality.
- Dataset validation for group-level splits, evaluation-contract equality, path confinement, and expected deterministic error closure.
- `validate-dataset` and `replay-mutation` CLI commands plus a public three-tier synthetic protocol fixture.

### Changed

- Normalize tracked text files to LF so registered report and mutation hashes remain stable across operating systems.

### Limitations

- The public fixture is one synthetic development group for protocol verification, not a benchmark result or human-labeled dataset.

## 0.18.0 - 2026-08-30

### Added

- Blinded A/B report comparison under an identical deterministic evaluation contract.
- Alternating presentation order and 2-10 repeated Hy3 semantic Judge trials.
- Fixed local aggregation of deterministic contributions, semantic scores, and per-report hard caps.
- Score standard deviation, preference flip rate, quality-band flips, and observed A/B position deltas.
- Tamper-evident online bundles, credential-free replay, CLI support, and a public synthetic example.

### Security

- Pairwise prompts omit case IDs and file paths, serialize both reports as untrusted data, and validate all cited lines locally.

## 0.17.0 - 2026-08-30

### Added

- Constrained Hy3 semantic Judge for reasoning consistency and clarity/actionability.
- Versioned Judge prompt, deterministic inference parameters, strict structured response schema, and report-line evidence validation.
- Tamper-evident Judge records with report, Rubric, request, and structured-response SHA-256 fingerprints.
- Credential-free offline replay and online/replay CLI modes.

### Changed

- Hybrid aggregation fills only previously unassessed semantic dimensions and preserves all deterministic findings and hard caps.

## 0.16.0 - 2026-08-28

### Added

- Versioned seven-dimension public report-quality Rubric.
- Deterministic validation for citations, claim support, numerical facts, units, required sections, uncertainty disclosures, and artifact hashes.
- Coverage-aware aggregation, `insufficient_evidence` dimensions, provisional results, and critical-error hard caps.
- `hy3-reproeval evaluate-report` CLI and a credential-free public sample.
- Linux Python 3.11-3.13 plus Windows/macOS Python 3.11 CI matrix.

### Changed

- Decoupled historical ReproScope 0.15.0 client evidence from the current ReproEval package version.

## 0.15.0 - 2026-08-28

### Added

- Migrated the validated ReproScope application layer, 10 MCP tools, tests, examples, offline evaluations, packaging checks, and selected client evidence.
- Added the `hy3_reproeval` package and retained ReproScope module and command compatibility.
