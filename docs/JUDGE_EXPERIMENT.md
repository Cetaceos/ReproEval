# Frozen Repeated-Judge Experiment

`run-judge-experiment` composes the existing Dataset Freeze, resumable Judge batch, replay Benchmark,
stability analysis, and review export protocols into one fail-closed workflow. It does not change the public
Rubric or any score calculation.

## Run

Load the private `HY3_*` environment variables in the parent process, then use an absent or empty output
directory:

```bash
hy3-reproeval run-judge-experiment \
  --manifest evals/p1_transfer_dataset/dataset.json \
  --output-dir .reproeval/p1-transfer-experiment \
  --runs 3
```

The command creates:

```text
judge_experiment.json
dataset_freeze.json
judge-run-01/judge_record_index.json
judge-run-02/judge_record_index.json
judge-run-03/judge_record_index.json
benchmark-run-01.json
benchmark-run-02.json
benchmark-run-03.json
benchmark_stability.json
review/
```

Each Judge run has a distinct `run_id`. All runs, Benchmarks, Stability output, and review files bind to the
same Dataset Freeze. The experiment manifest records relative paths and SHA-256 index identities without
recording credentials.

## Resume

After reviewing an interrupted experiment, rerun the same command with `--resume`. The run count, Dataset,
Freeze, model, provider, completed indexes, and completed Benchmarks must still match. Verified records are
reused; missing records and later runs continue. A completed experiment is fully revalidated without making
another API call.

The output root uses `.judge-experiment.lock`. If a process is forcibly terminated and leaves the lock, first
confirm that no experiment still owns the directory before removing it and resuming.

## Claim Boundary

The workflow reduces orchestration error; it does not turn synthetic tiers into human ground truth. Repeated
Hy3 scores describe only the frozen Dataset, Rubric, provider, model, and executions represented by the output.
Expert agreement, real transfer feasibility, deployment performance, and legal conclusions require separate
evidence.
