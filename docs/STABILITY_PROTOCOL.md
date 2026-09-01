# Repeated Benchmark Stability Protocol

ReproEval measures Judge stability across complete Dataset Benchmark runs. The protocol reports score
dispersion and quality-band flips without treating repeated model outputs as human ground truth.

## Required Lineage

Every input must be a replay-mode Dataset Benchmark bound to:

- the same Dataset ID, version, Manifest SHA-256, and Dataset Freeze SHA-256;
- the same public Rubric version and SHA-256;
- the same report IDs, groups, splits, tiers, Cases, and report hashes;
- a distinct Judge `run_id` and a distinct complete Judge Record Index.

New Judge Record indexes store a random 32-character `run_id` and UTC start time. Resuming an interrupted run
preserves both values. Older artifacts remain valid for ordinary replay but cannot establish independent-run
provenance for this protocol.

## Three-Run Workflow

Create and verify one P0 Dataset Freeze:

```bash
mkdir .reproeval
hy3-reproeval freeze-dataset \
  --manifest evals/p0_dataset/dataset.json \
  --output .reproeval/p0-dataset-freeze.json \
  --require-p0-ready
```

For each run number `1`, `2`, and `3`, create a new empty output directory and make fresh online Hy3 calls:

```bash
mkdir .reproeval/judge-run-1
hy3-reproeval generate-judge-records \
  --manifest evals/p0_dataset/dataset.json \
  --dataset-freeze .reproeval/p0-dataset-freeze.json \
  --output-dir .reproeval/judge-run-1

hy3-reproeval benchmark-dataset \
  --manifest evals/p0_dataset/dataset.json \
  --dataset-freeze .reproeval/p0-dataset-freeze.json \
  --mode replay \
  --judge-index .reproeval/judge-run-1/judge_record_index.json \
  --output .reproeval/benchmark-run-1.json
```

Use the same two commands with new `judge-run-2` and `judge-run-3` directories. `--resume` may recover an
interrupted directory, but it preserves the original `run_id` and does not create an independent repeat.

Aggregate all three Benchmark artifacts without another API call:

```bash
hy3-reproeval analyze-benchmark-stability \
  --benchmark .reproeval/benchmark-run-1.json \
  --benchmark .reproeval/benchmark-run-2.json \
  --benchmark .reproeval/benchmark-run-3.json \
  --output .reproeval/benchmark-stability.json
```

## Metrics

For each report, the result records score coverage, mean, population standard deviation, range, quality-band
flip, ranking-eligibility flip, evaluation-status flip, and the same score statistics for each Rubric dimension.
Aggregate output reports mean and maximum report standard deviation, flip counts and rates, and dimension-level
coverage and dispersion.

`protocol_coverage_ready=true` requires at least three runs and a score for every report and every Rubric
dimension in every run. The planned score-stability target is evaluated conservatively against the maximum
report standard deviation: `maximum_report_score_stddev <= 5`. A failed target remains a valid experimental
result and must not be removed.

## Claim Boundary

The output describes only the supplied frozen model runs. It does not prove expert agreement, label accuracy,
adversarial robustness, or generalization to other datasets, prompts, models, providers, or model revisions.
