# ReproEval Batch Benchmark Protocol

ReproEval 0.21.0 batch-evaluates reports registered by the Dataset Protocol and aggregates results without comparing scores across unrelated source groups. It supports deterministic protocol checks and Judge replay; neither mode creates human ground truth.

## Modes

### Deterministic

```bash
hy3-reproeval benchmark-dataset \
  --manifest examples/dataset/sample_dataset.json \
  --mode deterministic \
  --output deterministic-benchmark.json
```

This mode runs only local validators. Reports with unassessed semantic dimensions remain provisional. Their scores are retained for inspection but are excluded from ranking metrics, so missing semantic evidence cannot silently become a ranking claim.

### Replay

```bash
hy3-reproeval benchmark-dataset \
  --manifest examples/dataset/sample_dataset.json \
  --mode replay \
  --output replay-benchmark.json
```

Replay accepts either a Judge Record registered on every report or one complete external index produced by `generate-judge-records`:

```bash
hy3-reproeval benchmark-dataset \
  --manifest path/to/dataset.json \
  --mode replay \
  --judge-index .reproeval/judge-run/judge_record_index.json \
  --output replay-benchmark.json
```

ReproEval reconstructs the versioned prompt and verifies the Dataset, Case, scenario, report, Rubric, model, provider, request, structured response, evidence lines, and file hashes before using a record. Partial indexes and missing or mismatched records fail closed. See [JUDGE_BATCH.md](JUDGE_BATCH.md) for online generation and resume semantics.

## Ranking Eligibility

A report is eligible for ranking only when it has an overall score and `provisional=false`. Expected ordering is defined only for `high > medium > low` within one source group. Reports in the same tier are not compared. `adversarial` reports are retained for future attack-specific analysis but excluded from this order because adversarial intent alone does not define a quality position.

No pair is formed across different papers, solutions, scenarios, or source groups. This avoids treating task difficulty as report quality.

## Metrics

Every result reports its numerator, denominator, and coverage:

| Metric | Definition |
| --- | --- |
| Ranking score coverage | Ranking-eligible high/medium/low reports divided by candidate reports |
| Pair coverage | Evaluated expected pairs divided by all expected within-group tier pairs |
| Pairwise accuracy | Correctly ordered pairs divided by evaluated pairs; score ties are incorrect |
| Complete-order coverage | Groups with every expected pair evaluated divided by all groups |
| Complete-order accuracy | Fully correct groups divided by complete-order-evaluable groups |
| Macro Spearman | Mean of group-level Spearman correlations for complete groups |
| Error-label recall | Detected expected error labels divided by registered expected labels |
| Unexpected errors | Failed evaluator error labels absent from the registered expectation |

Undefined metrics are serialized as `null`, never rewritten as zero. Macro Spearman gives each source group equal weight and is not pooled across unrelated tasks.

## Public Fixture Boundary

The public fixture contains one repository-authored synthetic development group. Its Judge records were deliberately constructed for credential-free replay and identify their provider as `public-synthetic-replay`. A perfect ordering or error-label result on this fixture proves only that hashing, replay, aggregation, and expected protocol behavior close correctly.

Claims about Hy3 quality, held-out generalization, model-human agreement, stability, or adversarial robustness require frozen validation/test groups, real model runs, and independently reviewed human labels. Dataset validation warnings keep these missing conditions visible.

Annotation Bundle validation and the double-annotation readiness gate are defined in [ANNOTATION_PROTOCOL.md](ANNOTATION_PROTOCOL.md). Passing that gate establishes input coverage, not agreement quality.

A bound Benchmark result may be passed to `analyze-annotations` for system-human Spearman correlation and mean absolute error. ReproEval requires exact Dataset, Rubric, group, split, report, and report-hash closure before comparison; undefined correlations remain `null`.
