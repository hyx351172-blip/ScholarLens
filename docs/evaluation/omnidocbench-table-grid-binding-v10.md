# 表格物理框 → 逻辑网格绑定 v10

## 结论

空单元格造成的顺序错列已在 EEPROM 冻结样本上修复。保留 v8 的逻辑结构和 v9
的检测/OCR 输出，只改变几何映射：完整 TEDS 从 v9 原始候选的 **0.630081**
提升至 **0.997186**，也高于 Docling 基线 **0.959662**。

这是独立离线原型，**未接入正式 PDF 解析、未重新入库、未提交或推送**。
一张科研表的多层表头仍有结构问题，不能因此宣布所有表格已解决。

## 固定条件及方法

- 同一批 3 个开发样本：2 张 datasheet、1 张科研论文表格；不是独立 held-out。
- 同一裁图、v8 空 HTML 结构、v9 原始物理检测框及 OCR 文本/坐标；没有重跑模型。
- 运行阶段不读取 Gold；Gold 仅在独立评分脚本中使用，不参与候选选择。
- 使用重复物理边缘推断非等宽行列轴，按 10%/15%/20% 容差检查稳定性。
  内部边缘至少需要 `max(2, ceil(2% × 唯一检测框数))` 次支持，外侧边缘至少 2 次。
- 要求轴的边界数与冻结逻辑结构一致；不会补齐缺失边界或强行压缩表头。
- 按 row/column/rowspan/colspan 构造逻辑矩形，再按 OCR 框覆盖率分配文字。
  最佳覆盖率至少 0.7，且比次佳格高至少 0.4；有歧义则拒绝。
- 保留空单元格、原始 OCR ID 和文本。数字/字母不自动纠错，HTML 正确转义。
- Gate 不再要求“检测框数 = 逻辑格数”；检查的是几何证据、拓扑维度及 OCR
  唯一归属。通过只代表可以人工审查，不证明 OCR 正确，更不自动上线。

实现见 `scripts/table_grid_binding.py`、`scripts/experiment_table_grid_binding.py`、
`scripts/score_table_grid_binding.py`。

## 同一组完整 TEDS 对比

| 样本 | Docling 基线 | v9 原始候选（均被拒绝） | v10 候选 | v10 决策 |
|---|---:|---:|---:|---|
| `035cb436…` 复杂电子元件表 | 0.211165 | 无有效结构 | 无 | v8 结构无效，保留基线 |
| `0cbdcfa9…` EEPROM 表 | 0.959662 | 0.630081 | **0.997186** | 几何门通过，待审候选 |
| `14a6b411…` 科研规划基准表 | 0.896314 | 0.939872 | 无 | 行边界不足，保留基线 |

三张表都计入分母。按无 Gold 的几何门执行离线回退后，平均 TEDS 为
**0.701555**，原基线为 **0.689047**。这不是已部署系统的新分数；科研表不采用
v9 更高分的候选，因为该候选并未通过完整性检查。

## EEPROM：修复了什么

- 原始检测 298 个框，但逻辑表有 41 行 × 12 列 = 492 格。
- 检测边缘形成 42 条水平边界、13 条垂直边界；无需每个空格都有检测框。
- 280 段 OCR 全部唯一分配，无遗漏或重复；212 格保持空白。
- 例：0-based `(row=1,col=2)` 恢复为空，`col=3` 为 `40`，`col=4` 为 `41`，
  `col=5` 为 `A`。v9 曾把这些值依次向左挤入空格。
- 结构 TEDS = **1.0**，与冻结 v8 一致；逐格完整文本 **490/492**，
  非空格文本 **278/280（99.29%）**。
- 数字正则覆盖的单元格：v9 **65/254** → v10 **254/254**；Docling 为 **249/254**。
  **此指标不覆盖所有十六进制字符串**，不能解释为所有数字都正确。
- 原始 HTML 逐格诊断与官方归一化后诊断结果一致。本轮明确记录的剩余错误：
  `(13,1)` Gold `0D` / OCR `OD`；`(25,2)` Gold `O` / OCR `0`。
- Gold 未提供 `th/thead` 语义，单位正则也没有覆盖单元格：表头语义准确率、
  单位准确率是 **N/A**，不是 100%。

## 仍未解决的科研表

该表的重复物理边缘只支持 40 个行区间（41 条边界），而 v8 冻结结构需要
41 行（42 条边界）；在三个聚类容差下这个冲突都存在。因此 v10 在生成 HTML
之前拒绝绑定，475 段 OCR 未进入候选，而不是悄悄丢弃或塞到正文行里。

单独评分可见 Gold 为 42 行，v8 为 41 行。该差异说明上游逻辑结构也存在
表头缺行/跨度问题，不能只增加一个 OCR 匹配规则解决。几何门只知道“结构与
物理证据矛盾”，不会使用 Gold 告诉它应该补几行。

后续应针对**多层表头的局部行边界及 rowspan/colspan 重建**做独立实验，保留
本轮映射和回退策略作为对照；字符纠错另行验证，不能靠猜测替换 `O/0`。

## 测试及审查

按 `ai-product-dev-pack` 的单特性流程执行：先建立 AC 和失败测试，后实现、
回放真实冻结产物、独立评分，最后做回归及可追溯检查。

- 新增 **19** 个单元/契约测试（14 个几何/绑定 + 5 个运行产物保护）。
  RED：新模块不存在时导入失败；GREEN：实现后全通过。
- 全套 **289 个测试通过，0 失败、0 错误、0 跳过，22.967 秒**。
- Paddle 隔离环境中再次运行 14 个纯逻辑测试，全部通过。
- AC-1301～1305 双向可追溯检查通过；`git diff --check` 无空白错误。
- 真实接缝：冻结检测/OCR → 逻辑格 → HTML → 官方评测器；没有 mock 几何数据。
- 27 个受保护输入/代码文件在运行和评分后 SHA-256 保持一致；其中包括冻结的
  15 个裁图、基线、源图及解析产物。额外校验输出 HTML/trace 哈希，评分前后复查。
- 模型调用 0，付费 API 调用 0；EEPROM 映射约 0.486 秒，科研表拒绝约 0.035 秒。
  这些仅为回放映射耗时，不是端到端 PDF 解析性能。

审查范围：空值/非法几何、歧义回退、HTML 注入、输入大小限制、重复框投票、
源/输出路径重叠、输出篡改、源码/输入完整性、Gold 隔离。没有涉及数据库迁移、
网络重试、权限接口或 UI；没有新增完整应用用户旅程。本次没有发现剩余阻断性
代码缺陷；已知复杂表头限制明确回退。可追溯检查是已执行的本地检查，非 CI 保证。

## 产物与复现

- 回放：`output/benchmarks/omnidocbench-table-grid-binding-v10/`
  - `summary.json` / `input-integrity.json`
  - 每个样本 `result.json`；可映射样本有 `grid-trace.json`，含逻辑格、轴证据、
    OCR ID、坐标、文本及覆盖率；仅生成成功的候选有 `raw-candidate.html`。
- 最终评分：`output/benchmarks/omnidocbench-table-grid-binding-v10-scored-v2/`
  - `results.json` / `index.html` / 每张表的 `comparison.html`
  - 完整归一化 HTML、原始字符及归一化后的逐格错误清单。
- 回归：`output/benchmarks/omnidocbench-table-grid-binding-v10-validation/`
  中的 `regression.json`、`regression.log`。
- 本报告机器可读摘要：`docs/evaluation/omnidocbench-table-grid-binding-v10-results.json`。
- 初次评分 `…-v10-scored/` 保留，不覆盖；最终 v2 增加原始字符诊断，主分数不变。

在项目根目录中运行（两处 output 均必须是尚不存在的新目录）：

```powershell
python scripts/experiment_table_grid_binding.py `
  --prepared output/benchmarks/omnidocbench-table-vlm-v5/prepared `
  --v8 output/benchmarks/omnidocbench-table-decoder-v8-run3 `
  --v9 output/benchmarks/omnidocbench-table-ocr-binding-v9 `
  --output output/benchmarks/table-grid-replay-new

backend/data/benchmarks/omnidocbench/.eval-venv/Scripts/python.exe scripts/score_table_grid_binding.py `
  --prepared output/benchmarks/omnidocbench-table-vlm-v5/prepared `
  --run-dir output/benchmarks/table-grid-replay-new `
  --v9-scored output/benchmarks/omnidocbench-table-ocr-binding-v9-scored-v2/results.json `
  --gold output/benchmarks/omnidocbench-scholar-lens-smoke-v2/selected_annotations.json `
  --evaluator backend/data/benchmarks/omnidocbench/evaluator `
  --output output/benchmarks/table-grid-score-new
```

目前需要本机已保存的忽略 Git 的冻结数据及评测环境；仅 clone 源码并不能直接
复现实验。算法阈值基于已诊断的开发样本设计，虽未使用 Gold 调参，也仍须在
更多独立表格上验证。没有下游检索/回答评测，不宣称 RAG 效果因此提升。
