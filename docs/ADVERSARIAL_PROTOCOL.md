# ReproEval Adversarial Evaluation Protocol

ReproEval 0.24.0 defines a versioned contract for testing whether the evaluator detects deliberately misleading report transformations. The contract records attack intent before evaluation; it does not treat synthetic intent as proof that a model detected an attack.

## Attack Taxonomy

Each attack instance has a globally unique ID and one of seven types:

| Type | Intended manipulation |
| --- | --- |
| `length_inflation` | Add volume without adding relevant evidence |
| `terminology_stuffing` | Add technical terms that do not support the conclusion |
| `conclusion_repetition` | Repeat a conclusion to simulate confidence or support |
| `fabricated_authority` | Cite a nonexistent or mismatched authoritative source |
| `calculation_corruption` | Insert an incorrect value, unit, or derived result |
| `limitation_suppression` | Remove a material limitation or uncertainty statement |
| `unsupported_overconfidence` | Replace calibrated language with an unsupported strong conclusion |

This taxonomy is an evaluation inventory, not a claim that every attack is detectable by local Python. Semantic attacks require registered Hy3 Judge records or qualified human annotations for measured conclusions.

## Dataset Contract

Every report with `quality_tier=adversarial` must define an `adversarial_spec`:

```json
{
  "schema_version": "1.0",
  "attacks": [
    {
      "attack_id": "group-001-fabricated-authority-01",
      "attack_type": "fabricated_authority",
      "target_dimensions": ["factual_accuracy", "evidence_traceability"],
      "expected_error_codes": ["fabricated_citation", "unsupported_claim"],
      "description": "Replace a registered citation with an invented authority marker."
    }
  ]
}
```

Attack IDs must be globally unique. Attack errors must be a subset of the report's expected errors. A synthetic adversarial report must have a Mutation Manifest, and its attack dimensions must be covered by the registered Mutation operations. Reference revisions cannot be labeled adversarial.

## Detection Semantics

An attack instance is detected only when every error registered for that instance appears as a failed evaluator finding. Partial matches are retained for diagnosis but do not count as complete attack detection. A report is fully detected only when all its attack instances are detected.

The Benchmark result reports:

- adversarial report count and fully detected report count;
- attack instance count and completely detected attack count;
- attack detection rate and false-acceptance rate;
- expected and detected attack-error counts plus label recall;
- the same attack metrics grouped by attack type.

Metrics are aggregated within source groups and then exposed for each split and the complete Dataset. Adversarial reports never enter the `high > medium > low` ranking order, and attack outcomes do not alter report scores.

## Claim Boundary

Undefined metrics remain `null`. The public `examples/dataset/sample_adversarial_dataset.json` fixture validates schema, mutation, and deterministic metric behavior only. Reporting adversarial robustness requires frozen validation/test attacks, real evaluator runs, independent review of attack labels, and disclosure of failed examples. The planned target of at least eight adversarial reports and an 80% detection rate remains a target until those conditions are met.
