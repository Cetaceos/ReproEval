# ReproEval Benchmark Review Bundle

## Experiment identity

- Dataset: `reproeval-p1-synthetic-transfer` version `0.1.0`
- Dataset Freeze SHA-256: `91B7DA90654FBFFD15C51F6197A74F782825F8DB55164E684B63EB0782CA2685`
- Rubric: `0.1.0` (`1B1F6F8A425C1B84AAE88EFDA8E21950F2CF603325414316AEA773A1CD68F40A`)
- Independent Judge runs: 3

## Benchmark runs

| Run | Pairwise accuracy | Complete-order accuracy | Macro Spearman | Error-label recall | Adversarial detection |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 100.00% | 100.00% | 1 | 100.00% | n/a |
| 2 | 100.00% | 100.00% | 1 | 100.00% | n/a |
| 3 | 100.00% | 100.00% | 1 | 100.00% | n/a |

## Repeated-run stability

- Fully scored reports: 15/15
- Mean report score standard deviation: 1.41421
- Maximum report score standard deviation: 3.53553
- Preregistered standard-deviation target: <= 5 (`met`)
- Quality-band flips: 0/15
- Ranking-eligibility flips: 0
- Evaluation-status flips: 0

## Dimension stability

| Dimension | Coverage | Mean report stddev | Maximum report stddev | Status flips |
| --- | ---: | ---: | ---: | ---: |
| `factual_accuracy` | 100.00% | 0 | 0 | 0 |
| `evidence_traceability` | 100.00% | 0 | 0 | 0 |
| `numerical_consistency` | 100.00% | 0 | 0 | 0 |
| `reasoning_consistency` | 100.00% | 0.377124 | 0.942809 | 0 |
| `uncertainty_handling` | 100.00% | 0 | 0 | 0 |
| `content_completeness` | 100.00% | 0 | 0 | 0 |
| `clarity_actionability` | 100.00% | 0 | 0 | 0 |

## Non-zero report variation

| Report | Tier | Mean score | Score stddev | Score range | Band flip |
| --- | --- | ---: | ---: | ---: | --- |
| `p1-transfer-01-gpu-to-cpu-edge-high` | `high` | 95 | 3.53553 | 7.5 | no |
| `p1-transfer-02-federated-uav-link-high` | `high` | 95 | 3.53553 | 7.5 | no |
| `p1-transfer-02-federated-uav-link-low` | `low` | 32 | 3.53553 | 7.5 | no |
| `p1-transfer-04-isac-bandwidth-transfer-high` | `high` | 95 | 3.53553 | 7.5 | no |
| `p1-transfer-05-semantic-codec-embedded-high` | `high` | 95 | 3.53553 | 7.5 | no |
| `p1-transfer-05-semantic-codec-embedded-low` | `low` | 32 | 3.53553 | 7.5 | no |

## Boundaries

- Stability describes the supplied frozen runs only; it does not establish expert agreement or generalization.
- Synthetic labels and model stability are not substitutes for blinded expert annotation.
