"""Deterministic localization for user-facing Markdown reports."""

from __future__ import annotations

# Long table-header mappings are intentionally kept as exact strings.
# ruff: noqa: E501, RUF001
import re

_ZH_CN_LINES = {
    "## Executive summary": "## 执行摘要",
    "## Core claims": "## 核心主张",
    "## Reported experiment settings": "## 已披露的实验设置",
    "## Reproduction comparison": "## 复现结果对比",
    "### Per-group metric comparisons": "### 分组指标对比",
    "### Cross-group stability": "### 跨组稳定性",
    "### Metric data quality": "### 指标数据质量",
    "### Claim relationship coverage": "### 主张验证覆盖情况",
    "### Experimental setting differences": "### 实验设置差异",
    "### Deterministic setting checks": "### 本地确定性设置校验",
    "### Unresolved questions": "### 待确认问题",
    "## Claim-Evidence-Result graph": "## 主张-证据-结果关系图",
    "## Reliability rubric": "## 可靠性评估",
    "## Verdicts": "## 综合结论",
    "### Major strengths": "### 主要优势",
    "### Major risks": "### 主要风险",
    "### Recommended checks": "### 建议验证项",
    "## Missing reproduction details": "## 缺失的复现信息",
    "## Source inventory": "## 输入来源清单",
    "## Audit trail": "## 运行追踪",
    "### Upstream artifact inventory": "### 上游结果文件清单",
    "### Direct parent lineage": "### 直接输入输出关系",
    "## ISAC physical-layer audit": "## ISAC 物理层专项检查",
    "### ISAC metrics": "### ISAC 指标",
    "### ISAC assumptions": "### ISAC 前提条件",
    "### ISAC risk findings": "### ISAC 风险发现",
    "## Decision summary": "## 决策摘要",
    "## Source solution profile": "## 源方案画像",
    "### Objectives": "### 方案目标",
    "### Components and dependencies": "### 组件与依赖",
    "## Transfer rubric": "## 迁移可行性评估",
    "## Assumption compatibility": "## 前提条件兼容性",
    "## Dependency and resource feasibility": "## 依赖与资源可行性",
    "## Reuse and adaptation": "## 复用与改造",
    "### Transferable strengths": "### 可迁移优势",
    "### Required adaptations": "### 必要改造",
    "## Risks": "## 风险",
    "## Validation plan": "## 验证计划",
    "## Transfer evidence graph": "## 迁移证据关系图",
    "Evidence quality notes:": "证据质量说明：",
    "Warnings:": "警告：",
    "Profile limitations:": "专项检查局限：",
    "No setting differences were identified from the supplied evidence.": "根据现有证据，未发现实验设置差异。",
    "No supported experiment settings were found on both sides.": "论文和复现材料中没有可由证据共同支持的实验设置。",
    "No evidence-grounded validation steps were produced.": "未生成有证据支持的验证步骤。",
    "This is a conditional evidence assessment. It does not predict point performance in the target environment, and license or provenance signals are not legal advice.": "这是基于现有证据的条件化评估，不预测目标环境中的具体性能；许可证和来源信息也不构成法律意见。",
    "- No missing details were extracted.": "- 未提取到缺失信息。",
    "- None supported by the supplied evidence.": "- 现有证据未支持任何项目。",
    "- No risks were returned; this does not establish risk absence.": "- 未返回风险项，但这不代表风险不存在。",
    "- None recorded.": "- 未记录。",
    "| - | - | - | No core claims were extracted. | - |": "| - | - | - | 未提取到核心主张。 | - |",
    "| - | - | no | No experiment settings were extracted. |": "| - | - | 否 | 未提取到实验设置。 |",
    "| - | - | - | No source lineage recorded. |": "| - | - | - | 未记录输入来源。 |",
    "| - | - | - | - | - | No direct parent artifacts recorded. |": "| - | - | - | - | - | 未记录直接上游结果文件。 |",
    "| - | No objectives were supported by the supplied evidence. | - | - |": "| - | 现有证据未支持任何方案目标。 | - | - |",
    "| - | No components were extracted. | - | - |": "| - | 未提取到组件。 | - | - |",
    "| - | unknown | - | No assumptions were assessed. | - |": "| - | 未知 | - | 未评估前提条件。 | - |",
    "| - | unknown | - | - | No dependencies were assessed. | - |": "| - | 未知 | - | - | 未评估依赖项。 | - |",
    "| - | unknown | - | - | No resource requirements were assessed. | - |": "| - | 未知 | - | - | 未评估资源需求。 | - |",
    "| - | unknown | - | No components were assessed. | - |": "| - | 未知 | - | 未评估组件。 | - |",
    "| - | - | - | - | unknown | - | No registered ISAC metrics were extracted. | - |": "| - | - | - | - | 未知 | - | 未提取到已登记的 ISAC 指标。 | - |",
    "| - | - | unknown | No registered ISAC assumptions were extracted. |": "| - | - | 未知 | 未提取到已登记的 ISAC 前提条件。 |",
}


_ZH_CN_HEADERS = {
    "| Overall score | Reliability band | Confidence | Evidence coverage | Rubric coverage | Assessment scope |": "| 总分 | 可靠性等级 | 结论置信度 | 证据覆盖率 | 量表覆盖率 | 评估范围 |",
    "| Claim | Type | Reported value | Statement | Evidence |": "| 主张 | 类型 | 论文报告值 | 内容 | 证据 |",
    "| Setting | Value | Disclosed | Evidence |": "| 设置项 | 值 | 是否披露 | 证据 |",
    "| Metric | Paper reported | Unit | Paper normalized | Reproduced mean | Scale | Conversion | Std. dev. | n | Absolute delta | Relative delta | Severity | Status | Evidence |": "| 指标 | 论文报告值 | 单位 | 论文归一化值 | 复现均值 | 数值尺度 | 换算方式 | 标准差 | 样本数 | 绝对差值 | 相对差值 | 严重程度 | 状态 | 证据 |",
    "| Group | Metric | Reproduced mean | Std. dev. | n | Absolute delta | Relative delta | Severity | Status |": "| 分组 | 指标 | 复现均值 | 标准差 | 样本数 | 绝对差值 | 相对差值 | 严重程度 | 状态 |",
    "| Metric | Groups | Group mean | Group-mean std. dev. | Minimum group | Minimum | Maximum group | Maximum | Range | Range / reported | Largest paper delta | Delta group |": "| 指标 | 分组数 | 分组均值 | 分组均值标准差 | 最小值分组 | 最小值 | 最大值分组 | 最大值 | 极差 | 极差/论文值 | 最大论文差值 | 对应分组 |",
    "| Scope | Metric | Source column | Rows | Valid numeric | Missing | Non-numeric | Non-finite | Valid ratio |": "| 范围 | 指标 | 来源列 | 总行数 | 有效数值 | 缺失值 | 非数值 | 非有限值 | 有效率 |",
    "| Total claims | Fully supported | Partially supported | Contradicted | Unassessed | Coverage |": "| 主张总数 | 完全支持 | 部分支持 | 存在矛盾 | 未评估 | 覆盖率 |",
    "| Setting | Paper | Reproduction | Severity | Likely effect | Evidence |": "| 设置项 | 论文 | 复现 | 严重程度 | 可能影响 | 证据 |",
    "| Setting | Paper values | Reproduction values | Status | Evidence |": "| 设置项 | 论文取值 | 复现取值 | 状态 | 证据 |",
    "| Nodes | Edges | Claim evidence coverage | Claim source coverage | Reproduction-assessed claims | Contradiction ratio | Orphan claims | Source closure | Setting coverage | Full support | Partial support |": "| 节点数 | 关系数 | 主张证据覆盖率 | 主张来源覆盖率 | 已由复现评估的主张 | 矛盾率 | 无关联主张 | 来源关联完整率 | 设置覆盖率 | 完全支持率 | 部分支持率 |",
    "| Dimension | Weight | Status | Score | Rationale | Evidence gaps | Evidence |": "| 评估维度 | 权重 | 状态 | 得分 | 判断依据 | 证据缺口 | 证据 |",
    "| Source | Path | Type | SHA-256 |": "| 来源 | 路径 | 类型 | SHA-256 |",
    "| Role | Run | Path | Type | Schema | File SHA-256 | Payload SHA-256 |": "| 结果角色 | 运行 ID | 路径 | 类型 | Schema | 文件 SHA-256 | 结构化内容 SHA-256 |",
    "| Child role | Child run | Parent role | Parent run | Parent path | Parent file SHA-256 |": "| 当前结果角色 | 当前运行 ID | 上游结果角色 | 上游运行 ID | 上游路径 | 上游文件 SHA-256 |",
    "| System type | Sensing topology | Waveform | Research method | Evidence level | Evidence |": "| 系统类型 | 感知拓扑 | 波形 | 研究方法 | 证据等级 | 证据 |",
    "| Canonical metric | Reported name | Value | Unit | Scale | Present context | Missing context | Evidence |": "| 规范指标 | 原文名称 | 值 | 单位 | 数值尺度 | 已有上下文 | 缺失上下文 | 证据 |",
    "| Assumption | Value | Evidence kind | Evidence |": "| 前提条件 | 值 | 证据类型 | 证据 |",
    "| Rule | Status | Finding | Evidence kind | Missing evidence | Review | Evidence |": "| 规则 | 状态 | 发现 | 证据类型 | 缺失证据 | 是否复核 | 证据 |",
    "| Transfer score | Feasibility band | Confidence | Evidence coverage | Rubric coverage |": "| 迁移得分 | 可行性等级 | 结论置信度 | 证据覆盖率 | 量表覆盖率 |",
    "| ID | Objective | Success criteria | Evidence |": "| ID | 目标 | 成功标准 | 证据 |",
    "| Component | Responsibility | Interfaces | Evidence |": "| 组件 | 职责 | 接口 | 证据 |",
    "| Dependency | Type | Required condition | Replaceable | Evidence |": "| 依赖项 | 类型 | 必要条件 | 是否可替换 | 证据 |",
    "| Assumption | Compatibility | Target condition | Rationale | Evidence |": "| 前提条件 | 兼容性 | 目标环境条件 | 判断依据 | 证据 |",
    "| Dependency | Status | Target condition | Required action | Rationale | Evidence |": "| 依赖项 | 状态 | 目标环境条件 | 必要操作 | 判断依据 | 证据 |",
    "| Resource | Status | Target condition | Required action | Rationale | Evidence |": "| 资源 | 状态 | 目标环境条件 | 必要操作 | 判断依据 | 证据 |",
    "| Component | Reuse level | Required changes | Rationale | Evidence |": "| 组件 | 复用程度 | 必要改动 | 判断依据 | 证据 |",
    "| Nodes | Edges | Profile evidence | Assumptions assessed | Components assessed | Dependencies assessed | Resources assessed | Invalidated conditions | Transferred components | High risks | Validation steps | Source closure |": "| 节点数 | 关系数 | 方案画像证据覆盖率 | 已评估前提条件 | 已评估组件 | 已评估依赖 | 已评估资源 | 不满足条件数 | 可迁移组件数 | 高风险数 | 验证步骤数 | 来源关联完整率 |",
    "| Role | Run | Path | Schema | File SHA-256 | Payload SHA-256 |": "| 结果角色 | 运行 ID | 路径 | Schema | 文件 SHA-256 | 结构化内容 SHA-256 |",
}


_ZH_CN_VALUES = {
    "yes": "是",
    "no": "否",
    "unknown": "未知",
    "assessed": "已评估",
    "not assessed": "未评估",
    "insufficient": "证据不足",
    "insufficient_evidence": "证据不足",
    "strong": "较强",
    "moderate": "中等",
    "weak": "较弱",
    "paper_and_reproduction": "论文与复现证据",
    "paper_only": "仅论文证据",
    "critical": "严重",
    "material": "重要",
    "minor": "轻微",
    "none": "无",
    "computed": "已计算",
    "unmatched": "未匹配",
    "missing_paper_value": "论文未报告该值",
    "unmatched_reproduction_metric": "未匹配到复现指标",
    "ambiguous_reproduction_group": "复现分组不明确",
    "metric_alias_mismatch": "指标名称未匹配",
    "unresolved_metric_scale": "数值尺度未确定",
    "unresolved_metric_unit": "单位未确定",
    "incompatible_metric_scale": "数值尺度不兼容",
    "match": "一致",
    "mismatch": "不一致",
    "ambiguous": "存在歧义",
    "missing_in_paper": "论文缺失",
    "missing_in_reproduction": "复现材料缺失",
    "compatible": "兼容",
    "incompatible": "不兼容",
    "uncertain": "不确定",
    "missing_target_evidence": "目标环境证据不足",
    "conditional": "有条件",
    "satisfied": "满足",
    "unsatisfied": "不满足",
    "direct": "可直接复用",
    "adapt": "需要改造",
    "replace": "需要替换",
    "not_reusable": "不可复用",
    "high_risk": "高风险",
    "promising": "较可行",
    "method": "方法",
    "main_result": "主要结果",
    "baseline": "基线",
    "ablation": "消融实验",
    "limitation": "局限性",
    "dataset": "数据集",
    "efficiency": "效率",
    "other": "其他",
    "reproduction_result_agreement": "复现结果一致性",
    "experiment_setup_transparency": "实验设置透明度",
    "baseline_fairness": "基线比较公平性",
    "ablation_quality": "消融实验质量",
    "statistical_reporting": "统计报告完整性",
    "data_implementation_availability": "数据与实现可用性",
    "evidence_reliability": "源方案证据可靠性",
    "assumption_compatibility": "前提条件兼容性",
    "dependency_feasibility": "依赖可行性",
    "resource_feasibility": "资源可行性",
    "adaptation_manageability": "改造可控性",
    "validation_readiness": "验证准备度",
    "observed": "直接证据",
    "deterministically_derived": "本地确定性推导",
    "inferred": "推断证据",
    "speculative": "推测",
    "fraction": "小数",
    "percentage": "百分比",
    "linear": "线性值",
    "decibel": "分贝",
}


def localize_report(markdown: str, *, language: str) -> str:
    """Localize fixed report text without changing schemas, IDs, or citations."""

    if language != "zh-CN":
        return markdown

    localized: list[str] = []
    for original_line in markdown.splitlines():
        line = _ZH_CN_LINES.get(original_line, original_line)
        line = _ZH_CN_HEADERS.get(line, line)
        line = _localize_dynamic_line(line)
        if line.startswith("|"):
            line = _localize_table_values(line)
        localized.append(line)
    return "\n".join(localized)


def _localize_dynamic_line(line: str) -> str:
    warning_match = re.fullmatch(r"- `([^`]+)`: (.+)", line)
    if warning_match:
        code, message = warning_match.groups()
        return f"- `{code}`: {_localize_warning(code, message)}"

    prefixes = (
        ("**Unassessed claims:** ", "**未评估主张：** "),
        ("**Conclusion stability:** ", "**结论稳定性：** "),
        ("**Reproduction:** ", "**复现结论：** "),
        ("**Experimental rigor:** ", "**实验严谨性：** "),
        ("**Target context:** ", "**目标环境：** "),
        ("Group dimensions: ", "分组维度："),
        ("Experiment group filters: ", "实验分组筛选条件："),
        ("Graph validation marker: ", "关系图校验标记："),
    )
    for source, target in prefixes:
        if line.startswith(source):
            line = target + line[len(source) :]
            break

    if line.startswith("Source runs: "):
        if "Rubric aggregation and the feasibility band" in line:
            runs = line.removeprefix("Source runs: ").split(". Rubric aggregation", maxsplit=1)[0]
            return f"来源运行：{runs}。量表汇总和可行性等级由 ReproScope 本地确定性计算。"
        runs = line.removeprefix("Source runs: ").split(". Metric aggregates", maxsplit=1)[0]
        return f"来源运行：{runs}。指标汇总和最终加权得分由 ReproScope 本地确定性计算。"

    if line.startswith("Profile ") and " was activated by " in line:
        match = re.fullmatch(
            r"Profile (.+) version (.+) was activated by (.+) with detector confidence (.+)\. "
            r"Domain findings are advisory and do not affect the generic score\.",
            line,
        )
        if match:
            profile, version, source, confidence = match.groups()
            return (
                f"专项检查 {profile}（版本 {version}）由 {source} 启用，检测置信度为 {confidence}。"
                "领域发现仅供辅助审查，不影响通用可靠性得分。"
            )

    graph_match = re.fullmatch(
        r"Built a validated graph with (\d+) nodes, (\d+) edges, and (\d+) orphan claims\.", line
    )
    if graph_match:
        nodes, edges, orphans = graph_match.groups()
        return f"已构建并校验关系图：{nodes} 个节点、{edges} 条关系、{orphans} 条无关联主张。"

    transfer_graph_match = re.fullmatch(
        r"Built a validated transfer graph with (\d+) nodes, (\d+) edges, (\d+) invalidated conditions, "
        r"and (\d+) transferred components\.",
        line,
    )
    if transfer_graph_match:
        nodes, edges, invalidated, transferred = transfer_graph_match.groups()
        return (
            f"已构建并校验迁移关系图：{nodes} 个节点、{edges} 条关系、"
            f"{invalidated} 个不满足条件、{transferred} 个可迁移组件。"
        )

    exact_sentences = {
        "Coverage reports how many extracted Claims received one locally validated three-way relation. It does not measure whether a relation is correct and does not modify the reliability score.": "覆盖率表示有多少条已提取主张获得了本地校验的三方关系；它不衡量关系判断是否正确，也不改变可靠性得分。",
        "Claim source coverage counts direct Claim citations. Reproduction-assessed claims count Claim relations from an assessment that directly depends on a locally recalculated reproduction result; this does not prove that the supplied reproduction is independent. Graph relations and coverage metrics are validated locally, but inferred relations do not become observations merely because they appear in the graph.": "主张来源覆盖率统计主张的直接引用情况；‘已由复现评估的主张’统计直接依赖本地重算结果的主张关系，但这不能证明输入的复现实验具有独立性。关系图及覆盖率由本地程序校验，推断关系不会仅因写入关系图就被视为实测事实。",
        "Graph relations are constructed and validated locally from the supplied profile and assessment. Inferred transfer relations remain conditional evidence, not measured target performance.": "关系图由本地程序根据输入的方案画像和迁移评估结果构建并校验。图中的推断关系仍属于条件性证据，不代表目标环境中的实测性能。",
    }
    line = exact_sentences.get(line, line)
    line = line.replace(" Reason: ", " 原因：")
    line = line.replace(" Mitigation: ", " 缓解措施：")
    line = line.replace(" Success criteria: ", " 成功标准：")
    line = line.replace(" Prerequisites: ", " 前置条件：")
    parenthetical_values = {
        "low": "低",
        "medium": "中",
        "high": "高",
        "unknown": "未知",
        "none": "无",
        "minor": "轻微",
        "material": "重要",
        "critical": "严重",
    }
    for source, target in parenthetical_values.items():
        line = line.replace(f"({source}, ", f"({target}, ")
        line = line.replace(f"({source}; ", f"({target}; ")
        line = line.replace(f"({source}):", f"({target}):")
    return line


def _localize_warning(code: str, message: str) -> str:
    fixed = {
        "METRIC_VALUES_RECALCULATED": "复现均值、标准差、样本数和差值已由本地程序重新计算。",
        "SCORE_NORMALIZED": "总分和可靠性等级已根据固定维度权重在本地重新计算。",
        "TRANSFER_SCORE_NORMALIZED": "迁移总分和可行性等级已根据固定量表在本地重新计算。",
        "CONDITIONAL_TRANSFER_ASSESSMENT": "该评估以提供的目标环境为前提；形成工程决策前仍需使用代表性测量结果验证。",
        "NO_TARGET_PERFORMANCE_PREDICTION": "缺少目标环境测量结果时，不提供具体性能预测。",
        "LICENSE_SIGNALS_NOT_LEGAL_ADVICE": "许可证和来源信息仅用于初步检查，不构成法律结论。",
        "TRANSFER_BLOCKERS_PRESENT": "目标环境中至少有一项前提、依赖或资源要求未满足；问题解决前不能判为较可行。",
    }
    if code in fixed:
        return fixed[code]

    if code == "CLAIM_RELATION_COVERAGE_INCOMPLETE":
        counts = re.search(r"(\d+) of (\d+) claims", message)
        if counts:
            missing, total = counts.groups()
            return f"{total} 条主张中有 {missing} 条未获得经校验的完全支持、部分支持或矛盾关系。"
    if code in {"RUBRIC_PARTIAL_COVERAGE", "TRANSFER_RUBRIC_PARTIAL_COVERAGE"}:
        coverage = re.search(r"(\d+%)", message)
        if coverage:
            scope = "固定迁移量表" if code.startswith("TRANSFER_") else "固定量表"
            return f"{scope}中只有 {coverage.group(1)} 的维度具有足够证据可评分；未评估维度已排除，而不是按零分处理。"
    return message


def _localize_table_values(line: str) -> str:
    for source, target in _ZH_CN_VALUES.items():
        line = line.replace(f"| {source} |", f"| {target} |")
    return line
