# ReproEval 最终交付状态

> 核对日期：2026-09-11
>
> 任务：犀牛鸟实战任务一“开放式场景：AI 应用与评判标准设计”
>
> 最终提交日期：2026-09-11

## 1. 当前结论

应用层、评估方法、分档数据以及判别力和重复稳定性实验已经形成可运行的工程链路。仓库已加入 6 组
开放获取真实论文 Pilot，并完成 Dataset 1.2 来源清单、PDF 哈希与 30 条论文证据摘录核验。真实 Pilot
已在同一 Freeze 上完成三轮、共 54 次 `hy3` Judge 调用并公开聚合结果。12 份 validation/test 报告的
双人盲评、4 项第三人裁决和最终共识均已完成，二次加权 Kappa 为 `0.964225`，三轮系统—最终共识
Spearman 为 `0.988483`、`1.0` 和 `0.988483`，`consensus_ready=true`。逐报告、逐维度和逐轮系统—人工
结果已形成脱敏公开包并纳入 CI。Hy3 高档候选生成与人工审核保留为独立实验支线：6 份候选均为 `pending`，
不进入 Dataset `0.2.0`，也不作为本轮人工真值。6 组真实论文 Pilot 本身未执行对应第三方软件；独立
DiffeRT2d v0.3.4 案例已经执行其 JOSS Figure 2 固定入口并形成可校验公开证据。当前公开真实材料已通过
论文复现和条件化技术迁移两条 MCP stdio 预检，但该预检不等同于 WorkBuddy 客户端录屏，最终演示仍是
终稿前的阻塞项。

由外部可认证领域专家扩展标签规模和真实论文 held-out 实验仍能显著提高项目可信度。任务书允许使用“同一输出多次评估的分数波动”完成一致性验证，因此当前重复实验满足该项要求，但不能替代更大规模真实场景有效性证据。
当前 validation/test 共识只能用于披露校准误差，不能用于事后调参后在同一批样本上重新宣称独立性能；
任何分数校准都应使用 development 或新增校准集，并重新建立来源隔离的 held-out 结果。

## 2. 任务书逐项核对

| 任务书要求 | 状态 | 当前证据 | 仍需处理 |
| --- | --- | --- | --- |
| 独立公开仓库并标明个人活动作品 | 已完成 | README 首屏明确说明项目性质 | 将本地待推送提交 push 后确认 GitHub 展示正常 |
| README、运行方法和环境要求 | 已完成 | [`README_CN.md`](../README_CN.md)、[`.env.example`](../.env.example)、[`.mcp.json`](../.mcp.json) | 最终检查链接和安装命令 |
| 基于 Hy3 的可运行 AI 应用 | 工程实现已完成 | 10 个 stdio MCP Tool、两条 ReproScope 工作流、真实来源候选生成与三轮在线 Hy3 Judge | 不把在线调用等同于第三方软件复现或专家验证 |
| 明确目标用户、问题和使用大模型的必要性 | 已完成 | README、[项目方案](PROJECT_PROPOSAL_CN.md) | 终稿摘要保持简洁 |
| 至少 5 个可操作评估维度 | 已完成 | 7 维版本化 Rubric 与 0–4 分锚点 | 无 |
| 自动或半自动评测流程 | 已完成 | Validators、Hy3 Judge、replay Benchmark、人工 Bundle 接口 | 无 |
| 样本来源、构造和覆盖范围 | 已完成 | [真实论文 Pilot](REAL_PAPER_PILOT.md)、[Dataset 协议](DATASET_PROTOCOL.md)、[P0 数据集](P0_DATASET.md)、[P1 数据集](P1_TRANSFER_DATASET.md) | 真实 Pilot 高档报告保持 `curator_draft`；未经人工审核的在线候选作为独立后续研究，不进入当前 Dataset |
| 难例和反例 | 已完成 | P0 的 44 份分档/对抗报告及 8 份 adversarial report，P1 的 10 个 Mutation | 不外推为真实攻击鲁棒性 |
| 判别力验证 | 已完成（构造标签与人工共识对照） | P1 与[真实论文 Pilot 三轮结果](REAL_PAPER_JUDGE_EXPERIMENT_CN.md)：各轮组内排序均为 100%；三轮系统—最终共识 Spearman 为 0.988483、1.0、0.988483 | MAE 为 14.541667–15.791667，中档报告存在系统性高估 |
| 一致性验证 | 已完成 | 真实 Pilot 双人 Kappa 0.964225、精确同分率 85.7143%、一分内一致率 100%；4/4 争议经第三人裁决 | 人工身份和专业背景仍为自我声明 |
| 完整结果表格与图表 | 已完成 | P1 与真实 Pilot 均含运行级、报告级、维度级 CSV、确定性 SVG 和独立 manifest；最终人工共识另有脱敏完整结果包 | 无 |
| 典型 Case 归因和失败模式 | 已完成 | [P1 实验报告](P1_JUDGE_EXPERIMENT_CN.md)、[真实 Pilot 实验报告](REAL_PAPER_JUDGE_EXPERIMENT_CN.md)、[人工验证报告](REAL_PAPER_HUMAN_VALIDATION_CN.md) | 无 |
| 对抗性验证 | 已完成任务书鼓励项 | P0 含 8 份 adversarial report、7 类攻击、Mutation 与预期错误完整对应，并提供确定性检测指标 | 未开展 P1/真实 Pilot 在线对抗实验，不外推为真实攻击鲁棒性 |
| 人工标注接口 | 已完成 | [盲审工作包](ANNOTATION_PACKET.md)、两份独立 Bundle、父哈希绑定的第三人裁决 Bundle、12/12 最终共识、[人工验证报告](REAL_PAPER_HUMAN_VALIDATION_CN.md) | 无 |
| Skill 适配 | 已完成（P1 增强） | [`reproeval-research-audit`](../skills/reproeval-research-audit)、[Skill 文档](SKILL_ADAPTER.md) | 可在支持 Skills 的客户端补一次调用截图 |
| 实际结果复现案例 | 已完成一个受限案例 | [DiffeRT2d v0.3.4 Figure 2](../case_studies/differt2d_v0_3_4) 已实际执行并得到像素与文件字节一致的公开证据 | 只证明固定 Figure 2 程序的软件输出复现，不外推到整篇论文或真实物理测量 |
| 2 分钟以内演示 | 待完成，阻塞最终提交 | 旧 ReproScope 客户端证据不能完整代表当前 ReproEval | 录制当前版本的应用调用与评测结果 |

## 3. 已公开的核心实验

P1 实验通过腾讯云 TokenHub 对同一个冻结合成数据集完成 3 轮在线 Hy3 Judge 调用，共产生 45 次成功调用。这里的“在线”仅说明 API 调用实际发生，不能证明输入、档位标签或评测结论具有真实场景有效性。公开结果包只包含聚合 Markdown/CSV 和由哈希绑定的数据溯源信息，不包含 API Key、请求体或原始响应。

```bash
hy3-reproeval verify-results-export --bundle results/p1_transfer_judge
```

当前公开 manifest SHA-256：

```text
DD3BDAC5F5E204E2BACB2BD4DF22835065BC0C96E0136D0272DFE5D173A83072
```

该实验支持“当前评估器能够稳定区分这组合成迁移报告”的有限结论，不支持真实部署可行性、专家一致性或未见材料泛化结论。

真实论文 Pilot 也在同一冻结输入上完成三轮 TokenHub `hy3` Judge，共 54 次成功调用。三轮 Pairwise accuracy、Complete-order accuracy 和宏 Spearman 均分别为 100%、100% 和 1.0；18/18 报告完整评分，总分标准差最大值为 3.535534，质量档位无翻转。Run 1 对 `real-paper-06-cdcam-high` 额外标记一次 `reasoning_gap`，后两轮未重复。

```bash
hy3-reproeval verify-results-export --bundle results/real_paper_judge
```

该公开包 manifest SHA-256 为 `266DDCEFF6B734B753CF98E3B2123C027D2F470F61CDF62F4D71BEB9DF2DBAD8`。论文来源真实，但分档仍是策展草稿与 Mutation，因此结果不替代人工有效性验证。

最终人工共识、七维分数和三轮系统—人工对照已导出为不含评审身份、Bundle ID、评语和原始响应的
公开完整结果包：

```bash
hy3-reproeval verify-human-consensus-results --bundle results/real_paper_human_consensus
```

该包 manifest SHA-256 为 `8BE621BE084A2F18449B4CF4CDCB49DF6374F759AA4F681B8BE8CE3D5E2D7B5A`。

## 4. 剩余交付工作与持续边界

### 4.1 最终演示

最终演示必须展示当前 ReproEval，而不是只展示迁移前的 ReproScope：

1. 客户端发现 `hy3-reproeval` MCP Server；
2. 选择论文复现或技术迁移场景并实际调用关键 Tool；
3. 展示 MCP 返回的 `run_id`、结果文件路径和证据不足/警告信息；
4. 展示最终 Markdown 报告；
5. 展示一次 `hy3-reproeval` 结果校验或公开 P1 结果表；
6. 总时长控制在 2 分钟以内，不显示 API Key、本地用户名或私有目录内容。

### 4.2 人工一致性边界

两套独立随机顺序工作包和第三人裁决包均已回收，并通过来源、行号、Assignment、Rubric、Freeze 和
父 Bundle 哈希验签。12/12 份目标报告形成最终共识，4/4 个 `factual_accuracy` 错误码分歧均已解决，
`consensus_ready=true`。这证明协议闭环和当前样本上的人工一致性，不证明评审者外部身份、专业资质或
论文结论本身正确；这些信息仍来自自我声明。

### 4.3 真实材料泛化与候选支线

`evals/real_paper_pilot` 已登记 6 篇 CC BY 4.0 的 JOSS 论文、期刊记录、论文哈希、软件仓库、发表时归档和本地证据包，共 30 个来源资产及 30 条可回查论文证据。PDF 原文只保存在被忽略的私有缓存中，验证命令会重算哈希并逐页检查证据摘录。冻结 Pilot 的所有组仍标记为 `reproducibility_readiness`，不登记第三方软件执行结果；仓库内 6 份高档报告仍标记为 `curator_draft`，不能作为专家真值。私有目录已用 Prompt `reproeval-reference-generation-1.1` 完成 6 份 TokenHub `hy3` 候选并通过数据溯源关系重算验证；它们仍全部等待人工审核，因此本轮明确将该流程保留为实验性后续研究，不以候选替换当前报告。若未来采用审核通过的候选，必须显式升级 Dataset、重建 Mutation、重新冻结并运行新的 Judge 和人工实验，不能与 `0.2.0` 结果混用。

独立的 `case_studies/differt2d_v0_3_4` 案例已使用 Python 3.11.8 和上游锁定依赖实际执行
DiffeRT2d v0.3.4 JOSS Figure 2 程序。登记运行退出码为 0，300 x 300 功率网格生成完成，输出 PNG
与归档参考图字节及像素完全相同；公开证据包通过 SHA-256 复验。该结果不回写冻结 Pilot，也不扩展为
整篇论文或传播模型准确性已经得到独立验证。

## 5. 9 月 11 日前建议顺序

| 日期 | 工作 | 完成标准 |
| --- | --- | --- |
| 9 月 7 日 | 完成真实论文 Pilot 来源层、在线候选和协议校验 | 已完成：6 组、18 份草稿、30 个来源资产、30 条证据和 2/2/2 划分通过校验；6 份待人工审核候选保留为实验支线 |
| 9 月 8 日 | 冻结 Pilot，完成三轮在线 Hy3 Judge | 已完成：54 次调用、3 份 Benchmark、稳定性与公开聚合结果均通过复验 |
| 9 月 8–9 日 | 组织双人盲评 validation/test | 已完成：两份 Bundle 验签、12/12 双人覆盖和一致性分析；生成 4 项裁决队列 |
| 9 月 9 日 | 完成第三人裁决和案例分析 | 已完成：回收包仅修改 responses，4/4 争议解决，12/12 共识报告，`consensus_ready=true` |
| 9 月 9 日 | 公开脱敏人工结果并补 CI 校验 | 已完成：12 份报告、84 条维度结果、36 条系统对照和 9 条逐档校准结果均由完整性 manifest 保护；真实 Pilot 三类结果进入 CI |
| 9 月 9 日 | 完成 DiffeRT2d 实际结果复现 | 已完成：来源与环境冻结、固定入口执行、8 项私有证据、6 项公开证据和防篡改验证；结果为 exact |
| 9 月 10 日 | 录制演示并在干净环境完成发行验收 | 两分钟内，无密钥；Python 3.11–3.13 CI 绿色 |
| 9 月 11 日 | 提交最终仓库链接和材料 | GitHub CI 绿色，提交内容与仓库版本一致 |

## 6. 最终提交前命令

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -e . --no-deps
python -m pytest
python -m ruff check src tests scripts case_studies
python -m ruff format --check src tests scripts case_studies
python -m hy3_reproeval build-p0-dataset --output evals/p0_dataset --check
python -m hy3_reproeval build-p1-transfer-dataset --output evals/p1_transfer_dataset --check
python -m hy3_reproeval build-real-paper-pilot --output evals/real_paper_pilot --check
python -m hy3_reproeval validate-dataset --manifest evals/real_paper_pilot/dataset.json
# 准备私有 PDF 缓存后执行：
python -m hy3_reproeval verify-real-paper-sources --source-dir .reproeval/source_cache
python -m hy3_reproeval verify-results-export --bundle results/p1_transfer_judge
python -m hy3_reproeval verify-results-export --bundle results/real_paper_judge
python case_studies/differt2d_v0_3_4/scripts/run_reproduction.py verify-public --evidence-dir case_studies/differt2d_v0_3_4/evidence
python -m hy3_reproeval verify-human-consensus-results --bundle results/real_paper_human_consensus
python -m hy3_reproeval verify-results-figures --figures results/real_paper_judge_figures --source-bundle results/real_paper_judge
python -m hy3_reproeval verify-results-figures --figures results/p1_transfer_judge_figures --source-bundle results/p1_transfer_judge
python -m build
python scripts/check_distribution.py dist --version 0.38.0
```

在提交前还需执行 `git status`，确认 `.mcp.json` 中只有公共占位模板进入暂存区，本机启动路径和私有环境配置仍只保留在工作区；同时确认 `.env`、私有标注、原始 Judge Record、录屏原文件和 `.reproeval` 均未进入暂存区。
