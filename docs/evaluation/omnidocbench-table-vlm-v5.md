# ScholarLens 局部表格 VLM 重识别实验 v5

日期：2026-09-25。结论：**实验工具和安全回退已实现，但本轮没有得到可用的 VLM 修复候选，不接入生产。**

## 1. 本次做了什么

- 冻结原来的 3 个表格开发样本：1 张困难表、2 张较好的对照表。
- 从保存的 native Docling bbox 裁图，明确转换坐标原点与图像比例，加 12 像素边距；未读取 Gold 框。
- 保存原生单元格框叠加图、原表格 HTML、裁图、文件哈希、固定提示词、API 原始返回及校验结果。
- 只向 `qwen3-vl-plus` 发送表格裁图和固定通用提示词；没有发送 Gold、Docling 文本或已知得分。
- 要求返回 `rows/cols/cells`，每格为 `[row, col, rowspan, colspan, text, header, uncertain]`。
  不确定文字必须显式 `null + uncertain=true`，程序不推测补全数值。
- 严格校验整数、边界、跨度、重叠、完整覆盖和未知值。非法候选保留原始响应，但不生成可用替换表。
- Gold 只进入独立评分/对照页面；没有修改原解析器、chunker、数据库、向量索引或前端。

按 `ai-product-dev-pack` 将该任务限定为单个离线特性，先定义验收与故障测试，再实现和实测。
测试通过不等于模型效果通过，两者在下面分别报告。

## 2. 真实实验结果

参数：`temperature=0`、`enable_thinking=false`、`max_tokens=16384`、SDK `max_retries=0`、请求超时 180 秒。

| 页面 | Docling v4 TEDS ↑ | VLM 结果 | 耗时 | 实验回退后的 TEDS |
|---|---:|---|---:|---:|
| `page-035cb436...` | 0.2112 | 返回 JSON，但单元格重叠/越界，拒绝 | 132.422 秒 | 0.2112 |
| `page-0cbdcfa9...` | 0.9597 | `APITimeoutError`，未收到完整响应 | 180.031 秒 | 0.9597 |
| `page-14a6b411...` | 0.8963 | `APITimeoutError`，未收到完整响应 | 180.188 秒 | 0.8963 |

- 成功收到完整 API 响应：**1/3**。
- 通过结构校验的可评测候选：**0/3**。
- 原始表格均保留，实验回退后平均 TEDS：**0.6890469428**，与 v4 相同，**没有提升**。
- 原始候选的 TEDS 记为 `null`，不是把超时解释为 OCR 分数为 0。
  JSON 另有 `candidate_teds_failed_as_zero=0`，这是将不可交付候选计零的任务完成口径，
  不能当作 VLM 的实际内容识别准确率。
- 没有根据 Gold 挑选“新旧结果中得分更高的那个”。当前回退只看请求/结构是否有效。
  同样，结构合法本身也不足以证明文字和数值正确。

### 网络尝试与费用边界

初次在沙箱内运行的 3 次连接尝试全部被本机套接字权限拦截（另行只读连接检查确认 WinError 10013），
没有收到服务端响应。这些日志保留在 `live/`，没有伪装成模型质量结果。
申请联网权限后另建 `live-authorized/`，进行了上表 3 次请求，未自动重试。

已收到 usage 的第一张表：输入 **2730 tokens**（其中图像 2480）、输出 **5292 tokens**，合计 **8022**。
另外两次超时没有 usage 返回，**消耗和是否计费未知**，不能说总成本只有 8022 tokens 或超时免费。
请以阿里云账单为准；本轮没有估算未经核实的金额，也没有继续付费重跑。

## 3. 失败样本实际说明了什么

`page-035cb436...` 是元器件规格表（数据集来源标签为 academic_literature，不能因此把它说成科研论文）。
原图含复杂多层表头、跨行备注和成对型号，原始 Docling 输出可见：

- 表头文字与列发生混合，例如 `Rated DC Resistance Current`；
- 两个电阻值被并进同一单元格，例如 `0.18 0.28`；
- 百分号/字符误识别，例如 `25%` 被转为 `259`，型号中的 `1/I` 等混淆。

说明原问题确实包含结构与文字识别错误，保真导出不能解决这些错误。

本次 VLM 返回了 35 行、8 列、234 个单元格，但进一步检查发现：

- **2 个网格位置被重复覆盖**；表头跨行单元格与 `Typical` 等子表头发生冲突。
- **7 个单元格超出它自己声明的行列范围**。
- 只统计有效边界内单元格时仍有 **11 个未覆盖位置**。
- 模型没有标记任何 uncertain 格，说明不能仅依赖模型自己报告不确定性。

这些问题没有利用 Gold 自动修补。原始 JSON 在对照页面中保留，可继续人工检查。

两张大表超时仅证明**当前模型/输出协议/180 秒预算组合下交付失败**，
不能直接证明模型看不懂表格。长单元格 JSON 增加输出负担是待验证的解释，
服务端排队或网络因素也尚未排除。

## 4. 评分与验证

使用固定 OmniDocBench checkout `f133a71e9e91c3621c7ce8994200a7b394a06eb3` 中的
`normalized_html_table` 和 `TEDS`，按 1:1 表格配对评分；对应文件 SHA-256 在 JSON 报告中。
本轮没有改 TEDS/标准答案，也没有重跑全部 10 页的 end-to-end 匹配。
3 张 baseline 的 TEDS、structure-only 均与 v4 保存结果一致（误差 < 1e-9）。

Gold SHA-256：`f25369f9845039f7474591e9a0c275443c5a2149fc975270f35a80ada7da43a4`，未变化。

另提供数字 token 多重集合 P/R/F1 作为原表问题诊断：它可以发现重复数值的遗漏/增加，
但不检查所在行列、单位、型号和语义，不能叫作“单元格数值准确率”。由于候选均未通过，
本轮没有可比较的 VLM 数值指标。

工程验证：

- 新增 11 个测试，先观察模块缺失的 RED，再实现 GREEN。
- 全套 **196 tests passed**，0 失败、0 跳过，15.619 秒。
- 覆盖裁图原点/缩放/裁剪、重叠/越界/缺格、显式未知值、HTML 转义、输出目录隔离、
  哈希篡改、请求预算、超时、截断、秘密不写入异常日志、真实 SDK 请求参数（mock）和失败分母。
- 真实接缝：3 次模型请求、3 表固定官方 TEDS 函数评分与可视化产物生成。
- 3 个源 document/native JSON 和原图哈希均未变化；无重新入库、线上替换、commit 或 push。
- `git diff --check` 通过。工程用例通过不代表本次模型修复策略通过效果验收。

## 5. 查看产物

- 配对诊断入口：[`index.html`](../../output/benchmarks/omnidocbench-table-vlm-v5/scored/index.html)。
- 困难表对照：[`comparison.html`](../../output/benchmarks/omnidocbench-table-vlm-v5/scored/page-035cb436-c01e-41db-b40e-8977678777eb/comparison.html)。
- 机器可读报告：[`omnidocbench-table-vlm-v5-results.json`](omnidocbench-table-vlm-v5-results.json)。
- 准备产物：`output/benchmarks/omnidocbench-table-vlm-v5/prepared/<page>/`。
- 真实调用：`output/benchmarks/omnidocbench-table-vlm-v5/live-authorized/summary.json`；
  第一张表的 `response.json` 保存完整响应。超时没有伪造响应文件。
- 评分与归一化 HTML：`output/benchmarks/omnidocbench-table-vlm-v5/scored/`。
- 测试日志：`output/benchmarks/omnidocbench-table-vlm-v5/unit-tests-final.log`。

`output/` 继续被 Git 忽略，因此完整图像/响应只在本机，仓库保存脚本、测试、设计与精简报告。

## 6. 复现

在项目根目录、现有 `multimodal-rag` Python 环境执行准备，输出目录必须全新：

```powershell
python scripts/experiment_vlm_tables.py prepare --source-dir output/benchmarks/omnidocbench-table-fidelity-v4/structure_export --images-dir backend/data/benchmarks/omnidocbench/images_academic_en_100 --output-dir output/benchmarks/table-vlm-reproduce/prepared
```

下列命令会发送 3 张公开数据集裁图至 `.env` 中配置的 VLM 服务并可能产生费用，**不自动执行**：

```powershell
python scripts/experiment_vlm_tables.py run --prepared-dir output/benchmarks/table-vlm-reproduce/prepared --output-dir output/benchmarks/table-vlm-reproduce/live --max-calls 3
```

只重新评分已保存的本次结果，不调用 API；仍需新的输出目录：

```powershell
$env:PYTHONUTF8 = '1'
$env:MPLCONFIGDIR = (Join-Path (Get-Location) 'backend/data/benchmarks/model_cache/matplotlib')
$env:HF_HOME = (Join-Path (Get-Location) 'backend/data/benchmarks/model_cache/huggingface-eval')
& 'backend/data/benchmarks/omnidocbench/.eval-venv/Scripts/python.exe' scripts/score_vlm_table_experiment.py --prepared-dir output/benchmarks/omnidocbench-table-vlm-v5/prepared --run-dir output/benchmarks/omnidocbench-table-vlm-v5/live-authorized --gold output/benchmarks/omnidocbench-scholar-lens-smoke-v2/selected_annotations.json --evaluator backend/data/benchmarks/omnidocbench/evaluator --output-dir output/benchmarks/table-vlm-rescore --previous-results output/benchmarks/omnidocbench-table-fidelity-v4/scores/table_structure/result/predictions_quick_match_table_result.json
python -m unittest discover -s tests
```

## 7. 下一步建议（本轮未实施）

1. 优先设计 **HTML 表格 → 程序解析为 cells** 的紧凑输出协议，减少逐格坐标/标志重复，
   让程序计算位置；仍需严格检查跨度、覆盖和数值，不是允许任意 HTML 进入前端。
2. 先用单张困难表验证该协议的结构与耗时，再决定是否对长表按区域处理、调整超时预算。
   分区时必须保留多层表头和跨区合并关系，不能机械截断。
3. 重跑两个正常对照并追加未用于开发的新表格页，验证错误修复与正常表退化率；
   这 3 张已看过的表不可以再叫 held-out。
4. 达到质量与延迟门槛后，再讨论选择性接入 Accurate 模式和结构感知 chunker。

当前决定：**保留离线能力；不把本轮 VLM 表格结果接入正式链路。**
