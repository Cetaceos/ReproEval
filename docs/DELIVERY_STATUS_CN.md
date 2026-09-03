# ReproEval 最终交付状态

> 核对日期：2026-09-03
>
> 任务：犀牛鸟实战任务一“开放式场景：AI 应用与评判标准设计”
>
> 最终提交日期：2026-09-11

## 1. 当前结论

任务一要求的应用、评估方法、分档数据、判别力实验和重复一致性实验已经形成可运行闭环。当前唯一明确的必交阻塞项是重新录制一段不超过 2 分钟、展示 ReproEval 当前版本的最终演示视频或 GIF。

真实专家标签、系统—人工一致性和真实论文 held-out 实验仍能显著提高项目可信度，但任务书允许使用“同一输出多次评估的分数波动”完成一致性验证，因此它们属于终稿前的优先增强项，不应被描述为已经完成，也不阻止当前主闭环成立。

## 2. 任务书逐项核对

| 任务书要求 | 状态 | 当前证据 | 仍需处理 |
| --- | --- | --- | --- |
| 独立公开仓库并标明个人活动作品 | 已完成 | README 首屏明确说明项目性质 | 将本地 3 个提交 push 后确认 GitHub 展示正常 |
| README、运行方法和环境要求 | 已完成 | [`README_CN.md`](../README_CN.md)、[`.env.example`](../.env.example)、[`.mcp.json`](../.mcp.json) | 最终检查链接和安装命令 |
| 基于 Hy3 的可运行 AI 应用 | 已完成 | 10 个 stdio MCP Tool，两条端到端流程，真实 Hy3 API 验证 | 保留 API 渠道与模型标识说明 |
| 明确目标用户、问题和使用大模型的必要性 | 已完成 | README、[项目方案](PROJECT_PROPOSAL_CN.md) | 终稿摘要保持简洁 |
| 至少 5 个可操作评估维度 | 已完成 | 7 维版本化 Rubric 与 0–4 分锚点 | 无 |
| 自动或半自动评测流程 | 已完成 | Validators、Hy3 Judge、replay Benchmark、人工 Bundle 接口 | 无 |
| 样本来源、构造和覆盖范围 | 已完成 | [P0 数据集](P0_DATASET.md)、[P1 数据集](P1_TRANSFER_DATASET.md)、Dataset Freeze | 明确公开数据均为仓库合成材料 |
| 难例和反例 | 已完成 | P0 的 44 份分档/对抗报告及 8 份 adversarial report，P1 的 10 个 Mutation | 不外推为真实攻击鲁棒性 |
| 判别力验证 | 已完成 | [P1 三轮结果](../results/p1_transfer_judge/summary.md)：三轮组内排序均为 100% | 明确这是合成档位判别力 |
| 一致性验证 | 已完成（重复稳定性） | 15/15 报告完整评分，总分标准差最大值 3.535534，0 次质量带翻转 | 人工一致性仍待增强 |
| 完整结果表格 | 已完成 | 运行级、报告级、维度级 CSV 与 SHA-256 manifest | 无 |
| 典型 Case 归因和失败模式 | 已完成 | [P1 实验报告](P1_JUDGE_EXPERIMENT_CN.md) | 最终答辩突出 `reasoning_gap` 和中档偏高 |
| 对抗性验证 | 部分完成（鼓励项） | 对抗类型、Mutation、检测指标和确定性协议已实现 | 尚无 P1 真实 Hy3 对抗运行和专家确认 |
| 人工标注接口 | 已完成（增强基础设施） | [盲审工作包](ANNOTATION_PACKET.md)、一致性分析和裁决共识 | 尚未取得两名真实专家 Bundle |
| Skill 适配 | 已完成（P1 增强） | [`reproeval-research-audit`](../skills/reproeval-research-audit)、[Skill 文档](SKILL_ADAPTER.md) | 可在支持 Skills 的客户端补一次调用截图 |
| 2 分钟以内演示 | 待完成，阻塞最终提交 | 旧 ReproScope 客户端证据不能完整代表当前 ReproEval | 录制当前版本的应用调用与评测结果 |

## 3. 已公开的核心实验

P1 实验在同一个冻结数据集上完成 3 次独立真实 Hy3 Judge 运行，共产生 45 次成功调用。公开结果包只包含聚合 Markdown/CSV 和密码学血缘，不包含 API Key、请求体或原始响应。

```bash
hy3-reproeval verify-results-export --bundle results/p1_transfer_judge
```

当前公开 manifest SHA-256：

```text
DD3BDAC5F5E204E2BACB2BD4DF22835065BC0C96E0136D0272DFE5D173A83072
```

该实验支持“当前评估器能够稳定区分这组合成迁移报告”的有限结论，不支持真实部署可行性、专家一致性或未见材料泛化结论。

## 4. 尚未完成的证据

### 4.1 最终演示

最终演示必须展示当前 ReproEval，而不是只展示迁移前的 ReproScope：

1. 客户端发现 `hy3-reproscope` MCP Server；
2. 选择论文复现或技术迁移场景并实际调用关键 Tool；
3. 展示 MCP 返回的 `run_id`、工件路径和证据不足/警告信息；
4. 展示最终 Markdown 报告；
5. 展示一次 `hy3-reproeval` 结果校验或公开 P1 结果表；
6. 总时长控制在 2 分钟以内，不显示 API Key、本地用户名或私有目录内容。

### 4.2 人工一致性

若能邀请两名具有科研阅读经验的标注者，应优先标注 P1 的 12 份 validation/test 报告。完成后运行：

```bash
hy3-reproeval validate-annotations ...
hy3-reproeval analyze-annotations ...
hy3-reproeval finalize-annotations ...
```

只有真实 Bundle 和可核对的实验记录存在后，才能在终稿中报告 Kappa、系统—人工 Spearman、MAE 或裁决结果。不得用测试中自动填充的 Bundle 代替专家标注。

### 4.3 真实材料泛化

当前 P0/P1 Dataset 都是可公开、可复现的合成协议数据。若时间允许，可增加少量具有合法来源和明确许可边界的真实论文或开源方案案例；若无法完成，应直接保留“合成数据验证”限定，不把公开元数据候选升级为专家真值。

## 5. 9 月 11 日前建议顺序

| 日期 | 工作 | 完成标准 |
| --- | --- | --- |
| 9 月 3 日 | push 当前 3 个本地提交并观察 CI | GitHub `main` 与本地同步，Python 3.11–3.13 全部通过 |
| 9 月 4–5 日 | 组织双人盲评，或确认无法获得专家资源 | 有真实 Bundle，或在报告中明确未完成原因 |
| 9 月 6 日 | 可选：补真实 Hy3 对抗运行或少量合法真实案例 | 生成可验证结果；失败时不影响主线 |
| 9 月 7–8 日 | 录制并剪辑最终演示 | 时长不超过 2 分钟，无密钥和 traceback |
| 9 月 9 日 | 整理最终分析与 README 入口 | 结果、失败模式、边界和演示链接可从首屏访问 |
| 9 月 10 日 | 在干净环境做发行验收 | 安装、MCP 初始化、测试、结果验签均通过 |
| 9 月 11 日 | 提交最终仓库链接和材料 | GitHub CI 绿色，提交内容与仓库版本一致 |

## 6. 最终提交前命令

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -e . --no-deps
python -m pytest
python -m ruff check src tests scripts
python -m ruff format --check src tests scripts
python -m hy3_reproeval build-p0-dataset --output evals/p0_dataset --check
python -m hy3_reproeval build-p1-transfer-dataset --output evals/p1_transfer_dataset --check
python -m hy3_reproeval verify-results-export --bundle results/p1_transfer_judge
python -m build
python scripts/check_distribution.py dist --version 0.34.0
```

在提交前还需执行 `git status`，确认真实 `.mcp.json`、`.env`、私有标注、原始 Judge Record、录屏原文件和 `.reproeval` 均未进入暂存区。
