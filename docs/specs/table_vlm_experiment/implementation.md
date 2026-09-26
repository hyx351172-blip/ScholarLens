# 离线局部表格 VLM 重识别实验 v1

状态：实现与实验完成；模型效果未通过，不接入生产。2026-09-25。

## 范围

对冻结的 3 张 OmniDocBench 表格页做配对实验：Docling 表格保真 v4 vs.
同一图像上局部 VLM 转录。包含最差表和两个正常对照。它们是开发样本，
不是 held-out，不能据此声称论文问答或全部 PDF 解析能力提升。

使用已有预测框裁图，只发图像与通用固定提示词。Gold 只由独立评分脚本读取，
不得进入裁图、请求、校验或候选接收规则。原产物、正式解析器、chunker 和知识库不变。

## 验收

- AC-VTABLE-801：依据 native Docling bbox/origin/page size 正确裁图、缩放、边界裁剪；
  拒绝非法坐标、跨页表及缺失来源。保存裁图和带原生 cell 框的诊断图。
- AC-VTABLE-802：紧凑 JSON 单元格映射为独立结构化候选；严格验证维度、跨度、
  重叠、覆盖、类型和规模；未知文本必须显式 null + uncertain，不补造数值。
  schema 合法不等于语义正确，所有候选均需复核。
- AC-VTABLE-803：最多 3 次 API 请求，SDK retries=0，每次 timeout=180 秒、
  max_tokens=16384、temperature=0。超时/截断/非法 JSON 保留诊断、回退 baseline，
  不重试。调用前持久化 attempted 状态，拒绝覆盖/自动续跑已有结果以免重复付费。
- AC-VTABLE-804：prepare 与 run 接口不接受 Gold；源文件哈希可核对，拒绝输出
  目录与输入重叠，拒绝篡改的裁图和路径穿越；不修改原文、chunk 或数据库。
- AC-VTABLE-805：评分独立计算 paired TEDS / structure-only，记录数字 token
  multiset P/R/F1（仅文本诊断，不等于单元格数值准确率）、延迟、tokens 与失败数。
  正常对照退化必须报告；不得基于 Gold 挑选最优候选充当生产策略。
- AC-VTABLE-806：报告提供原图/预测框/Docling/Gold/VLM 对照。模型内容与 Gold
  以转义文本展示，预览只渲染我们生成的安全表格，不开放任意 HTML/脚本。

## 实施步骤

1. 先写裁图、验证、隔离和故障路径测试，记录 RED。
2. 新增独立实验脚本及评分脚本；离线准备并人工检查裁图。
3. 使用现有配置做至多 3 次调用；原始响应与候选分目录保存。
4. 用固定 evaluator 的 normalization/TEDS 计算 3 表配对结果，同时校验 baseline
   与 v4 已保存分数一致。此为局部表格实验，不冒充全量 end-to-end 重测。
5. 跑回归测试、记录结果和限制；下一轮在新表格页验证后再考虑生产接入。

## 测试路由

后端/脚本单元层：bbox、网格、HTML 转义、非法输入。
切片层：prepare → fake client → candidate，超时/截断/预算、哈希与不可覆盖。
真实接缝：3 次图像 API 与固定官方 TEDS 函数。无前端、数据库、部署变更，
不触发这些层的写入或浏览器测试。本轮不 commit/push。

## 验证记录

- AC-VTABLE-801/802/803/804/806：`tests/test_experiment_vlm_tables.py`，7 项；
  包括 mock SDK 的真实请求参数检查、prepare/run 切片及故障/隔离路径。
- AC-VTABLE-805/806：`tests/test_score_vlm_table_experiment.py`，4 项；
  覆盖失败分母、数值诊断边界、不安全 HTML 和被拒绝网格的诊断。
- 先 RED（新增模块不存在），后 GREEN；全套 196 项通过、0 失败/跳过。
- 已检查 3 张裁图，已完成 3 次联网请求：1 张结构无效、2 次超时，0 张可用候选。
- 单独评分与原 v4 baseline 全部一致。没有 Gold 调参、最优结果选择或线上替换。
- 自审：保留用户已有 dirty worktree；首次沙箱连接失败和后续联网运行分开记录；
  两次超时费用未知，不将工程测试成功当作模型效果提升。
- 报告：`docs/evaluation/omnidocbench-table-vlm-v5.md`，含全部失败、复现与后续建议。
