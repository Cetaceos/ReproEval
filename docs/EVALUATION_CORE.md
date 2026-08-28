# ReproEval Deterministic Evaluation Core

## Scope

The deterministic core evaluates claims that can be checked against an explicit case manifest. It does not infer a hidden reference answer from arbitrary documents and does not perform semantic judging.

Implemented checks:

- source ID and locator registration for `[source_id@locator]` citations;
- required claim presence and same-line source support;
- decimal value and absolute-tolerance checks after a registered literal label;
- expected unit presence on the registered numeric line;
- exact normalized Markdown heading presence;
- registered uncertainty or limitation phrase presence;
- SHA-256 verification for registered local artifacts;
- path confinement, UTF-8 decoding, and input-size limits.

## Case Manifest

The JSON manifest uses Schema `1.0` and resolves every referenced path relative to the manifest directory. Absolute paths and paths escaping that directory are rejected.

```json
{
  "schema_version": "1.0",
  "case_id": "example-v1",
  "scenario": "reproduction",
  "report_path": "report.md",
  "sources": [
    {"source_id": "paper", "locators": ["L10-L12"]}
  ],
  "claims": [
    {
      "claim_id": "main_result",
      "marker": "reproduced Accuracy",
      "required_source_ids": ["paper"]
    }
  ],
  "numeric_expectations": [
    {
      "fact_id": "accuracy",
      "label": "Accuracy is",
      "expected": "0.876",
      "absolute_tolerance": "0.0001",
      "critical": true
    }
  ],
  "required_sections": [
    {"section_id": "summary", "heading": "Executive summary"}
  ],
  "uncertainty": {
    "required": true,
    "accepted_phrases": ["insufficient evidence"]
  },
  "artifacts": []
}
```

## Scoring

The public Rubric is stored at `src/hy3_reproeval/data/rubric.yaml`. Each of seven dimensions has a weight and 0, 2, and 4 anchors. Deterministic checks currently assess factual accuracy, evidence traceability, numerical consistency, uncertainty handling, and content completeness.

Every result records `evaluation_mode=deterministic_only`, the report SHA-256, the exact Case Manifest SHA-256, the canonical Rubric SHA-256, the engine version, and the Rubric version. These fields distinguish content changes from version-label reuse and support offline result replay.

For each assessed dimension, the deterministic pass ratio maps to a 0-4 score. A critical failure forces its dimension to 0. The weighted score is normalized over assessed dimensions only, and the result records `assessed_weight` so partial coverage cannot be mistaken for full evaluation.

- assessed weight below `0.50`: no overall score or quality band;
- any unassessed dimension: `provisional=true`;
- fabricated citations and artifact lineage failures: overall score capped at 40;
- critical numerical errors: capped at 50;
- unsupported claims and citation mismatches: capped at 55;
- missing required uncertainty disclosure: capped at 60.

Hard caps are applied after weighted aggregation, so fluent writing cannot compensate for deterministic critical errors.

## Current Limitations

- Claim support is checked on the line containing the registered literal marker.
- Numerical extraction uses the first decimal token after the registered literal label.
- Citation validity is relative to the manifest's source and locator registry; the registry itself must be prepared independently.
- Reasoning consistency and clarity/actionability remain `insufficient_evidence` until the Hy3 Judge layer is added.
- Deterministic scores are not yet calibrated against blinded human labels and must be treated as provisional engineering output.
