# Changelog

All notable ReproEval changes are documented in this file.

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
