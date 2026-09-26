# 多层表头与 rowspan / colspan 修复 v11

## 结论与范围

科研规划基准表的缺失表头层已恢复：**2 层 → 3 层，整表 41 行 → 42 行**。
20 个表头单元格的坐标及跨度全部匹配 Gold；整表结构 TEDS **1.0**，完整 TEDS
**0.990868**（Docling 基线 0.896314，v9 原始候选 0.939872）。

此实现延续 v10 的**独立离线修复链**。未修改生产 PDF 解析、chunker、数据库或
前端，未提交或推送；没有调用模型或付费 API。不代表任意复杂表头都已解决。

## 修复机制

1. 保留 v10 的校验、非等宽行列轴及已通过的候选。EEPROM 输出逐字节不变。
2. 只处理受支持的失配：物理检测把整个表头压成一行，但已有逻辑结构提供
   顶层列组，表体行数与几何证据仍一致，且有跨行独立表头的检测框支持。
3. 在原始裁图中提取竖直分隔线，检查它们在表头内的起始高度。至少两个独立
   父表头组需共同支持每个新增层次，并由这些组中的 OCR 纵向位置交叉确认。
   独立跨行表头的文字换行不参与层数判定。
4. 在父组内按局部分隔线恢复子表头 `colspan`；独立表头延长至完整表头高度。
   没有文字的子区域保留原子空列，不因缺字挤压后面的单元格。
5. 正文只统一增加行偏移。重新严格验证完整网格，再按矩形覆盖率唯一绑定
   OCR；文本不拆词、不纠错。矛盾或歧义保留基线，不借助 Gold 决定修复。

实测表头分界 y = 14.471、39、61、84.056（裁图像素坐标）。这些边界来自
图像与 OCR，不来自 Gold 或写死的目标行数。

新增实现：`scripts/table_header_reconstruction.py`。其输出包括：

- `header_rows_before` / `header_rows_after`、`header_y`、`ruling_evidence`。
- 修复前后的表头跨度签名、`body_topology_preserved`。
- 每格 `is_header`、OCR 来源、几何位置，以及 `origin` 中的原结构单元格 ID、
  原坐标和变更类型（跨行延长、父组保留、子表头推断或正文行偏移）。
- `header_tree` 的 `parent_id` 及各列 `header_paths`。例如第 5 列的路径是
  `RBS → +ACI → +PE`。第 10 列为独立的 `RBS +LPG`，跨 3 个表头行。

HTML 继续采用已有兼容的 `td` 结构；表头角色存于结构化 trace 的 `is_header`
和层级字段，并未擅自改变既有下游契约。

## 同组评测

| 样本 | Docling 完整 TEDS | v10 离线回退结果 | v11 离线回退结果 | 决策 |
|---|---:|---:|---:|---|
| `035cb436…` 复杂电子元件表 | 0.211165 | 0.211165 | 0.211165 | v8 HTML 仍无效，保留基线 |
| `0cbdcfa9…` EEPROM | 0.959662 | 0.997186 | 0.997186 | v10 成功结果逐字节不变 |
| `14a6b411…` 科研规划表 | 0.896314 | 0.896314 | **0.990868** | 新表头候选通过几何门 |
| 3 张平均 | 0.689047 | 0.701555 | **0.733073** | 3 张都计入分母 |

没有根据 Gold 分数择优替换。候选选择由运行时无 Gold 的几何/拓扑门决定；
正式系统尚未采用上述候选。两张 datasheet 加一张论文表是开发集，不是 held-out。

### 科研表：结构、文字分别看

- 42 行 × 12 列，488 个逻辑单元格；475 段 OCR 全部唯一分配，无遗漏。
- 20/20 个表头单元格的 `(row, col, rowspan, colspan)` 完全一致，缺失/额外跨度均为 0。
- 4 个原本跨 2 行的独立格恢复为跨 3 行；两个 `+ACI` 子表头恢复 `colspan=2`。
- 完整结构 TEDS 由基线 **0.973585 → 1.0**。
- 表头文字 17/20 完全匹配；3 处仍为 OCR/换行转录问题：
  `Mercury` / `Mer- cury`，`+RE` / `|:RE`，`+RE` / `|+RE`。
- 整表逐格文本 **456/488**；非空 Gold 格 **441/472（93.43%）**。
  原始字符诊断与官方归一化后的逐格诊断一致，没有改评分规则消除差异。
- 数字正则覆盖的 Gold 格 **461/461** 正确，但此数字不是“全表内容 100% 正确”。
  它不惩罚 Gold 空格中多出的数字，也不校验所有科学表达式。

32 处严格文本差异的构成：

| 类型 | 数量 | 示例/说明 |
|---|---:|---|
| 标签内部空格 | 27 | `Barman(40)` 与 `Barman (40)`；仍计为不一致 |
| 表头 OCR / 断词 | 3 | 上述 `Mercury` 和两处 `+RE` |
| 数学符号表示 | 1 | Gold 为 LaTeX `\sum`，OCR 为 Unicode `∑` |
| Gold 空白但 OCR 非空 | 1 | 0-based `(4,4)`：Gold 空字符串，候选 `3` |

最后一格的原始裁图可见 `3`，因此可能涉及标注遗漏；本轮**没有更改 Gold，也没有
从分母删除该格**。应另行人工复核后做有版本的标注修订，不能用本次推测调高分数。

表头专用诊断依据跨度及规则正文的起始位置推断表头前缀，不是新增的人工表头
语义标注。Gold 没有 `th/thead` 语义标签，不能据此宣称通用表头分类准确率。

## 测试、审查及完整性

依照 `ai-product-dev-pack`，先建立 AC 与失败测试，再实现和运行真实接缝；
审查时发现的“竖线穿过父表头却仍放行”问题，已补红测试并修复。

- 新增 **17** 个测试：10 个重建/失败场景、4 个运行契约、3 个表头诊断测试。
- 全量 **306 个通过，0 失败、0 错误、0 跳过，24.894 秒**。
- Paddle 隔离环境中的 10 个重建测试同样通过。
- AC-1401～1405 可追溯检查通过；`git diff --check` 无空白错误。
- 真实接缝是冻结裁图像素 + 检测/OCR → 新拓扑 → HTML → 官方评分器。
  没有新建完整应用用户旅程，也没有用 mock 图代替实际评测样本。
- 37 个受保护输入/代码文件哈希不变；同时验证了 v10 已记录产物的哈希。
- 本次科研表回放约 1.378 秒，包含本地线段处理及几何映射，不含 PDF 解析或模型推理。
- 沿用已有 NumPy/OpenCV，未改依赖；模型调用 0、付费 API 调用 0。

审查涵盖非法图像/像素预算、源数据不变、原成功结果不变、OCR 冲突、缺线/单侧证据、
父组边界冲突、严格网格、HTML 转义、来源记录及 Gold 隔离。没有数据库迁移、
权限接口、网络依赖或 UI 改动。局部可追溯检查已执行，不等于已部署 CI 门。

| 编号 | 类别 | 文件:行 | 描述 | 优先级/状态 |
|---|---|---|---|---|
| 1 | 防御性 | `scripts/table_header_reconstruction.py:146` | 父组内贯穿竖线与 colspan 冲突时必须拒绝；已由 `tests/test_table_header_reconstruction.py:76` 固化回归 | P1，已修复 |

其余审查项未发现剩余阻断性代码缺陷；方法适用范围限制保留在下节，不等同于通用正确性保证。

## 当前限制与下一步

- 需要已有可靠顶层组、可见竖向分隔线、至少两个独立组，以及规则正文。
  无框线表、任意层数/不对称复杂拓扑、无效 v8 HTML 仍可能被拒绝。
- 当前 `rowspan` 修复针对有物理框支持的独立表头；不能推断所有可能的内部跨行关系。
- OCR 字符错误、断词、公式表示和 Gold 标注分歧未混入本次结构修复。
- 下一步优先扩展独立多层表头样本做泛化验证，再决定是否接入正式解析。
  需要 OCR 规范化时单独做实验，保留原文字和编辑轨迹，不能无证据替换 `O/0`。

## 产物与复现

- 运行：`output/benchmarks/omnidocbench-table-header-v11/`
- 科研表子目录 `page-14a6b411-9097-4eec-86da-92075868d243/`：
  `repaired-structure.html`、`raw-candidate.html`、`grid-trace.json`、`result.json`。
- 评分：`output/benchmarks/omnidocbench-table-header-v11-scored/`：
  `results.json`、`index.html`、逐样本 `comparison.html` 和完整逐格错误清单。
- 回归日志：`output/benchmarks/omnidocbench-table-header-v11-validation/`。
- 机器可读摘要：`docs/evaluation/omnidocbench-table-header-v11-results.json`。

在项目根目录运行；输出目录必须是新的，原始冻结数据和评测环境需已存在：

```powershell
python scripts/experiment_table_header_reconstruction.py `
  --prepared output/benchmarks/omnidocbench-table-vlm-v5/prepared `
  --v8 output/benchmarks/omnidocbench-table-decoder-v8-run3 `
  --v9 output/benchmarks/omnidocbench-table-ocr-binding-v9 `
  --v10 output/benchmarks/omnidocbench-table-grid-binding-v10 `
  --output output/benchmarks/table-header-replay-new

backend/data/benchmarks/omnidocbench/.eval-venv/Scripts/python.exe scripts/score_table_header_reconstruction.py `
  --prepared output/benchmarks/omnidocbench-table-vlm-v5/prepared `
  --run-dir output/benchmarks/table-header-replay-new `
  --v9-scored output/benchmarks/omnidocbench-table-ocr-binding-v9-scored-v2/results.json `
  --gold output/benchmarks/omnidocbench-scholar-lens-smoke-v2/selected_annotations.json `
  --evaluator backend/data/benchmarks/omnidocbench/evaluator `
  --output output/benchmarks/table-header-score-new
```
