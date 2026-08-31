# Human Annotation Bundle Protocol

ReproEval 0.21.0 defines a strict, de-identified format for collecting report-quality judgments against the same seven-dimension public Rubric used by the evaluator. This release validates annotation inputs and coverage; agreement, adjudication, and system-human metrics are not yet computed.

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

## Public Fixture Boundary

[`examples/annotations/synthetic_annotation_bundle.json`](../examples/annotations/synthetic_annotation_bundle.json) is a schema and CLI test fixture only:

```bash
hy3-reproeval validate-annotations \
  --manifest examples/dataset/sample_dataset.json \
  --bundle examples/annotations/synthetic_annotation_bundle.json
```

Its source is `synthetic_protocol_fixture`, so it never counts as a human annotation or makes the development-only public dataset benchmark-ready. Real agreement claims require frozen validation/test data, independent qualified annotators, documented adjudication, and analysis code added in a later release.
