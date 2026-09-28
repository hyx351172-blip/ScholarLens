# ScholarLens 评测与实验索引

*索引更新：2026-09-28。各历史报告保留原始日期与结论；后续检查独立记录。*

---

## 📋 先看哪些结果

| 阅读目的 | 报告 | 解释边界 |
| --- | --- | --- |
| 查看本次开发版本合并检查 | [提交前验收（2026-09-28）](publication-20260928.md) | 当前回归 745、前端 20 项及构建通过；补充规范路由后完整追踪 254/254；不等于生产上线验收 |
| 查看 BM25 + Dense 混合检索 | [实现与离线 A/B（2026-09-28）](hybrid-search-ab-20260928.md) | 19 篇/2,057 chunks；已使用 v2 完整证据命中 75%→90%，MRR/NDCG 略降；历史 Top-10 回放，非在线回答质量，默认仍为 Dense |
| 查看定向复测后的修复和版本化测试 | [后续修复与回归（2026-09-27）](browser-fix-followup-20260927.md) | 版本化回归 853/853；用户另行授权后的单题真实复测核心结论有据，不代表整体准确率或完整发布验收 |
| 查看修复后的两题真实复测 | [定向浏览器复测（2026-09-27）](browser-fix-retest-20260927.md) | 跨论文覆盖与 BERT 单论文核心检查 2/2；严格源文核对 1 通过、1 有扩展句保留项；非整体准确率，未覆盖原失败记录 |
| 查看浏览器失败的后续修复 | [修复与回归（2026-09-27）](browser-acceptance-fixes-20260927.md) | 相关后端 104、前端 18 项通过；全量 852 项有 59 项历史指纹错误；真实问答后续见定向复测 |
| 查看当前版本真实浏览器验收 | [浏览器端到端验收（2026-09-27）](browser-final-e2e-20260927.md) | 2 篇 / 31 页 / 108 chunks；8 次网页问答核心检查 7/8，跨论文引用失败；另有公式、窄屏与 PDF 预览未通过/待核验，不是全项通过 |
| 了解真实上传到引用的主链路 | [多论文端到端验收](multipaper-e2e-20260926.md) | 3 篇、57 页、205 chunks；原始严格契约 13/16，保留失败 |
| 了解单论文范围修复 | [文档范围回归](document-scope-fix-20260926.md) | 同批 16 题机械契约 16/16；没有重新上传或完整浏览器验收 |
| 查看浏览器证据 | [前端初验](frontend-acceptance-20260926.md)、[后续多论文验收](multipaper-e2e-20260926.md) | 按时间阅读；引用计数等后续修复不能倒写为早期已通过 |
| 理解回答格式取舍 | [新旧模式 A/B](answer-mode-ab-v1.md)、[输出校验回放](claim-output-v2-replay.md) | `claim_bound` 非默认；缓存结构修复不等于语义提升 |
| 查看最近回归及核验边界 | [v3 定向真实验证](qualified-ids-pilot-v3.md) | 844 项代码测试通过；模型实验 7 次调用后停止，不是 10 题全部完成 |

三论文验收与范围回归使用开发案例、指定模型和参数。部分答案内容核对由 AI 完成，不能标作用户确认的人工 Gold。报告中的 `16/16`、来源精确关联或测试通过数，不是系统整体语义准确率。

## 🔍 解析、切分与检索

| 主题 | 报告入口 |
| --- | --- |
| 原始基线 / Docling 接入 | [baseline v1](baseline-v1.md)、[Docling v1](docling-parsing-v1.md) |
| 表格、章节、阅读顺序 | [逻辑表](table-postprocessor-v1.md)、[Caption 所有权](caption-owned-logical-tables-v1.md)、[章节层级](section-hierarchy-v1.md)、[阅读顺序](reading-order-v1.md) |
| 扩展论文解析 / VLM repair | [论文集解析](parser-dataset-2026-08-30.md)、[VLM A/B](vlm-page-repair-live-ab-v1.md)、[语义重分类](vlm-semantic-reclassification-v1.md) |
| 结构感知切分 | [v1](structure-aware-chunking-v1.md)、[v2](structure-aware-chunking-v2.md)、[切分后 Dense](dense-retrieval-chunker-v2.md) |
| 证据检索与重排 | [证据检索](evidence-retrieval-v1.md)、[Reranker A/B](reranker-ab-v1.md)、[Rank fusion](rank-fusion-v1.md)、[Held-out v2](rank-fusion-heldout-v2.md) |
| 多查询规划 | [覆盖开发集](multi-query-coverage-v3.md)、[Planner v4](query-planner-live-v4.md)、[v4 回放](query-planner-live-v4-replay.md)、[目标论文检索](target-grounded-retrieval-dev-v1.md) |
| 回答引用 | [引用 Held-out](answer-citations-heldout-v4.md)、[逐断言 Held-out v5](claim-citation-entailment-heldout-v5-results.md) |

每个报告分别说明开发/held-out、人工检查、配置和指标定义；不把有 Gold 的阶段级验证直接推广为真实用户任意问答能力。Query RRF 与重排实验不代表已经实现 BM25 混合检索。

## 📊 表格专项实验档案

这些原先散落在根 README 的实验已集中索引。报告、原始结论与代码均保留；下列专用候选流程没有替换默认解析器。

| 版本 | 关注点与结果摘要 | 报告 |
| --- | --- | --- |
| v5 | 局部 VLM 重识别，保留裁图、响应与失败记录 | [VLM](omnidocbench-table-vlm-v5.md) |
| v6 | HTML 双模型转录；复杂表未通过 | [HTML A/B](omnidocbench-table-html-v6.md) |
| v7 | PP-TableMagic 与原生 table parsing 候选均未通过 | [专用解析](omnidocbench-table-specialist-v7.md) |
| v8 | 解码上限诊断；结构有效不代表 OCR 正确 | [解码审计](omnidocbench-table-decoder-v8.md) |
| v9 | 单元格 OCR 绑定；仍有错位 | [OCR 绑定](omnidocbench-table-ocr-binding-v9.md) |
| v10 | 几何网格修复空格错列；复杂表头仍拒绝 | [几何绑定](omnidocbench-table-grid-binding-v10.md) |
| v11 | 多层表头与跨行跨列；仅指定样本改善 | [表头重建](omnidocbench-table-header-v11.md) |
| v12 | 新页面 20 张表扩测暴露泛化缺口 | [扩测](omnidocbench-table-unseen-v12.md) |
| v13 | 多记录合并拦截、方向探测；开发回归 | [保守修复](omnidocbench-table-safety-v13.md) |
| v14 | 有独立记录锚点的合并行重建；真实正例有限 | [记录重建](omnidocbench-table-records-v14.md) |
| v15 | 新页面未进入重建分支，不能证明其泛化 | [新页验收](omnidocbench-table-records-validation-v15.md) |
| v16 | 网格检测上限与 HTML 包装诊断；最终指标不变 | [几何审计](omnidocbench-table-geometry-audit-v16.md) |
| v17 | 单元格 OCR 重读未超过已有回退；暂停追加优化 | [OCR 重读](omnidocbench-table-cell-ocr-v17.md) |

局部 TEDS、结构 TEDS、OCR 内容准确性与最终回答正确性是不同指标。不要只摘取最佳单表分数作为整个解析器效果。

## ⚠️ 回答与核验实验边界

| 实验线 | 入口 | 当前解读 |
| --- | --- | --- |
| 数据与证据审计 | [已下载数据审计](downloaded-dataset-audit-20260926.md)、[QASPER 证据规划](qasper-evidence-plan-v1.md)、[QASPER 验证](qasper-guard-validation-v1.md) | 抽样或指定条件实验，不是完整官方榜单成绩 |
| 冻结回答 / 语义评审 | [多论文断言审计](multipaper-claim-audit-v1.md)、[隔离审计](isolated-claim-audit-v2-results.md)、[语义评审说明](semantic-review-v1/README.md) | 保留评审来源与人工未裁决项 |
| 逐结论证据输出 | [Claim-bound](claim-bound-answer-v1.md)、[完整句证据](evidence-units-live-v1.md) | 有可选 API 路径；不自动替代默认回答 |
| SciFact / 已选证据核验 | [SciFact live v1](scifact-verifier-live-v1.md)、[Selected-support live](selected-claim-support-live-v1.md) | 核验器收到已选证据，不代表上传到检索的完整 RAG 评测 |
| Qualified-support v2 / v2.1 | [v2 live](qualified-claim-support-live-v2.md)、[空白对齐回放](qualified-quote-alignment-v21.md)、[剩余批次](qualified-support-remaining-v21.md) | 分开统计真实调用、离线修复、停止及未运行项 |
| Qualified IDs v3 | [协议与离线准备](qualified-evidence-ids-v3.md)、[定向真实验证](qualified-ids-pilot-v3.md) | 6 条结构有效，1 条契约错误，3 条未运行；尚不能认定质量提升 |

当前暂停这些细节优化。保留失败和中止状态，不继续消费旧批次剩余调用额度；未运行项不补成成功。此前报告中的“下一步建议”属于当时的研究记录，不是现在自动续跑的授权。

## 🔧 文档整理检查（浏览器验收之前）

此前文档整理只调整 README、项目说明、启动指南和本索引，没有修改业务逻辑或历史评测结果，也未调用外部模型。后续真实浏览器验收及其已授权模型调用独立记录于上方新增报告，不能与本节静态检查混为一轮。

- 本地文档链接存在性、PowerShell 示例语法、Markdown 标题/代码围栏及差异空白检查通过；这些静态检查不等于实际执行安装或启动。
- `harness validate` 的 `validated-replay-v1` 配置校验通过（2 个 stage），没有运行 live 评测。
- 对 `docs/specs` 与专用 `tests/traceability` 检查：237 条声明、237 条引用，双向对齐。
- 扩展到整个 `tests`、仍只扫描 `docs/specs`：237 条声明、242 条引用；`test_docling_parser.py` / `test_table_postprocessor.py` 中的 `AC-101` 至 `AC-105` 被报告为未声明。实际定义位于 [早期 PDF 解析技术设计](../technical/PDF_PARSING_DESIGN.md)，不在该规格扫描范围内。这是追踪入口不统一，不是发现了 5 项产品功能失败。

因此，当时该全目录调用返回 no-go，不能倒写为通过；应统一追踪范围，并核对早期“仅解析阶段”的验收定义与当前阶段的关系，而不是删除引用或编造规格来凑通过。该文档整理阶段未重跑历史回归、演示或提交。

2026-09-28 补充：新增指向原始技术设计的早期编号路由索引，保留旧定义及 parse-helper/当前上传链路区别；重新执行两种完整追踪范围均为 254/254。详见 [本次合并检查](publication-20260928.md)，该新检查不覆盖或改写以上历史失败记录，也不关闭真实产品上线的待验项。

## 💾 复核与复现

- `docs/evaluation/`：可随 Git 保存的报告、部分结果和审阅记录。
- `output/`、`backend/output/`：本地 PDF、完整解析、请求/响应与冻结清单等产物，通常被 Git 忽略；公开仓库不保证包含它们。
- `harness/runs/`：本地 Harness 运行快照，被 Git 忽略。
- `tests/integration/`：含离线检查，也含真实服务或付费 API 执行器，不能整目录当成无费用测试运行。

阅读报告可以复核结论及口径；重新执行具体实验还可能需要报告中指定的数据、产物、服务和版本。缺失文件应明确标为缺失，不复制其他运行的答案或重写哈希来“恢复通过”。

使用 [Evaluation Harness](../../harness/README.md) 前先检查配置的 source 类型：`artifact` 回放使用冻结结果，不重新调用模型；live 配置需确认发送内容、调用上限与预算。当前手动检查不等同于已经有 CI/hook 强制发布门。

返回 [项目说明](../PROJECT_OVERVIEW.md) 或 [根 README](../../README.md)。
