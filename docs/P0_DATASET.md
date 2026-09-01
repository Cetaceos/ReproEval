# P0 Synthetic Dataset Candidate

`evals/p0_dataset` is ReproEval's deterministic P0 benchmark candidate for testing the report-evaluation
protocol before expert annotation. It contains repository-authored synthetic material only; it is not a corpus
of real papers, human ground truth, or evidence of Hy3 performance.

## Inventory

| Item | Count |
| --- | ---: |
| Independent source groups | 12 |
| Development / validation / test groups | 4 / 4 / 4 |
| High / medium / low reports | 12 / 12 / 12 |
| Adversarial reports | 8 |
| Total reports | 44 |
| Deterministic Mutation Manifests | 32 |

Every source group contains one evidence packet and high, medium, and low reports under one evaluation
contract. Medium and low variants are generated from the high-quality parent through registered literal
mutations. Eight groups add adversarial variants. The attack inventory covers length inflation, terminology
stuffing, conclusion repetition, fabricated authority, calculation corruption, limitation suppression, and
unsupported overconfidence.

## Reproducible Construction

Generate the complete Dataset into an absent or empty directory:

```bash
hy3-reproeval build-p0-dataset --output evals/p0_dataset
```

Verify that a checked-in copy has the exact canonical file inventory and bytes:

```bash
hy3-reproeval build-p0-dataset --output evals/p0_dataset --check
```

The write command refuses a non-empty output directory. The check command rejects missing, additional, or
modified files. This protects the generated reports, Cases, Mutations, hashes, labels, and Dataset Manifest
from silent drift.

## Protocol Validation

The following commands require no API key:

```bash
hy3-reproeval validate-dataset --manifest evals/p0_dataset/dataset.json

mkdir .reproeval
hy3-reproeval freeze-dataset \
  --manifest evals/p0_dataset/dataset.json \
  --output .reproeval/p0-dataset-freeze.json \
  --require-p0-ready
```

`--require-p0-ready` verifies the declared structural targets: 12 source groups, validation and test coverage,
and at least 8 adversarial reports. The Freeze also binds all registered inputs and the public Rubric by
SHA-256.

## Experimental Boundary

The tier labels and adversarial expectations are generated protocol hypotheses. Deterministic validators can
confirm citation, number, artifact, structure, and mutation invariants, but semantic labels still require Hy3
Judge and blinded human review. The Dataset therefore supports pipeline development and preregistration; it
must not be reported as a held-out benchmark result until expert provenance, annotation agreement, consensus,
and frozen online experiments are complete.
