# 表格解码上限审计 v8

## 结论

**证实 v7 中两张长表存在静态解码上限截断。** 在保持裁图、预处理、分类器、
结构识别权重不变的前提下，将独立实验副本的循环上限从 500 延长为 1000，
两张表均出现自然结束标记（EOS），严格有效结构从 **0/3 提升到 2/3**。
另外一张表原本已经自然结束，延长后输出完全相同且仍然无效，说明长度上限不是所有问题的原因。

这次是**结构识别对照，不是完整 OCR 修复**：没有把文字、数字重新填入恢复的单元格，
没有验证单元格内容准确率、完整 TEDS、下游 RAG 或生产链路；未替换正式解析器。

## 实验设计与因果证据

延用 v5 的三张固定预测框裁图，不使用 Gold 框、文字或行列数指导识别。
其中两页为电子元件数据表，只有一页为科研论文 benchmark 表，不称作三篇论文测试。

环境：PaddleOCR 3.7.0、PaddleX 3.7.2、PaddlePaddle 3.3.1、NumPy 1.26.4；
CPU、4 线程、关闭 MKLDNN。实际分类器三张均选中 `SLANeXt_wired`。
使用与 PP-TableMagic 相同的分类器和结构识别模型，但跳过 OCR、单元格检测和文字匹配，
直接捕获结构解码前的真实概率张量，不再用 HTML 字符数猜测生成长度。

静态 `inference.json` 中存在：

- 循环上限标量 500（SSA 2389）；循环条件使用上限加一。
- 三个缓冲区容量标量 501（SSA 2367、2373、2379）。
- EOS 类别编号 49。

只修改 YAML 的 `max_text_length` 不会改变这个已导出的静态循环。
实验仅在新目录克隆模型，对已固定哈希的图精确修改上述 **4 个常量**：
500 → 1000，三个 501 → 1001。权重、配置及原始模型保持不变。
两个模型副本均完成哈希/差异检查，实际推理只用到了 wired 副本。
这是**非官方实验图变体**，不是重新训练或官方重新导出的模型，不能直接当生产配置使用。

## 实测结果

| 固定样本 | 原始张量时间步 / EOS | 延长后时间步 / EOS | 严格结构 | Docling 结构 TEDS | 延长候选结构 TEDS |
|---|---:|---:|---|---:|---:|
| `035cb436…` 复杂元件数据表 | 350 / 有 | 350 / 有 | 仍无效，标签不平衡 | 0.358730 | 不计分 |
| `0cbdcfa9…` EEPROM 数据表 | 501 / 无 | 576 / 有 | 有效，41×12，492 cells | 0.975610 | **1.000000** |
| `14a6b411…` 论文 benchmark 表 | 501 / 无 | 588 / 有 | 有效，41×12，482 cells | 0.973585 | **0.979245** |

时间步是模型返回张量的长度，不是正文 token 数。自然结束的三个结果中，EOS 的
零基索引分别为 348、574、586，之后还有一个尾部槽；实际 HTML 解码器在 EOS 处停止。

三组配对的原始预测序列均与延长序列的前缀完全一致；两张长表的前 501 步一致。
短表作为提前结束对照，全部 token ID 一致。因此，在这两张长表上，恢复后续输出
可以归因于移除了当前静态长度限制，而不是换模型、换裁图或改预处理。

延长后的两张表均通过原有严格 HTML 标签、span 与完整网格校验；没有补空格、
猜数字、自动补标签或用 Gold 修复候选。第一张拒绝结果保留原样。

使用已固定版本的 OmniDocBench `normalized_html_table` 和 `TEDS(structure_only=True)`，
对固定 1:1 表格配对评分。重新计算的 Docling 分数全部复现 v4。

- 原始结构有效率：0/3；延长后：2/3。
- 无效结果保留 Docling 的模拟组合结构分数：**0.769308 → 0.779325**。
- 组合仅按结构合法性决定回退，不按 Gold 分数择优；本轮没有有效但退步的候选。
- 这里的 1.000000 只代表归一化后的结构匹配，不代表文字/数字识别完全正确。
- 无效结构不报告候选 TEDS；不能把“未计分”误写为 OCR 准确率为零。

单张结构推理耗时：原始约 6.44–6.92 秒，延长约 6.02–6.77 秒；含启动和初始化的
子进程耗时约 16.23–20.20 秒。只运行一次，没有重复计时或性能显著性结论。
本轮不包含 OCR 和单元格检测，**不能与 v7 完整流水线耗时直接比较速度提升**。
付费 API 调用为 0。

## 验证与完整性

- 新增 18 项测试；全量本地回归 **245 passed，0 failures / errors / skips**，22.531 秒。
- 15 项解码/克隆测试在隔离 Paddle 环境中也全部通过。
- 六次真实结构推理与官方评分接缝均执行完成；保存概率张量后重新检查，全部与记录一致。
- 原模型文件哈希前后相同；每个克隆图恰好只有四个叶子值变更；复制权重哈希一致。
- 全部 15 个冻结源图、源解析 JSON、原生 Docling JSON、裁图和基线 HTML 哈希通过。
- 5 条验收标准通过需求—测试双向追溯；Python 编译与 `git diff --check` 通过。
- 模型及完整本地产物受 `.gitignore` 保护；无生产依赖、API、前端或数据库变更。
- 按 `ai-product-dev-pack` 流程先写验收与失败测试，再实现、运行真实对照和回归。

接入阶段两次在结构模型推理前停止：PIR 参数节点的 `O` 是单个对象，
以及 `combine` 属于 `0` 方言而不是 `1` 方言。已修正并加入测试。
原失败目录 `omnidocbench-table-decoder-v8` 与 `…-run2` 保留；没有自动重试或覆盖。
最终六次推理在 `…-run3` 完成。

## 产物位置

所有路径相对于仓库根目录：

- `scripts/audit_table_decoder.py`：静态图审计、独立克隆、真实张量捕获、条件对照。
- `scripts/score_table_decoder_audit.py`：单独读取 Gold 的结构评分及 HTML 对照。
- `output/benchmarks/omnidocbench-table-decoder-v8-run3/summary.json`：六次尝试、前缀对照、模型哈希。
- 同目录 `original/<page>/` 和 `extended/<page>/`：`structure.html`、`decoder.json`、
  `decoder-tensors.npz`、`predictor-config.json`、`result.json` 和 `worker.log`。
- 同目录 `experimental-models/`：独立图副本及 `clone-audit.json`，不是部署目录。
- 同目录 `real-seam-validation.json`、`input-integrity.json`、`regression-tests.json/.log`：复核记录。
- `output/benchmarks/omnidocbench-table-decoder-v8-scored/index.html`：Gold / Docling / 原始 / 延长结构对照。
- `output/benchmarks/omnidocbench-table-decoder-v8-scored/results.json`：官方结构评分及逐产物哈希。
- `docs/evaluation/omnidocbench-table-decoder-v8-results.json`：可入库的简短结果摘要。

## 复现

在仓库根目录执行，使用已安装的隔离环境及已有模型缓存；不下载新模型。
每次指定新的 ASCII 输出目录，Windows 模型路径必须使用项目相对路径。

```powershell
$env:PYTHONUTF8 = '1'
& 'E:/Anaconda/envs/multimodal-rag/python.exe' scripts/audit_table_decoder.py `
  --output output/benchmarks/table-decoder-v8-repro

$env:MPLCONFIGDIR = (Join-Path (Get-Location) 'backend/data/benchmarks/model_cache/matplotlib')
$env:HF_HOME = (Join-Path (Get-Location) 'backend/data/benchmarks/model_cache/huggingface-eval')
& 'backend/data/benchmarks/omnidocbench/.eval-venv/Scripts/python.exe' scripts/score_table_decoder_audit.py `
  --prepared output/benchmarks/omnidocbench-table-vlm-v5/prepared `
  --run-dir output/benchmarks/table-decoder-v8-repro `
  --gold output/benchmarks/omnidocbench-scholar-lens-smoke-v2/selected_annotations.json `
  --evaluator backend/data/benchmarks/omnidocbench/evaluator `
  --previous output/benchmarks/omnidocbench-table-fidelity-v4/scores/table_structure/result/predictions_quick_match_table_result.json `
  --output output/benchmarks/table-decoder-v8-repro-scored

& 'E:/Anaconda/envs/multimodal-rag/python.exe' -m unittest discover -s tests -p 'test_*.py'
```

若模型缓存因 Windows ACL 不可读，需为该次本地进程授予读取权限，不要修改源模型。
每个 worker 最长 300 秒、无自动重试；原始组确认长度耗尽后才开启延长组。

## 下一步

优先对这两个有效结构复用/绑定 OCR 单元格文字，验证**完整 TEDS、数字与单位的
行列归属、表头合并关系**，确认结构改善能变成内容改善，再考虑扩大独立测试集。
第一张自然结束但结构无效的表，需要另外评估保留表头/span 的局部识别或几何方案，
继续增加输出上限不会解决当前错误。

现阶段不把实验图直接接入生产，也不把 3 张事后选择的开发样本结果外推到全部论文。
