import ReactMarkdown from 'react-markdown';

import {
  buildSourceMap,
  linkifyCitationMarkers,
  sourceIdFromEvidenceHref,
  type CitationSource,
} from '../src/citations';

interface CitationMarkdownProps {
  content: string;
  sources?: CitationSource[];
  onSelectSource: (sourceId: string, source?: CitationSource) => void;
}

export function CitationMarkdown({ content, sources = [], onSelectSource }: CitationMarkdownProps) {
  const sourceMap = buildSourceMap(sources);

  return (
    <ReactMarkdown
      components={{
        h1: ({ node: _node, ...props }) => <h1 className="mb-3 text-xl font-semibold text-slate-950" {...props} />,
        h2: ({ node: _node, ...props }) => <h2 className="mb-2 mt-5 text-lg font-semibold text-slate-950" {...props} />,
        h3: ({ node: _node, ...props }) => <h3 className="mb-2 mt-4 font-semibold text-slate-900" {...props} />,
        p: ({ node: _node, ...props }) => <p className="mb-3 leading-7 text-slate-700 last:mb-0" {...props} />,
        ul: ({ node: _node, ...props }) => <ul className="mb-3 list-disc space-y-1.5 pl-5 text-slate-700" {...props} />,
        ol: ({ node: _node, ...props }) => <ol className="mb-3 list-decimal space-y-1.5 pl-5 text-slate-700" {...props} />,
        li: ({ node: _node, ...props }) => <li className="pl-1 leading-7" {...props} />,
        strong: ({ node: _node, ...props }) => <strong className="font-semibold text-slate-950" {...props} />,
        em: ({ node: _node, ...props }) => <em className="text-violet-700" {...props} />,
        code: ({ node: _node, ...props }) => <code className="rounded bg-violet-50 px-1.5 py-0.5 text-sm text-violet-800" {...props} />,
        pre: ({ node: _node, ...props }) => <pre className="my-3 overflow-x-auto rounded-xl bg-slate-950 p-4 text-slate-100" {...props} />,
        blockquote: ({ node: _node, ...props }) => <blockquote className="my-3 border-l-2 border-violet-300 bg-violet-50/70 py-2 pl-4 text-slate-600" {...props} />,
        table: ({ node: _node, ...props }) => <table className="my-4 w-full overflow-hidden rounded-xl border border-slate-200 text-sm" {...props} />,
        th: ({ node: _node, ...props }) => <th className="border border-slate-200 bg-slate-50 px-3 py-2 text-left font-semibold text-slate-800" {...props} />,
        td: ({ node: _node, ...props }) => <td className="border border-slate-200 px-3 py-2 text-slate-700" {...props} />,
        hr: ({ node: _node, ...props }) => <hr className="my-5 border-slate-200" {...props} />,
        a: ({ node: _node, href, children, ...props }) => {
          const sourceId = sourceIdFromEvidenceHref(href);
          if (sourceId) {
            const source = sourceMap.get(sourceId);
            return (
              <button
                type="button"
                onClick={() => onSelectSource(sourceId, source)}
                className={source
                  ? 'mx-0.5 inline-flex translate-y-[-1px] items-center rounded-md border border-violet-200 bg-violet-50 px-1.5 py-0.5 text-xs font-semibold text-violet-700 transition hover:border-violet-400 hover:bg-violet-100 focus:outline-none focus:ring-2 focus:ring-violet-300'
                  : 'mx-0.5 inline-flex translate-y-[-1px] items-center rounded-md border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-xs font-semibold text-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-300'}
                aria-label={source ? `查看来源 ${sourceId}` : `来源 ${sourceId} 不可用`}
                title={source ? `${source.filename} · 查看证据` : '回答引用了未返回的来源'}
              >
                {children}
              </button>
            );
          }
          return <a href={href} target="_blank" rel="noreferrer" className="text-violet-700 underline decoration-violet-300 underline-offset-2" {...props}>{children}</a>;
        },
      }}
    >
      {linkifyCitationMarkers(content)}
    </ReactMarkdown>
  );
}
