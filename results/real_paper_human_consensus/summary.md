# ReproEval De-identified Human Consensus Results

## Experiment identity

- Dataset: `reproeval-real-paper-pilot` version `0.2.0`
- Dataset Freeze SHA-256: `90AB080294B1050FBBAB612EE93E6BC7C79AA4E02A13746E11E28A52C1A97D04`
- Rubric: `0.1.0` (`1B1F6F8A425C1B84AAE88EFDA8E21950F2CF603325414316AEA773A1CD68F40A`)
- Consensus reports: 12/12
- Resolved adjudication items: 4/4

## Human agreement

- Exact dimension-score agreement: 85.7143%
- Within-one-point agreement: 100.0000%
- Quadratic-weighted Cohen's Kappa: 0.964225
- Mean absolute dimension-score difference: 0.142857

## Final consensus by registered quality tier

| Tier | Reports | Mean human score |
| --- | ---: | ---: |
| `high` | 4 | 100 |
| `medium` | 4 | 55 |
| `low` | 4 | 21.5 |

## System-human comparison

| Run | Coverage | Spearman | MAE |
| ---: | ---: | ---: | ---: |
| 1 | 100.0000% | 0.988483 | 15.791667 |
| 2 | 100.0000% | 1 | 15.166667 |
| 3 | 100.0000% | 0.988483 | 14.541667 |

## Calibration by registered quality tier

Positive signed error means that the system score is higher than the final human consensus.

| Run | Tier | Mean human | Mean system | Mean signed error | MAE |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | `high` | 100 | 98.125 | -1.875 | 1.875 |
| 1 | `medium` | 55 | 87.5 | 32.5 | 32.5 |
| 1 | `low` | 21.5 | 34.5 | 13 | 13 |
| 2 | `high` | 100 | 100 | 0 | 0 |
| 2 | `medium` | 55 | 87.5 | 32.5 | 32.5 |
| 2 | `low` | 21.5 | 34.5 | 13 | 13 |
| 3 | `high` | 100 | 100 | 0 | 0 |
| 3 | `medium` | 55 | 87.5 | 32.5 | 32.5 |
| 3 | `low` | 21.5 | 32.625 | 11.125 | 11.125 |

## Boundaries

- The source papers are real, but the tiered reports are curator drafts and registered Mutations.
- The Pilot evaluates reproducibility readiness; it did not execute third-party software.
- Reviewer identity and expertise are self-attested, not externally certified.
- This bundle intentionally excludes reviewer IDs, Bundle IDs, rationales, private paths, and raw model responses.
- Strong rank correlation does not establish score calibration or scientific correctness.
