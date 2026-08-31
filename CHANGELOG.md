# Changelog

All notable ReproEval changes are documented in this file.

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
