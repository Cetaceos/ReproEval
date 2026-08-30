# Hy3 ReproEval

[English](README.md)

Hy3 ReproEval 是一个面向开放式科研报告的 Hy3 多工具应用与可信评测框架。项目以论文复现审查为主场景，并将技术方案迁移评估保留为跨场景泛化案例。

本项目是为 2026 腾讯犀牛鸟开源课题实战开发的个人作品，不是腾讯官方产品。

## 当前进度

第一阶段迁移已经完成。本仓库已纳入 [Tencent-Hunyuan/Hy3 PR #187](https://github.com/Tencent-Hunyuan/Hy3/pull/187) 中经过验证的 ReproScope 应用层，包括：

- 10 个 stdio MCP Tool，覆盖论文复现、方案迁移、证据图、报告和只读仓库审计；
- 本地统计重算、Schema 校验、来源哈希、工件血缘和证据不足拒答；
- 合成示例、离线评测集、在线验证门禁和 269 个迁移测试；
- 对原有 `hy3_reproscope_mcp` 模块和 `hy3-reproscope-mcp` 命令的兼容。

版本化七维 Rubric、确定性校验器、受限 Hy3 语义 Judge 和盲化重复报告比较已经实现。模型判断不能覆盖本地引用、数值、工件或硬性分数上限结论。人工标注和 Benchmark 分析仍在开发中，详见[项目方案](docs/PROJECT_PROPOSAL_CN.md)。

## 架构

```text
论文材料 + 复现实验结果
          |
          v
   ReproScope 应用生成层
Hy3 语义提取 + Python 本地校验
          |
          v
   可追溯报告与结构化工件
          |
          v
    ReproEval 质量评估层
规则校验 + Hy3 Judge + 人工标签
```

Hy3 负责语义提取和证据关系判断；本地 Python 负责数值重算、Schema 与引用校验、工件血缘和固定规则聚合。模型输出不能覆盖本地重新计算的事实。

## 快速开始

要求 Python 3.11 或更高版本，以及可用的 Hy3 兼容接口。

```bash
git clone https://github.com/Cetaceos/ReproEval.git
cd ReproEval
python -m venv .venv
```

Windows：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Linux / macOS：

```bash
./.venv/bin/python -m pip install -e .
```

请将 `.env.example` 中的变量加载到父进程，或通过 MCP 客户端提供。程序不会自动读取 `.env` 文件，不得提交真实 API Key。

```text
HY3_API_PROVIDER=tokenhub
HY3_BASE_URL=https://tokenhub.tencentmaas.com/v1
HY3_API_KEY=replace-with-your-key
HY3_MODEL=hy3-preview
REPROSCOPE_ALLOWED_ROOTS=.
REPROSCOPE_WORKSPACE=.reproeval/reproscope
```

通过 stdio 启动 MCP Server：

```bash
hy3-reproeval-mcp
```

已有客户端仍可继续使用兼容命令：

```bash
hy3-reproscope-mcp
```

项目级客户端配置可参考 [.mcp.json](.mcp.json)，使用时需替换占位路径，并在私有配置中注入密钥。

## 报告评估

以下公开样例无需 API Key：

```bash
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --output evaluation.json
```

Case Manifest 登记合法来源定位、必需主张与章节、数值期望、不确定性短语和工件哈希。评估结果包含维度分数、证据位置、错误标签、已评估权重、硬性分数上限、Manifest 与 Rubric 指纹和机器可读质量结论。

以下命令使用公开的合成 Judge 记录，无需 API Key：

```bash
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --judge replay \
  --judge-record examples/evaluation/sample_judge_record.json \
  --output hybrid-evaluation.json
```

在线调用 Hy3 Judge 并保存可回放记录：

```bash
hy3-reproeval evaluate-report \
  --case examples/evaluation/sample_case.json \
  --judge online \
  --judge-record judge-record.json \
  --output hybrid-evaluation.json
```

在线模式读取现有 `HY3_*` 环境变量。回放记录仅在 Prompt 版本、Case、场景、报告、Rubric、请求和结构化响应指纹全部匹配时生效。没有确定性或语义证据的维度保持 `insufficient_evidence`，已评估权重低于 50% 时不输出总分。评分边界和限制详见 [EVALUATION_CORE.md](docs/EVALUATION_CORE.md)。

## 盲化重复比较

使用公开的三次合成回放记录，比较采用同一确定性评测契约的两份报告：

```bash
hy3-reproeval compare-reports \
  --left-case examples/evaluation/sample_case.json \
  --right-case examples/evaluation/sample_case_variant.json \
  --comparison-id sample-pairwise-v1 \
  --repeats 3 \
  --judge replay \
  --judge-record examples/evaluation/sample_pairwise_judge_bundle.json \
  --output pairwise-result.json
```

Prompt 不包含 Case ID 和文件路径，交替将两份报告呈现为 A，并仅让 Hy3 判断两个语义维度。Python 将语义分数与各报告的确定性贡献和 hard cap 合并，输出分数标准差、排序翻转率、质量等级翻转和观察到的 A/B 位置差值。公开 Bundle 是用于验证协议的合成回放数据，不代表真实模型 Benchmark。详见 [PAIRWISE_COMPARISON.md](docs/PAIRWISE_COMPARISON.md)。

## 已迁移的 MCP Tools

| Tool | 功能 |
| --- | --- |
| `reproscope_extract_claims` | 提取论文实验主张和可选领域证据 |
| `reproscope_compare_results` | 对齐指标并重新计算复现实验统计量 |
| `reproscope_score_paper` | 执行六维证据充分性评估 |
| `reproscope_build_evidence_graph` | 构建论文证据图 |
| `reproscope_render_report` | 生成论文复现审查报告 |
| `reproscope_extract_solution_profile` | 提取结构化技术方案画像 |
| `reproscope_assess_transfer` | 评估迁移条件、风险和证据缺口 |
| `reproscope_build_transfer_graph` | 构建技术迁移证据图 |
| `reproscope_render_transfer_report` | 生成技术迁移决策报告 |
| `reproscope_audit_repository` | 静态审计 Python 仓库的复现条件 |

## 开发验证

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install -e . --no-deps
python -m pytest
python -m ruff check src tests scripts
python scripts/run_offline_eval.py
python scripts/run_transfer_offline_eval.py
```

在线验证脚本仅在显式提供 Hy3 API Key 时运行，并在保留工件前执行输出安全检查。

## 目录结构

```text
src/hy3_reproeval/          ReproEval 公共包和 CLI
src/hy3_reproscope_mcp/     迁移后的应用与 MCP 兼容层
tests/                      单元、集成、stdio、安全和工件测试
examples/                   公开合成输入与 MCP 客户端配置
evals/                      已迁移的确定性评测样例
scripts/                    离线评测、在线验证、打包与证据检查脚本
docs/PROJECT_PROPOSAL_CN.md 实战阶段设计和交付计划
docs/EVALUATION_CORE.md     确定性评估器契约和能力边界
docs/reproscope/             ReproScope 验证证据与历史材料
```

兼容性和来源说明见 [MIGRATION.md](docs/MIGRATION.md)。
版本更新记录见 [CHANGELOG.md](CHANGELOG.md)。

## 安全与能力边界

- API Key 和私有科研材料不得进入版本控制；
- 仓库审计仅执行静态分析，不运行第三方代码；
- 系统评估当前材料中的证据，不判断学术不端，也不提供法律结论；
- 报告和评分用于辅助专家复核，不能替代专家判断。

## 许可证

Apache License 2.0，详见 [LICENSE](LICENSE)。
