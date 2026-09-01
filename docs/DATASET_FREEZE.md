# ReproEval Dataset Freeze Protocol

ReproEval 0.25.0 defines a tamper-evident Dataset Freeze for locking experiment inputs before online Judge generation, blinded annotation, or held-out evaluation. ReproEval 0.26.0 carries its fingerprint through downstream machine and human evaluation artifacts. A Freeze is a reproducibility artifact, not a performance result.

## Bound Inputs

`freeze-dataset` first executes the complete Dataset validator and then inventories every registered file reachable from the Dataset Manifest:

| Role | Bound content |
| --- | --- |
| `dataset_manifest` | Dataset identity, groups, splits, provenance, tiers, and expected labels |
| `evaluation_case` | Deterministic evaluation contracts |
| `report` | Exact report bytes |
| `evidence_artifact` | Files registered by Case Manifest artifact expectations |
| `mutation_manifest` | Controlled degradation operations and parent/output hashes |
| `judge_record` | Optional Judge Records registered directly by report entries |

The Freeze also binds the public Rubric version and canonical SHA-256. External Judge Record indexes, Annotation Bundles, Benchmark results, and Consensus results are downstream experimental outputs and are not Dataset inputs.

Every file entry contains a Dataset-root-relative path, one or more roles, byte size, and uppercase SHA-256. Paths are unique, canonically ordered, and confined to the Dataset root. Shared evidence files appear once with their combined roles.

## Create And Verify

Create the output directory and Freeze artifact:

```bash
mkdir .reproeval
hy3-reproeval freeze-dataset \
  --manifest path/to/dataset.json \
  --output .reproeval/dataset-freeze.json
```

The artifact contains `freeze_sha256`, calculated over its canonical JSON payload excluding that field. Record this fingerprint in experiment notes or a reviewed commit. Recheck the stored artifact before each experimental run:

```bash
hy3-reproeval verify-dataset-freeze \
  --freeze .reproeval/dataset-freeze.json \
  --manifest path/to/dataset.json \
  --output .reproeval/dataset-freeze-verification.json
```

Verification rejects an invalid self-digest, changed Dataset or Rubric identity, altered files, changed inventory, or changed readiness state. It reruns Dataset validation, so a registered report, Mutation, artifact, or Judge Record that no longer satisfies its own contract fails before comparison.

## Bind Downstream Outputs

For controlled experiments, pass the same reviewed Freeze to every downstream command:

```bash
hy3-reproeval generate-judge-records \
  --manifest path/to/dataset.json \
  --dataset-freeze .reproeval/dataset-freeze.json \
  --output-dir .reproeval/judge-run

hy3-reproeval benchmark-dataset \
  --manifest path/to/dataset.json \
  --dataset-freeze .reproeval/dataset-freeze.json \
  --mode replay \
  --judge-index .reproeval/judge-run/judge_record_index.json \
  --output .reproeval/dataset-benchmark.json
```

Annotation Bundles collected for the same run must include the resulting uppercase `dataset_freeze_sha256`. Pass `--dataset-freeze` to `validate-annotations`, `analyze-annotations`, and `finalize-annotations`. ReproEval then rejects missing, mixed, or mismatched fingerprints, including a system-human comparison whose Benchmark result belongs to another Freeze lineage. A Freeze-bound Judge index or Annotation Bundle cannot be consumed without explicitly supplying and re-verifying its Freeze.

Omitting `--dataset-freeze` keeps old development fixtures readable. This compatibility mode verifies Dataset and Rubric identity but is not the recommended contract for reviewed validation/test experiments.

## P0 Dataset Gate

The readiness block evaluates only the Dataset construction targets declared in the project proposal:

- at least 12 source groups;
- at least one validation group;
- at least one test group;
- at least 8 adversarial reports.

Use `--require-p0-ready` to fail instead of writing a below-target Freeze:

```bash
hy3-reproeval freeze-dataset \
  --manifest path/to/frozen_dataset.json \
  --output .reproeval/dataset-freeze.json \
  --require-p0-ready
```

The normal mode still creates a Freeze for development fixtures and lists every unmet requirement. This supports protocol testing without presenting a one-group sample as the final Dataset.

## Claim Boundary

`meets_p0_dataset_targets=true` means only that the declared Dataset size, split, and adversarial inventory requirements are present and that registered inputs validated at freeze time. It does not establish:

- completeness or quality of Hy3 Judge outputs;
- two-person blinded annotation coverage;
- annotator expertise or independence;
- agreement, adjudication, or consensus readiness;
- held-out ranking accuracy, system-human correlation, stability, or adversarial robustness.

Those claims require their respective Judge Record, Annotation, Benchmark, Agreement, and Consensus protocols. A Freeze self-digest is not a digital signature; its value must be retained in a trusted experiment log or reviewed Git history to detect coordinated replacement of both the Dataset and Freeze artifact.
