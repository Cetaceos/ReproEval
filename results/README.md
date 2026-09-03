# Published Evaluation Results

This directory contains review artifacts exported from completed ReproEval experiments. Published bundles include
aggregate Markdown/CSV results and a SHA-256 manifest only. API credentials, source materials not already tracked,
and raw Hy3 request or response bodies remain outside version control.

Verify a bundle after installation:

```bash
hy3-reproeval verify-results-export --bundle results/p1_transfer_judge
```

The manifest proves byte integrity and records the frozen experiment lineage. It does not establish label quality,
expert agreement, real-world feasibility, or model generalization.
