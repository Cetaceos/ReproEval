# Hy3 高档候选报告生成与人工复核

本流程用于真实论文 Pilot 的高档参考候选。它不会直接改写 Dataset，也不会把 Hy3 输出自动标为人工真值。

当前 Dataset `0.2.0` 的六份候选复核表均保持 `pending`。本次实验不采用这些候选，也不把候选人工审核
列为当前 Dataset 的完成门槛；该流程作为后续独立研究支线保留。未来若完成审核并采用候选，必须发布
新的 Dataset 版本、重建 Mutation、重新冻结并重新执行 Judge 与人工实验。

## 1. 前置门禁

1. 从 `evals/real_paper_pilot/dataset.json` 的 `paper_url` 下载 6 份 PDF 到私有目录
   `.reproeval/source_cache`，文件名依次为 `opticommpy.pdf`、`pyngham.pdf`、`differt2d.pdf`、
   `lyceanem.pdf`、`itmlogic.pdf` 和 `cdcam.pdf`。
2. 执行来源核验：

```powershell
hy3-reproeval verify-real-paper-sources `
  --source-dir .reproeval/source_cache `
  --output .reproeval/real-source-verification.json
```

通过标准为：6 份 PDF 哈希一致、共 30 条摘录均能在声明页码中找到。该结果只证明来源一致，不证明软件
已运行或论文结果已复现。

## 2. Hy3 重新生成

在父进程私有环境中设置 `HY3_API_KEY`、`HY3_BASE_URL`、`HY3_MODEL=hy3` 等变量，然后执行：

```powershell
hy3-reproeval generate-real-paper-references `
  --manifest evals/real_paper_pilot/dataset.json `
  --output-dir .reproeval/real-paper-reference-candidates
```

每组输出：

- `candidate.md`：Hy3 结构化结果经固定模板渲染后的候选报告；
- `generation_record.json`：模型、Provider、Prompt 版本、输入与输出哈希及结构化响应；
- `review_form.json`：状态默认为 `pending` 的人工复核表；
- 根目录 `index.json`：覆盖 6 组的只读生成清单。

程序固定写入“复现条件审查而非独立复现结果”的边界，并固定使用 Dataset 登记的数值。Hy3 负责中心主张、
证据解释、限制和下一实验的语义生成；未知 Evidence ID 会被拒绝。

## 3. 人工复核

实际评审者逐组打开论文 PDF、`source_material.md`、`candidate.md` 和 `review_form.json`，检查：

1. 论文 PDF 的哈希与登记值一致；
2. 报告使用的 Evidence ID 与页码、章节和摘录一致；
3. 登记数值和单位正确；
4. 没有把论文陈述写成独立复现结果；
5. 关键限制没有被弱化或省略；
6. 下一实验包含环境、命令或输入、输出和比较准则；
7. 不存在来源无法支持的新主张。

全部满足时填写去标识化 `reviewer_id`、日期、专业背景，将七项 checklist 设为 `true`，保持 `findings=[]`，
并将状态设为 `approved`。任何问题未解决时使用 `rejected` 并记录 `findings`，不得勉强批准。

```powershell
hy3-reproeval validate-reference-reviews `
  --manifest evals/real_paper_pilot/dataset.json `
  --bundle-dir .reproeval/real-paper-reference-candidates `
  --require-approved `
  --output .reproeval/real-paper-reference-review-validation.json
```

只有该命令通过后，候选才具备进入下一次 Dataset 修订的条件。是否将其提升为 `human_reviewed` 仍需一次
显式的数据版本升级、Mutation 重建和 Dataset Freeze；本流程不会静默修改公开标签。

## 4. 真实性边界

- Codex、Hy3 或单元测试不能代替真实人工审核。
- `approved` 是评审者的协议声明，不是身份认证或同行评审证明。
- 真实论文来源不等于真实复现实验；当前 `study_mode` 仍是 `reproducibility_readiness`。
- 私有 API 响应、评审身份和 PDF 缓存位于 `.reproeval/`，不应提交到 Git。
