# Human Annotation Bundle Protocol

ReproEval 0.21.0 and later define a strict, de-identified format for collecting report-quality judgments against the same seven-dimension public Rubric used by the evaluator. ReproEval 0.22.0 adds agreement analysis, deterministic adjudication queues, and optional system-human comparison.

## Annotation Unit

One Bundle records one annotator's work and binds it to exact Dataset Manifest and Rubric SHA-256 fingerprints. Each report annotation must:

- match a registered group, report ID, and report hash;
- contain every Rubric dimension exactly once;
- use `assessed` with a 0-4 score and at least one valid report line, or `insufficient_evidence` without a score;
- include a concise rationale and only dimension-compatible error codes.

Annotator IDs must be pseudonymous identifiers, not names or email addresses. Expertise, rubric training, independence, blinding, and conflict-of-interest fields are auditable declarations, not proof of identity or expertise.

## Benchmark Eligibility

An annotation contributes to benchmark readiness only when all of the following hold:

- `annotation_source` is `human` and `annotation_round` is `independent`;
- the report belongs to the `validation` or `test` split;
- the annotator declares independent work, blindness to system scores, and completed rubric training;
- conflict of interest was disclosed and is not present.

Every validation/test report must have eligible independent annotations from at least two distinct annotators for `benchmark_ready=true`. Adjudication and repeat rounds remain valid records but do not satisfy this gate. One pseudonymous annotator cannot submit multiple independent Bundles in the same validation call.

## Validate Bundles

The repeatable `--bundle` option validates several annotators together:

```bash
hy3-reproeval validate-annotations \
  --manifest path/to/frozen_dataset.json \
  --bundle private_annotations/annotator-01.json \
  --bundle private_annotations/annotator-02.json \
  --output .reproeval/annotation-validation.json
```

Private annotation files are ignored by the repository defaults. The output reports counts, split coverage, eligible double annotation, readiness, file fingerprints, and warnings. It does not expose API credentials or infer annotator identity.

## Analyze Agreement

Use the same independently collected Bundles to compute human-human agreement:

```bash
hy3-reproeval analyze-annotations \
  --manifest path/to/frozen_dataset.json \
  --bundle private_annotations/annotator-01.json \
  --bundle private_annotations/annotator-02.json \
  --output .reproeval/annotation-agreement.json
```

The result reports all metric denominators and includes:

- status, exact-score, within-one-point, and error-code-set agreement;
- mean absolute score difference and quadratic weighted Cohen's Kappa;
- pooled, per-dimension, and per-annotator-pair views;
- an adjudication item for every status mismatch or dimension score gap greater than one point.

Kappa is calculated only over pairs where both dimensions are assessed. It remains `null` when there are no scored pairs or expected score variance is zero. `agreement_ready=true` means every validation/test report has the required double annotation; it does not establish label correctness or annotator expertise.

The queue identifies disagreements but does not resolve them. A human adjudicator must review both evidence trails and deliver a separate `adjudication` round Bundle; adjudicated-label aggregation is a later protocol step.

## Compare System and Human Scores

Pass a previously generated Dataset Benchmark result to compare each non-provisional system score with the mean of at least two eligible human scores:

```bash
hy3-reproeval analyze-annotations \
  --manifest path/to/frozen_dataset.json \
  --bundle private_annotations/annotator-01.json \
  --bundle private_annotations/annotator-02.json \
  --benchmark-result .reproeval/dataset-benchmark.json \
  --output .reproeval/annotation-agreement.json
```

Human report scores use the public Rubric weights, minimum assessed-weight rule, and declared hard caps. The comparison reports coverage, Spearman correlation, MAE, and per-report values. Before analysis, ReproEval verifies the Dataset and Rubric fingerprints plus the complete group, split, report, and report-hash inventory. Correlation remains `null` for fewer than two matched reports or constant ranks.

## Public Fixture Boundary

[`examples/annotations/synthetic_annotation_bundle.json`](../examples/annotations/synthetic_annotation_bundle.json) is a schema and CLI test fixture only:

```bash
hy3-reproeval validate-annotations \
  --manifest examples/dataset/sample_dataset.json \
  --bundle examples/annotations/synthetic_annotation_bundle.json
```

Its source is `synthetic_protocol_fixture`, so it never counts as a human annotation, contributes no agreement observations, and cannot make the development-only public dataset benchmark-ready. Real agreement claims require frozen validation/test data, independent qualified annotators, and documented adjudication.
