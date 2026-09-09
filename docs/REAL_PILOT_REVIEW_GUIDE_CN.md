# 真实论文 Pilot 双人盲评操作手册

本手册用于 `evals/real_paper_pilot` 的 validation/test 集。每位标注者独立评审 12 份匿名报告，不能接触
Dataset Manifest、质量档位、Mutation、系统分数或另一位标注者的答案。

## 协调者准备

```powershell
# 当前实验 Freeze 已由 run-judge-experiment 创建并完成复验：
hy3-reproeval verify-dataset-freeze `
  --manifest evals/real_paper_pilot/dataset.json `
  --freeze .reproeval/real-paper-judge-experiment/dataset_freeze.json

hy3-reproeval prepare-annotation-packet `
  --manifest evals/real_paper_pilot/dataset.json `
  --dataset-freeze .reproeval/real-paper-judge-experiment/dataset_freeze.json `
  --output-dir private_annotations/real-pilot-v0-2-reviewer-a `
  --assignment-id real-pilot-v0-2-independent-a `
  --annotator-id reviewer-a `
  --bundle-id real-pilot-v0-2-bundle-a
```

当前已生成两套工作目录及对应的 `*-blind.zip`。为第二位标注者重复命令时需替换全部 `a` 标识。只发送各自的 `annotator/` 目录或盲审压缩包；
`coordinator_manifest.json` 必须由协调者保留。

## 标注者操作

1. 阅读 `annotator/assignment.json` 中的说明、七维 Rubric、评分锚点和各维度允许的错误类型。
2. 对 `reports/` 中每份报告逐维评分，同时核对 `sources/` 中对应匿名证据包。
3. 仅编辑 `annotator/responses.json`，不要修改报告、来源、assignment 或 Rubric。
4. 填写日期、专业背景、独立完成、对系统分数盲化、Rubric 培训和利益冲突声明。
5. 每个 `assessed` 维度给出 0–4 分、理由和报告行号。
6. 事实准确性、证据可追溯性和数值一致性还必须填写来源文件及来源行号。
7. 无法评价时使用 `insufficient_evidence`，不得为了完成表格猜测分数。

标注者不需要判断论文是否造假，也不需要运行第三方代码。评审对象是报告是否忠实、可追溯、数值正确、
推理合理、正确处理不确定性，并给出可执行验证计划。

## 回收与验签

协调者将返回的 `annotator/` 放回原私有目录后执行：

```powershell
hy3-reproeval finalize-annotation-packet `
  --manifest evals/real_paper_pilot/dataset.json `
  --dataset-freeze .reproeval/real-paper-judge-experiment/dataset_freeze.json `
  --packet-dir private_annotations/real-pilot-v0-2-reviewer-a `
  --output private_annotations/real-pilot-v0-2-bundle-a.json
```

第二位标注者完成后，将两份 Bundle 同时传给 `validate-annotations` 和 `analyze-annotations`。如果出现状态
冲突、错误类型冲突或维度分差超过 1 分，保留裁决队列并组织第三位评审；不得直接改写原始独立标注。

## 结论边界

- 人工评分是独立参照，不进入对应测试样本的 Hy3 Prompt。
- `benchmark_ready=true` 只表示覆盖和协议条件满足，不证明标注者身份或结论必然正确。
- 当前 Pilot 是复现条件审查；没有实际运行记录时不能写成论文结果已复现。
- `private_annotations/` 和 `.reproeval/` 已被 Git 忽略，任何真实身份信息也不得提交。
