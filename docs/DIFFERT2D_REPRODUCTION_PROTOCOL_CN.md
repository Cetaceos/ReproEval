# DiffeRT2d 实际复现证据协议

## 目标与边界

本案例复现 DiffeRT2d v0.3.4 发布归档中的 JOSS Figure 2 程序。实验对象是归档内
papers/joss/plot_ris_power_map.py 的可执行性、数值网格和渲染产物，不是整篇论文，也不是
DiffeRT2d 传播模型相对真实测量的准确性验证。

现有 evals/real_paper_pilot 0.2.0 保持冻结，仍表示复现准备度评测。实际运行产生的新证据位于
独立案例 case_studies/differt2d_v0_3_4，避免改变已有 Dataset、Hy3 Judge 和人工盲审结果的
哈希与解释边界。

## 来源冻结

| 对象 | 冻结值 |
| --- | --- |
| 论文 | JOSS 10.21105/joss.06915 |
| 软件归档 | Zenodo 10.5281/zenodo.12600658 |
| 版本 | v0.3.4 |
| 归档大小 | 30,520,081 bytes |
| Zenodo MD5 | A4497F4CCABA5CE5D8F867EC5B4D176C |
| 本地观测 SHA-256 | F61FA9F...6BABE |
| Figure 2 入口 SHA-256 | E9F5BDE1...2F7A1 |
| 归档参考 PNG SHA-256 | D9DA4C4D...8FCE1 |

完整值由 source_manifest.json 管理。MD5 仅用于核对 Zenodo 元数据，完整性冻结和结果文件验证均使用
SHA-256。运行器在解压前拒绝摘要不符、绝对路径、父目录路径、反斜杠路径、重复成员和超过大小
上限的 ZIP。官方归档包含两个仅用于文档和测试材料的相对符号链接；运行器只接受解析后仍位于归档
根目录内的链接，在 Windows 解压时跳过并记录它们，不创建系统链接。

## 环境侦察结论

1. 归档 .python-version 固定为 Python 3.11.8，发布元数据声明 Python 3.9 至 3.12。
2. requirements.lock 固定 JAX 0.4.28、jaxlib 0.4.28、DiffeRT-core 0.0.17、
   Equinox 0.11.4、Matplotlib 3.8.4 和 NumPy 2.0.0 等依赖。
3. ReproEval 当前开发虚拟环境使用 Python 3.13.5，超出该版本的上游声明范围，不能作为正式复现环境。
4. 正式运行使用独立 Python 3.11.8 环境、JAX CPU 后端和 Matplotlib Agg 后端。
5. Figure 2 脚本不需要网络；Windows 运行器只做到不传递凭据和固定入口，不能证明操作系统级断网，
   因而 manifest 明确记录 network_isolation=not_enforced_by_the_windows_runner。

## 固定执行路径

~~~text
Zenodo 归档校验
  -> 安全解压到新 run/work
  -> 校验 Figure 2 脚本和参考 PNG
  -> 使用指定 Python 执行受版本控制的 capture_figure2.py
  -> runpy 执行官方 plot_ris_power_map.py
  -> 采集 P、PdB、PNG、PDF、stdout、stderr 和环境
  -> 生成并验证 run_manifest.json
~~~

运行器不接受 shell 字符串、模块名或用户脚本路径。子进程环境采用白名单继承，名称包含
API_KEY、TOKEN、SECRET、PASSWORD 或 CREDENTIAL 的变量不传入子进程，并将被拒绝的变量名
写入清单，变量值永不落盘。

## 必需证据

| 文件 | 作用 |
| --- | --- |
| run_manifest.json | 运行身份、来源、命令参数、时长、退出状态及全部结果文件摘要 |
| environment.json | Python、平台、依赖版本、JAX 后端与设备 |
| metrics.json | P/PdB 形状、有限值比例、统计量和图像差异 |
| figure2_summary.csv | 从同次运行导出的扁平数值视图，供确定性聚合与 MCP 演示使用 |
| logs/stdout.txt | 官方入口标准输出 |
| logs/stderr.txt | 官方入口标准错误或失败原因 |
| artifacts/figure2_arrays.npz | Figure 2 的线性功率和 dB 网格 |
| artifacts/ris_power_map.png | 本次生成 PNG |
| artifacts/ris_power_map.pdf | 本次生成 PDF |
| artifacts/reference_ris_power_map.png | 执行前从归档保存的参考 PNG |

manifest 对除自身外的每个证据记录相对路径、大小和 SHA-256，并通过
manifest_payload_sha256 保护自身规范化内容。verify 会拒绝路径逃逸、缺失文件、大小变化、
摘要变化或清单篡改。

## 结果判定

- exact：进程成功、证据完整、功率网格为 300 x 300，且生成 PNG 与归档 PNG 像素相同。
- visually_consistent：除像素全等外的门槛均通过，图像形状一致，归一化像素 MAE 不超过 0.01。
- artifact_divergence：程序成功完成，但图像形状或预注册差异阈值不满足。
- failed：来源、环境、执行、结果文件完整性或证据校验任一失败。

0.01 是本案例在执行前声明的工程比较阈值，不是论文指标。任何成功标签都只支持“归档 Figure 2
工作流在所记录环境中得到相同或近似渲染产物”，不能扩展为“整篇论文已复现”或“传播模型已被真实
测量验证”。

## 与 ReproEval 的衔接

实际运行完成后，只把经过 verify 的公开证据摘要登记为新的 case artifact；不回写冻结 Pilot。
随后使用 ReproScope 对论文证据、运行 manifest、环境、指标和日志生成实际复现报告，再由 WorkBuddy
通过 MCP Tool 完成可见调用。最终报告应明确区分论文主张、程序执行事实、图像比较结果和未验证主张。

export 子命令只接受已通过 verify 的成功运行。`figure2_summary.csv` 由 export 根据已校验的
`metrics.json` 和运行时长生成，不是另一轮实验结果。公开包删除解释器绝对路径，不包含第三方源码、下载
归档、虚拟环境、NPZ 和 PDF，只保留可审查的环境版本、数值摘要、日志、复现 PNG、全部公开文件
SHA-256 和私有 run manifest 的 SHA-256。verify-public 对公开清单及其文件再次执行防篡改校验。
