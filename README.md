# Hy3 ReproEval

[中文说明](README_CN.md)

Hy3 ReproEval is an evidence-grounded Hy3 application and evaluation framework for open-ended research reports. Its primary scenario is research reproducibility review; technology-transfer assessment is retained as a cross-scenario generalization case.

This is a personal project developed for the 2026 Tencent Rhino-Bird open-source practical program. It is not an official Tencent product.

## Current Status

The first migration milestone is implemented. The repository now contains the validated ReproScope application layer from [Tencent-Hunyuan/Hy3 PR #187](https://github.com/Tencent-Hunyuan/Hy3/pull/187), including:

- 10 stdio MCP tools for reproducibility review, transfer assessment, evidence graphs, reports, and read-only repository audits;
- deterministic statistics, schema validation, source hashes, artifact lineage, and fail-closed evidence checks;
- synthetic examples, offline evaluation suites, live-validation gates, and 269 migrated tests;
- compatibility with existing `hy3_reproscope_mcp` module and `hy3-reproscope-mcp` command names.

The versioned seven-dimension rubric, deterministic validators, and constrained Hy3 semantic Judge are implemented. The Judge assesses only reasoning consistency and clarity/actionability; it cannot replace local citation, numerical, artifact, or hard-cap decisions. Blinded report comparison, human annotation, and benchmark analysis remain in development and are described in [the project proposal](docs/PROJECT_PROPOSAL_CN.md).

## Architecture

```text
research sources + reproduction results
                  |
                  v
       ReproScope application layer
   Hy3 semantic extraction + local checks
                  |
                  v
      traceable reports and artifacts
                  |
                  v
       ReproEval evaluation layer
 validators + Hy3 rubric judge + human labels
```

Hy3 handles semantic extraction and evidence reasoning. Local Python recalculates numerical results, validates schemas and citations, enforces artifact lineage, and applies deterministic aggregation rules. Model output cannot overwrite locally recomputed facts.

## Quick Start

Requirements: Python 3.11 or newer and a Hy3-compatible API endpoint.

```bash
git clone https://github.com/Cetaceos/ReproEval.git
cd ReproEval
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Linux / macOS:

```bash
./.venv/bin/python -m pip install -e .
```

Load the variables in `.env.example` into the parent shell, or provide them through your MCP client. The package does not auto-load `.env` files. Never commit a real API key.

```text
HY3_API_PROVIDER=tokenhub
HY3_BASE_URL=https://tokenhub.tencentmaas.com/v1
HY3_API_KEY=replace-with-your-key
HY3_MODEL=hy3-preview
REPROSCOPE_ALLOWED_ROOTS=.
REPROSCOPE_WORKSPACE=.reproeval/reproscope
```

Start the MCP server over stdio:

```bash
hy3-reproeval-mcp
```

The original command remains available for existing clients:

```bash
hy3-reproscope-mcp
```

Use [.mcp.json](.mcp.json) as the project-level configuration template. Replace placeholder paths and inject secrets through private client configuration.

## Report Evaluation

Run the public sample without an API key:

```bash
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --output evaluation.json
```

The case manifest registers source locators, required claims and sections, numerical expectations, uncertainty phrases, and artifact hashes. The evaluator returns dimension scores, evidence locations, error codes, assessed weight, hard caps, manifest and Rubric fingerprints, and a machine-readable quality result.

Replay the public synthetic Judge record without an API key:

```bash
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --judge replay \
  --judge-record examples/evaluation/sample_judge_record.json \
  --output hybrid-evaluation.json
```

Run the semantic Judge online and save a reusable record:

```bash
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --judge online \
  --judge-record judge-record.json \
  --output hybrid-evaluation.json
```

The online mode reads the existing `HY3_*` environment variables. A replay record is accepted only when its prompt version, case, scenario, report, Rubric, request, and structured response fingerprints match. Dimensions without deterministic or semantic evidence remain `insufficient_evidence`, and an overall score is withheld below 50% assessed weight. See [EVALUATION_CORE.md](docs/EVALUATION_CORE.md) for the scoring boundary and limitations.

## Migrated MCP Tools

| Tool | Purpose |
| --- | --- |
| `reproscope_extract_claims` | Extract experimental claims and optional domain evidence |
| `reproscope_compare_results` | Align metrics and recompute reproduction statistics |
| `reproscope_score_paper` | Apply the six-dimension evidence sufficiency rubric |
| `reproscope_build_evidence_graph` | Build a traceable paper evidence graph |
| `reproscope_render_report` | Render a reproducibility review report |
| `reproscope_extract_solution_profile` | Extract a structured technology solution profile |
| `reproscope_assess_transfer` | Assess transfer conditions, risks, and evidence gaps |
| `reproscope_build_transfer_graph` | Build a transfer evidence graph |
| `reproscope_render_transfer_report` | Render a transfer decision report |
| `reproscope_audit_repository` | Statically audit Python repository reproducibility signals |

## Development

Install the locked development environment and run the deterministic checks:

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -e . --no-deps
python -m pytest
python -m ruff check src tests scripts
python scripts/run_offline_eval.py
python scripts/run_transfer_offline_eval.py
```

The live validation scripts require an explicitly supplied Hy3 API key and apply output safety gates before retaining artifacts.

## Repository Layout

```text
src/hy3_reproeval/          ReproEval public package and CLI
src/hy3_reproscope_mcp/     migrated application and MCP compatibility layer
tests/                      unit, integration, stdio, security, and artifact tests
examples/                   public synthetic inputs and MCP client examples
evals/                      migrated deterministic evaluation fixtures
scripts/                    offline, live, packaging, and evidence checks
docs/PROJECT_PROPOSAL_CN.md practical-stage design and delivery plan
docs/EVALUATION_CORE.md     deterministic evaluator contract and limitations
docs/reproscope/             selected ReproScope validation evidence and history
```

See [MIGRATION.md](docs/MIGRATION.md) for compatibility and provenance details.
Release history is recorded in [CHANGELOG.md](CHANGELOG.md).

## Security and Scope

- API keys and private research materials must remain outside version control.
- Repository auditing is static and does not execute third-party code.
- The system evaluates available evidence; it does not determine academic misconduct or provide legal conclusions.
- Reports and scores support expert review and do not replace it.

## License

Apache License 2.0. See [LICENSE](LICENSE).
