# Paper Reproduction Review

Use this workflow when the user wants to compare claims in a paper or research note with reproduced measurements,
training logs, configuration, or implementation evidence.

## Inputs

Collect the following without inventing missing values:

- one or more paper, supplement, or structured-note paths;
- one or more reproduction result paths for a full comparison;
- optional metric names, structured group filters, and grouping dimensions;
- an optional Python repository path for static reproducibility signals;
- an optional domain profile: use `isac_phy` only when requested, and otherwise keep `generic` or conservative
  `auto` detection.

## Full MCP sequence

1. If a repository is supplied, call `reproscope_audit_repository`. Keep its `repository_audit.json` artifact path.
2. Call `reproscope_extract_claims` with the paper paths and optional focus/profile. Keep the returned
   `extract_claims.json` path.
3. Call `reproscope_compare_results` with the same paper paths, the reproduction paths, any metric/group choices,
   and the exact claims artifact path. Keep `compare_results.json`.
4. Call `reproscope_score_paper` with the same source inputs and filters plus the exact claims, comparison, and
   optional repository-audit artifact paths. Keep `reliability_score.json`.
5. Call `reproscope_build_evidence_graph` with the three completed JSON artifact paths. Continue only when
   `graph_validated` is `true`; keep `evidence_graph.json`.
6. Call `reproscope_render_report` with the same three parent paths and the validated graph path.

Every parent argument must come from `artifacts[].relative_path` in the preceding MCP responses. A renderer error
is not permission to call internal Python functions or to claim the report was produced through MCP.

## Partial evidence

If reproduction results are absent, claim extraction and paper-only scoring may still be useful. State that no
reported-versus-reproduced comparison was performed. Do not fabricate a comparison artifact, evidence graph, or
full reproduction conclusion merely to finish the nominal sequence.

If a metric cannot be deterministically aligned, retain its unmatched or insufficient status. Never calculate a
replacement value from prose when the registered structured evidence is missing.

## Result summary

Report the reliability band and score only when present, followed by evidence and Rubric coverage, reproduced
metric deltas, claim-relation coverage, setting mismatches, major risks, warning codes, and recommended checks.
Describe the output as an evidence audit, not a finding of research misconduct.
