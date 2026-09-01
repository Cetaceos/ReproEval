# P1 Transfer-Generalization Dataset

`evals/p1_transfer_dataset` is a deterministic synthetic Dataset for checking whether ReproEval's public
seven-dimension report-quality protocol generalizes from paper reproduction to conditional technology-transfer
reviews. It does not measure real deployment feasibility.

## Inventory

| Item | Count |
| --- | ---: |
| Independent source groups | 5 |
| Development / validation / test groups | 1 / 2 / 2 |
| High / medium / low reports | 5 / 5 / 5 |
| Total reports | 15 |
| Deterministic Mutation Manifests | 10 |

The five groups cover GPU-to-CPU edge deployment, federated learning over intermittent UAV links,
millimeter-wave to sub-6 GHz array migration, wideband-to-narrowband ISAC transfer, and cloud-to-embedded
semantic communication.

Each high-quality report states a conditional decision, cites both source-solution and target-context evidence,
preserves the registered target constraint, discloses missing target measurements, and gives a rejection-aware
validation step. Medium mutations weaken reasoning and actionability. Low mutations additionally corrupt one
target constraint and replace its target citation with an unregistered source.

## Reproducible Construction

```bash
hy3-reproeval build-p1-transfer-dataset --output evals/p1_transfer_dataset --check
hy3-reproeval validate-dataset --manifest evals/p1_transfer_dataset/dataset.json
```

The write command accepts only an absent or empty directory. `--check` rejects missing, additional, or changed
bytes. Mutation replay, source-group isolation, report hashes, Case Manifests, and expected deterministic errors
are validated by the shared Dataset Protocol.

## Experimental Boundary

The Dataset tests report-quality generalization under synthetic transfer contexts. It does not execute source
code, predict target performance, provide legal advice, prove compatibility, or create expert ground truth.
Semantic mutation labels still require Hy3 Judge or blinded human review before measured claims are made.
