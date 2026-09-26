import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import {
  buildSourceMap,
  partitionSources,
  collectCitationIds,
  formatEvidenceLocation,
  linkifyCitationMarkers,
  sourceIdFromEvidenceHref,
  type CitationSource,
} from './citations.ts';

const sources: CitationSource[] = [
  {
    source_id: 'S1',
    file_id: 'file-paper-a',
    filename: 'paper-a.pdf',
    chunk_text: 'Grounded evidence.',
    score: 0.91,
    metadata: {
      chunk_id: 'paper-a:chunk_0001',
      page_start: 3,
      page_end: 4,
      section_path: ['Methods', 'Training'],
    },
  },
];

test('AC-2301 partitions cited evidence without renumbering or duplicates', () => {
  const candidates = [...sources, { ...sources[0], source_id: undefined }];
  const result = partitionSources('Claim [S2][S2][S99]', candidates);
  assert.deepEqual(result.cited.map(([id]) => id), ['S2']);
  assert.deepEqual(result.uncited.map(([id]) => id), ['S1']);
  assert.deepEqual(result.unknown, ['S99']);
});

test('AC-2302 abstention has zero citations even with ten candidates', () => {
  const candidates = Array.from({ length: 10 }, (_, i) => ({ ...sources[0], source_id: `S${i + 1}` }));
  const result = partitionSources('当前检索证据不足。', candidates);
  assert.equal(result.cited.length, 0);
  assert.equal(result.uncited.length, 10);
  assert.equal(partitionSources('[S1]').cited.length, 0);
});

test('AC-2303 waiting status and separated source component are wired into chat', () => {
  const chat = readFileSync(new URL('../components/Chat.tsx', import.meta.url), 'utf8');
  const panel = readFileSync(new URL('../components/AnswerSources.tsx', import.meta.url), 'utf8');
  assert.match(chat, /role="status" aria-live="polite"/);
  assert.match(chat, /正在检索证据并生成、检查回答，请稍候/);
  assert.match(chat, /<AnswerSources content=\{item.content\} sources=\{item.sources\}/);
  assert.match(panel, /\{cited.length\} 个片段/);
  assert.match(panel, /检索候选（未引用）/);
  assert.doesNotMatch(panel, /<details[^>]*\bopen\b/);
});

test('AC-301.1 linkifies adjacent citation markers without rewriting existing links', () => {
  const markdown = 'Claim [S1][S2]. Existing [S3](#evidence-S3).';

  assert.equal(
    linkifyCitationMarkers(markdown),
    'Claim [S1](#evidence-S1)[S2](#evidence-S2). Existing [S3](#evidence-S3).',
  );
  assert.deepEqual(collectCitationIds(markdown), ['S1', 'S2', 'S3']);
});

test('AC-301.1 maps sources by stable API id and a deterministic fallback id', () => {
  const sourceMap = buildSourceMap([
    ...sources,
    { ...sources[0], source_id: undefined, filename: 'paper-b.pdf' },
  ]);

  assert.equal(sourceMap.get('S1')?.filename, 'paper-a.pdf');
  assert.equal(sourceMap.get('S2')?.filename, 'paper-b.pdf');
});

test('AC-301.2 formats page range and hierarchical section metadata', () => {
  assert.equal(formatEvidenceLocation(sources[0]), '第 3–4 页 · Methods › Training');
});

test('AC-301.3 preserves an unknown source id instead of falling back to another source', () => {
  const sourceMap = buildSourceMap(sources);

  assert.equal(sourceMap.get('S9'), undefined);
  assert.equal(sourceIdFromEvidenceHref('#evidence-S9'), 'S9');
  assert.equal(sourceIdFromEvidenceHref('https://example.com'), null);
});
