import { BookOpen, Copy, ExternalLink, FileText, Hash, MapPin, X } from 'lucide-react';
import { motion } from 'motion/react';
import { buttonStyles } from './ui/button';

import { config } from '../src/config';
import {
  formatEvidenceLocation,
  getSourceChunkId,
  getSourceFileId,
  getSourcePageRange,
  getSourceSectionPath,
  type CitationSource,
} from '../src/citations';

interface EvidenceDrawerProps {
  sourceId: string;
  source: CitationSource;
  onClose: () => void;
}

export function EvidenceDrawer({ sourceId, source, onClose }: EvidenceDrawerProps) {
  const chunkId = getSourceChunkId(source);
  const fileId = getSourceFileId(source);
  const pageRange = getSourcePageRange(source);
  const sectionPath = getSourceSectionPath(source);
  const pdfUrl = fileId
    ? `${config.milvusApiUrl}/document/${encodeURIComponent(fileId)}/pdf${pageRange ? `#page=${pageRange.start}` : ''}`
    : null;

  return (
    <motion.aside
      initial={{ opacity: 0, x: 28 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 28 }}
      transition={{ duration: 0.2 }}
      className="absolute inset-y-0 right-0 z-30 flex w-full max-w-[400px] flex-col border-l border-slate-200 bg-white shadow-[-18px_0_50px_rgba(49,46,129,0.08)] lg:static lg:z-auto lg:shadow-none"
      aria-label={`来源 ${sourceId} 证据详情`}
    >
      <div className="flex items-start justify-between border-b border-slate-200 px-5 py-5">
        <div>
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-700">
            <BookOpen size={13} />
            证据 {sourceId}
          </div>
          <h3 className="line-clamp-2 font-semibold leading-6 text-slate-950">{source.filename}</h3>
        </div>
        <button
          type="button"
          onClick={onClose}
          className={buttonStyles({ variant: 'ghost', size: 'sm', iconOnly: true, className: 'ml-3 text-slate-400' })}
          aria-label="关闭证据面板"
        >
          <X size={18} />
        </button>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
        <section className="rounded-2xl border border-violet-100 bg-gradient-to-br from-violet-50 to-white p-4">
          <div className="mb-3 flex items-start gap-3">
            <div className="rounded-xl bg-white p-2 text-violet-600 shadow-sm ring-1 ring-violet-100">
              <MapPin size={17} />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.14em] text-slate-400">文献位置</p>
              <p className="mt-1 text-sm font-medium leading-6 text-slate-800">{formatEvidenceLocation(source)}</p>
            </div>
          </div>
          {sectionPath.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {sectionPath.map((section, index) => (
                <span key={`${section}-${index}`} className="rounded-md border border-violet-100 bg-white px-2 py-1 text-xs text-slate-600">
                  {section}
                </span>
              ))}
            </div>
          )}
        </section>

        <section>
          <div className="mb-2 flex items-center justify-between">
            <h4 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <FileText size={16} className="text-violet-600" />
              检索原文
            </h4>
            <span className="rounded-full bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">
              相似度 {source.score.toFixed(3)}
            </span>
          </div>
          <div className="whitespace-pre-wrap rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm leading-7 text-slate-700">
            {source.chunk_text}
          </div>
        </section>

        {chunkId && (
          <section className="rounded-xl border border-slate-200 p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 text-xs font-medium text-slate-500"><Hash size={13} />Chunk ID</p>
                <p className="mt-1 truncate font-mono text-xs text-slate-700" title={chunkId}>{chunkId}</p>
              </div>
              <button
                type="button"
                onClick={() => navigator.clipboard?.writeText(chunkId)}
                className={buttonStyles({ variant: 'ghost', size: 'sm', iconOnly: true, className: 'text-slate-400' })}
                aria-label="复制 Chunk ID"
              >
                <Copy size={15} />
              </button>
            </div>
          </section>
        )}
      </div>

      <div className="border-t border-slate-200 p-4">
        {pdfUrl ? (
          <a
            href={pdfUrl}
            target="_blank"
            rel="noreferrer"
            className={buttonStyles({ variant: 'primary', size: 'lg', className: 'w-full' })}
          >
            打开原文 PDF
            <ExternalLink size={16} />
          </a>
        ) : (
          <p className="rounded-xl bg-slate-50 px-3 py-2.5 text-center text-xs leading-5 text-slate-500">
            当前历史来源没有 file_id，仍可核对上方精确检索原文。
          </p>
        )}
      </div>
    </motion.aside>
  );
}
