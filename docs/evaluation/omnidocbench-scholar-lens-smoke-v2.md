# ScholarLens OmniDocBench 解析基线（Smoke v2）

## 结论

当前解析器已能稳定完成复杂学术页面的文本与表格解析，但公式识别链路尚未形成有效输出，阅读顺序在单栏复杂页面上也存在明显错误。本轮结果适合作为后续改进的开发基线，不应视为完整 OmniDocBench 榜单成绩。

## 评测范围

- 数据集：OmniDocBench 英文学术页面子集
- 抽样方式：按 `subset` 确定性分层配额、各层按文件名排序取样（没有随机种子）
- 页面数：10
- 页面构成：4 页 `equation_hard`、3 页 `table_hard`、1 页 `layout_hard`、2 页 `v1.5`
- 布局构成：7 页单栏、3 页双栏
- 解析配置：Docling `accurate` 表格模式 + EasyOCR
- 评测器：OmniDocBench 官方 evaluator，`quick_match`
- 评测日期：2026-09-25

## 运行结果

- 成功解析：10/10 页
- 失败：0 页
- 总耗时：629.793 秒
- 平均耗时：62.979 秒/页
- 页匹配超时或回退：0
- TEDS 超时或异常：0

## 官方指标

`Edit_dist` 越低越好，`TEDS` 越高越好。

| 能力 | 指标 | 结果 | 样本量 | 判断 |
|---|---:|---:|---:|---|
| 文本块 | Edit distance | 0.2333 | 9 页 / 59 块 | 基础可用，仍有字符与块边界误差 |
| 公式 | Edit distance | 1.0000 | 4 页 / 30 个公式 | 失败；30 个公式预测均为空 |
| 表格 | TEDS | 0.6856 | 3 张表 | 中等，内容与结构仍需提升 |
| 表格结构 | TEDS structure-only | 0.7719 | 3 张表 | 结构优于单元格内容 |
| 表格 | Edit distance | 0.6137 | 3 张表 | 单元格文本误差较大 |
| 阅读顺序 | Edit distance | 0.4842 | 10 页 | 偏弱，复杂单栏页面问题突出 |

公式 CDM 本轮未运行，因为本机缺少官方指标所需的 TeX Live/Ghostscript 环境；公式的 Edit distance 已足以确认当前主要故障是预测缺失。

## 分组观察

- 文本块在 `table_hard` 页面表现最好（Edit distance 0.0406），在 `equation_hard` 页面最差（0.3954）。
- 双栏文本优于单栏文本（0.1453 vs 0.2773），说明本轮主要错误不只是传统的双栏串行问题。
- 阅读顺序在 `table_hard` 页面最差（0.7857），`equation_hard` 次之（0.5402）。
- 表格结构分数 0.7719 明显高于表格整体 TEDS 0.6856，说明表格骨架大体可恢复，主要损失来自单元格内容和局部合并关系。
- 公式结果中 30/30 个匹配项的预测为空。后续代码排查确认：未启用 Docling 公式 enrichment，且评测 Markdown 来自原始导出，未包含 canonical block 的 `orig` 回退文本。这个结果表示评测端没有可匹配公式，并不代表结构化 JSON 中没有公式 block。
- 阅读顺序 Edit distance 同时受漏块影响，不能将 0.4842 全部归因为几何排序错误。

## 结果解释边界

本轮使用的是 OmniDocBench 页面图片。为了复用 ScholarLens 的 PDF 入口，每张图片被无损包装成单页 PDF 后解析。因此，它主要衡量扫描页/图片页的 OCR、布局、表格和公式能力，不能替代对原生数字 PDF 的评测。

10 页只用于快速暴露系统级缺陷。完成公式链路与阅读顺序修复后，应在已准备的 100 页固定子集上重跑，再考虑扩大到完整公开集。

## 可复现产物

- 推理摘要：`output/benchmarks/omnidocbench-scholar-lens-smoke-v2/inference-summary.json`
- 页级 Markdown：`output/benchmarks/omnidocbench-scholar-lens-smoke-v2/predictions/`
- 每页完整解析产物：`output/benchmarks/omnidocbench-scholar-lens-smoke-v2/artifacts/`
- 官方评测结果：`output/benchmarks/omnidocbench-scholar-lens-smoke-v2/official-results/`
- 官方评测配置：`output/benchmarks/omnidocbench-scholar-lens-smoke-v2/omnidocbench-eval.yaml`

## 后续优先级

1. 修复公式块到 Markdown 的输出链路，先将“空预测率”从 100% 降到 0%。
2. 用页内几何位置与栏结构重建阅读顺序，重点覆盖表格前后正文和单栏复杂页。
3. 改进表格单元格 OCR 与跨块合并，目标是 TEDS ≥ 0.75、structure-only ≥ 0.85。
4. 在固定 100 页子集上复跑，形成可用于版本比较的正式解析基线。
5. 后端服务恢复后，再分别用 QASPER、SciFact 与 SPIQA 评测问答、证据定位和多模态问答；这些结果不能由当前解析指标代替。
