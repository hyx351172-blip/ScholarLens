export interface CitationMetadata {
  chunk_id?: string;
  file_id?: string;
  page_start?: number;
  page_end?: number;
  pages?: number[];
  section_path?: string[];
  headers?: string[];
  [key: string]: unknown;
}

export interface CitationSource {
  source_id?: string;
  file_id?: string;
  chunk_text: string;
  filename: string;
  score: number;
  retrieval_score?: number;
  rerank_score?: number;
  query_rrf_score?: number;
  matched_query_ids?: string[];
  query_ranks?: Record<string, number>;
  metadata: CitationMetadata;
}

const CITATION_MARKER = /\[(S\d+)\]/gi;
const UNLINKED_CITATION_MARKER = /\[(S\d+)\](?!\()/gi;
const EVIDENCE_HREF = /^#evidence-(S\d+)$/i;

export function sourceIdFor(source: CitationSource, index: number): string {
  const explicitId = source.source_id?.trim().toUpperCase();
  return explicitId && /^S\d+$/.test(explicitId) ? explicitId : `S${index + 1}`;
}

export function buildSourceMap(sources: CitationSource[] = []): Map<string, CitationSource> {
  return new Map(sources.map((source, index) => [sourceIdFor(source, index), source]));
}

export function collectCitationIds(markdown: string): string[] {
  const seen = new Set<string>();
  for (const match of markdown.matchAll(CITATION_MARKER)) {
    seen.add(match[1].toUpperCase());
  }
  return [...seen];
}

export function partitionSources(markdown: string, sources: CitationSource[] = []) {
  const sourceMap = buildSourceMap(sources);
  const ids = new Set(collectCitationIds(markdown));
  return {
    cited: [...sourceMap].filter(([id]) => ids.has(id)),
    uncited: [...sourceMap].filter(([id]) => !ids.has(id)),
    unknown: [...ids].filter((id) => !sourceMap.has(id)),
  };
}

export function linkifyCitationMarkers(markdown: string): string {
  return markdown.replace(
    UNLINKED_CITATION_MARKER,
    (_marker, sourceId: string) => `[${sourceId.toUpperCase()}](#evidence-${sourceId.toUpperCase()})`,
  );
}

export function sourceIdFromEvidenceHref(href?: string): string | null {
  if (!href) return null;
  return EVIDENCE_HREF.exec(href)?.[1].toUpperCase() ?? null;
}

export function getSourceFileId(source: CitationSource): string | undefined {
  const fileId = source.file_id ?? source.metadata.file_id;
  return typeof fileId === 'string' && fileId.trim() ? fileId.trim() : undefined;
}

export function getSourceChunkId(source: CitationSource): string | undefined {
  const chunkId = source.metadata.chunk_id;
  return typeof chunkId === 'string' && chunkId.trim() ? chunkId.trim() : undefined;
}

export function getSourceSectionPath(source: CitationSource): string[] {
  const path = source.metadata.section_path ?? source.metadata.headers;
  if (!Array.isArray(path)) return [];
  return path.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
}

export function getSourcePageRange(source: CitationSource): { start: number; end: number } | null {
  const start = source.metadata.page_start;
  const end = source.metadata.page_end ?? start;
  if (typeof start !== 'number' || typeof end !== 'number') return null;
  return { start, end };
}

export function formatEvidenceLocation(source: CitationSource): string {
  const pageRange = getSourcePageRange(source);
  const sectionPath = getSourceSectionPath(source);
  const parts: string[] = [];

  if (pageRange) {
    parts.push(
      pageRange.start === pageRange.end
        ? `第 ${pageRange.start} 页`
        : `第 ${pageRange.start}–${pageRange.end} 页`,
    );
  }
  if (sectionPath.length) parts.push(sectionPath.join(' › '));

  return parts.join(' · ') || '位置元数据暂缺';
}
