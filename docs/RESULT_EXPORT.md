# Benchmark Result Export

ReproEval 0.29.0 converts repeated Dataset Benchmark and Stability JSON artifacts into a deterministic review
bundle. ReproEval 0.33.0 adds standalone verification for published bundles, and 0.38.0 adds a de-identified final
human-consensus export. None of these operations calls Hy3 or includes Judge response bodies.

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

Verify a copied or published bundle without its private Benchmark inputs:

```bash
hy3-reproeval verify-results-export --bundle results/p1_transfer_judge
```

Verification requires the exact closed five-file inventory, rejects symbolic links and extra files, validates the
manifest schema, and checks every declared byte size and SHA-256 fingerprint. It proves public-bundle integrity,
not that the private inputs were scientifically valid; the initial exporter performs the stronger recomputation
before publication.

The bundle summarizes the supplied model runs. It does not create human labels, prove expert agreement, or
establish generalization. Review source-material policy before publishing any associated private artifacts.

## De-identified human consensus export

After independent annotation and any required adjudication have produced `consensus_ready=true`, export the final
consensus together with every bound Judge Benchmark:

```bash
hy3-reproeval export-human-consensus-results \
  --consensus private_annotations/annotation-consensus.json \
  --benchmark .reproeval/benchmark-run-1.json \
  --benchmark .reproeval/benchmark-run-2.json \
  --benchmark .reproeval/benchmark-run-3.json \
  --output-dir results/human_consensus
```

The exporter requires matching Dataset, Freeze, Rubric, report hashes, unique Judge runs, and complete non-provisional
system scores. It writes report-level consensus, all seven dimension results, per-run system-human comparisons,
aggregate run metrics, a summary, and a closed manifest. Reviewer IDs, Annotation Bundle IDs, rationales, private
paths, and raw model responses are deliberately omitted.

```bash
hy3-reproeval verify-human-consensus-results --bundle results/human_consensus
```

Standalone verification proves the integrity and closed inventory of the published bundle. The manifest records the
private consensus and Benchmark input hashes, but publication does not authenticate reviewer identity or establish
scientific ground truth.
