import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { retrievalOptions, retrievalScoreLabel } from '../src/retrievalMode.ts';

test('AC-5101 retrieval options send explicit opt-in and retain Dense', () => {
  assert.deepEqual(retrievalOptions('dense'), { retrieval_mode: 'dense' });
  assert.deepEqual(retrievalOptions('hybrid'), { retrieval_mode: 'hybrid' });
  const chat = readFileSync(new URL('../components/Chat.tsx', import.meta.url), 'utf8');
  assert.match(chat, /useState<RetrievalMode>\('dense'\)/);
  assert.match(chat, /\.\.\.retrievalOptions\(retrievalMode\)/);
  assert.match(chat, /value=\{retrievalMode\}[\s\S]*?disabled=\{isLoading\}/);
  assert.match(chat, /option value="hybrid"/);
});

test('AC-5105 RRF is labeled as a ranking score, not cosine similarity', () => {
  const source = { chunk_text: 'text', filename: 'paper.pdf', score: .016, metadata: {} };
  assert.equal(retrievalScoreLabel(source), '相似度');
  assert.equal(retrievalScoreLabel({ ...source, retrieval_mode: 'hybrid', dense_score: null }), '融合排序分数');
  assert.equal(retrievalScoreLabel({ ...source, query_rrf_score: .03 }), '多查询排序分数');
  assert.equal(retrievalScoreLabel({ ...source, retrieval_mode: 'hybrid', rerank_score: .7 }), '重排序分数');
});
