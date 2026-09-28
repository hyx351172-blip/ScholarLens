import type { CitationSource } from './citations.ts';

export type RetrievalMode = 'dense' | 'hybrid';

export function retrievalOptions(mode: RetrievalMode) {
  return { retrieval_mode: mode };
}

export function retrievalScoreLabel(source: CitationSource): string {
  if (source.rerank_score != null) return '重排序分数';
  if (source.retrieval_mode === 'hybrid') return '融合排序分数';
  if (source.query_rrf_score != null) return '多查询排序分数';
  if (source.section_boost) return '章节排序分数';
  return '相似度';
}
