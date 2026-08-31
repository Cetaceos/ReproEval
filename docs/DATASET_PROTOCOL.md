# ReproEval Dataset Protocol

ReproEval 0.19.0 and later define a versioned protocol for constructing auditable high-, medium-, low-, and adversarial-quality research reports. The protocol makes controlled degradation reproducible without treating a synthetic fixture as evidence of benchmark performance.

## Files

A dataset consists of one Dataset Manifest and the files it registers:

```text
dataset.json
case-high.json             evaluation contract + high report path
case-medium.json           same contract + medium report path
case-low.json              same contract + low report path
high.md
medium.md
low.md
mutation-medium.json       high -> medium literal operations
mutation-low.json          high -> low literal operations
judge-record.json          optional registered semantic replay evidence
```

Every registered path is relative to the Dataset Manifest directory and must remain inside it. Reports, source groups, mutation parents, and mutation outputs use uppercase SHA-256 fingerprints. Tracked text files use LF line endings through `.gitattributes`, because report hashes cover exact UTF-8 bytes.

## Dataset Manifest

The strict `1.0` schema records:

- dataset ID, version, description, and source groups;
- one group-level split: `development`, `validation`, or `test`;
- one scenario and one provenance record per group;
- report ID, tier, Case Manifest, report hash, label source, expected errors, and optional Mutation Manifest;
- an optional Judge Record path and SHA-256, which must be declared together;
- provenance kind, license signal, acquisition date, source-group fingerprint, and public description.

Each group must contain at least three reports, exactly one `high` report, and at least one `medium` and one `low` report. All reports in a group must use the same deterministic evaluation contract. The validator rejects duplicate report content, duplicate IDs, and reuse of one declared source-group fingerprint across groups or splits.

The source-group fingerprint is a registered provenance value. ReproEval detects duplicate declarations but cannot derive that value from external material absent from the repository; dataset maintainers remain responsible for its construction and review.

## Mutation Manifest

A strict `1.0` Mutation Manifest links one parent report to one output report and records:

- parent and output report IDs, paths, and SHA-256 fingerprints;
- ordered `replace_once`, `delete_once`, or `append_text` operations;
- dimensions and error codes expected to be affected by each operation.

Replacement and deletion targets must occur exactly once. Replay starts from the registered parent bytes, applies operations in order, and accepts the result only when its output hash matches. Validation also compares replayed bytes with the stored output report.

Use `--write` only to regenerate a registered output deliberately:

```bash
hy3-reproeval replay-mutation \
  --manifest examples/dataset/medium_mutation.json \
  --root examples/dataset \
  --write
```

The command does not create missing directories and never permits an absolute or escaping path.

## Error Closure

For errors that local Python can determine, declared labels must close exactly over failed validator findings: a missing expected error or an undeclared observed error invalidates the dataset. Current deterministic examples include fabricated citations, unsupported claims, and numerical errors.

Semantic labels such as `reasoning_gap`, `verbosity_without_evidence`, and `actionability_gap` are recorded for later Hy3 Judge or human experiments. Dataset validation does not claim to prove those labels. This boundary prevents synthetic mutation intent from being presented as measured model performance.

When a Judge Record is registered, validation reconstructs its versioned prompt and checks its Case, scenario, report, Rubric, request, response, evidence lines, and file hash. Batch ranking uses these records only in explicit replay mode; see [BENCHMARK_PROTOCOL.md](BENCHMARK_PROTOCOL.md).

## Validation

Validate the public fixture without an API key:

```bash
hy3-reproeval validate-dataset \
  --manifest examples/dataset/sample_dataset.json \
  --output dataset-validation.json
```

The result reports group, report, mutation, split, tier, scenario, deterministic-error, and human-review counts. It also warns when the dataset lacks validation/test splits, the planned 12 source groups, 8 adversarial reports, or human-reviewed labels.

The repository fixture contains one synthetic development group and three quality tiers. It verifies schema, hash, replay, isolation, and deterministic-error behavior only. Ranking accuracy, model-human agreement, stability, and adversarial detection require the larger group-isolated and human-reviewed dataset planned in the project proposal.
