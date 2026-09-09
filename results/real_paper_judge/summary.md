# ReproEval Benchmark Review Bundle

## Experiment identity

- Dataset: `reproeval-real-paper-pilot` version `0.2.0`
- Dataset Freeze SHA-256: `90AB080294B1050FBBAB612EE93E6BC7C79AA4E02A13746E11E28A52C1A97D04`
- Rubric: `0.1.0` (`1B1F6F8A425C1B84AAE88EFDA8E21950F2CF603325414316AEA773A1CD68F40A`)
- Independent Judge runs: 3

## Benchmark runs

| Run | Pairwise accuracy | Complete-order accuracy | Macro Spearman | Error-label recall | Adversarial detection |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 100.00% | 100.00% | 1 | 100.00% | n/a |
| 2 | 100.00% | 100.00% | 1 | 100.00% | n/a |
| 3 | 100.00% | 100.00% | 1 | 100.00% | n/a |

## Repeated-run stability

- Fully scored reports: 18/18
- Mean report score standard deviation: 0.392837
- Maximum report score standard deviation: 3.53553
- Preregistered standard-deviation target: <= 5 (`met`)
- Quality-band flips: 0/18
- Ranking-eligibility flips: 0
- Evaluation-status flips: 0

## Dimension stability

| Dimension | Coverage | Mean report stddev | Maximum report stddev | Status flips |
| --- | ---: | ---: | ---: | ---: |
| `factual_accuracy` | 100.00% | 0 | 0 | 0 |
| `evidence_traceability` | 100.00% | 0 | 0 | 0 |
| `numerical_consistency` | 100.00% | 0 | 0 | 0 |
| `reasoning_consistency` | 100.00% | 0.104757 | 0.942809 | 0 |
| `uncertainty_handling` | 100.00% | 0 | 0 | 0 |
| `content_completeness` | 100.00% | 0 | 0 | 0 |
| `clarity_actionability` | 100.00% | 0 | 0 | 0 |

## Non-zero report variation

| Report | Tier | Mean score | Score stddev | Score range | Band flip |
| --- | --- | ---: | ---: | ---: | --- |
| `real-paper-04-lyceanem-low` | `low` | 32 | 3.53553 | 7.5 | no |
| `real-paper-06-cdcam-high` | `high` | 97.5 | 3.53553 | 7.5 | no |

## Boundaries

- Stability describes the supplied frozen runs only; it does not establish expert agreement or generalization.
- Synthetic labels and model stability are not substitutes for blinded expert annotation.
