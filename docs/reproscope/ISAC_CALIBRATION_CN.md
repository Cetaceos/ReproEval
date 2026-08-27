# ISAC 校准层边界

本文件描述 0.16 方向的第一步工程化工作：为 ISAC Profile 提供显式标注驱动的离线校准接口。它不是新的 MCP Tool，也不改变 0.15.0 的 Artifact Schema、Generic reliability score 或 ISAC 自动激活阈值。

## Evidence Card

每个案例包含一个 `label` 和至少一个 `prediction`：

- `case_id`：稳定的案例 ID；
- `split`：`development`、`calibration`、`held_out`、`negative` 或 `demo`；
- `expected_isac`：人工或合成材料是否应当被识别为 ISAC；
- `expected_risk_rule_ids`：该案例应命中的风险规则 ID 集合；
- `expected_citations` 与 `expected_unsupported_assertion_ids`：引用正确性和应拒答断言的显式标签；
- `annotation_source`：`expert`、`reviewed` 或 `synthetic`；
- `group_id`：论文、仓库、场景或作者变体的稳定分组键；同一分组不能跨 split；
- `content_hash`：可选的脱敏源材料 SHA-256，用于发现不同 case ID 的重复材料；
- `predictions`：同一案例的一次或多次已记录预测，用于主预测指标和 inter-run stability。

`ISACEvidenceCard` 和 `ISACPrediction` 使用 Pydantic 严格校验，拒绝重复或格式错误的规则 ID。当前规则 ID 只校验 `ISAC-Rddd` 形状；是否属于当前注册表仍由现有 Profile 归一化层负责。

## 输出指标

`evaluate_isac_calibration` 只做描述性统计：

- 激活 precision、recall、F1、TP/FP/TN/FN；
- false activation rate；
- 风险规则集合的 precision、recall、F1；
- 引用集合的 precision、recall、F1，以及 unsupported assertion rate；
- 引用 exact-set accuracy（只在含引用标签或预测的案例上计算）；
- 针对显式 unsupported 标签的 correct abstention rate（CAR）；
- 预期拒答案例的 correct abstention rate；
- 有多次预测的案例的 inter-run stability；
- 各 split 的同类指标和缺失 split 警告。

没有标注时不生成指标。分母为零的指标返回 `null`，不被改写为 0。报告固定为 `descriptive_calibration`，不能据此宣称领域 benchmark、专家一致性或 held-out 泛化能力。

报告中的 `uar`（Unsupported Assertion Rate）是被标注为 unsupported、但模型仍输出的断言数除以模型输出断言数；`car`（Correct Abstention Rate）是对标注为 unsupported 的断言正确不输出的比例。二者只在 Evidence Card 明确提供 `expected_unsupported_assertion_ids` 时有分母，不能用合成回归 fixture 宣称真实领域准确率。

## 人工标注导入与无泄漏划分

真实校准集通过 `load_expert_calibration_cases` 导入。它要求顶层 `annotation_policy` 为 `expert`、`reviewed` 或 `mixed`，拒绝 `synthetic` 标签，并要求同时存在 `calibration` 与 `held_out` split：

`evals/isac_expert_annotation_template.json` 是人工标注交付模板，不是数据集；其中的空 `cases` 必须由外部标注流程替换，仓库不会把候选论文或合成案例升级成专家真值。

```bash
python scripts/run_isac_calibration.py \
  --fixture path/to/human_isac_calibration.json \
  --require-human-annotations \
  --select-threshold \
  --max-false-activation-rate 0.05
```

`--select-threshold` 只使用 calibration split 中带 `confidence` 的预测选择激活阈值，然后把冻结阈值应用到所有 split；held-out 不参与选择。加载和评估都会拒绝同一 `group_id` 或 `content_hash` 跨 split，防止同一论文/场景泄漏到 held-out。仓库不伪造专家标签；外部标注者应在导入前补齐脱敏片段、精确页/行定位、标注来源和分歧处理记录。

使用 `--require-human-annotations` 时，协议还必须提供去标识的 `annotator_ids`、`adjudicator_id`、仲裁记录 ID、标注协议版本、观察到的标注一致性指标，以及覆盖每个案例的 `source_manifest`。清单中的 SHA-256 必须与 Evidence Card 的 `content_hash` 一一匹配；缺少案例、额外案例或摘要不一致都会拒绝导入。这些字段是可审计的来源声明，不会把声明本身当作专家真值。

报告额外包含 `label_fingerprint` 和 `prediction_fingerprint`。前者在改变阈值或重跑预测后保持不变，后者随预测变化；两者都只对规范化的脱敏结构计算 SHA-256，不会把全文或用户路径写入公开产物。一个案例的多次预测必须使用不同的 `run_id`，避免重复记录虚增稳定性。

## 当前状态

`evals/synthetic_isac_calibration.json` 是公开、合成的回归 fixture，覆盖四类 split 和重复预测稳定性。它只证明计算路径和边界行为，不代表真实论文样本、专家标注或 0.16 校准结果。

## 公开论文候选集

`evals/isac_public_candidate_cases.json` 保存了通过 Crossref 公开元数据选出的 3 个 ISAC/雷达通信正例候选和 2 个雷达单领域负例候选。每条记录包含 DOI、题名、年份、来源 URL、来源定位符 SHA-256 和当前工程候选标签；其中一个负例还保留了 Crossref 的公开摘要摘录。`source_locator_sha256` 只校验 DOI 定位符，不是全文内容哈希。该文件有意不直接作为 `ISACCalibrationCase` fixture：标签只基于公开元数据或单人初审，没有两名独立领域专家和仲裁记录，因此不能用于宣称引用准确率、风险规则准确率、UAR/CAR 或 held-out 泛化能力。

要把候选集升级为真实校准集，必须为每个案例补充脱敏全文片段和页/行定位符，由至少两名 ISAC 领域标注者独立填写 Evidence Card，再由第三人处理分歧并冻结 development/calibration/held-out/negative 划分。只有完成这一步后，`run_isac_calibration.py` 的输出才可以作为真实校准结果；在此之前，脚本结果仍固定标记为 `descriptive_calibration`。

`load_calibration_cases` 默认要求 fixture 的 `profile_version` 等于当前安装的 ISAC Profile 版本；版本不匹配会在库 API 层拒绝，避免脚本入口之外的调用误把旧标注集当作当前校准结果。

真实校准仍需外部补充：

1. 由领域专家标注的 development/calibration/held-out/negative 案例；
2. 每个规则的证据卡、引用正确性和错误激活定义；
3. 在不参与阈值调节的 held-out 集合上重新运行；
4. 发布前保存脱敏的版本、Profile/registry hash、run ID 和结果 artifact。

运行合成回归：

```bash
python scripts/run_isac_calibration.py
```
