# ScholarLens 表格专用解析对照 v7

2026-09-25。按优化计划执行第一阶段：PP-TableMagic 独立本地实验和
Qwen-OCR 原生 `table_parsing`。本轮不改正式 PDF 解析、chunker、知识库或前端。

## 结论与结果

**工程实现与本轮实验完成，但两条新方案均未通过严格结构准入，不接入生产。**
3 次原生 API 请求全部正常结束；Paddle 修复 Windows 路径问题后也完成了 3 张图推理。
这不代表输出的表格结构完整。

| 表格 | Docling v4 TEDS | PP-TableMagic | Qwen 原生任务 |
|---|---:|---|---|
| 困难器件规格表 `035cb436...` | 0.211165 | 标签不闭合；实际推理 163.156 秒 | 53×8 网格，176 缺位；12.750 秒 |
| EEPROM 表 `0cbdcfa9...` | 0.959662 | 36 个起始行标签、35 个结束行标签；188.375 秒 | 41×12 网格，113 缺位；16.797 秒 |
| 规划算法表 `14a6b411...` | 0.896314 | 缺少表体结束标签；293.812 秒 | 40×36 网格，943 缺位；21.594 秒 |

“缺位”是输出跨度推导的矩形网格中未覆盖的位置，不是实际缺失文字数量。
异常列数会放大此值。Paddle 和 Qwen 均为 **0/3 候选通过结构校验**，
拒收结果没有作为正式候选计算 TEDS；这不是声称它们的 OCR 文字准确率为零。

| 方案 | 有效候选 | 无效候选保留基线后的平均 TEDS |
|---|---:|---:|
| Docling v4 基线 | — | 0.689047 |
| v6 Qwen3-VL + 自定义 HTML 提示词（历史结果） | 1/3 | 0.702493 |
| v6 Qwen-OCR + 自定义 HTML 提示词（历史结果） | 0/3 | 0.689047 |
| v7 Qwen 原生表格任务 | 0/3 | 0.689047 |
| v7 PP-TableMagic | 0/3 | 0.689047 |

两组 v7 的候选失败计零汇总均为 0，代表“可用候选完成口径”，不是原始 HTML 的真实 TEDS。
独立官方评分确认所有基线数值仍与 v4 一致。不存在按 Gold 挑更高分结果的流程。

本轮新增付费调用 **3 次，18,064 tokens**，平均请求 17.047 秒，无重试、无截断或超时。
v6 的 6 次请求只读取历史记录，没有重复计费。不推算金额，以供应商账单为准。
Paddle 为 CPU 本地推理：平均实际推理 215.114 秒；首次初始化含下载 127.813 秒，
后两次初始化 9.875 / 9.563 秒。不能把冷启动总耗时与 API 请求耗时当成公平性能排名。

## 失败定位与下一步

1. **Paddle 不仅是外围 HTML 标签问题。** 困难表有孤立的 `</tbody>`；只在内存中
   临时忽略该孤立结束标签作诊断，仍得到 33×10 网格、53 个缺位。未修改任何候选或评分。
2. **长表的结构序列长度值得优先检查。** 下载模型配置含 `max_text_length=500`，
   resize 长边为 512。根据模型的合并空跨度单元格词表从输出反推，后两表均约为
   **501 个结构 token**，同时存在行/表体未闭合；与长度上限假设一致。
   这是诊断推断，尚未记录实际静态解码器 EOS/输出张量，不能断言已完全证明根因。
   困难表约 348 token，不能用同一个长度原因解释所有失败。
3. **Qwen 原生任务未修复结构问题。** 最后一表输出大量额外空单元格，列数变成 36；
   不能通过右侧统一补空格或减少列数来猜修。三个 `finish_reason=stop` 只证明 API 正常结束。
4. 下一步应先做**结构解码器长度与网格定位实验**：捕获结构 token/EOS，评估支持长序列的
   模型路径或保留表头与跨行关系的局部识别，再考虑 render-then-verify。
   静态导出模型的长度上限不一定能靠改配置生效；不要直接改 `500` 就声称已修复。
   暂不扩大付费样本、改线上解析器，或同时叠加更多模型。

Paddle 适配层当前把“流水线正常返回”映射为通用 `finish_reason=stop`；
这不是 Paddle 暴露的 EOS 信号，也不能据此断言没有结构序列截断。

## 验证记录

- 本次新增 14 项测试；最终全套 **227 passed，0 failures/errors/skips**，24.890 秒。
- 同一批 14 项新测试也在独立 Paddle 环境中通过；`pip check` 无依赖冲突。
- 评分器报告标签改为通用 model 后，6 项评分器测试再次通过。
- 原生接口真实 HTTP/SSE seam、3 次真实 API 请求、3 张实际 Paddle 推理、两组官方评分均已执行。
- AC-1001 至 AC-1006 可追溯检查通过；原始输入与基线 15 个文件哈希全部匹配。
- 不提交/推送、不更改密钥、不覆盖原始解析、不写入知识库。

## 实验设计

- 使用 v5 保存的相同 3 张裁图；预测框来自 Docling，而非 Gold。
- 对照为 v4 Docling 结构导出基线，以及已完成的 v6 两组 HTML 转录结果。
- `035cb436...` 为复杂器件规格表；`0cbdcfa9...` 为 EEPROM 规格表；
  `14a6b411...` 为规划算法实验表。前两张不是科研论文。
- 全部是观察过的开发样本，不是 held-out；不能外推到所有论文或 RAG 问答。
- 推理阶段只读取图片和配置。Gold 仅由独立评分脚本读取，不用于补值、修跨度或选高分候选。
- 结构准入规则与 v6 一致：完整 HTML、单表、显式单元格覆盖、跨度合法；失败保留基线。
- 使用未修改的 OmniDocBench `normalized_html_table` + TEDS，对固定表格做 1:1 配对，
  同时报 structure-only TEDS、HTML edit distance 和数字 multiset 诊断。
  数字 multiset 不包含单元格位置关系，不是数值单元格准确率。

## 两条新路径

### PP-TableMagic

固定 `paddleocr==3.7.0`、`paddlex==3.7.2`、`paddlepaddle==3.3.1`、`numpy==1.26.4`，
独立环境在 `backend/data/benchmarks/tablemagic/.venv`。不更改应用环境依赖。

完整 TableRecognitionPipelineV2 使用表格分类、SLANeXt 有线/无线结构识别、
RT-DETR 有线/无线单元格检测、PP-OCRv5 server 文字检测与识别。
已裁好的图不再进行页面布局检测、转正或去扭曲。4 CPU threads，MKLDNN 关闭。
这不是最优 CPU 性能调参实验；不能用其耗时推断所有部署方式的性能。

每张表独立子进程、600 秒上限；保存 `paddle-raw.json` 中的单元格框、OCR 和 HTML，
以及 `pipeline-config.yaml`、实际依赖版本、初始化/推理/进程总时间。
模型下载、环境安装和缓存均与应用隔离。缓存位于项目忽略目录，不上传 Git。

首轮本地启动失败：Windows 底层模型加载器未能读取含中文的绝对路径。
同一 JSON 可由 Python 读取，用 ASCII 相对路径交给同一 Paddle 模型后成功。
已通过固定工作目录和相对缓存路径解决；图片由 Python 解码为数组后传入。
原失败记录留在 `live/pp_tablemagic`，修复后实际实验在 `live/pp_tablemagic-v2`。
没有移动项目、修改第三方源码或重跑付费接口。

### Qwen-OCR 原生任务

复用本地配置的官方阿里端点及密钥，模型 `qwen3.5-ocr`，通过 DashScope
原生 HTTP/SSE 调用 `parameters.ocr_options.task=table_parsing`，只传图片，不传手写提示词。
max_tokens=8192、incremental_output=true，其他采样参数使用服务默认值。

只允许已识别的官方 HTTPS 域名；禁用跳转和重试；connect/read/write/pool
分别 20/60/30/10 秒，另设 300 秒总 deadline。调用前持久化 attempted 日志，
最多 3 次；保存部分响应、finish_reason、usage、首文本时间与请求总时长。
不保存 Key、请求头或供应商原始错误正文。

这与 v6 的 OpenAI 兼容接口手写 HTML 提示词存在任务、提示词和默认采样差异，
只能视为系统方案对照，不能声称是单变量消融。

## 产物

所有大型/原始产物位于本地忽略目录 `output/benchmarks/omnidocbench-table-specialist-v7/`：

- `live/qwen_native/`：3 次原生请求的日志与原始响应。
- `live/pp_tablemagic/`：首次 Windows 路径失败记录。
- `live/pp_tablemagic-v2/`：修复路径后的完整 Paddle 原始结构。
- `scored-qwen-native/`、`scored-pp-tablemagic/`：独立评分和逐表图文对照。
- `comparison/index.html`：四组方案与 Docling 基线的汇总入口。
- `paddle-environment.json`：本次独立环境全部包版本。
- `paddle-models.json`：7 个模型的 28 个权重/结构/配置文件的 SHA256。
- `paddle-structure-diagnostics.json`：标签计数与结构序列长度的只读诊断估计。
- `input-integrity.json`：15 个原图/裁图/解析文件/基线文件的哈希校验。
- `regression-tests.json`、`regression-tests.log`：完整回归测试执行记录。

## 复现

从项目根目录运行，下列命令需要已准备好的同名 v4/v5 产物；没有这些文件时不要重新
按 Gold 裁图凑输入。已有输出目录不可覆盖，重跑请改成新的实验目录。

```powershell
python -m venv backend/data/benchmarks/tablemagic/.venv
backend/data/benchmarks/tablemagic/.venv/Scripts/python.exe -m pip install -r scripts/requirements-table-specialist.txt

python scripts/experiment_table_specialists.py --arm pp_tablemagic --prepared-dir output/benchmarks/omnidocbench-table-vlm-v5/prepared --output-dir output/benchmarks/NEW/local

# 以下命令会产生最多 3 次 API 费用；不自动重试。
python scripts/experiment_table_specialists.py --arm qwen_native --prepared-dir output/benchmarks/omnidocbench-table-vlm-v5/prepared --output-dir output/benchmarks/NEW/native
```

如需显式配置原生端点，可在本地 `.env` 添加 `TABLE_OCR_NATIVE_BASE_URL` 或
`DASHSCOPE_NATIVE_BASE_URL`，取值为官方 `/api/v1` 基址或完整 generation 地址。
未配置时仅从已识别的官方 OpenAI-compatible 地址推导同源原生地址。
模型可用 `TABLE_OCR_MODEL_NAME`；Key 优先级为 `TABLE_OCR_API_KEY`、`DASHSCOPE_API_KEY`、
`VLM_REPAIR_API_KEY`、`API_KEY`。不支持向第三方地址自动转发 Key。

评分使用 `scripts/score_vlm_table_experiment.py` 与固定 evaluator 环境；参数与 v6 相同，
更换 `--run-dir` 和全新的 `--output-dir` 即可。
四组汇总使用 `scripts/summarize_table_specialists.py --scores <各组 results.json> --output-dir <新目录>`。
实验 CLI 退出码 2 表示至少一个候选未通过，不等于全部请求失败；以 `summary.json` 的
逐项状态、`response.json` 和 `worker.log` 定位原因。全量测试使用
`python -m unittest discover -s tests -p 'test_*.py'`。

## 依据

- [PaddleOCR TableRecognitionPipelineV2](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/table_recognition_v2.html)
- [阿里 Qwen-OCR 原生任务与 SSE 契约](https://help.aliyun.com/zh/model-studio/qwen-vl-ocr-api-reference)

按 `ai-product-dev-pack` 的单特性闭环先写验收和失败测试，再实现、联调、运行真实实验与回归；
没有通过改松校验规则提升通过率。
