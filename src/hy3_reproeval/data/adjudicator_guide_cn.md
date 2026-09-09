# ReproEval 第三人裁决工作包

本工作包只包含两位独立评审者产生分歧的报告和维度。你会看到匿名的 `parent-001` 与
`parent-002` 意见，但不会看到原评审者身份、质量档位、Mutation 或 Hy3 系统分数。

## 操作步骤

1. 阅读 `assignment.json` 中的 Rubric、争议原因和两条匿名证据轨迹。
2. 阅读 `reports/` 中对应报告，并用 `sources/` 中的源材料核查事实。
3. 只编辑 `responses.json`；不要修改 assignment、报告、来源或本说明。
4. 对模板中列出的每个争议维度给出最终 `status`、`score`、`rationale`、报告行号和错误码。
5. `factual_accuracy`、`evidence_traceability`、`numerical_consistency` 若为 `assessed`，还必须填写
   `source_evidence`，引用 `source-001` 等匿名来源及其行号。
6. 行号可写为整数 `9` 或显示形式 `L000009`；来源行可使用 `evidence_lines` 或 `lines` 字段。

## 评审者声明

请填写 `annotation_date` 与 `annotator_profile`。由于本轮会看到匿名父意见，
`independent_annotation` 必须为 `false`；若你未查看 Hy3 或其他系统评分，
`blind_to_system_scores` 填 `true`。只有已完成 Rubric 阅读、披露利益冲突且不存在利益冲突时，
其余资格字段才可按要求填写为 `true/true/false`。

匿名父意见不是投票结果。请以报告、源材料和公开 Rubric 为依据独立作出裁决；若证据不足，使用
`insufficient_evidence`、保持 `score=null` 并说明缺失证据。完成后原样返回整个目录或压缩包。
