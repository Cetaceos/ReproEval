# ReproScope 0.15.0 实时 Hy3 验证记录

> 记录日期：2026-08-01
> 版本：`hy3-reproscope-mcp 0.15.0`
> Artifact Schema：`1.21`
> 记录性质：当前版本的脱敏工程证据；不替代领域专家评审，也不把合成输入解释为真实科研结论。

## 1. 结论摘要

最近完成在线验证的 0.15.0 wheel `3C940...` 已使用现有私密 TokenHub/Hy3 配置完成论文、技术迁移和 ISAC 三条真实调用链。13 个成功 run manifest 均为 `completed`，28 个成功 artifact（26 JSON、2 Markdown）的 content hash 均已独立重算匹配，JSON payload hash 也全部匹配；Schema 均为 `1.21`。最终 CodeBuddy MP4 已归档；后续代码收口产生的新 wheel 仍需单独区分本地门禁、客户端录屏和既有在线模型证据。

完整脱敏汇总保存在本地忽略的 `.hy3-reproscope/readme-wheel-live-evidence-index.json`，SHA-256 为 `0FE83471A9B613F807193E275EA3A6B85C0F4159C0198F1521AB0C8EE80E619A`；持久 artifact workspace 为 `.hy3-reproscope/readme-wheel-live-20260801`。第一次 ISAC 显式案例收到 HTTP 200 空 completion，失败 run `claims_05dfe2ec2b6c` 已单独保留；有界重试完成三个 ISAC 案例，失败 run 不计入 13 个成功 run 和 28 个成功 artifact。

- `scripts/run_live_transfer_validation.py`
- `scripts/run_live_isac_validation.py`

## 2. 论文五工具链

### 2.1 运行环境

| 字段 | 值 |
| --- | --- |
| package / distribution | `0.15.0` / `0.15.0` |
| Provider | `tokenhub` |
| Model | `hy3` |
| Schema | `1.21` |
| 端到端耗时 | `312.521 s` |
| HTTP 结果 | 真实 Hy3 调用完成；请求正文、密钥和 endpoint 私密参数不入库 |
| 输入 | `examples/sample_paper.md`、`sample_results.csv`、`sample_train.log` |
| 输入性质 | 仓库内合成演示材料，不是真实论文 benchmark |

本次实时 run 使用的 wheel SHA-256 为 `3C940B9CED5D95EACCABC563DCB459B462CE35B597AE8FDB20B2EC673976F950`。
`scripts/run_live_wheel_validation.py` 从该 wheel 创建隔离环境，按 `requirements.lock --require-hashes` 安装依赖，
并在显式 1200 秒有界子进程超时下依次运行三条工作流。先前 `61F776...` 和 `07FE0F...` wheel 的成功记录、配额恢复前的 402/401008 失败，以及当前 wheel 的一次空 completion 重试均保留在机器索引的 `historical_validation.retry_history` 中。

### 2.2 run 与 artifact

| Tool | Run ID | 状态 | Artifact | content hash | payload hash |
| --- | --- | --- | --- | --- | --- |
| `reproscope_extract_claims` | `claims_c6789d403a3c` | `completed` | `claims_c6789d403a3c/extract_claims.json` | `a87b94c7e2a616b0c62f4b40ec715ee491f36fc96dc1654bc5211966887695f1` | `3ca2f0498f9732b18e87fa29130f704c656efdcee95de69c848c1eef19d4119f` |
| `reproscope_compare_results` | `compare_4425f4b90db3` | `completed` | `compare_4425f4b90db3/compare_results.json` | `ce79856c2a354d55ed5bbbd76985ed30736b927d32821375b0182b6c4b91b48c` | `b935d4f351142ce43aff53c725de68a5722531844507ea6ca57b263f401318d0` |
| `reproscope_score_paper` | `score_691f61731662` | `completed` | `score_691f61731662/reliability_score.json` | `608b7721813e72991a235158561a13a6562563f9bab3b8d4848a4c3c60d802e6` | `425616cde52e84b147169c9f9d65872283962f1b55e4e7993337406ea82b2054` |
| `reproscope_build_evidence_graph` | `graph_101f7a23137e` | `completed` | `graph_101f7a23137e/evidence_graph.json` | `64e1e8a6523b9832f11722140d716b30fc5a1ab10f96fd58c025b85165a9f8a7` | `45fe69f56ed905920c3d1ee7295ba35346a75eef29fba4392effc08b3a571a70` |
| `reproscope_render_report` | `report_9e42ad6e9cef` | `completed` | `report_9e42ad6e9cef/reproscope_report.md` | `608205d4acf2dd278d67982bdb3f631de5968f3e3a138cce73c79ebfa7dec94c` | 不适用（文本 artifact） |
| 报告 manifest | `report_9e42ad6e9cef` | `completed` | `report_9e42ad6e9cef/report_manifest.json` | `f6ced554f78ceb4d1e5181b65ab7a3a2e761a365abac63769bdfbe4fbe336f6d` | `b0c6acc7ecd535952add3a1353c19c8db798a8bc022eb96e3648d92191a740cd` |

五个 manifest 的状态序列均为 `created -> running -> completed`。图验证为 `graph_validated=true`，报告 inventory 包含四个上游 artifact，且报告 manifest 自身不被列入报告正文 inventory。

### 2.3 确定性结果

- claims：6 个 core claims、11 个实验设置，Profile 为 `generic`。
- accuracy：论文值 `0.91`，5 个复现样本均值 `0.876`，stddev `0.0114`，绝对差 `-0.034`，相对差 `-3.7363%`，状态 `computed`，严重度 `material`。
- latency：复现均值 `14.3`，论文没有该指标，状态 `missing_paper_value`，严重度 `unknown`。
- 设置核对：`epochs`、`learning_rate`、`optimizer` 为 `match`；`seed` 为 `missing_in_paper`。
- score：`45.0`，band `weak`，rubric coverage 为 `0.9`；图包含 32 个节点、30 条边且 `graph_validated=true`。

这些数值证明的是本地确定性重算、artifact lineage 和 0.15.0 调用链；输入是合成样例，不能外推为 Hy3 在真实论文上的科学质量。

## 3. 技术迁移四工具链

| Tool / artifact | Run ID | 状态 | content hash | payload hash |
| --- | --- | --- | --- | --- |
| `extract_solution_profile` | `solution_01b54ae47d1e` | `completed` | `6f0f5abce1d44e3f8a34b055c83193c9be3977bbae9f7b5c88c673af8f4e1bd7` | `eaf2ec14018029e5e4a27929b2ab751aa57b702cd42203b670b0290c040a4f47` |
| `audit_repository` | `repository_cc3c6cfb3127` | `completed` | `b73d9321701cf4c549ad87dcca7b62c690f8e30471d8d3da711589f34c5b6c72` | `773d124f488e8a9a9cf628fc3dd89bc4411eb03c6815eca7703fbdd91100dd04` |
| `assess_transfer` | `transfer_427f7b78535a` | `completed` | `c5978d4876f01638719e7af4f392c86638283b6002c6e87d5950cccf00761604` | `17d98d438e25a7f57e6c7202de4a0f6cc66375cbac0a737ea0d392834de72cfe` |
| `build_transfer_graph` | `transfer_graph_0ee7b9cf3ac8` | `completed` | `50776bd01eb03c5e6665354d5fa081486fbbd5b86607c906779af2cc118ff501` | `9a299046e02428d03b73aac9c43fffdde577eb45bae1ed3abe47afacad3e8dca` |
| `render_transfer_report` | `transfer_report_963f898f32f5` | `completed` | `d962129a20b004f0f59400e03e6428ebddabbb14f5ab1f4d40359ca9fed70db4` | 不适用（Markdown） |
| transfer report manifest | `transfer_report_963f898f32f5` | `completed` | `d11693fb2cdacccadbb0a39d7a630dfadaccc7cc5ddd581b3636ed8531101a41` | `ec4355f1b80d56a7526e2128a99f1bf38dc3f86e6f8de1a788dbff946ee820f6` |

关键结果为 `overall_score=31.0`、`feasibility_band=high_risk`、`evidence_coverage=1.0`、`rubric_coverage=1.0`。结果保留一个高风险迁移项，未提供目标性能点预测，也未提供法律结论；transfer graph `validated=true`，包含 5 个失效条件、3 个可迁移组件、1 个高风险项和 5 个验证步骤。各 run manifest 均为 `created -> running -> completed`，Schema 均为 `1.21`。

## 4. ISAC 显式与自动激活

| 案例 | Run ID | requested / effective | activation source | 结果摘要 | artifact content hash | artifact payload hash | manifest content hash |
| --- | --- | --- | --- | --- | --- | --- | --- |
| explicit ISAC | `claims_28c0a4b6a050` | `isac_phy / isac_phy` | `explicit_parameter` | 2 metrics、4 assumptions、12 findings、0 risk | `4c2a1b5339593b3c020c95173b55ea9a3ab963c27a94420004e3c05976ee8a16` | `625226da91eccd8153de8bb18f4446576d8653c30a27d8125e2b74fe836e54f4` | `fc50d45c651f076a604dc6f4c7700d4a2225cf70f98d536a1888b41ff5fb6283` |
| auto positive ISAC | `claims_399109c85ab3` | `auto / isac_phy` | `auto_detection` | 2 metrics、4 assumptions、12 findings、2 risk | `4e53d3c69b82377c4eb21e9193bb84c5478f8dfd52948be7863c05c1c3019240` | `99bbfbecf6ed81dc496a62d17c46c2d0b9966d7cadfe5fc1fdf7cd7dde868c4c` | `374cc648643298209d43b2e819494b0a2fdb942d062360f63f51715c276a823f` |
| auto radar negative | `claims_d2bac55494b0` | `auto / generic` | `default_generic` | 0 metrics、0 assumptions、0 findings | `bff6d868a9bec8b1d48073b50b8e7a45aefcec247d1d6a88e90d61cbe1e84dcf` | `10206fc0ce8e9cb2e5b212bb52f1c91078891999f951f1d5c2b8dd9408e65d13` | `8903cce0472ad658918be62938408a4dd19fc0e7ed2f324d35196e2d6dd9283e` |

三份 manifest 均为 `created -> running -> completed`，Schema 均为 `1.21`。第二次在线运行设置 `HY3_MAX_TOKENS=32000`、`HY3_REASONING_EFFORT=low`，避免自动正例在默认 16000 token 预算下被截断；这只是请求参数记录，不是模型质量结论。ISAC findings 固定 `affects_score=false`，上述结果只证明当前示例材料的真实 Hy3 调用和本地归一化链。

## 5. 当前客户端证据

两张用户提供的当前版本工具发现截图已保存：

- [CodeBuddy 0.15.0 十工具发现](assets/codebuddy-0.15.0-tool-discovery.png)
- [Visual Studio Code 0.15.0 十工具发现](assets/vscode-0.15.0-tool-discovery.png)

The CodeBuddy full-pipeline capture supplied after the 0.15.0 run adds a client-side
cross-step assertion for `transfer_graph.graph_validated=true`. This is stronger than tool discovery,
but it remains a user-provided GUI capture; the persisted JSON artifact is the authoritative evidence.
For both clients, verify the top-level `graph_validated` boolean in `transfer_graph.json`, or use the
same marker exposed by `reproscope_render_transfer_report` and `transfer_report_manifest.json`.

截图可证明两个客户端各发现 10 个 Tool，且未包含 API key、Authorization header、`.env` 内容或私有 endpoint。用户另行提供的 CodeBuddy 全流程截图包含十步顺序执行和 `transfer_graph.graph_validated=true` 跨步断言。Visual Studio Code 1.131.0 使用运行时代码等价的前一构建 wheel `61F776...` 完成 `reproscope_audit_repository`：run `repository_8246ee4f34e0`、Schema 1.21、0 gaps、0 warnings、未截断、未执行代码；artifact content/payload hash 为 `8f271a...`/`34342b...`。最终 CodeBuddy 演示位于 [demo-0.15.0-codebuddy-mcp.mp4](assets/demo-0.15.0-codebuddy-mcp.mp4)，展示报告 Tool 的真实 stdio 调用、血缘拒绝和 completed 迁移报告；它不证明论文链或新构建 wheel 的完整在线重复。脱敏索引见 [CLIENT_VALIDATION_0_15_INDEX.json](CLIENT_VALIDATION_0_15_INDEX.json)，并由 `validate_client_evidence.py` 校验。双客户端发现 montage 位于 [demo-0.15.0-client-discovery-montage.gif](assets/demo-0.15.0-client-discovery-montage.gif)。

## 6. 在线验证命令

下面的 PowerShell 命令从私有 `.env` 加载变量但不打印变量值；运行前请确认端点可达。命令只写入仓库忽略的 `.hy3-reproscope/live_*` 目录。

```powershell
$repo = (Resolve-Path '.').Path
$project = Join-Path $repo 'mcp_servers\reproscope'
$envFile = Join-Path $project '.env'
Get-Content -LiteralPath $envFile | ForEach-Object {
  $line = $_.Trim()
  if (-not $line -or $line.StartsWith('#')) { return }
  $pair = $line -split '=', 2
  if ($pair.Count -eq 2) {
    $name = $pair[0].Trim()
    $value = $pair[1].Trim()
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    Set-Item -Path ("Env:" + $name) -Value $value
  }
}
$env:REPROSCOPE_RUN_LIVE = '1'
$env:REPROSCOPE_ALLOWED_ROOTS = $project
$env:REPROSCOPE_WORKSPACE = Join-Path $project '.hy3-reproscope\live_transfer_0_15_20260731'
& (Join-Path $project '.verify-venv\Scripts\python.exe') (Join-Path $project 'scripts\run_live_transfer_validation.py')
```

ISAC 验证只需把最后两行的 workspace 和脚本替换为：

```powershell
$env:REPROSCOPE_WORKSPACE = Join-Path $project '.hy3-reproscope\live_isac_0_15_20260731'
$env:HY3_MAX_TOKENS = '32000'
$env:HY3_REASONING_EFFORT = 'low'
& (Join-Path $project '.verify-venv\Scripts\python.exe') (Join-Path $project 'scripts\run_live_isac_validation.py')
```

## 7. 外部证据状态

1. ReproScope CI [run 30689787695](https://github.com/Cetaceos/Hy3/actions/runs/30689787695) 已在提交
   `36253a6` 上完成 Linux 3.11/3.12/3.13、Windows 3.11 和 macOS 3.11 五项全绿；手动 live job 按设计跳过。
2. PR #187 正文已同步 0.15.0 十工具和两条端到端流程；本轮 README 与当前 wheel 证据尚未 commit、push，推送后需等待新 HEAD 的 CI。
3. 领域专家标注、真实 Calibration/Held-out、引用准确率和风险阈值尚未产生；当前 `evals/synthetic_isac_calibration.json` 只输出描述性合成指标，UAR/CAR 不能解释为 benchmark。
4. 最近完成在线验证的 `3C940...` wheel 已获授权并实际发送仓库合成样例；论文、迁移与 ISAC 三条链全部完成，run ID、artifact hash、汇总哈希和历史失败边界均已进入 `LIVE_VALIDATION_0_15_INDEX.json`。
5. 最终 CodeBuddy MP4 已完成；后续代码收口生成的新 wheel 必须重新记录哈希和本地门禁，不能从录屏或 `3C940...` 在线记录继承“精确新 wheel 已在线验证”的表述。
