# ReproScope Migration Notes

## Provenance

The initial application layer was migrated from `mcp_servers/reproscope` in the author's Hy3 contribution branch associated with [Tencent-Hunyuan/Hy3 PR #187](https://github.com/Tencent-Hunyuan/Hy3/pull/187). Both codebases are Apache-2.0 licensed and maintained by the same author.

## Compatibility

- Existing Python imports under `hy3_reproscope_mcp` remain valid.
- Existing `python -m hy3_reproscope_mcp` configurations remain valid.
- The `hy3-reproscope-mcp` console command remains as a compatibility alias.
- New installations use the `hy3-reproeval` distribution and may use `hy3-reproeval-mcp`.

## Migration Boundary

The migration includes public source code, tests, scripts, synthetic examples, deterministic evaluation fixtures, and selected validation evidence. It excludes private environment files, API responses, virtual environments, caches, build outputs, local notes, and the original large demonstration video.

The migrated ReproScope layer is the application generator and evidence-processing foundation. ReproEval's report-quality evaluator is developed as a separate layer so that generation and evaluation remain independently testable.
