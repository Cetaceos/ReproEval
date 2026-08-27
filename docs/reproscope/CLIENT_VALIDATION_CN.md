# Hy3 ReproScope MCP 客户端验证记录

> 更新日期：2026-08-01
> 传输方式：本地 stdio
> 文档性质：同时保留 0.15.0 当前工具发现/调用证据和 0.5.0 历史调用证据；不同版本不混写。

## 0. 0.15.0 当前客户端证据

用户提供的两张当前版本截图显示 CodeBuddy 和 Visual Studio Code 均发现 10 个 Tool。截图已脱敏并持久化到仓库：

| 客户端 | 当前证据 | 可证明的范围 |
| --- | --- | --- |
| CodeBuddy | [十工具发现截图](assets/codebuddy-0.15.0-tool-discovery.png)、用户提供的十步调用截图和 [最终演示 MP4](assets/demo-0.15.0-codebuddy-mcp.mp4) | 0.15.0 工具发现、客户端顺序调用、工件血缘拒绝和迁移报告成功生成 |
| Visual Studio Code 1.131.0 | [十工具发现截图](assets/vscode-0.15.0-tool-discovery.png) 和 [机器可校验证据](CLIENT_VALIDATION_0_15_INDEX.json) | 0.15.0 工具发现，以及前一构建 wheel 的一次真实静态审计 Tool 调用；当前精确 wheel GUI 待复核 |

两张截图没有 API key、Authorization header、`.env` 内容、用户名或私有 endpoint。2026-08-01 的 VS Code 调用使用
Python 3.13.5 和运行时代码等价的前一构建 wheel `61F776...`，生成 completed run `repository_8246ee4f34e0`：Schema 1.21、
83 个检查文件、0 gaps、0 warnings、`scan_truncated=false`、`executed_repository_code=false`。JSON artifact 的
content hash 为 `8f271a...`，payload hash 为 `34342b...`；run manifest 文件 SHA-256 为 `BA024C...`。凭据值扫描
为 0 命中。该调用证明 VS Code 确实通过 MCP 执行 0.15.0 Tool，不代表执行第三方仓库代码，也不替代真实 Hy3 链。最终候选 wheel 哈希为 `76A3F8...`，已通过本地安装和双入口 stdio 发现；其精确在线 Hy3 重复未执行。`3C940...` 是已完成真实 Hy3 三链验证的最近候选。

真实论文、迁移和 ISAC 链的 run ID、artifact hash 和结果见
[LIVE_VALIDATION_0_15_CN.md](LIVE_VALIDATION_0_15_CN.md)。最小截图 montage 位于
[demo-0.15.0-client-discovery-montage.gif](assets/demo-0.15.0-client-discovery-montage.gif)，它不是完整交互录屏。

CodeBuddy 最终演示为原始 MP4，时长 74.66 秒，SHA-256 为
`43BA80B1CEE67E8F32F29B88035017F4FB17DE3DF951C473641F963C227CE20C`。录屏未显示 API key、Authorization header、
`.env` 内容或 traceback；它保留了错误工作区/混合血缘输入被拒绝，以及随后
`reproscope_render_transfer_report` 返回 `completed`、Schema 1.21、`graph_validated=true` 和 Markdown artifact 的过程。
画面包含本机 Windows 用户名、本地绝对路径和前序校验失败，因此它证明真实 MCP 报告调用与恢复过程，不单独证明
论文链重新执行或模型质量。项目按参赛者最终选择将该文件作为公开演示，并保留这些证据边界。

脱敏客户端证据可用
`python scripts/validate_client_evidence.py docs/CLIENT_VALIDATION_0_15_INDEX.json` 校验。该门禁只接受 Schema 1.21、
0.15.0、十工具、completed run、相对 artifact 路径和 SHA-256 哈希；它不会把截图或客户端文本冒充为模型质量证明。

## 0.5.0 历史客户端证据

以下内容保持为不可替代旧版记录，不能用来宣称 0.15.0 GUI 真实调用已通过。

0.15.0 已扩展为十个 Tool，并加入技术迁移、静态仓库审计和实验性 ISAC Profile。当前证据证明两个客户端均能
发现十个 Tool，且两端都已有实际调用记录；其中 VS Code 有可机器校验的 persisted run。由于现有 GUI 调用对应
运行时代码等价的前一构建 wheel，精确当前 wheel 的双端复核仍是严格发布复核项；最终 CodeBuddy MP4 已归档。本文件下方内容保持为
0.5.0 历史证据，避免把旧截图改写成新版本结果。

## 1. 验证结论

ReproScope 0.5.0 曾在 CodeBuddy 和 Visual Studio Code 两个不同的 MCP 客户端中完成实际调用。

| 客户端 | Tool 发现 | 真实 Hy3 调用 | 本地工件 | 当前证据 |
| --- | --- | --- | --- | --- |
| CodeBuddy | 已通过 | 已完成论文 Claim 抽取和工作流调用 | 已生成 | 用户实际运行；最终 PR 前建议重新保存截图或录屏 |
| Visual Studio Code | 5/5 Tool | `reproscope_compare_results` 已通过 | completed comparison + run manifest | 两张脱敏截图和本地工件 |

Visual Studio Code 的证据已经保存在 `docs/assets/`。截图没有 API Key、`.env`
内容或 Authorization Header。

## 2. Visual Studio Code 环境

| 项目 | 值 |
| --- | --- |
| VS Code | 1.129.1 x64 |
| 操作系统 | Windows |
| Python | 3.13.5 |
| ReproScope | 0.5.0 |
| Provider | 腾讯云 TokenHub |
| 模型 | `hy3` |
| MCP 配置 | 工作区 `.vscode/mcp.json` |
| 环境变量 | 私有 `.env`，未写入截图或项目配置 |

VS Code 使用内置 MCP Agent/Chat，项目配置采用 `"servers"` 和 stdio：

```json
{
  "servers": {
    "hy3Reproscope": {
      "type": "stdio",
      "command": "${workspaceFolder}/mcp_servers/reproscope/.venv/Scripts/python.exe",
      "args": ["-m", "hy3_reproscope_mcp"],
      "cwd": "${workspaceFolder}/mcp_servers/reproscope",
      "envFile": "${workspaceFolder}/mcp_servers/reproscope/.env"
    }
  }
}
```

## 3. Tool 发现

VS Code 成功发现并启用全部五个 Tool：

- `reproscope_extract_claims`
- `reproscope_compare_results`
- `reproscope_score_paper`
- `reproscope_build_evidence_graph`
- `reproscope_render_report`

![VS Code MCP Tool discovery](assets/vscode-tool-discovery.png)

## 4. 真实比较调用

实际调用：

```text
reproscope_compare_results
```

输入为仓库中的合成论文、CSV 结果和训练日志。VS Code 展示的关键结果：

| 指标 | 结果 |
| --- | --- |
| 论文 accuracy | 0.91 |
| 复现 accuracy 均值 | 0.876 |
| 样本数 | 5 |
| 样本标准差 | 0.0114 |
| 绝对差 | -0.034 |
| 相对差 | -3.7363% |
| 严重度 | `material` |
| latency 均值 | 14.3 ms |
| latency 样本数 | 5 |
| latency 严重度 | `unknown`，论文未报告该指标 |

![VS Code comparison result](assets/vscode-compare-results.png)

## 5. 本地工件复核

截图对应的本地运行：

```text
compare_e91ecd751b02
```

复核结果：

| 项目 | 值 |
| --- | --- |
| Tool | `reproscope_compare_results` |
| Schema | 1.10 |
| Run status | `completed` |
| Status history | `created -> running -> completed` |
| Comparison artifact | `compare_e91ecd751b02/compare_results.json` |
| Lifecycle artifact | `compare_e91ecd751b02/run_manifest.json` |

本地 JSON 中的确定性指标与截图一致：

- `accuracy=0.876`
- `sample_count=5`
- `absolute_delta=-0.034`
- `relative_delta_percent=-3.7363`
- `epochs=match`
- `learning_rate=match`
- `optimizer=match`
- `seed=missing_in_paper`

## 6. 当前证据边界

现有证据只能证明 0.5.0 历史版本：

- 两个不同 MCP 客户端均可连接 ReproScope；
- Visual Studio Code 能发现完整 Tool Schema；
- Visual Studio Code 能通过 stdio 发起真实 Hy3 Tool 调用；
- GUI 输出、本地确定性结果和运行生命周期工件一致。

当前 0.15.0/Schema 1.21 已在 CodeBuddy 和 Visual Studio Code 留下工具发现与实际调用证据；VS Code 证据索引
可由仓库脚本复核。最终 CodeBuddy MP4 已保存在 `docs/assets/`。
