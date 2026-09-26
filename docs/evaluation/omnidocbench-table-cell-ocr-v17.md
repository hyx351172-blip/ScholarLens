# 单元格区域 OCR 重读 v17：局部改善，但不替换现有回退

## 结论

本轮只验证 v16 定位的跨列 OCR 粘连。固定规则从 12 例中选出 case-10，
重读 9 个单元格；没有重跑整篇论文，没有修改正式解析器。

**结论：保留原回退，暂停继续优化表格解析，转向端到端问答验收。**
重读改善了被拒绝的旧 OCR 网格，但并未超过当前实际使用的 Docling 回退。
低置信度字符触发事先约定的拒绝规则，没有为了指标降低门槛。

## 实验方法

输入冻结自 v15/v16：5×9 逻辑网格、稳定物理边界、166 条 OCR，
其中 5 条跨列未分配。仅接受唯一失败原因为 OCR 归属歧义的稳定网格，
按交叠区域选格，不按病例 ID、关键词或 Gold 选择。

选中零基 cell_id：21、22、28、29、30、33、34、37、38。
完整单元格向内取整裁剪，原分辨率，添加 16px 白边；固定本地
PP-OCRv5 server det/rec（PaddleOCR 3.7.0，CPU），置信度下限 0.5。
不按空格或正则拆分粘连字符串。裁剪、新旧坐标、置信度、原始结果均保存。

重读结果若有效，则移除对应旧 OCR 并建立新旧来源映射，再运行原网格绑定及
行安全检查；缺失、空结果、低置信度、越界、重复框或已确认数字丢失均拒绝。
所有输入/模型与推理输出做哈希冻结；独立评分程序才读取 Gold。

## 实测结果

| case-10 比较对象 | TEDS | 结构 TEDS | 严格文本完全一致格 | 数字完全一致格 |
|---|---:|---:|---:|---:|
| 当前实际回退 | 0.9744 | 1.0000 | 26/45 | 15/22 |
| 原先被拒绝的部分 OCR 网格 | 0.9359 | 1.0000 | 22/45 | 11/22 |
| 单元格重读诊断候选（未放行） | 0.9665 | 1.0000 | 25/45 | 13/22 |

重读相对旧部分网格 TEDS +0.0307，但相对实际回退 -0.0078。
不可把前一个增幅描述成线上效果提升。

9 个重读区域产生 49 条识别行。cell-34 中一个“ 一 ”字符的置信度
仅 0.30286，低于 0.5，正式实验候选被拒绝，后续绑定/行闸未执行。
为了评价文本效果，另建**仅诊断 HTML**：将全部新行（包括这个低置信度
字符）按空间顺序填回选中格，保留其他格；没有筛选掉坏字符，也没有修改
冻结的拒绝决定。这份 HTML 不等于通过了安全闸的输出。

12 例所有 effective 文件与之前字节一致（原本无输出的 1 例仍无输出）：

- 平均 TEDS：0.681440 → 0.681440。
- 平均结构 TEDS：0.846821 → 0.846821。
- 放行 0，实际输出改变 0；未接入生产。

## 内容核验与局限

- `Retrospective` 与 `Total (65)` / `Total (82)` 的跨列粘连被区域重读拆开。
  选中格 21、28、37 从文本不完全一致变为完全一致。
- 部分文字仍缺少空格，例如 `decreasedrate ofpostoperativedeliriumcomparedto`；
  还出现低置信度符号。局部裁剪不等于 OCR 内容完全正确。
- 人工抽查 cell-29 图像与文本：65、24、25、16 被识别，文字仍存在
  Gold 中 `rameIteon` 与图片/预测 `ramelteon` 等字形差异。
- 严格文本指标也受 Gold 空格、断词、LaTeX 单位表示影响。
  数字指标是坐标对齐后正则抽取的诊断值，不代表医学/科学事实正确率。
- 本轮只针对一张已诊断开发表，不能宣称在未见论文上泛化。
  300 检测框上限、复杂表头和长段落过度分行均不在本轮范围内。

## 执行与验证

- 完整 OCR 运行 48.44 秒，9 次本地单元格调用，无付费 API 调用。
- 首次尝试完成第一个单元格推理后，保存包含 Font 对象的原始字典失败；
  改用库自带 JSON 表示，在新目录重跑。因此包括失败尝试共 10 次单元格推理。
- 首次文字诊断评分遇到 Matplotlib 默认缓存路径权限错误；设置项目内缓存后
  在新目录完成。失败目录均保留，无模型下载、无正式配置变更。
- 133 项回归测试通过，其中 8 项新增；包含真实冻结输入、替换来源、不重复、
  坏结果拒绝、可通过的合成正例、诊断保留低置信度文本及 12 例回退不变。
- 5 条 AC 双向可追溯检查通过；`git diff --check` 通过（既有 CRLF 警告不变）。
- ai-product-dev-pack 将本轮限定为后端离线实验及 OCR 接缝验证：实际本地推理
  已执行，但没有新增或验收 PDF→入库→检索→回答的完整用户旅程。
  测试路由仅提供覆盖建议；本轮没有增加 CI 强制门或前端跨浏览器验收。

## 产物

成功目录：`output/benchmarks/omnidocbench-table-cell-ocr-v17-replay/`。

- `plan.json`、`frozen-inputs.json`、`summary.json`：规则、哈希、运行信息。
- `case-10/cell-*-raw.json`、`cell-*-mapped.json`、`cell-*.png`：逐格原始结果与图像。
- `case-10/replacement.json`：拒绝决定；各例 `effective.html` 保留原回退。
- `scored/results.json`：整个 12 例重新使用官方 TEDS 评分。
- `text-diagnostics-replay/results.json`：逐格文字、Gold、三组对照指标。
- [文字对照页](../../output/benchmarks/omnidocbench-table-cell-ocr-v17-replay/text-diagnostics-replay/case-10-comparison.html)。
- [本轮指标摘要](omnidocbench-table-cell-ocr-v17-results.json)。

复现实验须选择新的目录，使用项目已有 Paddle 环境及缓存权重：

```powershell
python scripts/experiment_cell_ocr_reread.py --output output/benchmarks/new-cell-reread
python scripts/score_cell_ocr_reread.py --root output/benchmarks/new-cell-reread
python scripts/audit_cell_ocr_text.py --root output/benchmarks/new-cell-reread
```

评分使用已有 OmniDocBench evaluator 环境；默认输出目录不会覆盖已存在产物。

## 下一步

冻结当前解析策略。选择一组未用于当前调参的论文/问题，覆盖正文、表格数字、
方法比较及无答案问题，完成 PDF→Chunk→入库→检索→回答→引用页码的端到端测试。
按解析、切分、检索、生成归因失败，只有确认阻断核心用户任务的问题才再修改。
