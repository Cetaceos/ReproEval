# ReproEval

English | [简体中文](README_CN.md)

ReproEval is a Hy3-powered project for research evidence review and open-ended report evaluation. Its MCP server
provides paper-reproduction review and conditional solution-transfer assessment to clients such as CodeBuddy,
WorkBuddy, VS Code/Copilot, Cursor, and Cline. Versioned rubrics, deterministic numerical checks, provenance records,
and blinded human review constrain the model's conclusions.

This repository is an individual submission to the Tencent Rhino-Bird open-ended AI application and evaluation task.
It is not an official Tencent product.

## Highlights

| Capability | Implementation |
| --- | --- |
| Two application workflows | Paper-reproduction evidence review and conditional transfer assessment for a new target context. |
| Hy3 plus deterministic code | Hy3 performs semantic interpretation; Python recomputes statistics and validates schemas, hashes, and direct inputs. |
| Ten MCP tools | A stdio client can orchestrate material extraction, comparison, scoring, evidence graphs, and Markdown reports. |
| Auditable evaluation | A seven-dimension rubric, tiered and adversarial samples, three-run Hy3 Judge experiments, blinded review, and adjudication. |
| Real sources and execution | A six-paper open-access pilot plus an executed DiffeRT2d v0.3.4 Figure 2 reproduction. |
| Traceable outputs | Each step returns a `run_id` and relative result path with input hashes, direct dependencies, warnings, and status. |

## Design

```text
MCP client
   |
   +-- paper + reproduction results --> Hy3 claim extraction --> Python metric recomputation
   |                                                          --> reliability assessment
   |                                                          --> evidence graph --> report
   |
   +-- source solution + target context --> Hy3 solution profile --> conditions, adaptations, and risks
                                                                  --> transfer graph --> report

Evaluation: seven-dimension rubric --> frozen datasets --> Hy3 Judge --> discrimination/stability
                                                                      --> blinded human review
```

Model output cannot override locally recomputed values or structural validation. Dimensions without enough evidence
return `insufficient` instead of receiving an automatic zero. Transfer assessment does not predict exact target
performance without target measurements.

## Final demo

[Download or view the WorkBuddy two-workflow demo (1080p MP4, 2:50)](docs/assets/reproeval-workbuddy-final-demo.mp4)

The video shows WorkBuddy discovering all ten tools, reviewing the public DiffeRT2d paper against an actual Figure 2
execution, and assessing transfer of that solution to a proposed 3D UAV-BS ISAC workflow. The API calls and displayed
results are from real runs. The conclusion is limited to the shown inputs and frozen case; it does not validate the
whole paper or the physical accuracy of the propagation model.

The exact prompts and acceptance boundaries are documented in the
[WorkBuddy demo guide](docs/WORKBUDDY_FINAL_DEMO_CN.md).

## Quick start

Python 3.11–3.13 and access to an OpenAI-compatible Hy3 API are required. The default example uses Tencent Cloud
TokenHub.

### One-command installation

```bash
python -m pip install "hy3-reproeval @ git+https://github.com/Cetaceos/ReproEval.git@main"
```

This installs the MCP server and CLI. Clone the repository to run its examples, datasets, and executable case study:

```bash
git clone https://github.com/Cetaceos/ReproEval.git
cd ReproEval
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Linux or macOS:

```bash
./.venv/bin/python -m pip install -e .
```

### Configure Hy3

Pass credentials through environment variables or private client configuration only. Never commit them. See
[`.env.example`](.env.example) for all settings.

```text
HY3_API_PROVIDER=tokenhub
HY3_BASE_URL=https://tokenhub.tencentmaas.com/v1
HY3_API_KEY=YOUR_HY3_API_KEY
HY3_MODEL=hy3
REPROSCOPE_OUTPUT_LANGUAGE=zh-CN
```

### Configure an MCP client

Copy [`.mcp.example.json`](.mcp.example.json) to a local `.mcp.json`, then replace the Python, repository, and workspace
paths with absolute local paths. A reliable Windows stdio configuration is:

```json
{
  "mcpServers": {
    "hy3-reproeval": {
      "type": "stdio",
      "command": "C:/path/to/ReproEval/.venv/Scripts/python.exe",
      "args": ["-m", "hy3_reproscope_mcp"],
      "env": {
        "HY3_API_PROVIDER": "tokenhub",
        "HY3_BASE_URL": "https://tokenhub.tencentmaas.com/v1",
        "HY3_API_KEY": "YOUR_HY3_API_KEY",
        "HY3_MODEL": "hy3",
        "HY3_TIMEOUT_SECONDS": "300",
        "REPROSCOPE_OUTPUT_LANGUAGE": "zh-CN",
        "REPROSCOPE_ALLOWED_ROOTS": "C:/path/to/ReproEval",
        "REPROSCOPE_WORKSPACE": "C:/path/to/ReproEval/.reproeval/reproscope"
      }
    }
  }
}
```

Client-specific examples are available for [CodeBuddy](examples/mcp-config/codebuddy.json) and
[VS Code](examples/mcp-config/vscode.json).

## End-to-end workflows

### Paper-reproduction review

```text
reproscope_extract_claims
  -> reproscope_compare_results
  -> reproscope_score_paper
  -> reproscope_build_evidence_graph
  -> reproscope_render_report
```

Use `examples/sample_paper.md`, `examples/sample_results.csv`, and `examples/sample_train.log` for a small demo. The
executed case uses the frozen protocol and public evidence in `case_studies/differt2d_v0_3_4`.

### Solution-transfer assessment

```text
reproscope_extract_solution_profile
  -> reproscope_assess_transfer
  -> reproscope_build_transfer_graph
  -> reproscope_render_transfer_report
```

The minimal inputs are `examples/sample_solution.md` and `examples/sample_target_context.md`. The proposed DiffeRT2d
to UAV-BS ISAC context is in `examples/differt2d_uav_isac_target.md`.

The additional `reproscope_audit_repository` tool performs read-only static analysis of Python repositories. It does
not install dependencies or execute discovered entry points, tests, or third-party code.

## MCP tools

| Tool | Purpose | Execution |
| --- | --- | --- |
| `reproscope_extract_claims` | Extract paper claims, settings, and optional ISAC evidence | Hy3 + local validation |
| `reproscope_compare_results` | Align metrics and recompute reproduction results | Hy3 + local statistics |
| `reproscope_score_paper` | Six-dimension reliability assessment and abstention | Hy3 + local aggregation |
| `reproscope_build_evidence_graph` | Build the paper evidence graph | Local deterministic |
| `reproscope_render_report` | Render the paper-review report | Local deterministic |
| `reproscope_extract_solution_profile` | Extract a structured solution profile | Hy3 + local validation |
| `reproscope_assess_transfer` | Assess transfer conditions, adaptations, and risks | Hy3 + local aggregation |
| `reproscope_build_transfer_graph` | Build the transfer evidence graph | Local deterministic |
| `reproscope_render_transfer_report` | Render the transfer decision report | Local deterministic |
| `reproscope_audit_repository` | Statically audit Python reproduction requirements | Local deterministic |

## Data and results

| Evidence | Scale and result | Supported conclusion |
| --- | --- | --- |
| [P0 dataset](evals/p0_dataset/dataset.json) | 12 groups and 44 high/medium/low/adversarial reports | Exercises dataset, error-label, and adversarial regression paths |
| [P1 transfer dataset](evals/p1_transfer_dataset/dataset.json) | 5 groups and 15 reports; 100% within-group ordering in each of three runs | Stable discrimination on the constructed transfer reports |
| [Real-paper pilot](evals/real_paper_pilot/dataset.json) | 6 open-access papers and 18 reports; no quality-band flips across three runs | Workflow and repeated-run stability on real-source material |
| [Human consensus](results/real_paper_human_consensus/summary.md) | 12 blinded reports; quadratic weighted kappa 0.964225 | Agreement among the current reviewers on the current sample |
| [System-human comparison](results/real_paper_human_consensus/system_human_comparison.csv) | Spearman 0.988483, 1.0, 0.988483; MAE 14.54–15.79 | Ranking is stable, but medium reports are over-scored and scores are not calibrated |
| [DiffeRT2d Figure 2](case_studies/differt2d_v0_3_4/RESULT.md) | Successful frozen entry point, 300 x 300 grid, byte-identical archived image | Reproduces this software output in the recorded version and environment |

A real paper is not the same as an executed reproduction. The pilot evaluates reproducibility readiness; only the
separate DiffeRT2d case executes upstream software. Selected outputs are in [`results`](results/README.md), and the
protocols, freezes, and human-review details are indexed in [`docs`](docs/README.md).

## Local verification

Core checks that do not require an API key:

```bash
python -m pytest
python -m ruff check src tests scripts case_studies
python scripts/run_offline_eval.py
python scripts/run_transfer_offline_eval.py
python -m hy3_reproeval build-p0-dataset --output evals/p0_dataset --check
python -m hy3_reproeval build-p1-transfer-dataset --output evals/p1_transfer_dataset --check
python -m hy3_reproeval build-real-paper-pilot --output evals/real_paper_pilot --check
python case_studies/differt2d_v0_3_4/scripts/run_reproduction.py verify-public \
  --evidence-dir case_studies/differt2d_v0_3_4/evidence
```

Build and inspect release archives:

```bash
python -m build
python scripts/check_distribution.py dist --version 0.38.0
```

## Repository layout

```text
src/            MCP application, evaluation core, and CLI
examples/       Minimal runnable inputs and client configurations
evals/          Regression fixtures, P0/P1 datasets, and the real-paper pilot
case_studies/   Executed case studies and verifiable evidence
results/        Selected aggregate results, CSV, SVG, and integrity manifests
scripts/        Offline evaluation, live validation, and release checks
skills/         Reusable research-audit Skill
tests/          Unit, integration, security, and tamper tests
docs/           Current protocols, experiment reports, delivery notes, and archive
```

## Security and limitations

- File access is restricted by `REPROSCOPE_ALLOWED_ROOTS`; outputs are written to a separate workspace.
- API keys, raw model responses, private reviewer notes, paper-PDF caches, and machine-specific paths are untracked.
- Evidence graphs and SHA-256 records detect substituted inputs and inconsistent processing; they do not prove a
  scientific conclusion.
- The system does not determine research misconduct, provide legal conclusions, or replace domain experts and
  real-system measurements.

## License

ReproEval source code is released under [Apache-2.0](LICENSE). Third-party papers, software, and data retain their own
licenses. Source records in this repository are not legal advice.
