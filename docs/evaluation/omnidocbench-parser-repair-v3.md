# ScholarLens 解析修复与复测（OmniDocBench v3）

日期：2026-09-25。范围：修复上一轮固定 10 页开发样本暴露的公式识别、Markdown 导出与阅读顺序一致性问题。

后续勘误：v4 已定位上游评分器将 `pred_idx=0` 当成空值的缺陷。本文保留当时的原始上游分数；修正评分器后，同一 v3 预测的 Reading Order 为 0.0319，而不是 0.2390。这是评分纠正而非模型提升，详见 `omnidocbench-table-fidelity-v4.md`。

## 结论

公式输出缺失问题已修复，阅读顺序指标明显改善，表格指标没有变化。此次是开发样本上的修复验证，不是完整 OmniDocBench 成绩，也不是未参与开发的 held-out 测试。

同一份 Gold、相同官方评分器与匹配参数下：

| 指标 | 修复前 v2 | 仅修复导出 | 完整修复 v3 | 分母 |
|---|---:|---:|---:|---|
| 文本 Edit distance ↓ | 0.2333 | 0.2057 | 0.2080 | 9 页 |
| 公式 Edit distance ↓ | 1.0000 | 0.8667 | 0.2547 | 4 页、30 条公式匹配结果 |
| 阅读顺序 Edit distance ↓ | 0.4842 | 0.3749 | 0.2390 | 10 页 |
| 表格 TEDS ↑ | 0.6856 | 0.6856 | 0.6856 | 3 张表 |
| 表格 structure-only TEDS ↑ | 0.7719 | 0.7719 | 0.7719 | 3 张表 |
| 表格 Edit distance ↓ | 0.6137 | 0.6137 | 0.6137 | 3 张表 |
| 公式匹配结果中的空预测 | 30/30 | 11/30 | 0/30 | 官方匹配输出 |

Edit distance 使用官方 `ALL_page_avg`，越低越好；TEDS 使用 0–1 原始值，越高越好。编辑距离不是准确率，不能将 `1 - Edit distance` 宣称为公式正确率。

精确数值、页面名单、运行环境及结果目录见同目录的 `omnidocbench-parser-repair-v3-results.json`。

## 根因和代码修改

1. **公式识别没有启用。** 现在为 Docling 配置 `do_formula_enrichment=True`，调用本地 CodeFormulaV2；支持显式关闭，并在解析产物的 `parser.formula_enrichment_enabled` 中记录设置。该选项用于公式转写，参见 [Docling 官方 enrichment 文档](https://docling-project.github.io/docling/usage/enrichments/)。
2. **导出与结构化结果不一致。** 之前 Markdown 使用 Docling 原始导出，未消费后处理后的 blocks。v2 JSON 中实际有 22 个公式块，其中 20 个有 `orig` 回退文本，但导出仍是公式占位符。现在统一从最终 blocks 生成 Markdown，导出公式、标题层级和后处理后的阅读顺序，保留表格文本。
3. **VLM 修复后 Markdown 可能过期。** 修复完成后重新渲染 Markdown，使展示、导出与 chunker 使用相同的最终证据。没有放宽 VLM 的对象修改权限。
4. **坐标原点需要统一。** 显式标记为 TOPLEFT 的 bbox 按页面高度转为系统使用的 bottom-left 坐标；缺少高度时禁用该块的几何信息，避免错误反转。此项有单元测试，但未单独测量其对本轮指标的贡献。
5. **扫描页 OCR 引擎显式配置。** 开启 OCR 时指定 EasyOCR，并补齐依赖，避免依赖自动选择时出现环境差异。服务支持通过环境变量控制 OCR 和公式识别。

新增的 canonical Markdown renderer 对没有识别出的公式仍保留缺失标记，对 `orig_fallback` 明确标记为未经验证的 OCR 转写，不编造 LaTeX。

## 对照实验设计

- Gold 沿用 smoke-v2 的 `selected_annotations.json`，SHA-256 为 `f25369f9845039f7474591e9a0c275443c5a2149fc975270f35a80ada7da43a4`，三组完全一致。
- 10 页按子集配额、文件名排序确定性选取：4 页 equation_hard、3 页 table_hard、1 页 layout_hard、2 页 v1.5；7 页单栏、3 页双栏。
- 图片无损包装为单页 PDF，沿用相同的页面尺寸约定（图片像素数对应 PDF point 数），不改变输入图像。
- **仅修复导出**：复用 v2 的完整 `document.json`，不重新运行 OCR、布局或公式模型，只使用新 renderer。每份输入的哈希保存在 `reexport-summary.json`。
- **完整修复**：重新运行解析，开启公式识别，再导出最终 blocks。
- 未更改 Gold、官方评分逻辑或匹配阈值。正文指标略差于仅导出组（0.2057 → 0.2080），并非所有指标都单调改善。

仅修复导出已经改善阅读顺序和公式指标，说明一部分缺陷在数据传递链路。进一步启用公式识别带来主要公式增益；阅读顺序改善也受到公式不再缺失的影响，不能全部归因于几何排序算法。

## 环境、运行与验证

- Python 3.11.16，Docling 2.117.0，EasyOCR 1.7.2，表格模式 accurate，CPU 推理。
- 公式模型：[docling-project/CodeFormulaV2](https://huggingface.co/docling-project/CodeFormulaV2)，快照 `ecedbe111d15c2dc60bfd4a823cbe80127b58af4`。
- 官方评测器：[OmniDocBench](https://github.com/opendatalab/OmniDocBench)，commit `f133a71e9e91c3621c7ce8994200a7b394a06eb3`。
- `quick_match`；page/TEDS workers 均为 2；truncated timeout 300 秒、page timeout 420 秒、fallback span 10、order penalty 0.10。三组的匹配超时及 TEDS 异常均为 0。
- 评分器使用独立虚拟环境；为兼容 Windows wheel，lxml 使用 4.9.3 代替 4.9.1，三组环境一致。
- 完整修复成功 10/10 页。首次运行因本地 Hugging Face 快照缺少 README 元数据导致前 6 页失败；补全官方快照后重跑这 6 页，保留原失败记录。最终目录汇总 10 份成功产物，不将失败页从评分中剔除。
- 已完成页记录的解析耗时合计 1402.163 秒，平均 140.216 秒/页；v2 为 629.793 秒、62.979 秒/页。公式模型增加 CPU 耗时，但本轮存在冷启动、分批重跑及其他 CPU 工作，不应视作严格的速度 A/B。失败尝试和下载时间不包含在该合计中。
- 最终汇总使用 `--reuse`，保留原始解析时长，另行记录缓存读取时间，不将重用缓存宣称为推理加速。
- 全程本地推理，没有调用收费模型 API。
- `python -m unittest discover -s tests`：**175 项通过，0 失败**（最终复跑 15.608 秒）；新增用例覆盖公式开关、导出缺失、最终顺序、坐标原点、表格/标题保留及旧缓存配置拒绝。`git diff --check` 通过。
- 后端服务未启动，本轮没有运行浏览器上传至 Milvus 的在线全链路测试；解析服务到 chunker 的集成路径通过自动化测试。

## 仍然存在的问题

1. **公式不是全部正确。** Canonical JSON 有 22 个公式块，22 个均有模型转写，不再使用 `orig_fallback`；Gold 有 30 个独立公式。块边界可能合并多个公式，官方匹配也会拆分，不能用 22/30 计算召回率，更不能用空预测为 0 宣称完全识别。
2. **复杂公式仍有明显误差。** `page-268266af-56c0-4b3b-9d07-73c6e50feb58.png` 的公式页均编辑距离仍为 0.4117，需要继续检查符号、数组及长表达式。LaTeX 字符串差异不完全等价于数学语义错误；本轮缺少 TeX Live/Ghostscript，未运行 CDM。
3. **表格内容与结构问题未修复。** TEDS 完全不变，本轮没有调整单元格识别、跨块合并或 rowspan/colspan 的表达。需要单独做表格专项实验。
4. **阅读顺序评分需要勘误。** 原始上游结果中 `page-035cb436-c01e-41db-b40e-8977678777eb.png` 和 `page-0cbdcfa9-3248-4e54-8704-2bc73e6d29e7.png` 的距离为 1.0，输出分别是 `gt=[3], pred=[]` 和 `gt=[1], pred=[]`。后续 v4 证实预测表格实际非空，但上游评分器丢弃了索引为 0 的预测位置；并非这两页表格没有识别。修正后的两页阅读顺序距离均为 0，不需要因此修改几何排序规则。
5. **评测范围有限。** 这里只衡量 10 页扫描/图片型学术页面，不能替代原生数字 PDF、固定 100 页评测，或 QASPER/SciFact/SPIQA 的问答与证据评测。由于本轮已针对这些样本修复，它们应保留为开发回归集。

## 应用到实际项目

服务默认开启 `DOCLING_FORMULA_ENRICHMENT=true` 和 `DOCLING_OCR_ENABLED=true`，示例见根目录 `.env.example`。首次使用需要下载本地模型；本轮模型缓存位于 `backend/data/benchmarks/model_cache/huggingface`，EasyOCR 缓存位于同级 `easyocr`。服务若使用不同缓存位置，可能需要重新下载；离线启动前应设置匹配的 `HF_HOME` 与 `EASYOCR_MODULE_PATH`。

重启解析服务后，新解析会使用修复版。已有解析产物、chunks 和 Milvus 向量**不会自动更新**，需按项目重解析/重建索引流程更新后才能影响已有知识库问答。本轮没有删除、覆盖或重建用户的现有 Milvus 数据。

如果只处理可靠的原生文本 PDF，可显式关闭 OCR；若关闭公式 enrichment，仍会导出已有 OCR 回退文本，但不再具有本轮验证的公式识别效果。

## 产物与复现入口

- 修复前：`output/benchmarks/omnidocbench-scholar-lens-smoke-v2/`
- 仅导出对照：`output/benchmarks/omnidocbench-scholar-lens-export-only-v3/`
- 最终修复结果：`output/benchmarks/omnidocbench-scholar-lens-fixed-v3/`
- 最终目录中的 `predictions/` 为评分 Markdown，`artifacts/<page>/` 保存完整结构化 JSON、原始 Docling JSON 和 Markdown；`result/` 保存官方详细指标与页级匹配结果。
- 首次运行及重跑审计分别保留在 `omnidocbench-scholar-lens-smoke-v3/` 和 `omnidocbench-scholar-lens-smoke-v3-prefix/`。
- 大体积数据、模型和解析产物保持 Git 忽略；本报告与精简 JSON 记录可随代码版本保存。

在项目根目录、已配置相同模型缓存及运行环境后，可在一个新输出目录重跑，避免覆盖本轮证据：

```powershell
python scripts/generate_omnidocbench_predictions.py --annotations output/benchmarks/omnidocbench-scholar-lens-smoke-v2/selected_annotations.json --image-dir backend/data/benchmarks/omnidocbench/images_academic_en_100 --output-dir output/benchmarks/omnidocbench-reproduce-v3 --ocr --formula-enrichment
python scripts/reexport_parser_artifacts.py --artifact-dir output/benchmarks/omnidocbench-scholar-lens-smoke-v2/artifacts --output-dir output/benchmarks/omnidocbench-reproduce-export-v3
python -m unittest discover -s tests
```

评分使用官方 `pdf_validation.py --config <yaml>`，配置沿用最终结果目录的 `omnidocbench-eval.yaml` 并将 prediction 路径指向新目录；在独立输出目录运行，官方结果写入当前目录的 `result/`。Gold 始终指向上述固定 10 页文件。
