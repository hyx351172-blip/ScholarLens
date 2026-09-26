# 表格 OCR 绑定与内容评测 v9

## 结论

已打通 v8 延长结构模型 → 单元格检测 → OCR 匹配 → 完整 HTML 的离线链路，
并保存逐单元格绑定追踪。**结构修复不能直接等同于内容修复**：

| 样本 | Docling 完整 TEDS | 绑定后原始候选完整 TEDS | 候选结构 TEDS | 绑定完整性门 |
|---|---:|---:|---:|---|
| `035cb436…` 复杂元件数据表 | 0.211165 | 未运行，v8 结构无效 | — | 不通过 / 保留基线 |
| `0cbdcfa9…` EEPROM 数据表 | 0.959662 | **0.630081，退步** | 1.000000 | 不通过 / 保留基线 |
| `14a6b411…` 科研 benchmark 表 | 0.896314 | **0.939872，提升** | 0.979245 | 不通过 / 保留基线 |

两张候选的 HTML 都完整，但存在物理框与逻辑单元格对应风险。两张实际处理的表
均未通过保守绑定门；三例组合保留原基线，完整 TEDS **0.689047 → 0.689047**。
拒绝候选的分数仍作为诊断公开，不按 Gold 分数挑选替换结果。

**未部署、未提交推送、付费 API 调用为 0。**

## 本轮新增内容

- `scripts/experiment_table_ocr_binding.py`：最多两个 CPU worker，600 秒/个，无重试；
  使用本地模型路径、v8 独立图副本和 v7 缓存 OCR，不下载模型，不读取 Gold。
- `scripts/table_ocr_binding.py`：逐个记录逻辑 `(row, col, rowspan, colspan)`、
  物理框 ID/bbox、OCR ID/文字/bbox、覆盖率、最终渲染文字；识别丢失、重复、缺框、
  越界、渲染索引异常。不是按序补空格或猜单元格内容。
- 保守绑定门：数量不一致、终止边界异常、未分配/重复 OCR、缺少几何、
  覆盖率不足或渲染文字不一致时，保留基线；通过也只进入人工审查，不自动部署。
- `scripts/score_table_ocr_binding.py`：独立 Gold 评分阶段，官方完整/结构 TEDS，
  全表数字多重集、严格坐标内容诊断、唯一首列标签锚定诊断、可视化及完整错误清单。

在当前已有未提交工作区中增量开发，没有新建会遗漏既有改动的 worktree。
按 `ai-product-dev-pack` 的验收 → 失败测试 → 实现 → 真实接缝 → 回归流程完成。

## 实验控制

沿用固定三例裁图，先对所有源图、源解析、裁图及基线校验哈希。只有 v8 两张结构
有效且含 EOS 的样本进入 worker，第三张仍保留在三例分母中。

两次运行均验证结构 token 与 v8 已保存 HTML **逐字相同**，未换结构或借助 Gold。
复用 v7 的全表 OCR，保留 Paddle 按新物理框拆分并重识别局部文本的既有路径。
**本轮最终 OCR 文字与框都与缓存完全相同**，因此验证的是已有 OCR 的绑定路径，
不声称重新识别带来了准确率收益，也未单独验证新局部 OCR 识别能力。

CPU、4 线程、MKLDNN 关闭；PaddleOCR 3.7.0、PaddleX 3.7.2、PaddlePaddle 3.3.1、
NumPy 1.26.4。绑定推理约 10.297 / 11.407 秒，复用了 OCR，不能与从零解析全流程比速度。
未修改第三方库文件，只在各子进程内包装函数记录输入输出，并在退出前恢复。

## 定位到的具体问题

### 1. 物理框不足，顺序匹配导致空格丢失与错列

| 样本 | 逻辑单元格 | 检测/NMS 后框数 | 后处理框数 | OCR 段数 | 未分配 OCR | 追踪中缺几何单元格 |
|---|---:|---:|---:|---:|---:|---:|
| EEPROM | 492 | 298 | 355 | 280 | 33 | 180 |
| benchmark | 482 | 300 | 474 | 475 | 0 | 8 |

缺几何数量按实际 renderer 分组/索引计算，不是简单的 `逻辑数 − 框数`。
两张表均没有检测到 OCR 重复绑定；已找到的匹配覆盖率高不代表逻辑列正确。

EEPROM 的明确错误例子（零基坐标）：

- `(row=1,col=2)` Gold 为空，却被填入 `40`。
- `(1,3)` 应为 `40`，输出为 `41`。
- `(1,4)` 应为 `41`，输出为 `A`。

这些值多数被 OCR 正确识别，但没有留住空单元格位置，后续内容向左移动。
因此“结构 TEDS=1”仍可能伴随严重的文字列归属错误。

### 2. Paddle 匹配器混用了两种索引

安装版本的 `table_recognition_post_processing_v2.py` 会将逻辑行的单元格起始索引
与物理框分组边界映射，最后在逻辑起点列表追加 `len(table_cells_result)`。
EEPROM 的终止段变成 `[456,468,480,355]`：最后一个数是物理框数量，不是逻辑总数。

审计器最初将这一非单调尾标记直接拒绝。随后补了真实语义回归测试：该尾标记
不会再推进到末组之外，因此可以**记录异常并追踪原有行为**，但不修改任何绑定，
也不会放宽最终绑定门。最初 worker 结果原样保留，最终判定以 `scored-v2` 的统一审计为准。

### 3. 表头行数差异使严格坐标诊断非常敏感

科研 benchmark 的 Gold 是 42 行、488 个单元格；候选是 41 行、482 个单元格，
三层表头/rowspan 没有完全恢复。少一行表头会让后续正文坐标整体偏移。
所以不能把低坐标一致率直接解读为同样比例的数字被 OCR 读错。

## 内容诊断及限制

### 严格坐标：EEPROM

| 指标（分母含缺失单元格） | Docling | 原始绑定候选 |
|---|---:|---:|
| 非空 Gold 单元格文字完全一致 | 269/280 = 96.07% | 81/280 = 28.93% |
| 同坐标数字多重集完全一致 | 249/254 = 98.03% | 65/254 = 25.59% |
| 首列非空文字完全一致 | 37/41 = 90.24% | 9/41 = 21.95% |
| 全表数字多重集 F1（不检查位置） | 0.990060 | 0.928571 |

全表数字大多仍在，按单元格比较却明显退步，说明只用数字召回会漏掉错列。
数值提取使用明确正则，空白/NFKC 归一化不修正单位、正负号或数值，不能代表全部科研数字格式。

### 对表头偏移的补充诊断

新增唯一首列标签锚定比较：只允许完全匹配的唯一非空标签，重复标签不猜测，
列号/span 不重排，未匹配行仍计入分母。这仅用于评分，未反馈给识别流程或修改 TEDS。

科研表中可匹配标签仅为 Docling **8/39**、候选 **11/39**；许多标签因 OCR 或
空格格式不一致而无法严格匹配，覆盖不足。因此不把该子集诊断宣传为整体数字准确率。
详细覆盖率、缺失标签和两类坐标错误列表均保留供人工审查。

当前三例 Gold 均无 `<th>`/`<thead>` 显式表头标记；两个实际处理样本也没有命中
预定义单位词表的数值单元格。对应指标为 **N/A，而不是 100%**。
**本轮不能宣称表头语义或单位准确性已验收**，需要补充有显式标注的样本。

## 测试与证据

- 新增 25 项测试；全量 **270 passed，0 failures / errors / skips**，24.031 秒。
- 19 项纯绑定/指标测试在隔离 Paddle 环境也通过。
- 真实执行两次本地结构、单元格检测和 OCR 匹配；独立官方评分两次，基础分数一致。
- 38 个缓存/模型/先前实验保护文件及 15 个冻结源输入全部保持不变。
- 五条 AC 通过双向追溯；Python 编译和 `git diff --check` 通过。
- 已审查超时/失败保留、路径/哈希、HTML 安全、索引/契约与生产隔离。无 DB、UI 变更，
  未声称运行前端或在线 RAG E2E，未声称已配置 CI 闸。

## 产物与复现

路径均相对仓库根目录：

- 真实运行：`output/benchmarks/omnidocbench-table-ocr-binding-v9/`。
- 每例：`binding-capture.json`（原始匹配输入）、`paddle-raw.json`、`raw.html`、
  `response.json`、`pipeline-config.yaml` 和 `worker.log`。
- 最终报告：`output/benchmarks/omnidocbench-table-ocr-binding-v9-scored-v2/index.html`、`results.json`。
- 每例最终目录：`binding-trace.json`、`*-aligned-cells.json`、`comparison.html`。
- 完整性/回归：运行目录下 `postrun-integrity.json`、`regression-tests.json/.log`。
- 可入库摘要：`docs/evaluation/omnidocbench-table-ocr-binding-v9-results.json`。

本地完整产物与模型仍被 Git 忽略。首次评分目录 `…-v9-scored` 保留；
`…-v9-scored-v2` 补充标签锚定诊断，没有重跑模型、改识别结果或改正式解析。

```powershell
$env:PYTHONUTF8 = '1'
& 'E:/Anaconda/envs/multimodal-rag/python.exe' scripts/experiment_table_ocr_binding.py `
  --output output/benchmarks/table-ocr-binding-v9-repro

$env:MPLCONFIGDIR = (Join-Path (Get-Location) 'backend/data/benchmarks/model_cache/matplotlib')
$env:HF_HOME = (Join-Path (Get-Location) 'backend/data/benchmarks/model_cache/huggingface-eval')
& 'backend/data/benchmarks/omnidocbench/.eval-venv/Scripts/python.exe' scripts/score_table_ocr_binding.py `
  --prepared output/benchmarks/omnidocbench-table-vlm-v5/prepared `
  --run-dir output/benchmarks/table-ocr-binding-v9-repro `
  --v8 output/benchmarks/omnidocbench-table-decoder-v8-run3 `
  --gold output/benchmarks/omnidocbench-scholar-lens-smoke-v2/selected_annotations.json `
  --evaluator backend/data/benchmarks/omnidocbench/evaluator `
  --previous output/benchmarks/omnidocbench-table-fidelity-v4/scores/table_structure/result/predictions_quick_match_table_result.json `
  --output output/benchmarks/table-ocr-binding-v9-repro-scored
```

## 下一步

修复**物理框到逻辑网格的映射**：以几何行/列及 span 约束定位文字，显式保留没有
文字/没有检测框的空位置；框数不足时不得把后续内容顺序前移。对表头层级不一致
单独处理并继续严格回退。先用这两例冻结输入验证完整 TEDS 和列归属，再扩大样本。

继续加长输出上限或只换提示词，不能解决本轮已经定位的空单元格占位与匹配索引问题。
