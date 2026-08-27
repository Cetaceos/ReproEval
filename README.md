# Hy3 ReproEval

Hy3 ReproEval is a personal project developed for the 2026 Tencent Rhino-Bird open-source practical program. It is not an official Tencent product.

The project will build an evidence-grounded Hy3 application and evaluation framework for open-ended research reports. Its primary scenario is research reproducibility review, with technology-transfer assessment used as a generalization scenario.

## Planned Capabilities

- Generate structured research reproducibility reports with Hy3 and local tools.
- Validate citations, numerical results, schemas, and artifact lineage deterministically.
- Evaluate reports with an operational seven-dimension rubric.
- Compare automatic evaluation with blinded human annotations.
- Measure discrimination, consistency, stability, and adversarial robustness.
- Expose reusable Python, CLI, MCP, and optional Skill adapters.

## Relationship to ReproScope

This repository continues the research direction explored in [Hy3 PR #187](https://github.com/Tencent-Hunyuan/Hy3/pull/187), while focusing on the validity of evaluation methods for open-ended AI outputs. It uses an independent repository and Git history as required by the practical-stage task.

## Status

Initial planning and repository setup. The final project submission is planned for September 11, 2026.

## Security

API keys and private research materials must not be committed. Hy3 credentials will be supplied through environment variables or private client configuration.

## License

Apache License 2.0. See [LICENSE](LICENSE).
