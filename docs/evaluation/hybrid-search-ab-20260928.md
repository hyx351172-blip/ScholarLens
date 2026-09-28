# ScholarLens 混合检索实现与 A/B 对比

日期：2026-09-28。新增应用侧 BM25 + Milvus Dense + 等权 RRF；默认仍为 Dense。

## 已实现

- `/search`、`/chat` 支持 `retrieval_mode: "dense" | "hybrid"`，不需要重建已有 Collection 或重新 Embedding。
- 前端「模型设置 → 检索方式」可选择 Hybrid，回答生成期间禁用切换。刷新后默认 Dense。
- BM25 对完整的当前论文范围 Chunk 做关键词检索，而不是只重排 Dense 候选。两路使用相同 Collection/filter；Dense 保留原有阈值，BM25 正分匹配不受 cosine 阈值影响。
- 保留 `dense_score`、`bm25_score`、`hybrid_rrf_score`、`branch_ranks` 和 `score_type`。章节选择、多查询、引用源与可选 Reranker 路径继续可用；前端不把 RRF 显示为相似度。
- BM25 参数 k1=1.2、b=0.75；RRF k=60、等权。NFKC/casefold + 字词数字/CJK bigram，无词干化、语义翻译、同义词扩展。
- Hybrid 读取 Milvus Strong-consistency iterator，异常/超时关闭 iterator、不静默退回 Dense；空范围不调用 Embedding。最多 20,000 Chunk / 64 MiB 检索文本，扫描预算 15 秒。不使用缓存，因此上传/删除后下一次查询重读当前行。
- 已添加零网络 A/B 脚本与 Harness artifact 回放配置。没有使用本轮之外的旧付费调用额度。

这是面向当前个人项目规模的实现，不是 Milvus 内置 BM25 稀疏索引。后续大规模数据应评估持久倒排索引或新的 Milvus BM25 Collection；本轮不迁移已有数据。逐次扫描与构建索引存在成本；两路读不是跨查询原子快照，实验时应冻结入库/删除操作。

## 对比结果

19 篇论文、2,057 Chunk；v1 共 14 题、v2 共 24 题。以下只统计可回答题（分别 12、20 道），剩余 6 道无答案题不混入召回率分母。

| 数据集 | 方式 | 完整证据集命中率@10 | 平均证据集 Recall@10 | 证据集 MRR@10 | NDCG@10（已标注） |
| --- | --- | ---: | ---: | ---: | ---: |
| v1，12 道可回答 | Dense | 100% | 1.0000 | 0.6181 | 0.7274 |
| v1，12 道可回答 | Hybrid | 100% | 1.0000 | 0.5514 | 0.6872 |
| 已使用 v2，20 道可回答 | Dense | 75%（15/20） | 0.8500 | 0.5613 | 0.6789 |
| 已使用 v2，20 道可回答 | Hybrid | 90%（18/20） | 0.9250 | 0.5523 | 0.6645 |

完整证据集命中：至少一个可接受 Gold 集的所有 Chunk 均进入 Top-10。平均证据集 Recall：每题选择覆盖比例最高的可接受 Gold 集，再取均值。证据集 MRR 使用完整集最后一个所需证据的名次倒数，不是只看首个相关片段的普通 MRR。NDCG 的相关性为人工标注 Gold 集的并集，非所有候选的完整人工判断。

v2 找回 HV17、HV18、HV20 三道题所需证据，没有丢掉已有命中的完整集；HV14、HV19 仍缺证据。MRR 有 7 题改善、4 题退步、9 题不变，但总体均值略降。v1 的 MRR 有 3 改善、5 退步、4 不变。新增关键词召回提高部分题的完整性，不代表全方面排序改善，因此**保留 Dense 默认，Hybrid 可选**，不继续针对这两组题调参。

逐题与 BM25-only 消融见 [v1 报告](hybrid-search-v1-20260928.md)、[v2 报告](hybrid-search-v2-20260928.md)；机器结果包含每个命中的分数/排名和输入 SHA-256。

## 实验边界

- 使用保存的 **Dense Top-10**，与从完整语料新计算的 BM25 Top-10 融合；不是新的线上 candidate-50 实验，也不是当前 `/chat` 的完整范围/章节/回答 A/B。
- 两组标注集都已在此前实验中使用，v2 文件名的 heldout 不意味着这次仍然独立未见。参数运行前固定，未根据本轮结果调参。
- 重新切分得到 19/2,057 的相同数量，校验全部 Gold/历史检索 Chunk ID、文件名和已有页码/类型/章节字段；回放 Dense 指标与历史记录完全一致。历史文件没有原始问题/文本 SHA，无法声称逐字的历史内容相同；本轮新增指纹从现在开始可追踪。
- 外部 API 调用 **0**；没有新生成答案，没有测试回答正确率、引用语义或无答案拒答。报告的局部耗时不含 Milvus、Embedding 或网络，不能当作端到端延迟。
- 本机 Milvus API 检查时未启动；新增在线路径只做了受控桩/HTTP 契约测试。真实 Hybrid 浏览器问答与在线性能验收仍待运行。

## 复现

在仓库根目录、项目 Python 环境中执行，替换 `$hybridCorpus` 为已有 **19 篇 document.json** 的目录（不是 PDF 文件夹）：

```powershell
$hybridCorpus = "C:\Users\hp\Desktop\ScholarLens\output\parser_dataset_full_2026_09_06\papers"
python -X utf8 -m scripts.evaluate_hybrid_search --dataset docs/evaluation/evidence-gold-v1.json --baseline docs/evaluation/evidence-retrieval-v1-results.json --corpus $hybridCorpus --output output/hybrid-v1.results.json --report output/hybrid-v1.md
python -X utf8 -m scripts.evaluate_hybrid_search --dataset docs/evaluation/evidence-gold-v2-heldout.json --baseline docs/evaluation/rank-fusion-heldout-v2-results.json --corpus $hybridCorpus --output output/hybrid-v2.results.json --report output/hybrid-v2.md
python -X utf8 -m harness run --config harness/configs/hybrid-search-ab-replay-v1.json
```

脚本检查缺失、重复、元数据和历史指标漂移，失败就停止；不会通过重新调用模型补齐历史候选。语料大文件不随 Git 自动提交，别人复现需要另外获取同一批解析产物。Harness 使用本次保存 JSON 做零成本 artifact 回放，不重新运行检索；本配置 PASS 只代表读入/指标提取/零调用门通过，**不是 Hybrid 上线或更换默认的放行**。

使用 API：向现有请求增加 `"retrieval_mode": "hybrid"`；原有 LLM/Embedding 配置无需改变。重启 Milvus API 和 chat 后端、刷新前端后可见开关。之后在线查询仍会使用原配置的 Embedding 和生成 API，费用与离线实验分开。

## 测试与交付

按 ai-product-dev-pack 的特性闭环补充 RED→GREEN 测试、契约/追踪检查，固定 Dense 默认和实验边界。没有提交、推送、合并或改变运行中服务。

- 本特性 26/26 离线/桩测试通过；当前版本全量 745/745 回归通过。另在经源码 SHA 验证的旧快照运行 134/134 历史测试通过（非当前源码测试），不能把历史指纹测试强行改成新源码通过。
- 前端 20/20 测试通过；TypeScript/Vite 生产构建通过。构建仍提示既有 bundle 体积与 Browserslist 数据陈旧警告，不等于新功能失败。
- 本特性追踪：6 个 AC、6 个追踪引用，双向对齐。该检查范围不是全仓库发布门；真实在线集成仍待验收。
- `/search` Dense 原有正数大 K 请求仍兼容；Hybrid 单独限 K≤500。未知模式/非法 K 返回 422，超出语料限制返回 413，扫描预算耗尽返回 503。未改动数据库 schema。

本地日志：`output/hybrid-current-final-suite.log`（当前版本）、`output/hybrid-final-suite.log`（先前 744 当前 + 134 冻结历史；后补 Prompt 分数回归使当前新增至 745）。这两个日志被 Git 忽略，公开仓库中的报告保留运行数量与边界，不伪称历史套件执行于当前代码。

审查修正并固化测试：RRF/cosine 阈值混淆、Prompt/前端分数标签、迭代器关闭与资源上限、旧后端错误契约、HTTP 错误码传播、Hybrid 扫描移出 FastAPI event loop。已完成静态韧性/防御性/消费者契约检查及 `git diff --check`；余项是真实在线验收、扫描规模与并发读写性能，不宣称完整上线门通过。

实现参考：[Lucene BM25](https://lucene.apache.org/core/9_12_1/core/org/apache/lucene/search/similarities/BM25Similarity.html)、[RRF 排名融合](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/reciprocal-rank-fusion)、[Milvus query iterator](https://milvus.io/api-reference/pymilvus/v2.6.x/ORM/Collection/query_iterator.md)。自定义 tokenizer 与 Lucene 默认 analyzer 不同，不应宣称结果完全一致。
