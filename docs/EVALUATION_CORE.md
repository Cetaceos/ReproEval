# ReproEval Evaluation Core

## Scope

The evaluation core runs deterministic checks against an explicit case manifest, then optionally asks a constrained Hy3 Judge to assess two open-ended semantic dimensions. It does not infer a hidden reference answer from arbitrary documents.

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

## Hy3 Semantic Judge

Judge Prompt `reproeval-judge-1.0` receives the scenario, the two relevant Rubric anchors, and a line-numbered copy of the report serialized as untrusted JSON data. Online scoring fixes `reasoning_effort=high` and `temperature=0.0`. The system instruction explicitly excludes facts, citations, numerical values, units, completeness, uncertainty, and overall scoring from the Judge's authority.

The structured response must contain exactly:

- one 0-4 `reasoning_consistency` assessment with report-line evidence;
- one 0-4 `clarity_actionability` assessment with report-line evidence;
- `reasoning_gap` for a reasoning score below 4;
- `actionability_gap` or `verbosity_without_evidence` for a clarity/actionability score below 4;
- no semantic error code when a dimension receives 4.

Local validation rejects missing or duplicate dimensions, unrelated error codes, unknown fields, and line numbers outside the report. Hybrid aggregation fills only dimensions that remain `insufficient_evidence`; it never replaces a deterministic dimension, finding, or hard cap.

Online runs can save a `JudgeRecord`. The record binds the structured response to the prompt version, case ID, scenario, report SHA-256, Rubric SHA-256, model, provider, reconstructed request SHA-256, and canonical response SHA-256. Replay reconstructs and verifies this contract before aggregation, allowing the scoring path to run without credentials while preventing a record from being silently reused with changed inputs.

```bash
# Online Hy3 call and record creation
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --judge online \
  --judge-record judge-record.json \
  --output hybrid-evaluation.json

# Credential-free replay
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --judge replay \
  --judge-record judge-record.json \
  --output replayed-evaluation.json
```

Repeated blinded A/B comparison is implemented as a separate protocol so it cannot alter single-report findings or scores. See [PAIRWISE_COMPARISON.md](PAIRWISE_COMPARISON.md) for the shared-contract requirement, order alternation, fixed aggregation, stability metrics, and replay boundary.

## Current Limitations

- Claim support is checked on the line containing the registered literal marker.
- Numerical extraction uses the first decimal token after the registered literal label.
- Citation validity is relative to the manifest's source and locator registry; the registry itself must be prepared independently.
- Semantic scores remain model judgments rather than ground truth and require calibration against blinded human labels.
- The online client performs one bounded JSON repair, so an invalid second response fails instead of being loosely parsed.
- Replay proves input and structured-response consistency, not that the recorded response came from a trusted remote service.
- Deterministic scores are not yet calibrated against blinded human labels and must be treated as provisional engineering output.
