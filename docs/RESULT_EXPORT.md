# Benchmark Result Export

ReproEval 0.29.0 converts repeated Dataset Benchmark and Stability JSON artifacts into a deterministic review
bundle. The exporter does not call Hy3 and does not include Judge response bodies.

## Command

Supply every independent Benchmark represented by the Stability result:

```bash
hy3-reproeval export-benchmark-results \
  --benchmark .reproeval/benchmark-run-1.json \
  --benchmark .reproeval/benchmark-run-2.json \
  --benchmark .reproeval/benchmark-run-3.json \
  --stability .reproeval/benchmark-stability.json \
  --output-dir .reproeval/benchmark-review
```

The output directory must be absent or empty. Before writing, the exporter recomputes Stability from the
Benchmark inputs and compares every field except the producing engine version. Dataset, Freeze, Rubric,
report inventory, Stability and Benchmark hashes, Judge index hashes, and Judge run IDs therefore remain
fail-closed.

## Files

| File | Contents |
| --- | --- |
| `summary.md` | Experiment identity, per-run metrics, stability metrics, volatile reports, and boundaries |
| `benchmark_runs.csv` | Ranking, error-label, and adversarial metrics for each independent run |
| `report_stability.csv` | Report-level mean, dispersion, coverage, and flip indicators |
| `dimension_stability.csv` | Rubric-dimension coverage, dispersion, and status flips |
| `export_manifest.json` | Input lineage plus byte size and SHA-256 for every exported result |

The bundle summarizes the supplied model runs. It does not create human labels, prove expert agreement, or
establish generalization. Review source-material policy before publishing any associated private artifacts.
