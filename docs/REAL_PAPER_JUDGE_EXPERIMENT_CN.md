# 真实论文 Pilot 三轮 Hy3 Judge 实验

## 实验范围

本实验评估 `reproeval-real-paper-pilot` Dataset `0.2.0` 中的 6 个真实开放获取论文来源组和 18 份
高、中、低档候选报告。论文来源真实，但高档标签仍是 `curator_draft`，中低档报告由登记 Mutation 构造；
因此本实验检验当前评估器对这组报告的判别力和重复稳定性，不等同于专家有效性或论文结果复现。

## 固定配置

| 项目 | 值 |
| --- | --- |
| 模型 | `hy3` |
| Provider | Tencent Cloud TokenHub |
| 独立运行次数 | 3 |
| 每轮报告数 | 18 |
| 成功 Judge 调用 | 54 |
| Dataset Manifest SHA-256 | `138CA40FF966ABAF6B9856619A474A2A12926EE8BA3CA90EA8570AC3558CD470` |
| Dataset Freeze SHA-256 | `90AB080294B1050FBBAB612EE93E6BC7C79AA4E02A13746E11E28A52C1A97D04` |
| Rubric | `0.1.0`，7 个维度 |

三轮使用不同 `run_id`，每轮 Judge Record Index、Benchmark、稳定性结果和聚合导出均绑定同一 Dataset
Freeze。完成后使用 `--resume` 进行了无新增 API 调用的全量复验。

## 主要结果

| 指标 | Run 1 | Run 2 | Run 3 |
| --- | ---: | ---: | ---: |
| Pairwise accuracy | 100% | 100% | 100% |
| Complete-order accuracy | 100% | 100% | 100% |
| Macro group Spearman | 1.0 | 1.0 | 1.0 |
| 已登记错误召回率 | 100% | 100% | 100% |
| 意外错误标签数 | 1 | 0 | 0 |

18/18 份报告在三轮中均得到完整评分。报告总分标准差均值为 `0.392837`，最大值为 `3.535534`，
满足预注册的 `<= 5` 目标；质量档位、排序资格和评估状态均没有翻转。非零波动集中在
`real-paper-04-lyceanem-low` 和 `real-paper-06-cdcam-high`，两者标准差均为 `3.535534`。

Run 1 将 `real-paper-06-cdcam-high` 额外标记为 `reasoning_gap`，后两轮没有重复该判断。该结果应作为
模型语义判断波动记录，不能删除，也不能把“已登记错误召回率 100%”表述成零误报。

## 公开结果

仓库仅公开聚合 Markdown、CSV 和哈希清单，不公开 API Key、请求体、原始响应或逐条 Judge Record：

```powershell
hy3-reproeval verify-results-export --bundle results/real_paper_judge
hy3-reproeval verify-results-figures \
  --figures results/real_paper_judge_figures \
  --source-bundle results/real_paper_judge
```

公开 Export Manifest SHA-256：

```text
266DDCEFF6B734B753CF98E3B2123C027D2F470F61CDF62F4D71BEB9DF2DBAD8
```

图表包包含质量档位分数和逐维稳定性两张确定性 SVG。Figure Manifest SHA-256 为
`D6344E3C4779FFE116AA06DF103A9DC44FDAC63874F143FACD668823E312D459`。

## 人工验证状态

同一 Freeze 上的两套独立随机顺序工作包均已回收并通过完整性校验，覆盖全部 12 份 validation/test
报告。双人二次加权 Kappa 为 `0.964225`，三轮系统—人工 Spearman 为 `0.988483`、`1.0` 和
`0.988483`。4 个 `factual_accuracy` 错误码分歧已由第三位评审者解决，最终 12/12 份目标报告形成
人工共识，`consensus_ready=true`。按最终共识重新计算的三轮 MAE 分别为 `15.791667`、`15.166667`
和 `14.541667`，说明中档高估仍是主要校准误差；低档也存在 `11.125–13.0` 分的持续高估。
人工来源和专业背景是自我声明，不构成身份或资质证明。详见[人工验证报告](REAL_PAPER_HUMAN_VALIDATION_CN.md)。

最终共识及逐轮系统—人工对照已脱敏导出到 `results/real_paper_human_consensus`，可执行：

```bash
hy3-reproeval verify-human-consensus-results --bundle results/real_paper_human_consensus
```

此外，本 Pilot 未执行六个第三方软件项目，没有产生独立实验测量，也不包含 adversarial report。结果只支持
“Hy3 Judge 能在当前构造的真实来源报告组上稳定恢复预设档位顺序”这一有限结论。
