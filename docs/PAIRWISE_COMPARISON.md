# Blinded Pairwise Report Comparison

## Purpose

The pairwise evaluator tests whether ReproEval consistently distinguishes two reports written for the same task. It complements single-report scoring; it is not a substitute for human labels or a benchmark result by itself.

Both Case Manifests must have the same scenario and the same canonical evaluation contract after excluding only `case_id` and `report_path`. This prevents reports from being compared under different source registries, numerical expectations, required sections, uncertainty rules, or artifact requirements.

## Protocol

For every trial, ReproEval:

1. runs the deterministic evaluator independently on both reports;
2. presents the report texts as anonymous A/B line arrays without Case IDs or paths;
3. alternates which logical report appears as A, with the starting side derived from `comparison_id`;
4. asks Hy3 to score only `reasoning_consistency` and `clarity_actionability` from 0 to 4;
5. validates the strict JSON response and every cited report line locally;
6. maps A/B scores back to the logical left/right reports;
7. combines semantic scores with deterministic weighted contributions and applies each report's hard cap.

The default is three trials; the accepted range is 2-10. Trial IDs remain local metadata and are not inserted into model input, so repeated trials with the same presentation order have identical request hashes. Online Judge calls use Prompt `reproeval-pairwise-1.0`, `reasoning_effort=high`, and `temperature=0.0`.

## Aggregation

Deterministic dimensions contribute their original Rubric weights without renormalization. The two semantic dimensions contribute the remaining 25%. If the resulting assessed weight is below the public Rubric threshold, that report receives no combined score.

For each trial:

```text
raw contribution = sum(dimension_score / 4 * dimension_weight * 100)
normalized score = raw contribution / assessed_weight
final score = min(normalized score, deterministic hard cap when present)
```

The final preference compares the two mean scores. A difference of at most one point is a tie. Results include:

- mean, population standard deviation, minimum, and maximum score for each report;
- semantic dimension means;
- trial-level preference and final preference;
- preference flip rate relative to the final preference;
- quality bands observed across trials and whether the band changed;
- maximum observed score difference for the same report when shown as A versus B.

The last value is named `observed_position_delta_max`, not position bias. With three alternating trials, A/B presentation counts are unequal and trial variation can contribute to the difference. A causal position-bias experiment should use a balanced even number of trials and sufficient repeated samples.

## Replay Integrity

An online run can save a `PairwiseJudgeBundle`. The Bundle records both report hashes, the shared evaluation-contract hash, Rubric hash, model/provider, fixed inference parameters, presentation order, request hash, response hash, and structured response for every trial.

Replay reconstructs each blinded prompt and rejects:

- changed reports, Rubric, comparison ID, trial count, or evaluation contract;
- missing or duplicate trials;
- trials that do not contain both A/B presentation orders;
- mixed model/provider or inference settings;
- request or response hash mismatches;
- report-line evidence outside the presented document.

## Commands

Online run and Bundle creation:

```bash
hy3-reproeval compare-reports \
  --left-case path/to/left-case.json \
  --right-case path/to/right-case.json \
  --comparison-id experiment-pair-001 \
  --repeats 3 \
  --judge online \
  --judge-record pairwise-bundle.json \
  --output pairwise-result.json
```

Credential-free replay:

```bash
hy3-reproeval compare-reports \
  --left-case path/to/left-case.json \
  --right-case path/to/right-case.json \
  --comparison-id experiment-pair-001 \
  --repeats 3 \
  --judge replay \
  --judge-record pairwise-bundle.json \
  --output replayed-result.json
```

## Limitations

- Blindness removes local identifiers and paths but cannot remove identifying phrases already present in report content.
- Repeated deterministic-temperature calls can still vary because remote inference systems may be nondeterministic.
- The public example uses synthetic responses and demonstrates only the protocol and aggregation path.
- A preferred report is not automatically a correct report; deterministic checks are limited to facts registered in the Case Manifest.
- Ranking accuracy and model-human agreement require a separately labeled, group-isolated evaluation dataset.
