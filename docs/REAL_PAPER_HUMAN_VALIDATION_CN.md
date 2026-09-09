# 真实论文 Pilot 人工验证报告

## 范围与血缘

本轮人工验证基于 `reproeval-real-paper-pilot` Dataset `0.2.0` 的同一冻结输入：

- Dataset Manifest SHA-256：`138CA40FF966ABAF6B9856619A474A2A12926EE8BA3CA90EA8570AC3558CD470`
- Dataset Freeze SHA-256：`90AB080294B1050FBBAB612EE93E6BC7C79AA4E02A13746E11E28A52C1A97D04`
- Reviewer A Bundle SHA-256：`099DCEDFC337EB91D51D3CA00A55AED92D41E7E0E6AF0D2B2EF70FEBCA67B9BE`
- Reviewer B Bundle SHA-256：`EEB0FDDF9ED117FEF65147F801331E72129703F8F313E750CDB5289EC96DE783`
- Adjudicator C Bundle SHA-256：`376CDBC014E0DBDFE4D2E0695A24555A8332726EFC88F57FFDEA92E780036144`
- Final Consensus SHA-256：`D8911FA8D9FD5F0FE13FEE6E3E2263A42339D83EDD1FD13DECEC3B4E9BDDA195`

两位去标识评审者分别完成 12 份 validation/test 报告的七维评分，共形成 24 份报告标注和 168 个维度
评分。工作包中的质量档位、Mutation、预期错误和系统分数保持隐藏。回收时重新验证了报告、来源、
assignment、协调者映射、Rubric 和 Dataset Freeze；只有 `responses.json` 发生变化。

人工来源、独立性和专业背景来自评审者自我声明，不构成外部身份或资质认证。

## 双人一致性

| 指标 | 结果 |
| --- | ---: |
| validation/test 双人覆盖 | 12/12 |
| 维度比较数 | 84 |
| 状态一致率 | 100% |
| 精确同分率 | 85.7143% |
| 一分内一致率 | 100% |
| 平均绝对分差 | 0.142857 |
| 二次加权 Cohen's Kappa | 0.964225 |
| 错误码集合一致率 | 95.2381% |

`factual_accuracy`、`evidence_traceability` 和 `reasoning_consistency` 的精确同分率均为 `66.6667%`；
其余四个维度为 `100%`。分歧集中而非均匀分布，不能只报告总体 Kappa。

## 裁决与最终共识

协议生成 4 个裁决项，均为中档报告的 `factual_accuracy`。两位评审者分别给出 4 分和 3 分，但对
`unsupported_claim` 是否成立意见不同：

- `real-paper-03-differt2d-medium`
- `real-paper-04-lyceanem-medium`
- `real-paper-05-itmlogic-medium`
- `real-paper-06-cdcam-medium`

裁决前 `consensus_ready=false`：12 份目标报告中 8 份形成无争议共识，4 份保持未决。项目通过
`prepare-adjudication-packet` 生成仅含 4 个争议维度的第三人盲包，以 `parent-001`/`parent-002` 展示
匿名父意见和证据轨迹，不包含父评审者身份、Bundle ID、质量档位、Mutation 或系统分数。

第三位评审者对四项均裁定为 3 分并保留 `unsupported_claim`。回收包只有 `responses.json` 与发出包
不同；最终器重新验证 Dataset、Freeze、Rubric、assignment、报告、来源、行号、匿名父意见和两份
父 Bundle 哈希后生成裁决 Bundle。最终共识结果为：

| 项目 | 结果 |
| --- | ---: |
| 目标报告 | 12 |
| 已形成共识报告 | 12 |
| 需裁决维度 | 4 |
| 已解决维度 | 4 |
| 未解决维度 | 0 |
| `consensus_ready` | `true` |

| 报告档位 | 报告数 | 最终人工共识分数 |
| --- | ---: | ---: |
| 高档 | 4 | 100.0 |
| 中档 | 4 | 55.0 |
| 低档 | 4 | 21.5 |

## 系统—人工比较

每轮 Hy3 Benchmark 均与裁决后的最终人工共识逐报告对齐：

| Hy3 运行 | 覆盖率 | Spearman | MAE |
| ---: | ---: | ---: | ---: |
| 1 | 100% | 0.988483 | 15.791667 |
| 2 | 100% | 1.000000 | 15.166667 |
| 3 | 100% | 0.988483 | 14.541667 |

三轮平均 Spearman 为 `0.992322`，平均 MAE 为 `15.166667`。当前系统能稳定恢复构造档位顺序，但绝对
分数明显偏高：四份中档报告的最终共识分数均为 `55.0`，系统三轮均为 `87.5`，单项误差 `32.5` 分；
低档报告也被平均高估 `11.125–13.0` 分。高档仅在 Run 1 平均低估 `1.875` 分。因此这组结果支持
“排序判别力较强”，不支持“评分已经与人工尺度充分校准”。

不得使用这 12 份 validation/test 人工共识反向调节当前 Rubric 权重、Prompt 或质量阈值后，再把同一批
样本报告成独立提升。后续校准应只使用 development 材料或新增校准集，并在新的来源隔离 held-out 集上
重新报告 Spearman、MAE、分档偏差和置信区间。

## 脱敏公开结果

仓库内的 `results/real_paper_human_consensus` 提供 12 份报告的最终共识、84 条逐维结果、三轮共
36 条系统—人工对照以及 9 条逐轮分档校准结果。公开包删除评审者身份、Bundle ID、评语、私有路径和模型原始响应，并使用闭合
清单及 SHA-256 防止文件被替换或额外混入：

```bash
hy3-reproeval verify-human-consensus-results \
  --bundle results/real_paper_human_consensus
```

公开包 manifest SHA-256 为
`8BE621BE084A2F18449B4CF4CDCB49DF6374F759AA4F681B8BE8CE3D5E2D7B5A`。该哈希证明当前公开文件集合
未发生变化，不证明匿名评审者身份或评分本身正确。

## 结论边界

- 真实的是论文来源和人工评分过程；高、中、低报告仍是策展草稿与登记 Mutation 构造的评测对象。
- 本 Pilot 没有执行论文软件、复现实验结果或验证论文结论，不能写成论文已复现。
- 评测规模仅为 4 个 validation/test 来源组和 12 份报告，同模板 Mutation 会降低样本独立性。
- 三位评审者的身份、专业背景、独立性和盲化状态仍是自我声明，不构成外部资质认证。
- 高档 Hy3 候选的签核是独立流程；本轮盲评不会自动把候选复核表从 `pending` 改为 `approved`。
