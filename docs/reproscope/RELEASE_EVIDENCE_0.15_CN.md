# ReproScope 0.15.0 发布证据矩阵

这份矩阵是 PR checklist 的事实来源。状态只允许写成 `通过`、`待真实验证`、`不适用` 或 `未核验`，不能用历史 0.5.x 截图代替当前版本证据。

| 项目声明 | 代码证据 | 自动化测试 | 真实 Hy3 | MCP Client | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| 10 个 Tool 可发现 | `src/hy3_reproscope_mcp/server.py`、`scripts/stdio_smoke.py` | `tests/test_server.py`、`tests/test_stdio.py` | 不适用 | CodeBuddy + VS Code 当前截图；CodeBuddy 有十步调用截图，VS Code 有 `repository_8246ee4f34e0` | 本地协议、两端发现与两端实际调用通过；VS Code 索引可机器校验 |
| 论文五工具链 | `src/hy3_reproscope_mcp/tools.py`、`scripts/run_live_validation.py` | `tests/test_tools.py`、`tests/test_workflow_cases.py` | 最近在线候选 `3C940...` 真实链通过；最终 `76A3F8...` 未重复在线 Hy3 | 真实 run/artifact 见 `LIVE_VALIDATION_0_15_CN.md` | 功能与离线链通过；最终精确候选在线状态保持未核验 |
| 技术迁移四工具链 | `transfer_*.py`、`repository_*.py`、`scripts/run_live_transfer_validation.py` | `tests/test_transfer_*.py` | 最近在线候选 `3C940...` 真实链通过；最终新构建候选仍需精确在线复核 | 直接 run/artifact 见 `LIVE_VALIDATION_0_15_CN.md`；CodeBuddy 最终 MP4 展示报告血缘校验和 completed 迁移报告 | 功能与客户端报告调用通过；精确新 wheel 的完整在线重复不由录屏证明 |
| 静态仓库审计 | `repository_scanner.py`、`execution.py` | `tests/test_repository_scanner.py` | 不需要 | VS Code 1.131.0 使用前一构建 `61F776...` wheel 调用完成；最终 `76A3F8...` 已通过自动 stdio 发现 | `repository_8246ee4f34e0` 为 0 gaps、0 warnings、未截断、`executed=false` |
| ISAC explicit | `profiles/isac_phy/`、`models.py`、`scripts/run_live_isac_validation.py` | `tests/test_isac_profile.py` | 最近在线候选 `3C940...` explicit 真实调用通过；最终 `76A3F8...` 未重复在线 Hy3 | 直接 run/artifact 见 `LIVE_VALIDATION_0_15_CN.md` | 功能通过；最终精确候选在线状态保持未核验 |
| ISAC auto 正/负样本 | `profiles/isac_phy/detector.py` | `tests/test_isac_profile.py`、synthetic fixtures | 最近在线候选 `3C940...` auto 正例激活、雷达负例保持 generic 均通过；最终 `76A3F8...` 未重复在线 Hy3 | 直接 run/artifact 见 `LIVE_VALIDATION_0_15_CN.md` | 功能通过；三个成功 manifest 均 completed；一次空 completion 失败已单独记录 |
| ISAC 校准 harness | `profiles/isac_phy/calibration.py`、`scripts/run_isac_calibration.py` | `tests/test_isac_calibration.py`、synthetic calibration fixture | 不需要 | 不需要 | 合成描述性指标通过；真实专家/held-out 校准待完成 |
| 证据不足拒答 | `errors.py`、工具边界和归一化逻辑 | `tests/test_workflow_cases.py`、offline eval | 需要当前版本复核 | 任一客户端 | 本地通过，真实待验证 |
| Artifact lineage 和 hash | `workspace.py`、`lineage.py` | `tests/test_artifact_integrity.py`、`test_run_manifest.py` | 可选 | 通过报告/manifest 证明 | 本地通过 |
| Schema 兼容拒绝 | `Workspace.require_artifact_schema`、`tools._read_result_artifact` | old/missing/future/exact 测试 | 不需要 | 不需要 | 本地通过 |
| 离线评测结果 | `scripts/run_offline_eval.py`、`run_transfer_offline_eval.py` | evaluation tests | 不需要 | 不需要 | 2 paper cases/49 checks；2 transfer cases/67 checks |
| 依赖 lockfile | `requirements.lock`、`repository_scanner.py` | `test_requirements_lock_is_parsed_as_exact_pip_lockfile`、`scripts/verify_lockfile.py` | 不需要 | 不需要 | 50 包、663 个下载 SHA-256 覆盖通用、源码和平台分发；文件 SHA-256 `A9BCEC436179BDDED5CC035629FD84C624927583E4CCF708796A650948924471`；根级 CI 在 Linux/Windows/macOS 使用 `--require-hashes` |
| 远端 CI 与 PR | `.github/workflows/reproscope-ci.yml`、PR #187 | 最近入库证据为 run `30689787695`（commit `36253a6`） | protected live job 手动触发 | 不需要 | 既有 Linux/Windows/macOS 五任务全绿；本轮 README/证据改动未 push，需等待新 CI 并同步 PR 正文 |

## 解释边界

- 49 和 67 是固定工程回归案例中的检查项数量，不是独立论文数量。
- CAR=1.0 当前只表示预期拒答案例的 `1/1` 正确，不外推为领域 benchmark。
- ISAC finding 固定 `affects_score=false`；当前仅有显式 Evidence Card 驱动的合成描述性校准 harness。公开论文候选清单仍需领域专家复核，尚未完成专家标注、真实 Calibration 或 Held-out 校准。
- 仓库审计只读取和静态解析声明，不执行第三方代码、安装命令或数据下载命令。
- 截图和录屏不得出现 API Key、Authorization Header、`.env` 内容、私有论文路径或私有 endpoint。最终 CodeBuddy
  MP4 未包含凭据，但保留本机用户名和本地绝对路径；该边界已在客户端证据文档中公开说明。

当前 0.15.0 论文、迁移和 ISAC 链的 run ID、artifact content/payload hash、确定性指标和失败边界见
[LIVE_VALIDATION_0_15_CN.md](LIVE_VALIDATION_0_15_CN.md)。两张当前客户端十工具发现截图位于
`docs/assets/`；VS Code 当前调用索引为 `docs/CLIENT_VALIDATION_0_15_INDEX.json`。最终 CodeBuddy 演示为
`docs/assets/demo-0.15.0-codebuddy-mcp.mp4`，截图 montage 仅用于双客户端 Tool 发现。

最近在线验证的 `3C940...` wheel 汇总覆盖 13 个成功 run 和 28 个成功 artifact；汇总 SHA-256 为
`0FE83471A9B613F807193E275EA3A6B85C0F4159C0198F1521AB0C8EE80E619A`。一次空 completion 失败和旧 wheel
记录单独保留为重试/历史证据；这三条工作流验证状态为通过。最终 `76A3F8...` wheel 已通过本地安装和 stdio 门禁，精确在线 Hy3 状态为`未核验`。

## 真实验证记录要求

每个当前版本案例至少保存：客户端版本、Python 版本、package 版本、Schema、run ID、关键 Artifact hash、脱敏截图和结果状态。关键案例至少重复两次，记录确定性字段是否稳定以及自然语言非关键差异。

客户端最小调用矩阵也必须覆盖新增工作流：至少一端完成 `reproscope_extract_solution_profile`、
`reproscope_assess_transfer`、`reproscope_build_transfer_graph` 和 `reproscope_render_transfer_report` 的完整迁移链，
并至少一端真实调用 `reproscope_audit_repository`；仅论文 `compare_results` 一次调用不能替代这些门禁。
