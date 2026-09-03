# Hy3 ReproEval

[中文说明](README_CN.md)

Hy3 ReproEval is an evidence-grounded Hy3 application and evaluation framework for open-ended research reports. Its primary scenario is research reproducibility review; technology-transfer assessment is retained as a cross-scenario generalization case.

This is a personal project developed for the 2026 Tencent Rhino-Bird open-source practical program. It is not an official Tencent product.

## Current Status

The first migration milestone is implemented. The repository now contains the validated ReproScope application layer from [Tencent-Hunyuan/Hy3 PR #187](https://github.com/Tencent-Hunyuan/Hy3/pull/187), including:

- 10 stdio MCP tools for reproducibility review, transfer assessment, evidence graphs, reports, and read-only repository audits;
- deterministic statistics, schema validation, source hashes, artifact lineage, and fail-closed evidence checks;
- synthetic examples, offline evaluation suites, live-validation gates, and more than 400 automated tests;
- compatibility with existing `hy3_reproscope_mcp` module and `hy3-reproscope-mcp` command names.

The versioned seven-dimension rubric, deterministic validators, constrained Hy3 semantic Judge, blinded repeated comparison, reproducible dataset protocol, resumable batch Judge runs, group-isolated benchmark runner, repeated-run stability analysis, blinded human work packets, de-identified annotation validation, agreement analysis, and adjudicated consensus aggregation are implemented. A deterministic 12-group P0 synthetic Dataset candidate is included for protocol experiments. Model judgments cannot replace local citation, numerical, artifact, or hard-cap decisions. Real expert labels and frozen held-out results remain future validation work described in [the project proposal](docs/PROJECT_PROPOSAL_CN.md).

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

## Agent Skill

The repository includes [`reproeval-research-audit`](skills/reproeval-research-audit), a thin Agent Skill that
routes natural-language requests through the two complete MCP workflows while preserving artifact lineage,
insufficient-evidence outcomes, and safety boundaries. It does not replace the MCP server or contain credentials.

Install it from a source checkout into an Agent Skills-compatible client, then invoke
`$reproeval-research-audit`. See [SKILL_ADAPTER.md](docs/SKILL_ADAPTER.md) for installation, workflow behavior, and
validation details.

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

### P1 transfer-generalization Dataset

The tracked P1 Dataset adds five isolated transfer scenarios and 15 high/medium/low reports across edge
inference, UAV federated learning, antenna arrays, ISAC, and semantic communication. It verifies whether the
same seven-dimension evaluator can audit conditional transfer reports without changing Rubric weights:

```bash
hy3-reproeval build-p1-transfer-dataset --output evals/p1_transfer_dataset --check
hy3-reproeval validate-dataset --manifest evals/p1_transfer_dataset/dataset.json
```

The Dataset evaluates report quality, evidence use, target constraints, limitations, and validation plans. It
does not establish that any synthetic solution is deployable. See [P1_TRANSFER_DATASET.md](docs/P1_TRANSFER_DATASET.md).

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

Create the output directory first and use `--resume` only after reviewing an interrupted run. Concurrent generators targeting one output directory are rejected by an exclusive lock. For controlled experiments, reuse the same `--dataset-freeze` on Judge, Benchmark, annotation, agreement, and consensus commands; each output then carries one verified lineage fingerprint and mismatches fail closed. See [JUDGE_BATCH.md](docs/JUDGE_BATCH.md) and [DATASET_FREEZE.md](docs/DATASET_FREEZE.md).

### One-command repeated Judge experiment

Freeze a Dataset, produce three independent resumable Judge runs, replay each Benchmark, analyze stability,
and export the review bundle through one command:

```bash
hy3-reproeval run-judge-experiment \
  --manifest evals/p1_transfer_dataset/dataset.json \
  --output-dir .reproeval/p1-transfer-experiment \
  --runs 3
```

Use an absent or empty output directory. After inspecting an interruption, append `--resume`; completed runs
are hash-verified and reused, while a completed experiment is revalidated without another API call. The command
uses an experiment-level exclusive lock and never stores credentials. See
[JUDGE_EXPERIMENT.md](docs/JUDGE_EXPERIMENT.md).

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

Export the verified results as a review-ready Markdown and CSV bundle:

```bash
hy3-reproeval export-benchmark-results \
  --benchmark .reproeval/benchmark-run-1.json \
  --benchmark .reproeval/benchmark-run-2.json \
  --benchmark .reproeval/benchmark-run-3.json \
  --stability .reproeval/benchmark-stability.json \
  --output-dir .reproeval/benchmark-review
```

The exporter recomputes Stability from the Benchmark inputs before writing any result and refuses a non-empty
output directory. See [RESULT_EXPORT.md](docs/RESULT_EXPORT.md).

The tracked [P1 transfer Judge result bundle](results/p1_transfer_judge) records three real Hy3 runs over the
synthetic transfer Dataset without publishing raw model responses. Its integrity can be checked locally:

```bash
hy3-reproeval verify-results-export --bundle results/p1_transfer_judge
```

See the [P1 experiment analysis](docs/P1_JUDGE_EXPERIMENT_CN.md) for result attribution, observed failure modes,
and claim boundaries.

Render and verify self-contained SVG figures from any verified result bundle:

```bash
hy3-reproeval render-results-figures \
  --bundle results/p1_transfer_judge \
  --output-dir .reproeval/p1-figures
hy3-reproeval verify-results-figures \
  --figures .reproeval/p1-figures \
  --source-bundle results/p1_transfer_judge
```

The tracked [P1 figures](results/p1_transfer_judge_figures) are bound to the published result manifest and contain
no raw model responses. See [RESULT_FIGURES.md](docs/RESULT_FIGURES.md).

### Annotation Bundle validation

Prepare a randomized work packet from one frozen Dataset before collecting independent expert labels:

```bash
hy3-reproeval prepare-annotation-packet \
  --manifest evals/p1_transfer_dataset/dataset.json \
  --dataset-freeze .reproeval/p1-transfer-freeze.json \
  --output-dir private_annotations/p1-reviewer-a \
  --assignment-id p1-independent-a \
  --annotator-id reviewer-a \
  --bundle-id p1-independent-bundle-a
```

Send only the generated `annotator/` directory to the reviewer; retain `coordinator_manifest.json` privately.
After the completed directory is returned, use `finalize-annotation-packet` to verify it and emit a strict Bundle.
See [ANNOTATION_PACKET.md](docs/ANNOTATION_PACKET.md) for the complete two-annotator workflow and trust boundary.

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
docs/P1_TRANSFER_DATASET.md canonical P1 transfer-generalization inventory and boundaries
docs/P1_JUDGE_EXPERIMENT_CN.md P1 real-Hy3 result analysis and failure modes
docs/SKILL_ADAPTER.md        Agent Skill installation and orchestration contract
docs/DELIVERY_STATUS_CN.md   requirement-by-requirement final delivery status
docs/RESULT_FIGURES.md       deterministic SVG rendering and verification protocol
docs/BENCHMARK_PROTOCOL.md  group-isolated batch metrics and claim boundaries
docs/ADVERSARIAL_PROTOCOL.md adversarial attack registration and detection metrics
docs/JUDGE_BATCH.md         resumable online Judge Record generation
docs/JUDGE_EXPERIMENT.md    one-command frozen repeated-Judge orchestration
docs/STABILITY_PROTOCOL.md  frozen repeated-Benchmark stability analysis
docs/RESULT_EXPORT.md       verified Markdown/CSV Benchmark review bundles
docs/ANNOTATION_PACKET.md   blinded human work-packet preparation and finalization
docs/ANNOTATION_PROTOCOL.md de-identified annotation and readiness contract
docs/reproscope/             selected ReproScope validation evidence and history
results/                     published aggregate result bundles with SHA-256 manifests
skills/                      reusable Agent Skill for the two MCP workflows
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
