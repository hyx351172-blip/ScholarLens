# ScholarLens 表格 HTML 转录 A/B v6

2026-09-25。**工程实现和实验完成；只在一张对照表上获得改进，复杂表未解决，不接入生产。**

## 结论

同一批 3 张裁图，对比 `qwen3-vl-plus + HTML` 和 `qwen3.5-ocr + HTML`，
共发送 6 次图像请求，无重试。6 次均收到完整响应、`finish_reason=stop` 和 usage，
但只有 1 份输出通过严格网格校验。请求完成不等于表格识别正确。

| 表格页 | Docling v4 TEDS | Qwen3-VL + HTML | Qwen-OCR + HTML |
|---|---:|---|---|
| `035cb436...` 困难规格表 | 0.211165 | 16 个缺位，拒收；50.281 秒 | 177 个缺位，拒收；11.296 秒 |
| `0cbdcfa9...` EEPROM 对照表 | 0.959662 | **TEDS 1.000000**；41.328 秒 | 113 个缺位，拒收；13.641 秒 |
| `14a6b411...` 规划算法对照表 | 0.896314 | 8 个缺位，拒收；49.156 秒 | 23 个缺位，拒收；18.922 秒 |

缺位指由模型给出的 HTML 行及 rowspan/colspan 计算后，矩形网格中未被显式单元格覆盖的位置。
它不等于图像中确有这么多缺失文字，可能源自漏写空格、错误跨度或错误列数，程序不猜测补齐。

| 汇总指标 | Qwen3-VL + HTML | Qwen-OCR + HTML |
|---|---:|---:|
| 完整请求 | 3/3 | 3/3 |
| 通过结构校验 | 1/3 | 0/3 |
| 原基线平均 TEDS | 0.689047 | 0.689047 |
| 无效候选回退后的平均 TEDS | **0.702493** | 0.689047 |
| 候选失败计零的任务完成口径 | 0.333333 | 0.000000 |
| 平均首文本时间 | 1.364 秒 | 1.677 秒 |
| 平均整次请求时间 | 46.922 秒 | 14.620 秒 |
| 已返回总 tokens | 15,861 | 18,560 |

通过的 EEPROM 表为 41 行、12 列、492 格；structure-only TEDS=1、归一化 HTML
edit distance=0、数字 token multiset F1=1。只能说明这一表在当前评测口径下匹配，
不能声称所有论文/数值/语义都完全正确。两组都没有通过扩大 held-out 实验的烟测门槛。

## 实现与保护措施

按 `ai-product-dev-pack` 先写设计/验收与失败测试，再实现、联调、实测。

1. **流式客户端**：connect/read/write/pool 分别为 20/60/30/10 秒；另外用异步 deadline
   限制整次生成为 300 秒。关闭 stream 最多额外等待 5 秒。read 超时只是两次网络读取间的
   不活跃时间，不替代总时限。记录首事件、首文本、最大事件/文本间隔、尾部等待、总时长及 usage。
2. **输出协议**：两组相同裁图字节、相同提示词、temperature=0、max_tokens=8192，
   不使用 JSON response constraint。通用模型单独设置 enable_thinking=false，OCR 不传 thinking 参数。
   使用 OpenAI 兼容接口手写 HTML 提示词，**没有使用 DashScope 的原生 `ocr_options.table_parsing`**。
3. **确定性转换**：HTML → 显式行序与跨度 → cells。保留空单元格与 `[UNCERTAIN]`；
   不伪造图像 bbox。严格拒绝缺格、重叠、越界、不完整标签、多表、嵌套表和过大网格。
4. **安全呈现**：拒绝脚本、链接、事件属性；仅丢弃允许的展示属性，文字转义后重新生成 HTML。
   不把原始模型 HTML 放进正式前端。原始响应以 JSON 保存，报告用转义文本展示。
5. **预算/回退**：每次网络调用前写 attempted 日志；最多 6 次、顺序交错执行、SDK retries=0。
   拒绝已有输出目录、重复 case 和输入哈希变更。鉴权/模型不存在时停止对应组；
   超时、拒绝、截断或非法结构均保留诊断并回退 baseline，不通过 Gold 选较高分结果。

新增配置是可选的 `TABLE_OCR_API_KEY`、`TABLE_OCR_BASE_URL`、`TABLE_OCR_MODEL_NAME`。
未设置前两项时复用已有 VLM 配置；OCR 模型默认 `qwen3.5-ocr`。本轮未改写 `.env` 或暴露 Key。
模型列表预检查只确认可列出，实际调用能力由这 6 次实验确认。

## 失败分析与限制

- 困难表：通用模型输出 56×9 网格，表头及后部若干行缺最后一列；OCR 输出 53×8 网格，
  多层表头及许多成对型号行未完整覆盖。整体 HTML 合法仍不能证明物理网格正确。
- 规划算法表：通用模型主要在两行表头各缺 4 格；OCR 为 42×12，23 个缺位分布在表头和其他行。
  这是接下来可先做局部诊断的样本，但不能直接往右侧补空格，缺位可能来自前面错误的 colspan。
- EEPROM：通用模型成功；OCR 多行短于 12 列。专用模型更快不等于能直接替换 Docling。
- 三份 OCR 输出均带 Markdown HTML 围栏；转换器仅允许整体围栏剥离，不从混杂文本中猜取表格。
- 6 次 usage 完整，合计 **34,421 tokens**。未根据不确定的端点价格估算金额，以服务商账单为准。
- 前两张是电子器件资料中的表格，不应因数据集来源标签而称为两篇科研论文。
  这 3 张是已经观察过的开发样本，**不是 held-out，也不是全 PDF/RAG 端到端评测**。
- v5 JSON 实验同时在提示词、输出长度、流式/非流式和超时策略上不同，因此不能把本次耗时变化
  归因于 HTML 格式这一项，更不能由 6 次无超时断言已解决所有网络/服务端问题。
- 数字 multiset 指标忽略单元格对齐、单位和含字母值；不是单元格数值准确率。

当前决定：不改生产解析器、chunker、检索、向量库或前端；不扩大付费样本。
下一步优先针对表头/合并关系做结构定位与 OCR 分离的实验，或在结构明确的局部区域重识别，
保留完整表头及跨区跨度。不得通过放宽校验或 Gold 补格把失败变成成功。

## 验证

- 新增 17 项测试，RED → GREEN；最终全套 **213 tests passed**，0 失败/跳过，18.945 秒。
- HTML 单元层、预算与篡改切片、真实本地 HTTP/SSE + OpenAI SDK 接缝、6 次真实服务请求、
  两组共 6 个固定表格配对评分分别验证，未声称覆盖真实数据库、前端或部署。
- 评分固定使用 OmniDocBench commit `f133a71e9e91c3621c7ce8994200a7b394a06eb3`
  的 `normalized_html_table`/`TEDS`；本轮不修改 evaluator。原基线 TEDS/structure-only
  与 v4 逐表一致，误差 < 1e-9。
- Gold SHA-256：`f25369f9845039f7474591e9a0c275443c5a2149fc975270f35a80ada7da43a4`。
- 复用裁图 manifest SHA-256：`ec607623012941880f473966b1ddbe4e345919a886561044d6604175054411de`。
- 第一次本地评分因间接导入 PyMuPDF 而失败；已改为纯 HTML 模块直接导入，新增禁用 site-packages
  的子进程回归测试；在新的 `scored-*-v2` 目录评分成功，没有重发 API。
- 评分阶段仅增强了拒收原因中的缺位计数，不改变任何候选接收规则。
- 保留原有 dirty worktree；没有提交、推送、自动生产替换或删除既有数据。
- 原图、原 document/native JSON、裁图和 baseline 共 15 个文件哈希复核全部未变化；
  `git diff --check` 与新增/调整模块的 Python 编译检查通过。

## 产物入口

- [联合对照入口](../../output/benchmarks/omnidocbench-table-html-v6/comparison/index.html)
- [通用模型逐表可视化](../../output/benchmarks/omnidocbench-table-html-v6/scored-generic-v2/index.html)
- [OCR 模型逐表可视化](../../output/benchmarks/omnidocbench-table-html-v6/scored-ocr-v2/index.html)
- [仓库精简机器报告](omnidocbench-table-html-v6-results.json)
- [设计与验收](../specs/table_html_ab/implementation.md)

原始响应及流式中间记录：`output/benchmarks/omnidocbench-table-html-v6/live/<arm>/<page>/`。
包含 `response.json`、`progress.json`；仅合法候选存在 `candidate.html`/`candidate-structure.json`。
每组 `summary.json` 保存全部 3 个样本（含失败）。`output/` 继续被 Git 忽略。

## 复现

在项目根目录、原 multimodal-rag 环境运行测试：

```powershell
python -m unittest discover -s tests -p 'test_*.py'
```

以下命令会产生最多 6 次付费请求；输出必须是全新目录，不自动续跑：

```powershell
python scripts/experiment_html_tables.py --prepared-dir output/benchmarks/omnidocbench-table-vlm-v5/prepared --output-dir output/benchmarks/table-html-new-run --max-calls 6
```

只重评已有响应、不调用模型（将输出根目录设为新路径）：

```powershell
$env:PYTHONUTF8 = '1'
$env:MPLCONFIGDIR = (Join-Path (Get-Location) 'backend/data/benchmarks/model_cache/matplotlib')
$env:HF_HOME = (Join-Path (Get-Location) 'backend/data/benchmarks/model_cache/huggingface-eval')
$tableReplayRoot = 'output/benchmarks/table-html-rescore-01'
foreach ($tableArm in @('generic_html', 'ocr_html')) {
  & 'backend/data/benchmarks/omnidocbench/.eval-venv/Scripts/python.exe' scripts/score_vlm_table_experiment.py --prepared-dir output/benchmarks/omnidocbench-table-vlm-v5/prepared --run-dir "output/benchmarks/omnidocbench-table-html-v6/live/$tableArm" --gold output/benchmarks/omnidocbench-scholar-lens-smoke-v2/selected_annotations.json --evaluator backend/data/benchmarks/omnidocbench/evaluator --output-dir "$tableReplayRoot/$tableArm" --previous-results output/benchmarks/omnidocbench-table-fidelity-v4/scores/table_structure/result/predictions_quick_match_table_result.json
}
python scripts/summarize_html_table_ab.py --generic-score "$tableReplayRoot/generic_html/results.json" --ocr-score "$tableReplayRoot/ocr_html/results.json" --run-summary output/benchmarks/omnidocbench-table-html-v6/live/summary.json --output-dir "$tableReplayRoot/comparison"
```

接口依据：[Qwen-OCR](https://help.aliyun.com/zh/model-studio/qwen-vl-ocr)、
[Qwen-OCR API](https://help.aliyun.com/zh/model-studio/qwen-vl-ocr-api-reference)、
[HTTPX 分项超时](https://www.python-httpx.org/advanced/timeouts/)。服务文档只支撑协议设计，
模型效果结论来自本地冻结数据与本次真实响应。
