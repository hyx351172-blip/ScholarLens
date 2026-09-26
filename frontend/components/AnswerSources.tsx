import { partitionSources, type CitationSource } from '../src/citations';
import { buttonStyles } from './ui/button';

interface Props {
  content: string;
  sources?: CitationSource[];
  onSelectSource: (sourceId: string, source: CitationSource) => void;
}

export function AnswerSources({ content, sources, onSelectSource }: Props) {
  const { cited, uncited, unknown } = partitionSources(content, sources);
  if (!sources?.length && !unknown.length) return null;
  const chips = (entries: [string, CitationSource][]) => (
    <div className="flex flex-wrap gap-2">
      {entries.map(([id, source]) => (
        <button key={id} type="button" onClick={() => onSelectSource(id, source)}
          className={buttonStyles({ variant: 'quiet', size: 'sm', className: 'max-w-full px-2.5 text-left' })}
          title={`${source.filename} · 查看证据`}>
          <span className="rounded bg-white px-1.5 py-0.5 font-semibold text-violet-700 shadow-sm">{id}</span>
          <span className="max-w-[220px] truncate">{source.filename}</span>
        </button>
      ))}
    </div>
  );
  return (
    <div className="mt-5 border-t border-slate-100 pt-4">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-medium text-slate-500">本回答引用的证据</p>
        <span className="text-[11px] text-slate-400">{cited.length} 个片段</span>
      </div>
      {cited.length ? chips(cited) : <p className="text-xs text-slate-500">本回答未引用证据。</p>}
      {unknown.length > 0 && <p className="mt-2 text-xs text-amber-700">引用来源暂不可用：{unknown.join('、')}</p>}
      {uncited.length > 0 && (
        <details className="mt-3 text-xs text-slate-500">
          <summary className="cursor-pointer rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300">
            检索候选（未引用）：{uncited.length} 个片段
          </summary>
          <p className="my-2">以下内容仅为检索结果，不代表回答已引用或得到其支持。</p>
          {chips(uncited)}
        </details>
      )}
    </div>
  );
}
