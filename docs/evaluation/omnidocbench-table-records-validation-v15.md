# 合并行重建的新页面验收 v15

日期：2026-09-25。目标：验证冻结的 v14 规则在未使用过的页面上是否误拆，
并检查是否出现可用于验证修复能力的真实正例。不是正式解析链路上线验收。

## 固定实验协议

- 本地 100 页数据中，排除之前选取的 30 页，剩余 18 个含表格页面。
  沿用冻结的哈希排序和分组轮选，事先选定 12 页，不按结果替换样本。
- 12 张新图与此前 30 张图的 SHA256 无重合。只保证页面及完全相同图片不重合，
  不保证来源论文独立，也不知道是否出现在模型预训练数据中。
- 11 页来自 `table_hard`，1 页来自 `v1.5`。包含科研表格和器件规格表，
  不是按真实用户论文分布抽样，不能外推整体上线准确率。
- 使用标注框裁图（oracle crop），不考察整页表格发现能力。
- 同一个冻结的 Paddle 候选经 v10 网格绑定、v11 表头后处理、v13 安全检查后，
  比较不加/加 v14 的有效 HTML；两组共用同一个 Docling 回退输出。
- 本轮不运行方向修正，因此不是此前完整 v13 方向调度流水线的复测。
- 本地 CPU 模型，单样本单模型最多 240 秒；失败不移出分母。无付费 API。
- 推理及重建不读 Gold HTML；所有输出冻结后才运行官方 TEDS。

冻结的 v14 规则 SHA256：
`1069831bd46ec49a4bb621841a920639dd2717d6cd1f13d269e83921b03ab385`。

## 环境问题与处理

首轮 Docling 基线在保存原始解析后，因环境安装的是 `docling-slim`、旧脚本查询
`docling` 发行包版本而失败。停止了该基线任务，完整保留 `baseline/`。
新增独立测试适配器，只在缺少 `docling` 元数据时查询 `docling-slim`，
不修改模型、PDF 参数、表格规则；结果重新生成在 `baseline-fixed/`。
不是把旧失败状态手工改为成功，也未覆盖之前 v10～v14 的代码/产物。

## 视觉风险核查

对 12 张源裁图进行了助手视觉检查。以下是场景标签，不是用户确认的人工 Gold：

| 样本 | 需要防止的错误 |
|---|---|
| 01 | 染色体清单在同一病例单元格内换行，不应增加病例 |
| 02 | 行标题及 Mean/SD 说明换行、多级表头 |
| 03、06 | 回归系数与标准误/统计量分行，不应增加变量 |
| 04 | 稀疏网格和大量真正的空单元格 |
| 05 | 同一个彩色参数行内并列两组数值，子记录语义需人审 |
| 07 | 多列长段落、连字符、化学公式，不应按文字基线拆行 |
| 08 | 旋转的二值矩阵，本轮不纠正方向 |
| 09 | 上下标及公式的二维排版 |
| 10 | 一个研究内多个分组/项目符号，不应变成多个研究 |
| 11 | 多面板、多级表头、方法小节行 |
| 12 | 分组名称跨 Mean/Min/Max/SD 记录、单位表头 |

标签保存在 `tests/fixtures/table_record_validation_v15/visual_review.json`，
`human_reviewed=false`。没有把助手观察冒充人工标注。

## 结果

12 个新样本均已完成本地推理及冻结后的后处理对照：

| 阶段 | 结果 |
|---|---:|
| Paddle 候选生成完成 | 12/12 |
| Docling 回退表格可用 | 11/12 |
| 上游网格/HTML 检查拒绝候选 | 12/12 |
| 满足 v14 唯一入口条件 | **0/12** |
| 实际重建 | **0** |
| 有效 HTML 字节变化 | **0** |
| 最终没有表格输出 | **1**（case-08） |

两组最终都回退到相同 Docling 结果；case-08 两组均无结果。逐例文件存在性及
SHA256 一致性已核对。**这里的零变化不是“误拆率为零”**：有效修复正例为零，
进入重建判断的困难反例也为零，不能计算有意义的条件误拆率或宣称泛化成功。

### 上游问题定位

- 11 张在 v10 阶段出现 `y_axis_count_mismatch`，即结构网格行数与物理边界
  推断行数不一致。其中 5 张同时有列数不一致，部分还有轴稳定性问题。
- v11 补救最后报告：10 张 `unsupported_header_prefix`，1 张
  `unstable_or_inconsistent_axes`。前者说明限定的表头修复模式不适用，
  **不是已证明表头文字识别错误**；其前置原因仍需看 `prior_gate`。
- case-10 的结构 HTML 出现 `Unbalanced HTML tags`，尚未进入几何绑定。
- case-08 为旋转矩阵，Docling 没有输出表格；本轮按约定没有做方向修正。

官方 TEDS 已完成，全部 12 例均保留在分母（无输出记 0）：

| 指标 | 不加 v14 | 加 v14 |
|---|---:|---:|
| 完整 TEDS 均值 | 0.681440 | 0.681440 |
| 结构 TEDS 均值 | 0.846821 | 0.846821 |
| 改善 / 退步 | — | 0 / 0 |

这些均值来自新的一组表，不能与 v14 原开发集的 0.619781 直接比较并宣称提升。
逐例分数见 [结果 JSON](omnidocbench-table-records-validation-v15-results.json)。
模型、规则和冻结输入校验通过；版本兼容适配层在运行前后的哈希一致。

### 验收结论

**重建能力的独立正反例验收尚未通过覆盖门，不接入生产。**
本轮验证了在这些上游失败输入上能保持原回退，不损坏已有有效输出；
没有验证新真实正例的恢复能力，也没有证明正常换行进入重建后不会误拆。

下一步应先做“网格冲突分型及坐标叠加诊断”：比较结构行列数、检测框聚类、
OCR 行带与源图，区分检测漏行/多检、结构解码错行和真实跨行。
同时单独定位 case-10 的 HTML 标签异常；不要直接放宽门槛或全部交给重建器。
需要补充能够进入重建判断的真实正例与正常换行反例，并由人确认记录边界。
若使用本批次修规则，它就成为开发集，下一轮验收必须另留未参与调整的数据。

## 验证及复现

按 `ai-product-dev-pack` 补齐协议验收标准及测试，按 `pdf` 技能检查源裁图。
29 项相关单元/协议测试通过（其中新协议 5 项）；4 条 AC 的可追溯检查通过。
本轮没有打通新 RAG 用户流程，未运行线上 E2E、未新增 CI 闸。

本轮首次运行所用流程如下（`new-v15` 是新输出目录示例）：

```powershell
python tests/experiments/validate_table_records.py prepare --root output/benchmarks/new-v15 --count 12
python tests/experiments/validate_table_records.py paddle --root output/benchmarks/new-v15
python tests/experiments/record_validation_compat.py baseline --root output/benchmarks/new-v15
python tests/experiments/record_validation_compat.py finish --root output/benchmarks/new-v15
backend/data/benchmarks/omnidocbench/.eval-venv/Scripts/python.exe tests/experiments/validate_table_records.py score --root output/benchmarks/new-v15
```

需要已缓存模型和原环境。`prepare` 会排除执行时已有实验页面；本轮之后仅剩
6 个未选含表格页面，因此再次要求 12 个新样本会被拒绝。严格复核本次应使用
已经冻结的 manifest、裁图及 hashes，在新目录运行推理与评分，不应再次抽样。
冻结 hashes 含本机绝对路径，异机重放需要显式重定位和重新登记输入校验，
不能悄悄删除校验。目录已存在时拒绝覆盖。

产物根目录：`output/benchmarks/omnidocbench-table-records-validation-v15/`。
其中 `prepared/` 为裁图及固定清单，`paddle/` 与 `baseline-fixed/` 为原始解析，
`validation/<case>/` 为两组有效 HTML 和诊断 trace，`scored/<case>.html`
为 Gold/两组输出的对照页，`scored/results.json` 为完整逐例评分。
不修改正式解析器、数据库或前端；未提交、未推送。
