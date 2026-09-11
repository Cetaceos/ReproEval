# Evaluation assets

`evals` contains checked-in inputs used to test and evaluate ReproEval. Generated API responses, private reviewer
records, and source-paper caches are deliberately excluded from version control.

| Directory | Purpose |
| --- | --- |
| `regression/` | Small deterministic fixtures and JSON Schemas used by tests and offline workflow checks. |
| `p0_dataset/` | Synthetic reproduction-readiness dataset with high, medium, low, and adversarial reports. |
| `p1_transfer_dataset/` | Synthetic conditional transfer dataset with registered Mutations. |
| `real_paper_pilot/` | Frozen dataset derived from six open-access JOSS source groups. |

The versioned dataset directories are generated deterministically and verified in CI. See
[`docs/DATASET_PROTOCOL.md`](../docs/DATASET_PROTOCOL.md) for the common contract and [`results`](../results/README.md)
for the selected public outputs.
