# WorkBuddy 最终双主线演示手册

## 1. 演示目标

最终视频展示当前 `hy3-reproeval` MCP Server 的两条应用主线：

1. 使用真实 DiffeRT2d 论文和真实 Figure 2 执行证据完成论文复现审查；
2. 将 DiffeRT2d 作为真实开源源方案，评估其迁移到三维 UAV-BS ISAC 研究流程的条件、风险和验证路径。

论文主线使用 `auto` Profile。DiffeRT2d 不包含通信与感知联合目标，因此正确结果应保持 `generic`，
不能为了展示 ISAC Profile 而强制误分类。可另用公开合成材料快速展示 `isac_phy` 扩展，但必须明确其
输入性质，且不能将其作为真实论文结论。

## 2. 录制前检查

1. 确认 Windows 用户环境中的 `MCP_TOOL_TIMEOUT` 为 `300000`。
2. 完全退出并重启 WorkBuddy，使新的环境变量和 `.mcp.json` 生效。
3. 确认 Server 名称为 `hy3-reproeval`，并发现 10 个 Tool。
4. 确认 `REPROSCOPE_OUTPUT_LANGUAGE=zh-CN`。
5. 确认 `REPROSCOPE_WORKSPACE` 指向空的 `.reproeval/workbuddy-final-demo`。
6. 不在录屏中展开 `.mcp.json`、私有环境脚本、模型原始响应或用户目录。
7. 将下文的 `<REPROEVAL_ROOT>` 替换为本机仓库绝对路径，将 `<DIFFERT2D_PDF_PATH>` 替换为已核验的
   DiffeRT2d 论文 PDF 绝对路径；不要把私有路径写回公共仓库。

## 3. 主线一：真实论文复现审查

在 WorkBuddy 中发送以下请求：

```text
请严格按顺序调用 hy3-reproeval 完成 DiffeRT2d 真实论文复现审查，不得跳步、模拟成功或改写结果文件路径。
每一步只调用一次；等待 Tool 返回后，从 `artifacts[].relative_path` 读取下一步参数。
所有过程说明和最终总结使用中文；JSON 字段名、枚举值、ID、引用、单位和代码标识符保持原样。

论文文件：
<DIFFERT2D_PDF_PATH>

复现证据：
<REPROEVAL_ROOT>/case_studies/differt2d_v0_3_4/RESULT.md
<REPROEVAL_ROOT>/case_studies/differt2d_v0_3_4/evidence/figure2_summary.csv

Step 1: reproscope_extract_claims
domain_profile=auto
profile_request_source=user_instruction
focus=物理层建模假设、Figure 2 数值设置、软件可复现性、证据边界和缺失的测量验证

Step 2: reproscope_compare_results
metric_hints=[power_grid_rows, power_grid_columns]
传入 Step 1 的 extract_claims.json。

CSV 中的像素差异和运行时仍作为复现证据保留，但论文没有报告这两个对照指标，因此不要求生成
论文数值差异；两个网格维度应由 Python 重算为 300，绝对差为 0。

Step 3: reproscope_score_paper
rubric_focus=[结果一致性, 实验设置透明度, 统计证据, 实现可用性, 物理有效性边界]
传入 Step 1 和 Step 2 的 JSON 结果文件，并继续使用上述两份复现证据路径。

Step 4: reproscope_build_evidence_graph
传入前三步对应结果文件。

Step 5: reproscope_render_report
title=DiffeRT2d Figure 2 复现证据审查
传入前四步对应结果文件。

最后显示 effective_profile、每一步 run_id、最终 Markdown 路径、总体状态和关键 warnings。
结论必须区分 Figure 2 软件输出复现、整篇论文复现和传播模型物理准确性。
```

预期的可信结论不是“整篇论文已经验证”，而是“固定环境中的 Figure 2 软件输出精确复现；物理准确性
和整篇论文结论仍需要独立证据”。`auto` 保持 `generic` 是正确的保守分类结果。

## 4. 可选进阶 ISAC Profile 片段

该片段用于展示通信物理层扩展机制，不属于真实论文主实验：

```text
只调用一次 reproscope_extract_claims，输入
<REPROEVAL_ROOT>/examples/sample_isac_paper.md，
domain_profile=isac_phy，profile_request_source=user_instruction。
显示 effective_profile、规范指标、假设、风险规则和 affects_score；明确输入是合成 fixture。
```

## 5. 主线二：真实源方案的条件化迁移评估

```text
请严格按顺序调用 hy3-reproeval，评估 DiffeRT2d 迁移到三维 UAV-BS ISAC 研究流程的可行性。
不得跳步、模拟成功或预测没有目标测量支持的性能点值。
所有过程说明和最终总结使用中文；JSON 字段名、枚举值、ID、引用、单位和代码标识符保持原样。

源方案材料：
<REPROEVAL_ROOT>/case_studies/differt2d_v0_3_4/TRANSFER_SOURCE_EVIDENCE.md
<REPROEVAL_ROOT>/case_studies/differt2d_v0_3_4/source_manifest.json

目标背景：
<REPROEVAL_ROOT>/examples/differt2d_uav_isac_target.md

Step 1: reproscope_extract_solution_profile
focus=可复用组件、二维几何和功率模型边界、JAX 依赖、接口、资源与证据缺口

Step 2: reproscope_assess_transfer
传入 Step 1 的 `solution_profile.json` 结果文件。
focus=三维移动场景、复杂信道、阵列、时延、多普勒、近远场、ISAC 指标和测量校准

Step 3: reproscope_build_transfer_graph
传入 Step 1 和 Step 2 的 JSON 结果文件。

Step 4: reproscope_render_transfer_report
title=DiffeRT2d 到 UAV-BS ISAC 研究流程的迁移评估
传入前三步对应结果文件。

最后显示 feasibility_band、可复用组件、必要改造、阻塞风险、验证步骤、run_id 和报告路径。
```

第一份源材料汇总了经真实开放论文、发布归档和实际 Figure 2 复现证据核验的事实，并列出对应
manifest 与结果文件；第二份材料提供冻结版本、DOI、许可证信号和来源哈希。两者都不是合成方案。
目标背景是拟议研究需求，不是已部署系统；迁移报告只能给出条件化决策，不能宣称真实迁移性能。

## 6. 两分钟视频结构

所有慢速 Hy3 Tool 必须先在 WorkBuddy 中真实完成。录屏可以展示已完成的调用历史，并现场重新执行
一个确定性证据图或报告 Tool；不能用内部 Python 脚本结果冒充 WorkBuddy 调用。

| 时间 | 画面 |
| --- | --- |
| 0:00-0:12 | 项目名称、WorkBuddy 已发现 10 个 Tool |
| 0:12-0:52 | DiffeRT2d 论文链的五个成功调用、来源和最终报告边界 |
| 0:52-1:08 | 可选 ISAC Profile：指标、假设、风险规则和合成输入声明 |
| 1:08-1:48 | DiffeRT2d 到 UAV-BS ISAC 的四个成功调用和迁移决策报告 |
| 1:48-2:00 | `run_id`、结果文件路径、证据关系图及“Hy3 + 本地确定性校验 + 人工评测”总结 |

如果需要展示等待过程，应剪除或加速纯等待片段；不得剪接伪造 Tool 成功状态。

## 7. 录制验收清单

论文主线必须同时满足：

- `effective_profile=generic`，并在结果中深入讨论二维、相位省略、测量验证和物理有效性边界；
- `power_grid_rows` 与 `power_grid_columns` 的状态均为 `computed`，本地重算值为 300、绝对差为 0；
- `graph_validated=true`，最终报告包含输入来源清单、直接输入输出关系和 `METRIC_VALUES_RECALCULATED`；
- 结论只确认冻结环境下的 Figure 2 软件输出，不扩展为整篇论文或传播模型物理准确性已验证。

迁移主线必须同时满足：

- `feasibility_band` 为 `conditional` 或 `high_risk`，存在阻塞条件时不得为 `promising`；
- `performance_prediction_provided=false`、`legal_conclusion_provided=false`；
- 报告区分可直接复用、需要改造和缺少证据的部分，并给出验证步骤；
- `graph_validated=true`，报告明确目标背景是拟议需求而不是已部署系统。

Hy3 语义评分可能在重复调用间小幅变化，因此不把某个固定总分作为录制门槛。若 Tool 返回 API 超时、
无效 JSON 或 `schema validation failed`，应停止当前链路，不得把失败步骤的结果传给下一步；确认 300 秒超时并使用
本手册中的精简输入后，在新的 WorkBuddy 对话中重新执行，只录制完整成功链路。单次 Tool 在 TokenHub 上可能
耗时约 1 至 4 分钟，录屏可展示已完成的真实调用历史。
