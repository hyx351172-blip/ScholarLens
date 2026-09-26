# ScholarLens 表格保真与评测器修复（v4）

日期：2026-09-25。范围：评分器零索引修复、表格结构保真转换、固定样本回归。

## 结论

两类问题已分别处理：第一类是评分器把第一个预测表格的位置丢掉；第二类是 Docling 已识别的合并单元格没有进入 ScholarLens 标准 block 和导出。

本轮保留并重放原始 Docling 产物，没有重新识别，也没有调用 VLM/API。修复解决了数据保真与评分正确性问题，**不能据此声称 OCR、复杂表格识别或问答能力已经大幅提升**。

## 一、评分器修正：不是模型提升

固定使用的上游 evaluator commit 为 `f133a71e9e91c3621c7ce8994200a7b394a06eb3`。`src/core/matching/match.py` 的 `match_gt2pred_simple` 用 `if pred_idx` 判断是否有匹配。当 `pred_idx=0` 时，预测内容仍存在，但 `pred_position` 和 `pred_category_type` 被写成空字符串。

本轮只将这两处改成 `if pred_idx != ""`，没有修改 Gold、匹配分配算法、TEDS 或编辑距离公式。可复现补丁保存在 `scripts/patches/omnidocbench-zero-pred-index.patch`。新增测试先复现失败，再验证索引 0、字符位置 0、非零索引和未匹配项。

相同预测文件重新评分后：

| 预测版本 | 原始上游评分器 Reading Order ↓ | 本地修正评分器 Reading Order ↓ |
|---|---:|---:|
| 初始 baseline | 0.4842 | 0.2770 |
| 仅 canonical 导出 | 0.3749 | 0.1678 |
| 公式修复版 v3 | 0.2390 | 0.0319 |

原先 `page-035cb436...` 和 `page-0cbdcfa9...` 的 `gt=[3]/[1], pred=[]` 来自这个评分缺陷，**不代表这两页没有识别出表格**。本地修正后，三个表格页的阅读顺序距离均为 0。原始官方结果完整保留，v4 所有分数明确标为 `local-patched-zero-pred-index-v1`，不冒充未修改的官方榜单成绩。

## 二、结构保真转换：实际改了什么

- `ContentBlock.table_structure` 新增可选结构，旧 JSON 缺少该字段时默认 `None`。
- 保存源表格引用、行列数、单元格文本、起止行列索引、row/column span、表头属性及原始 bbox/坐标原点。单元格 bbox 不与标准 block 的 bottom-left bbox 混用。
- 校验维度、整数偏移、越界、跨度一致性、单元格重叠、有限坐标和网格大小；无效结构保留原 Markdown，写入质量警告，不自动裁剪、猜测合并或修正数值。
- 对有效结构生成转义后的 HTML，保留 `rowspan`/`colspan`。无源单元格覆盖的位置输出空单元格并记录数量，不补造内容；原 Markdown 的表外 caption/context 保留。
- 现有 `block.text`、逻辑表文本和 chunker 输入不变，避免未验证的检索回归。
- 现有前端 `ReactMarkdown` 未启用原始 HTML，因此服务 `markdown` 字段继续返回兼容视图；另外返回 `structured_markdown` 并保存为 `<论文名>.structured.md`。没有为了新导出而开放前端任意 HTML 渲染。

这一步将结构保留在解析和导出层，并没有让 chunker 自动采用合并单元格结构。结构感知切分策略若要改变，仍需独立设计和检索实验。

## 三、统一评分口径下的实验

四组均使用上述同一份补丁和相同配置，Edit distance 使用 `ALL_page_avg`，TEDS 使用 0–1 原始值。

| 指标 | 初始 baseline | 仅 canonical 导出 | 公式修复版 v3 | 表格保真 v4 |
|---|---:|---:|---:|---:|
| 文本 Edit distance ↓ | 0.2333 | 0.2057 | 0.2080 | 0.2080 |
| 公式 Edit distance ↓ | 1.0000 | 0.8667 | 0.2547 | 0.2547 |
| 阅读顺序 Edit distance ↓ | 0.2770 | 0.1678 | 0.0319 | 0.0319 |
| 表格 TEDS ↑ | 0.6856 | 0.6856 | 0.6856 | 0.6890 |
| 表格 structure-only TEDS ↑ | 0.7719 | 0.7719 | 0.7719 | 0.7693 |
| 表格 Edit distance ↓ | 0.6137 | 0.6137 | 0.6137 | 0.2068 |

表格 TEDS 仅小幅提升，结构分数略降，**没有宣称表格全面改善**。表格 Edit distance 的较大变化伴随 Markdown→HTML 表达变化，而单元格识别来源完全相同，不能解释为 OCR 错字减少。内容和结构应优先结合 TEDS 与人工页面核对解读。

三张表的 TEDS 分别为：

| 页面 | v3 | v4 | 观察 |
|---|---:|---:|---|
| `page-035cb436...` | 0.2088 | 0.2112 | 主要失败案例；保真导出无法修复原始识别错误 |
| `page-0cbdcfa9...` | 0.9597 | 0.9597 | 保持不变 |
| `page-14a6b411...` | 0.8885 | 0.8963 | 小幅改善 |

最差页面的 structure-only 从 0.3683 降到 0.3587，说明保留下来的原生跨度也可能不正确；本轮没有利用 Gold 决定是否撤销某个页面的结构导出。

## 四、验证范围与兼容性

- 同一份冻结的 10 页：4 equation_hard、3 table_hard、1 layout_hard、2 v1.5；7 单栏、3 双栏。
- Gold SHA-256：`f25369f9845039f7474591e9a0c275443c5a2149fc975270f35a80ada7da43a4`，未修改。
- 指标分母：正文 9 页、公式 4 页/30 个独立公式、表格 3 张、阅读顺序 10 页。
- 四组均运行固定 evaluator 的 `pdf_validation.py`；quick_match、page/TEDS workers=2、匹配超时 300/420 秒，其他配置沿用 v3。各组匹配超时、TEDS 超时和异常均为 0。
- 通过生产适配器重放原始 Docling JSON：10/10 成功，共保存 853 个已识别单元格、14 个跨行/跨列单元格。结构校验通过仅表示数据内部一致，不表示它与真实页面完全相符。
- 对照原始 canonical 产物，10/10 页的旧 block 字段和逻辑表对象完全一致，重建的 **49 个 chunks 完全一致**（含文本、ID 和来源信息）。
- `python -m unittest discover -s tests`：**185 项通过，0 失败、0 跳过**，最终运行 15.250 秒。
- 新回归覆盖评分器零索引、保真映射、JSON 往返、HTML 转义、非法网格回退、旧数据/figure 兼容、服务双导出、chunk 不变和实验输出目录保护。
- `git diff --check` 通过；补丁能在当前 evaluator 上通过 `git apply --reverse --check` 验证。
- 本轮没有模型调用、付费 API 调用、数据库写入、重新入库或在线浏览器全链路验证；没有修改前端依赖或启用原始 HTML。

## 五、产物与复现

- 精确数值和输入/补丁哈希：`docs/evaluation/omnidocbench-table-fidelity-v4-results.json`。
- 固定补丁：`scripts/patches/omnidocbench-zero-pred-index.patch`。
- 复放脚本：`scripts/replay_docling_table_export.py`，只读已有 native JSON 和 PDF，拒绝覆盖已有输出目录。
- 完整产物：`output/benchmarks/omnidocbench-table-fidelity-v4/structure_export/`。
- 每页的 `artifacts/<page>/` 中保存 `document.json`、`docling-document.json`、`content.md`、逻辑表/公式/图和 `chunks.json`。
- 四组评分：`output/benchmarks/omnidocbench-table-fidelity-v4/scores/{baseline,export_only,formula_fixed,table_structure}/result/`；对应 `eval.yaml` 保留了输入路径和参数。
- 旧 v2/v3 预测、原始官方评分和模型产物未覆盖。大文件继续 Git 忽略，本报告、精简 JSON、补丁和脚本可随项目保存。

在项目根目录、相同依赖环境下，使用新的输出目录复现结构重放：

```powershell
python scripts/replay_docling_table_export.py --source-dir output/benchmarks/omnidocbench-scholar-lens-fixed-v3 --output-dir output/benchmarks/omnidocbench-table-fidelity-reproduce
python -m unittest discover -s tests
```

在干净的固定 evaluator checkout 上应用补丁前，先用 `git apply --check` 校验；已应用的 checkout 可用 `git apply --reverse --check` 验证，勿重复应用。评分复制相应 `eval.yaml` 至新目录，只改预测路径，继续使用原冻结 Gold；官方评分入口会向当前目录的 `result/` 写结果。

## 六、下一步

优先针对 `page-035cb436...` 检查原页面与原生单元格：问题已经不只是序列化，而是实际的行列/合并关系或文本识别。之后可做局部表格重识别对照，保留原识别与候选修复，并在未用于开发的新表格页验证，不能只优化这三张表。

当前服务新增的结构化导出需重启服务后对新解析生效。既有知识库不会自动更新；本轮不要求为了导出保真立即重建向量，因为验证范围内的 chunk 内容没有变化。
