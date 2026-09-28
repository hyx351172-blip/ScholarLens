"""Zero-network BM25/Dense A/B using saved Dense Top-10, NOT live Top-50.

Run with python -m scripts.evaluate_hybrid_search --help. Does not import
credentials, Milvus service or a model client; never retrieves/embeds/generates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from backend.Database.milvus_server.hybrid_search import BM25Index, TOKENIZER_VERSION, fuse_rrf
from scripts.evaluate_evidence_retrieval import _best_set_metrics, _gold_ids, _ndcg, _validate_dataset

TOP_K = 10


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def load_corpus(root: Path) -> tuple[list[dict], dict]:
    from scripts.reindex_structured_dataset import ChunkingConfig, _chunk_document
    paths = sorted(root.rglob('document.json'))
    if not paths:
        raise ValueError('No saved parser document.json files found')
    corpus, manifest = [], []
    for path in paths:
        document, chunks = _chunk_document(path, ChunkingConfig(target_tokens=600, max_tokens=900))
        manifest.append(dict(path=path.relative_to(root).as_posix(), filename=document.filename,
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest(), chunks=len(chunks)))
        for chunk in chunks:
            corpus.append(dict(id=chunk['chunk_id'], filename=document.filename,
                               file_id=document.file_id, metadata=chunk,
                               chunk_text=chunk.get('retrieval_text') or chunk['text']))
    unified = Path(__file__).resolve().parents[1] / 'backend/Information-Extraction/unified'
    code = {p.relative_to(unified).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(unified.rglob('*.py'))}
    return corpus, dict(document_count=len(paths), chunk_count=len(corpus), documents=manifest,
                        parser_artifacts_sha256=digest(manifest), chunker_code_sha256=digest(code),
                        reconstructed_corpus_sha256=digest(corpus))


def _cached_hits(result: dict) -> list[dict]:
    return result['dense']['hits'] if 'dense' in result else result['hits']


def validate_inputs(dataset: dict, baseline: dict, corpus: list[dict]) -> dict[str, dict]:
    _validate_dataset(dataset)
    for field in ('dataset_id', 'collection_id'):
        if not dataset.get(field) or dataset[field] != baseline.get(field):
            raise ValueError(f'Baseline/dataset mismatch: {field}')
    if baseline.get('top_k', baseline.get('configuration', {}).get('top_k')) != TOP_K:
        raise ValueError('Only saved Dense Top-10 is supported')
    if not dataset.get('cases'):
        raise ValueError('Empty evaluation dataset')
    rows = {str(row['metadata']['chunk_id']): row for row in corpus}
    if len(rows) != len(corpus):
        raise ValueError('Duplicate corpus chunk identities')
    counts = (len({row['filename'] for row in corpus}), len(corpus))
    expected = dataset.get('corpus', {})
    recorded = baseline.get('corpus_validation', {})
    for count, key, baseline_key in zip(counts, ('paper_count', 'chunk_count'), ('document_count', 'chunk_count')):
        if count != expected.get(key) or count != recorded.get(baseline_key):
            raise ValueError(f'Corpus count mismatch: {key}')
    cached = {result['id']: result for result in baseline.get('results', [])}
    if len(cached) != len(baseline.get('results', [])) or set(cached) != {c['id'] for c in dataset['cases']}:
        raise ValueError('Missing, extra or duplicate baseline cases')

    def check_reference(reference: dict):
        cid = reference['chunk_id']
        if cid not in rows:
            raise ValueError(f'Stale chunk reference: {cid}')
        row = rows[cid]
        for key in ('filename', 'page_start', 'content_type', 'section_path'):
            actual = row['filename'] if key == 'filename' else row['metadata'].get(key)
            if key in reference and reference[key] != actual:
                raise ValueError(f'Stale {key} for chunk: {cid}')

    for case in dataset['cases']:
        result = cached[case['id']]
        if result.get('answerable') != case['answerable']:
            raise ValueError('Baseline answerable flag mismatch')
        hits = _cached_hits(result)
        if len(hits) > TOP_K or len({hit['chunk_id'] for hit in hits}) != len(hits):
            raise ValueError('Invalid cached candidate count or duplicates')
        for rank, hit in enumerate(hits, 1):
            if hit.get('rank') != rank or not math.isfinite(hit['score']) or not -1 <= hit['score'] <= 1:
                raise ValueError('Invalid cached Dense rank/score')
            check_reference(hit)
        for evidence_set in case.get('gold_evidence_sets', []):
            for reference in evidence_set:
                check_reference(reference)
    return rows


def _evaluate(case: dict, hits: list[dict]) -> dict:
    ids = [hit['metadata']['chunk_id'] for hit in hits]
    strict, recall, rr = _best_set_metrics(ids, _gold_ids(case))
    compact = [dict(rank=rank, chunk_id=hit['metadata']['chunk_id'], filename=hit['filename'],
                    page_start=hit['metadata'].get('page_start'), score=hit.get('score', hit.get('bm25_score')),
                    **{key: hit[key] for key in ('dense_score', 'bm25_score', 'hybrid_rrf_score',
                                                'branch_ranks', 'score_type') if key in hit})
               for rank, hit in enumerate(hits, 1)]
    return dict(strict_evidence_hit=strict if case['answerable'] else None,
                best_evidence_set_recall=recall if case['answerable'] else None,
                evidence_set_reciprocal_rank=rr if case['answerable'] else None,
                ndcg=_ndcg(ids, _gold_ids(case)) if case['answerable'] else None, hits=compact)


def compare(dataset: dict, baseline: dict, corpus: list[dict]) -> dict:
    rows = validate_inputs(dataset, baseline, corpus)
    cached = {result['id']: result for result in baseline['results']}
    start = time.perf_counter()
    index = BM25Index(corpus)  # Does not see standard answers or gold labels.
    index_seconds = time.perf_counter() - start
    results = []
    for case in dataset['cases']:
        dense = [dict(rows[hit['chunk_id']], score=hit['score']) for hit in _cached_hits(cached[case['id']])]
        start = time.perf_counter()
        lexical = index.search(case['question'], TOP_K)
        fused = fuse_rrf(dense, lexical, TOP_K)
        elapsed = time.perf_counter() - start
        gold = {cid for group in _gold_ids(case) for cid in group}
        dense_ids = {hit['id'] for hit in dense}
        fused_ids = {hit['id'] for hit in fused}
        results.append(dict(id=case['id'], category=case.get('category'), question=case['question'],
                            answerable=case['answerable'], dense=_evaluate(case, dense),
                            bm25=_evaluate(case, lexical), hybrid=_evaluate(case, fused),
                            added_gold=sorted((fused_ids - dense_ids) & gold),
                            dropped_gold=sorted((dense_ids - fused_ids) & gold),
                            added_local_latency_seconds=elapsed))
    answerable = [result for result in results if result['answerable']]
    metric_fields = dict(strict_evidence_hit_rate='strict_evidence_hit',
                         mean_best_evidence_set_recall='best_evidence_set_recall',
                         evidence_set_mrr='evidence_set_reciprocal_rank', mean_ndcg='ndcg')
    summary = {variant: {output: statistics.mean(result[variant][metric] for result in answerable)
                         if answerable else None for output, metric in metric_fields.items()}
               for variant in ('dense', 'bm25', 'hybrid')}
    # Assert the replay reproduced the historical Dense metrics; fail on drift.
    historical = baseline.get('summary', {})
    historical = historical.get('dense', historical)
    for key, actual in summary['dense'].items():
        if key in historical and not math.isclose(actual, historical[key], abs_tol=1e-9):
            raise ValueError(f'Dense metric replay drift: {key}')
    paired = {}
    for metric in metric_fields.values():
        differences = [float(r['hybrid'][metric]) - float(r['dense'][metric]) for r in answerable]
        paired[metric] = dict(wins=sum(d > 1e-12 for d in differences),
                              losses=sum(d < -1e-12 for d in differences),
                              ties=sum(abs(d) <= 1e-12 for d in differences))
    return dict(schema_version='1.0', experiment='bm25-dense-rrf-offline-replay-v1',
                dataset_id=dataset['dataset_id'], collection_id=dataset['collection_id'],
                evaluation_role='previously-used-dataset-offline-replay', external_api_calls=0,
                case_count=len(results), answerable_cases=len(answerable),
                document_count=len({row['filename'] for row in corpus}), chunk_count=len(corpus),
                unanswerable_cases=len(results)-len(answerable),
                configuration=dict(top_k=TOP_K, dense_cached_k=TOP_K, bm25_k=TOP_K,
                                   bm25_k1=1.2, bm25_b=.75, rrf_k=60,
                                   dense_weight=1, bm25_weight=1, tokenizer=TOKENIZER_VERSION,
                                   score_threshold=None, reranker=False, multi_query=False),
                summary=summary, paired_outcomes=paired,
                local_timing=dict(index_seconds=index_seconds,
                                  mean_bm25_fusion_seconds=statistics.mean(r['added_local_latency_seconds'] for r in results)),
                limitations=[
                    'Cached Dense Top-10 plus BM25 Top-10; not a fresh Dense/Hybrid Top-50 online experiment.',
                    'Historical baseline lacks original query/corpus-content fingerprints; current IDs, counts and available metadata are validated, not historical raw text equality.',
                    'Both datasets have been used before. No independent fresh held-out claim or parameter tuning.',
                    'Gold relevance judgments are partial; NDCG uses the annotated union only.',
                    'No generation, citation entailment or no-answer correctness evaluation.',
                    'Local BM25 timing excludes Milvus scans, query Embedding and HTTP; not end-to-end latency.',
                ], results=results)


def markdown(result: dict) -> str:
    lines = [f"# Hybrid 检索离线对比：{result['dataset_id']}", '',
             f"{result['document_count']} 篇论文 / {result['chunk_count']:,} Chunk；{result['case_count']} 题，其中 {result['answerable_cases']} 道可回答题计入以下指标。", '',
             '历史 Dense Top-10 与完整语料的 BM25 Top-10 做等权 RRF，最终 Top-10。未运行新 Embedding、Reranker 或生成，外部 API 调用为 0。', '',
             '| 方式 | 完整证据命中率 | 平均证据集 Recall | 证据集 MRR | NDCG（已标注） |',
             '| --- | ---: | ---: | ---: | ---: |']
    for variant, values in result['summary'].items():
        lines.append(f"| {variant} | {values['strict_evidence_hit_rate']:.2%} | {values['mean_best_evidence_set_recall']:.4f} | {values['evidence_set_mrr']:.4f} | {values['mean_ndcg']:.4f} |")
    lines += ['', '## 逐题结果', '', '| 题目 | Dense 完整命中 / MRR | Hybrid 完整命中 / MRR | 新增 / 丢失 Gold Chunk |',
              '| --- | --- | --- | --- |']
    for item in result['results']:
        if not item['answerable']:
            continue
        a, b = item['dense'], item['hybrid']
        lines.append(f"| {item['id']} | {a['strict_evidence_hit']} / {a['evidence_set_reciprocal_rank']:.4f} | {b['strict_evidence_hit']} / {b['evidence_set_reciprocal_rank']:.4f} | {len(item['added_gold'])} / {len(item['dropped_gold'])} |")
    lines += ['', '## 结论边界', '',
              '- 参数在运行前固定：BM25 k1=1.2、b=0.75；RRF k=60、两路等权，未针对结果调参。',
              '- 两组标注集此前均已使用。这是历史排名回放，不是新的独立 Held-out，也不是当前含范围/章节规则的完整 `/chat` A/B。',
              '- 历史基线只有 Top-10，没有 Top-50 向量或候选全量排名。本结果不能代表在线 candidate-50 的效果。',
              '- 本次校验所有 Gold 和历史命中的 Chunk ID、文件名及已有页码/类型信息，并检查 19/2057 数量。历史文件未保存原始文本/问题指纹，不能证明历史原文逐字不变。',
              '- 无答案题不计入召回率；返回检索片段不等于产生错误答案。没有测试回答质量、语义引用或拒答。',
              '- 局部计时只含内存 BM25/融合，不含扫描 Milvus、Embedding 或 HTTP，不是在线总延迟。',
              '- 当前默认保持 Dense；Hybrid 作为可选模式，线上验证后再决定是否更换默认。', '',
              '完整参数、逐题排名、输入 SHA-256 与语料指纹见同名 results.json。', '']
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding='utf-8'))
    baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
    corpus, validation = load_corpus(args.corpus)
    result = compare(dataset, baseline, corpus)
    code_root = Path(__file__).resolve().parents[1]
    code_paths = ['scripts/evaluate_hybrid_search.py', 'backend/Database/milvus_server/hybrid_search.py']
    result['provenance'] = dict(dataset_file=args.dataset.name,
        dataset_sha256=hashlib.sha256(args.dataset.read_bytes()).hexdigest(), baseline_file=args.baseline.name,
        baseline_sha256=hashlib.sha256(args.baseline.read_bytes()).hexdigest(), corpus=validation,
        implementation_sha256={p: hashlib.sha256((code_root / p).read_bytes()).hexdigest() for p in code_paths})
    for path, content in ((args.output, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)),
                          (args.report, markdown(result))):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.rstrip('\n') + '\n', encoding='utf-8')
    print(json.dumps(dict(summary=result['summary'], paired_outcomes=result['paired_outcomes']), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
