# Resumable Hy3 Judge Runs

ReproEval 0.21.0 can generate one structured Hy3 Judge Record for every report in a validated Dataset Manifest. The run is written incrementally so an interrupted API session can resume without repeating verified requests.

## Generate Records

Load the existing `HY3_*` variables into the parent shell. Create a private output directory before starting; `.reproeval/` is ignored by Git by default.

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force .reproeval/judge-run
hy3-reproeval generate-judge-records `
  --manifest examples/dataset/sample_dataset.json `
  --output-dir .reproeval/judge-run
```

Linux / macOS:

```bash
mkdir -p .reproeval/judge-run
hy3-reproeval generate-judge-records \
  --manifest examples/dataset/sample_dataset.json \
  --output-dir .reproeval/judge-run
```

The command never creates the output directory, never writes an API key, and never edits the Dataset Manifest. It writes one UTF-8 LF JSON record per report and a `judge_record_index.json` bound to the current Dataset, public Rubric, model, and provider.

## Resume Safely

If a request fails, the index remains `complete=false` and lists only records already written and verified. Review the directory, then rerun the same command with `--resume`:

```bash
hy3-reproeval generate-judge-records \
  --manifest examples/dataset/sample_dataset.json \
  --output-dir .reproeval/judge-run \
  --resume
```

Resume mode validates each existing record's file hash, request and response fingerprints, report, Case, Rubric, model, and provider before reuse. A mismatch fails closed. Running without `--resume` refuses an output directory that already contains target records or an index.

## Replay the Batch

Only a complete index can enter replay benchmarking:

```bash
hy3-reproeval benchmark-dataset \
  --manifest examples/dataset/sample_dataset.json \
  --mode replay \
  --judge-index .reproeval/judge-run/judge_record_index.json \
  --output .reproeval/dataset-benchmark.json
```

The external index is an alternative to registering individual records in the Dataset Manifest. It does not create human labels, and its metrics describe only the bound model run on that dataset version. Review model outputs and source-material policy before deliberately publishing records.
