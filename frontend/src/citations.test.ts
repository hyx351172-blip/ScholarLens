import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildSourceMap,
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
