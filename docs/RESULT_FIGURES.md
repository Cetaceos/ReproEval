# Result Figure Protocol

ReproEval 0.35.0 can render deterministic SVG figures from a verified public Benchmark result bundle. The
figures are presentation artifacts derived only from aggregate CSV files. They do not read Judge response bodies,
call Hy3, or create new evaluation evidence.

## Render

```bash
hy3-reproeval render-results-figures \
  --bundle results/p1_transfer_judge \
  --output-dir results/p1_transfer_judge_figures
```

The command first runs the complete `verify-results-export` contract. It then validates the canonical columns,
identifiers, tiers, numeric ranges, coverage values, counts, and Boolean fields used by the figures. The output
directory must be absent or empty.

The closed figure bundle contains:

- `score_by_tier.svg`: mean total score for high-, medium-, and low-tier reports;
- `dimension_stability.svg`: mean and maximum report-score standard deviation for each Rubric dimension;
- `figure_manifest.json`: Dataset identity, engine version, source result-manifest hash, and figure byte hashes.

SVG output is self-contained and does not load scripts, fonts, images, styles, or other network resources.

## Verify

```bash
hy3-reproeval verify-results-figures \
  --figures results/p1_transfer_judge_figures \
  --source-bundle results/p1_transfer_judge
```

The verifier rejects changed bytes, extra or missing files, symbolic links, malformed manifests, Dataset identity
mismatches, and a source result bundle whose manifest SHA-256 differs from the value bound into the figure
manifest. Omitting `--source-bundle` verifies the closed figure inventory but not the current source binding.

## Claim Boundary

Deterministic rendering makes a published result easier to inspect; it does not improve discrimination,
stability, human agreement, adversarial robustness, or real-world generalization. Those claims remain governed by
the source experiment and its documented limitations.
