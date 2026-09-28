# 浏览器验收问题后续修复与版本化回归（2026-09-27）

## 结论与范围

本轮针对[定向复测](browser-fix-retest-20260927.md)中跨论文答案的额外扩写，收紧默认回答提示：只回答问题明确要求的比较维度；引用必须支持同一句的所有事实和限定词。增加离线回归用例，验证这些约束实际进入生成请求。**这是提示词层面的缓解，不是语义蕴含校验器；不能据此宣称真实模型的该题已经改对。**

另将当前代码回归和冻结历史实验测试分开运行。旧实验清单要求旧版源码指纹，不能把它们在修改后的源码上运行时出现的指纹拒绝记为产品功能失败，也不能放宽清单或改写已批准的历史数据。本轮没有修改历史实验清单、数据或预检策略。

## 修改

- `backend/chat/answer_guard.py`：通用证据约束新增“只回答所问维度”和“引用覆盖同句全部细节”。
- `backend/chat/kb_chat.py`：默认问答模板要求架构比较不附加训练任务、下游用途，并逐句核对原文支持。
- `tests/test_browser_acceptance_fixes.py`：加入生成消息离线测试；它检查约束进入模型上下文，不检查模型是否必然遵守。
- `tests/run_current_suite.py`：发现测试后将 10 个冻结实验模块与当前代码测试分组；可选 `--historical-root` 验证旧版关键源码的 SHA-256，再在独立历史快照中运行全部冻结模块。未提供历史快照时明确提示 134 项未运行，不能将当前子集称为完整测试。

## 验证口径

当前代码测试从仓库目录执行：

```powershell
E:\Anaconda\envs\multimodal-rag\python.exe -X utf8 tests/run_current_suite.py
```

本机历史快照由提交 `005c440d1408c685b74b399e722b7456d167080c` 导出，存于被 Git 忽略的 `output/historical-test-checkout-005c440/`；其 `answer_guard.py`、`kb_chat.py` 字节指纹与冻结清单一致，所需旧实验产物及 SciFact 数据以本地只读副本提供。两组测试可由以下入口串行执行：

```powershell
E:\Anaconda\envs\multimodal-rag\python.exe -X utf8 tests/run_current_suite.py --historical-root output/historical-test-checkout-005c440
```

历史快照及完整原始产物不随公开仓库提供；其他设备缺失它们时应报告不可复现，不应用新版本伪造旧版指纹。上述测试路径均使用测试替身，不向模型供应商发送问题。

## 结果与限制

- 版本化入口实际运行 **853/853 项通过**：当前代码 719/719（25.178 秒），冻结历史实验 134/134（363.324 秒），进程退出码 0。运行日志在本地 `output/browser-fix-followup-20260927/versioned-suite.log`；历史组此前拆成两批单独预检也分别为 89/89、45/45。测试中的预期异常会打印 traceback，但 `unittest` 最终均为 `OK`。
- 原先单目录 `unittest discover` 的 59 项错误来自新源码与冻结实验源码指纹不一致；新的版本化入口保留这一防漂移检查，而不是把拒绝改为通过。标准单目录命令仍不适合作为跨版本总门禁。
- 此前 2 次真实复测授权已用尽；第一次尝试追加问答受到自动审批拒绝，当时未发送请求。**用户随后明确确认新增最多 1 次向阿里云百炼发送问题及检索证据的计费问答**，才执行了下述真实浏览器复测。没有绕过拒绝直接调用后端，也没有扩大题量。
- 普通浏览器原文 PDF 跳页等上轮待验项仍未关闭，完整发布验收依然为 **未通过**。本轮未提交、推送或合并。

## 授权后真实浏览器复测

在 `Browser-final-mixed-20260927` 知识库、`qwen3-vl-plus`、Temperature `0.7`、最大输出 `2000` token 下，仅提交一题：

> 比较 Attention Is All You Need 与 BERT 的模型架构：前者是否包含编码器和解码器，后者采用什么结构？

页面完成一次回答；服务日志只显示 **1 次 `POST /chat`，HTTP 200**。这不证明供应商内部只有一次计费调用：检索 Embedding、SDK 内置重试及具体账单未单独核验。提交前两次按钮点击没有改变页面，服务日志也没有 `POST /chat`；刷新页面、重新选定测试知识库后，通过输入框按 Enter 完成唯一一次实际提交，没有重发。

本次答案正确区分前者的 encoder-decoder 与 BERT 的多层双向 Transformer encoder，没有重现先前未经同句证据完整支持的“预训练/下游用途”扩写。网页引用面板核对结果：

| 来源 | 打开的原文位置 | 核对结果 |
| --- | --- | --- |
| S1 | Attention，第 3 页，`3.1 Encoder and Decoder Stacks` | 明确给出编码器/解码器各 6 层、注意力/前馈子层、解码器额外跨注意力与掩码；支持对应架构细节 |
| S3 | Attention，第 2 页，`3 Model Architecture` | 给出编码器将输入映射成表示、解码器逐步生成输出；支持 encoder-decoder 概括 |
| S10 | BERT，第 3 页，`3 BERT` | 明确称其为多层双向 Transformer encoder，并列出 BERTBASE、BERTLARGE 的 L/H/A 参数；支持引用的结构及规模数字 |

本题的**核心结构结论与所引原文相符**。仍需保留边界：回答额外加入了 BERTBASE/BERTLARGE 配置；这部分虽然 S10 原文支持，却超过用户要求的最小比较范围。`encoder-only／未采用解码器`是对原文“Transformer encoder”架构描述的合理概括，而非该片段逐字否定解码器。单题通过不能外推为任意论文、任意问法的引用蕴含准确率。
