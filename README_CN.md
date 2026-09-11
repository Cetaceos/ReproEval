# ReproEval

[English](README.md) | 简体中文

ReproEval 是一个基于 Hy3 的科研证据审查与开放式报告评测项目。它通过 MCP Server 向 CodeBuddy、
WorkBuddy、VS Code/Copilot、Cursor 和 Cline 等客户端提供论文复现审查与技术方案迁移评估能力，并用
版本化量表、确定性数值校验、数据溯源和人工盲评约束大模型结论。

本仓库是腾讯犀牛鸟“开放式场景：AI 应用与评判标准设计”实战任务的个人作品。

## 核心亮点

| 能力 | 实现 |
| --- | --- |
| 双主线应用 | 论文复现证据审查，以及技术方案面向新场景的条件化迁移评估。 |
| Hy3 与确定性程序协作 | Hy3 负责语义理解与结构化判断，Python 负责统计重算、Schema 校验、哈希和输入输出关系检查。 |
| 10 个 MCP Tool | 从材料读取、主张提取、结果对比、评分、证据关系图到 Markdown 报告均可由 stdio 客户端编排。 |
| 可复核评测体系 | 7 维量表、好/中/差与对抗样本、三轮 Hy3 Judge、双人盲评和第三人裁决均有版本化协议。 |
| 真实来源与实际执行 | 真实论文 Pilot 包含 6 篇开放获取论文；DiffeRT2d v0.3.4 Figure 2 已在冻结环境中实际执行。 |
| 可追溯输出 | 每一步返回 `run_id` 和相对结果路径，并记录输入哈希、直接依赖、警告和运行状态。 |

## 系统设计

```text
MCP 客户端
   |
   +-- 论文材料 + 复现结果 --> Hy3 主张提取 --> Python 指标重算 --> 六维可靠性评估
   |                                                    --> 证据关系图 --> 中/英文报告
   |
   +-- 源方案 + 目标背景 ----> Hy3 方案画像 --> 条件、风险与改造分析
                                                        --> 迁移关系图 --> 中/英文报告

评测层：7 维 Rubric --> 冻结数据集 --> Hy3 Judge --> 稳定性/判别力 --> 人工盲评与裁决
```

### 两个评分层级

| 层级 | 评估对象 | 主要维度 |
| --- | --- | --- |
| 应用六维可靠性评分 | `reproscope_score_paper` 根据论文及复现证据判断结论可信度 | 结果一致性、设置透明度、基线、消融、统计报告、实现可用性 |
| 报告七维质量评测 | ReproEval Judge 与人工盲评检查系统生成的整份报告 | 事实准确性、证据可追溯性、数值一致性、推理一致性、不确定性处理、内容完整性、清晰度与可操作性 |

前者是论文复现流程的应用结论，后者用于评价该结论及报告的生成质量；两套量表相互独立，七维评测
不会回写或替代六维可靠性评分。

模型输出不能覆盖本地重新计算的数值或结构校验结果。证据不足的维度返回 `insufficient`，而不是被
机械记为零分；迁移评估在缺少目标实测数据时不会给出精确性能预测。

## 最终演示

[下载或在线观看 WorkBuddy 双主线演示（1080p MP4，2 分 50 秒）](docs/assets/reproeval-workbuddy-final-demo.mp4)

视频展示 WorkBuddy 发现 10 个 Tool，并以 DiffeRT2d 的公开论文和实际 Figure 2 执行证据完成论文审查，
随后评估该方案迁移到三维 UAV-BS ISAC 研究流程的条件、风险与验证路径。录屏中的 API 调用与结果均为
真实运行；结论只覆盖展示的输入和固定案例，不代表整篇论文或传播模型物理正确性已经得到验证。

详细录制输入和验收边界见 [WorkBuddy 演示手册](docs/WORKBUDDY_FINAL_DEMO_CN.md)。

## 快速开始

要求 Python 3.11–3.13，以及可用的 Hy3 OpenAI-compatible API。项目默认示例使用腾讯云 TokenHub。

### 一条命令安装

```bash
python -m pip install "hy3-reproeval @ git+https://github.com/Cetaceos/ReproEval.git@main"
```

这条命令适合安装 MCP Server 和 CLI。要运行仓库内样例、数据集与实际复现案例，请使用开发安装：

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

### 配置 Hy3

真实密钥应通过环境变量或客户端私有配置传入，仓库仅提供占位模板。完整配置项见
[`.env.example`](.env.example)，最小环境变量如下：

```text
HY3_API_PROVIDER=tokenhub
HY3_BASE_URL=https://tokenhub.tencentmaas.com/v1
HY3_API_KEY=YOUR_HY3_API_KEY
HY3_MODEL=hy3
REPROSCOPE_OUTPUT_LANGUAGE=zh-CN
```

### 配置 MCP 客户端

复制 [`.mcp.example.json`](.mcp.example.json) 为本地 `.mcp.json`，将 Python、仓库和工作目录替换为
本机绝对路径。可靠的 Windows
stdio 配置形式如下：

```json
{
  "mcpServers": {
    "hy3-reproeval": {
      "type": "stdio",
      "command": "C:/path/to/ReproEval/.venv/Scripts/python.exe",
      "args": ["-m", "hy3_reproscope_mcp"],
      "env": {
        "HY3_API_PROVIDER": "tokenhub",
        "HY3_BASE_URL": "https://tokenhub.tencentmaas.com/v1",
        "HY3_API_KEY": "YOUR_HY3_API_KEY",
        "HY3_MODEL": "hy3",
        "HY3_TIMEOUT_SECONDS": "300",
        "REPROSCOPE_OUTPUT_LANGUAGE": "zh-CN",
        "REPROSCOPE_ALLOWED_ROOTS": "C:/path/to/ReproEval",
        "REPROSCOPE_WORKSPACE": "C:/path/to/ReproEval/.reproeval/reproscope"
      }
    }
  }
}
```

CodeBuddy 和 VS Code 示例分别位于 [`examples/mcp-config/codebuddy.json`](examples/mcp-config/codebuddy.json)
和 [`examples/mcp-config/vscode.json`](examples/mcp-config/vscode.json)。

## 两条端到端流程

### 论文复现审查

依次调用：

```text
reproscope_extract_claims
  -> reproscope_compare_results
  -> reproscope_score_paper
  -> reproscope_build_evidence_graph
  -> reproscope_render_report
```

快速演示材料为 `examples/sample_paper.md`、`examples/sample_results.csv` 和
`examples/sample_train.log`。实际案例使用 `case_studies/differt2d_v0_3_4` 中的冻结协议和公开证据。

### 技术方案迁移评估

依次调用：

```text
reproscope_extract_solution_profile
  -> reproscope_assess_transfer
  -> reproscope_build_transfer_graph
  -> reproscope_render_transfer_report
```

最小材料为 `examples/sample_solution.md` 和 `examples/sample_target_context.md`。DiffeRT2d 到 UAV-BS ISAC
的目标背景位于 `examples/differt2d_uav_isac_target.md`。

另有 `reproscope_audit_repository` 对 Python 仓库进行只读静态审计。它不会安装依赖，也不会执行发现的
入口、测试或第三方代码。

## MCP Tools

| Tool | 作用 | 执行方式 |
| --- | --- | --- |
| `reproscope_extract_claims` | 提取论文主张、设置及可选 ISAC 证据 | Hy3 + 本地校验 |
| `reproscope_compare_results` | 对齐指标并重算复现结果 | Hy3 + 本地统计 |
| `reproscope_score_paper` | 六维可靠性评估与证据不足处理 | Hy3 + 本地聚合 |
| `reproscope_build_evidence_graph` | 构建论文证据关系图 | 本地确定性 |
| `reproscope_render_report` | 生成论文审查报告 | 本地确定性 |
| `reproscope_extract_solution_profile` | 提取技术方案画像 | Hy3 + 本地校验 |
| `reproscope_assess_transfer` | 评估迁移条件、改造和风险 | Hy3 + 本地聚合 |
| `reproscope_build_transfer_graph` | 构建迁移证据关系图 | 本地确定性 |
| `reproscope_render_transfer_report` | 生成迁移决策报告 | 本地确定性 |
| `reproscope_audit_repository` | 静态审计 Python 仓库复现条件 | 本地确定性 |

`reproscope_*` 前缀为兼容既有 MCP 客户端配置而保留；当前发行包和 Server 名称均为 `hy3-reproeval`。

## 数据与结果

| 证据 | 规模与结果 | 可支持的结论 |
| --- | --- | --- |
| [P0 数据集](evals/p0_dataset/dataset.json) | 12 组、44 份好/中/差及对抗报告 | 验证数据协议、错误标签与对抗回归路径 |
| [P1 迁移数据集](evals/p1_transfer_dataset/dataset.json) | 5 组、15 份报告；三轮组内排序均为 100% | 评估器可稳定区分当前构造的迁移报告 |
| [真实论文 Pilot](evals/real_paper_pilot/dataset.json) | 6 篇开放论文、18 份报告；三轮质量档位无翻转 | 验证真实来源材料上的评测流程和重复稳定性 |
| [人工共识](results/real_paper_human_consensus/summary.md) | 12 份盲评报告；二次加权 Kappa 0.964225 | 描述当前评审者在当前样本上的一致性 |
| [系统—人工对照](results/real_paper_human_consensus/system_human_comparison.csv) | 三轮 Spearman 分别为 0.988483、1.0、0.988483 | 记录系统排序与人工共识的对应关系 |
| [DiffeRT2d Figure 2](case_studies/differt2d_v0_3_4/RESULT.md) | 固定入口成功；300×300 网格；归档图像字节一致 | 证明指定版本与环境下该图的软件输出可复现 |

真实论文 Pilot 主要评估“复现准备度”，DiffeRT2d 案例进一步提供了实际执行证据。完整结果保存在
[`results`](results/README.md)，协议、冻结和人工评审说明见
[`docs`](docs/README.md)。

## 本地验证

无需 API Key 的核心检查：

```bash
python -m pytest
python -m ruff check src tests scripts case_studies
python scripts/run_offline_eval.py
python scripts/run_transfer_offline_eval.py
python -m hy3_reproeval build-p0-dataset --output evals/p0_dataset --check
python -m hy3_reproeval build-p1-transfer-dataset --output evals/p1_transfer_dataset --check
python -m hy3_reproeval build-real-paper-pilot --output evals/real_paper_pilot --check
python case_studies/differt2d_v0_3_4/scripts/run_reproduction.py verify-public \
  --evidence-dir case_studies/differt2d_v0_3_4/evidence
```

发行构建：

```bash
python -m build
python scripts/check_distribution.py dist --version 0.38.0
```

## 仓库结构

```text
src/            MCP 应用层、评测核心和 CLI
examples/       最小可运行输入及客户端配置
evals/          回归样例、P0/P1 数据集和真实论文 Pilot
case_studies/   实际执行案例及可校验证据
results/        精选聚合结果、CSV、SVG 和完整性清单
scripts/        离线评测、在线验证与发行检查
skills/         可复用研究审查 Skill
tests/          单元、集成、安全与防篡改测试
docs/           当前协议、实验报告、交付说明和历史归档
```

## 后续研究

- 扩展跨学科真实论文样本，并建立与开发集来源隔离的 held-out 测试集。
- 使用独立校准集优化绝对分数映射，引入更多可认证领域专家开展重复盲评。
- 增加可实际执行的论文复现案例，并为方案迁移补充目标环境测量和部署验证。

## 安全与边界

- 文件访问受 `REPROSCOPE_ALLOWED_ROOTS` 限制，输出写入独立工作目录。
- API Key、原始模型响应、私有评语、论文 PDF 缓存和本机路径不进入版本控制。
- 证据关系图与 SHA-256 用于发现输入被替换或链路不一致，不用于证明科学结论正确。
- 系统不判断学术不端，不提供法律结论，也不能替代领域专家和真实系统测量。

## 许可证

ReproEval 代码以 [Apache-2.0](LICENSE) 发布。第三方论文、软件和数据仍遵循各自许可证；仓库中的来源
记录不构成法律意见。
