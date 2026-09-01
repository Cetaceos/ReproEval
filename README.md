# Hy3 ReproEval

[中文说明](README_CN.md)

Hy3 ReproEval is an evidence-grounded Hy3 application and evaluation framework for open-ended research reports. Its primary scenario is research reproducibility review; technology-transfer assessment is retained as a cross-scenario generalization case.

This is a personal project developed for the 2026 Tencent Rhino-Bird open-source practical program. It is not an official Tencent product.

## Current Status

The first migration milestone is implemented. The repository now contains the validated ReproScope application layer from [Tencent-Hunyuan/Hy3 PR #187](https://github.com/Tencent-Hunyuan/Hy3/pull/187), including:

- 10 stdio MCP tools for reproducibility review, transfer assessment, evidence graphs, reports, and read-only repository audits;
- deterministic statistics, schema validation, source hashes, artifact lineage, and fail-closed evidence checks;
- synthetic examples, offline evaluation suites, live-validation gates, and more than 380 automated tests;
- compatibility with existing `hy3_reproscope_mcp` module and `hy3-reproscope-mcp` command names.

The versioned seven-dimension rubric, deterministic validators, constrained Hy3 semantic Judge, blinded repeated comparison, reproducible dataset protocol, resumable batch Judge runs, group-isolated benchmark runner, repeated-run stability analysis, de-identified annotation validation, agreement analysis, and adjudicated consensus aggregation are implemented. A deterministic 12-group P0 synthetic Dataset candidate is included for protocol experiments. Model judgments cannot replace local citation, numerical, artifact, or hard-cap decisions. Real expert labels and frozen held-out results remain future validation work described in [the project proposal](docs/PROJECT_PROPOSAL_CN.md).

## Architecture

```text
research sources + reproduction results
                  |
                  v
       ReproScope application layer
   Hy3 semantic extraction + local checks
                  |
                  v
      traceable reports and artifacts
                  |
                  v
       ReproEval evaluation layer
 validators + Hy3 rubric judge + human labels
```

Hy3 handles semantic extraction and evidence reasoning. Local Python recalculates numerical results, validates schemas and citations, enforces artifact lineage, and applies deterministic aggregation rules. Model output cannot overwrite locally recomputed facts.

## Quick Start

Requirements: Python 3.11 or newer and a Hy3-compatible API endpoint.

```bash
git clone https://github.com/Cetaceos/ReproEval.git
cd ReproEval
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Linux / macOS:

```bash
./.venv/bin/python -m pip install -e .
```

Load the variables in `.env.example` into the parent shell, or provide them through your MCP client. The package does not auto-load `.env` files. Never commit a real API key.

```text
HY3_API_PROVIDER=tokenhub
HY3_BASE_URL=https://tokenhub.tencentmaas.com/v1
HY3_API_KEY=replace-with-your-key
HY3_MODEL=hy3-preview
REPROSCOPE_ALLOWED_ROOTS=.
REPROSCOPE_WORKSPACE=.reproeval/reproscope
```

Start the MCP server over stdio:

```bash
hy3-reproeval-mcp
```

The original command remains available for existing clients:

```bash
hy3-reproscope-mcp
```

Use [.mcp.json](.mcp.json) as the project-level configuration template. Replace placeholder paths and inject secrets through private client configuration.

## Report Evaluation

Run the public sample without an API key:

```bash
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --output evaluation.json
```

The case manifest registers source locators, required claims and sections, numerical expectations, uncertainty phrases, and artifact hashes. The evaluator returns dimension scores, evidence locations, error codes, assessed weight, hard caps, manifest and Rubric fingerprints, and a machine-readable quality result.

Replay the public synthetic Judge record without an API key:

```bash
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --judge replay \
  --judge-record examples/evaluation/sample_judge_record.json \
  --output hybrid-evaluation.json
```

Run the semantic Judge online and save a reusable record:

```bash
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --judge online \
  --judge-record judge-record.json \
  --output hybrid-evaluation.json
```

The online mode reads the existing `HY3_*` environment variables. A replay record is accepted only when its prompt version, case, scenario, report, Rubric, request, and structured response fingerprints match. Dimensions without deterministic or semantic evidence remain `insufficient_evidence`, and an overall score is withheld below 50% assessed weight. See [EVALUATION_CORE.md](docs/EVALUATION_CORE.md) for the scoring boundary and limitations.

## Blinded Repeated Comparison

Compare two reports that use the same deterministic evaluation contract with the public three-trial replay bundle:

```bash
hy3-reproeval compare-reports \
  --left-case examples/evaluation/sample_case.json \
  --right-case examples/evaluation/sample_case_variant.json \
  --comparison-id sample-pairwise-v1 \
  --repeats 3 \
  --judge replay \
  --judge-record examples/evaluation/sample_pairwise_judge_bundle.json \
  --output pairwise-result.json
```

The prompt omits case IDs and paths, alternates which report is presented as A, and asks Hy3 only for the two semantic dimensions. Python combines those scores with each report's deterministic contribution and hard cap. The result reports score standard deviation, preference flips, quality-band flips, and the observed A/B position delta. The public bundle is synthetic replay data; it validates the protocol and does not claim a real model benchmark. See [PAIRWISE_COMPARISON.md](docs/PAIRWISE_COMPARISON.md).

## Reproducible Dataset Protocol

Validate the public high/medium/low synthetic group without an API key:

```bash
hy3-reproeval validate-dataset \
  --manifest examples/dataset/sample_dataset.json \
  --output dataset-validation.json
```

The versioned Dataset Manifest registers provenance, group-level splits, report tiers, Case Manifests, hashes, expected errors, and Mutation Manifests. Literal mutations can be replayed from their high-quality parent and are accepted only when the output bytes match the registered SHA-256:

```bash
hy3-reproeval replay-mutation \
  --manifest examples/dataset/medium_mutation.json \
  --root examples/dataset
```

Validate attack registration and metric aggregation on the public synthetic adversarial fixture without an API key:

```bash
hy3-reproeval benchmark-dataset \
  --manifest examples/dataset/sample_adversarial_dataset.json \
  --mode deterministic
```

The validator enforces one evaluation contract per source group, prevents a declared source fingerprint from crossing splits, confines paths, and requires exact closure for locally detectable errors. Adversarial reports must additionally register each attack type, target dimension, and expected error with Mutation closure. Semantic labels remain hypotheses for later Hy3 Judge or human validation. Both public fixtures are synthetic development groups for protocol verification, not held-out benchmarks. See [DATASET_PROTOCOL.md](docs/DATASET_PROTOCOL.md) and [ADVERSARIAL_PROTOCOL.md](docs/ADVERSARIAL_PROTOCOL.md).

### P0 synthetic Dataset candidate

The tracked P0 candidate contains 12 isolated synthetic source groups, balanced 4/4/4 development, validation,
and test splits, 44 reports, and 8 adversarial reports covering all seven registered attack types. Rebuild or
byte-verify it without an API key:

```bash
hy3-reproeval build-p0-dataset --output evals/p0_dataset --check
hy3-reproeval validate-dataset --manifest evals/p0_dataset/dataset.json
```

Its generated labels validate the protocol and P0 structural gates; they are not expert ground truth or a
held-out performance result. See [P0_DATASET.md](docs/P0_DATASET.md).

### Dataset freeze

Before generating Judge Records or collecting blinded annotations, freeze every registered input:

```bash
mkdir .reproeval
hy3-reproeval freeze-dataset \
  --manifest examples/dataset/sample_dataset.json \
  --output .reproeval/dataset-freeze.json

hy3-reproeval verify-dataset-freeze \
  --freeze .reproeval/dataset-freeze.json \
  --manifest examples/dataset/sample_dataset.json
```

The Freeze binds the Rubric version and hash and records relative paths, roles, byte sizes, and SHA-256 fingerprints for the Dataset, Cases, reports, evidence attachments, Mutations, and registered Judge Records. `--require-p0-ready` rejects a Dataset below 12 source groups, validation/test coverage, or 8 adversarial reports. The public development fixture freezes successfully with `meets_p0_dataset_targets=false`; freezing does not establish annotation, Judge, or held-out result readiness. See [DATASET_FREEZE.md](docs/DATASET_FREEZE.md).

## Batch Evaluation

Run the registered synthetic Judge records without an API key:

```bash
hy3-reproeval benchmark-dataset \
  --manifest examples/dataset/sample_dataset.json \
  --mode replay \
  --output dataset-benchmark.json
```

The runner evaluates reports only within their source group and reports ranking eligibility, pair coverage and accuracy, complete-order coverage and accuracy, macro group Spearman correlation, and error-label recall. Adversarial reports have separate per-attack-type detection, false-acceptance, and label-recall metrics and never enter the high/medium/low order. Provisional scores are excluded and undefined metrics remain `null`. The public replay is a protocol self-check, not evidence of Hy3 performance, model-human agreement, or adversarial robustness. See [BENCHMARK_PROTOCOL.md](docs/BENCHMARK_PROTOCOL.md).

### Resumable online Judge records

Generate one verified Hy3 record per dataset report in an existing private directory, then consume the complete index directly in replay mode:

```bash
hy3-reproeval generate-judge-records \
  --manifest examples/dataset/sample_dataset.json \
  --dataset-freeze .reproeval/dataset-freeze.json \
  --output-dir .reproeval/judge-run

hy3-reproeval benchmark-dataset \
  --manifest examples/dataset/sample_dataset.json \
  --dataset-freeze .reproeval/dataset-freeze.json \
  --mode replay \
  --judge-index .reproeval/judge-run/judge_record_index.json \
  --output .reproeval/dataset-benchmark.json
```

Create the output directory first and use `--resume` only after reviewing an interrupted run. For controlled experiments, reuse the same `--dataset-freeze` on Judge, Benchmark, annotation, agreement, and consensus commands; each output then carries one verified lineage fingerprint and mismatches fail closed. See [JUDGE_BATCH.md](docs/JUDGE_BATCH.md) and [DATASET_FREEZE.md](docs/DATASET_FREEZE.md).

### Repeated Benchmark stability

After producing three replay Benchmark results from separate Judge output directories, aggregate total-score and
dimension-level dispersion without another API call:

```bash
hy3-reproeval analyze-benchmark-stability \
  --benchmark .reproeval/benchmark-run-1.json \
  --benchmark .reproeval/benchmark-run-2.json \
  --benchmark .reproeval/benchmark-run-3.json \
  --output .reproeval/benchmark-stability.json
```

The analyzer requires distinct Judge run IDs and indexes bound to one Dataset Freeze and reports coverage,
standard deviation, score range, and quality-band flips. See [STABILITY_PROTOCOL.md](docs/STABILITY_PROTOCOL.md).

### Annotation Bundle validation

Validate the public synthetic protocol fixture without an API key:

```bash
hy3-reproeval validate-annotations \
  --manifest examples/dataset/sample_dataset.json \
  --bundle examples/annotations/synthetic_annotation_bundle.json
```

Real benchmark readiness requires two eligible independent, blinded human annotations for every validation/test report. The public synthetic Bundle never counts as human evidence. See [ANNOTATION_PROTOCOL.md](docs/ANNOTATION_PROTOCOL.md).

Analyze human-human agreement and optionally compare aggregated human scores with a bound Dataset Benchmark result:

```bash
hy3-reproeval analyze-annotations \
  --manifest path/to/frozen_dataset.json \
  --dataset-freeze .reproeval/dataset-freeze.json \
  --bundle private_annotations/annotator-01.json \
  --bundle private_annotations/annotator-02.json \
  --benchmark-result .reproeval/dataset-benchmark.json \
  --output .reproeval/annotation-agreement.json
```

The result includes quadratic weighted Cohen's Kappa, exact and within-one-point agreement, mean absolute score difference, per-dimension and per-pair metrics, and an adjudication queue for status mismatches or score gaps above one point. The queue does not resolve disputes automatically. System-human comparison requires at least two eligible human scores per report and reports Spearman correlation and MAE only after Dataset, Rubric, report inventory, split, and content hashes match. Undefined statistics remain `null`; `agreement_ready=true` establishes coverage, not expert provenance or label quality.

Repeat and adjudication Bundles declare `parent_annotation_bundle_ids`. A repeat round references one independent Bundle from the same annotator and appears as repeat stability, not human-human agreement. An adjudication round references at least two independent Bundles, covers reports present in at least two parents, and uses a trained, system-score-blind, conflict-free separate adjudicator. Finalize consensus with the complete lineage set:

```bash
hy3-reproeval finalize-annotations \
  --manifest path/to/frozen_dataset.json \
  --dataset-freeze .reproeval/dataset-freeze.json \
  --bundle private_annotations/annotator-01.json \
  --bundle private_annotations/annotator-02.json \
  --bundle private_annotations/adjudication-01.json \
  --output .reproeval/annotation-consensus.json
```

Non-disputed assessed scores are averaged under the public Rubric. Status mismatches, error-code mismatches, and score gaps above one point require a matching adjudication Bundle. Missing decisions remain unresolved; unrelated or duplicate adjudication is rejected. `consensus_ready=true` requires complete double annotation and a resolved consensus report for every validation/test item.

## Migrated MCP Tools

| Tool | Purpose |
| --- | --- |
| `reproscope_extract_claims` | Extract experimental claims and optional domain evidence |
| `reproscope_compare_results` | Align metrics and recompute reproduction statistics |
| `reproscope_score_paper` | Apply the six-dimension evidence sufficiency rubric |
| `reproscope_build_evidence_graph` | Build a traceable paper evidence graph |
| `reproscope_render_report` | Render a reproducibility review report |
| `reproscope_extract_solution_profile` | Extract a structured technology solution profile |
| `reproscope_assess_transfer` | Assess transfer conditions, risks, and evidence gaps |
| `reproscope_build_transfer_graph` | Build a transfer evidence graph |
| `reproscope_render_transfer_report` | Render a transfer decision report |
| `reproscope_audit_repository` | Statically audit Python repository reproducibility signals |

## Development

Install the locked development environment and run the deterministic checks:

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -e . --no-deps
python -m pytest
python -m ruff check src tests scripts
python scripts/run_offline_eval.py
python scripts/run_transfer_offline_eval.py
```

The live validation scripts require an explicitly supplied Hy3 API key and apply output safety gates before retaining artifacts.

## Repository Layout

```text
src/hy3_reproeval/          ReproEval public package and CLI
src/hy3_reproscope_mcp/     migrated application and MCP compatibility layer
tests/                      unit, integration, stdio, security, and artifact tests
examples/                   public synthetic inputs and MCP client examples
evals/                      migrated deterministic evaluation fixtures
scripts/                    offline, live, packaging, and evidence checks
docs/PROJECT_PROPOSAL_CN.md practical-stage design and delivery plan
docs/EVALUATION_CORE.md     deterministic evaluator contract and limitations
docs/DATASET_PROTOCOL.md    dataset, split, provenance, and mutation contract
docs/DATASET_FREEZE.md      experiment-input freeze, verification, and P0 gate
docs/P0_DATASET.md          canonical synthetic P0 Dataset inventory and boundaries
docs/BENCHMARK_PROTOCOL.md  group-isolated batch metrics and claim boundaries
docs/ADVERSARIAL_PROTOCOL.md adversarial attack registration and detection metrics
docs/JUDGE_BATCH.md         resumable online Judge Record generation
docs/STABILITY_PROTOCOL.md  frozen repeated-Benchmark stability analysis
docs/ANNOTATION_PROTOCOL.md de-identified annotation and readiness contract
docs/reproscope/             selected ReproScope validation evidence and history
```

See [MIGRATION.md](docs/MIGRATION.md) for compatibility and provenance details.
Release history is recorded in [CHANGELOG.md](CHANGELOG.md).

## Security and Scope

- API keys and private research materials must remain outside version control.
- Repository auditing is static and does not execute third-party code.
- The system evaluates available evidence; it does not determine academic misconduct or provide legal conclusions.
- Reports and scores support expert review and do not replace it.

## License

Apache License 2.0. See [LICENSE](LICENSE).
