"""Offline, additive audit; never rewrites the frozen run or changes its gates."""
import hashlib
import json
from pathlib import Path
import statistics

from run_multipaper_journey import CASES, OUT, ROOT, read


def build_audit():
    ingestion = read('ingestion.json')
    files = {r['paper']: r['file_id'] for r in ingestion['rows']}
    details = {files[k]: {c['chunk_id']: c for c in read(f'details-{k}.json')['chunks']}
               for k in files}
    rows = []
    for cid, targets, query, expected, answerable in CASES:
        raw = read(f'answer-{cid}.json')
        response = raw.get('response', {})
        checks = raw.get('checks', {})
        allowed = {files[t] for t in targets}
        sources = response.get('sources') or []
        provenance = []
        outside = []
        cited = []
        for s in sources:
            meta = s.get('metadata') or {}
            chunk = details.get(s.get('file_id'), {}).get(meta.get('chunk_id'))
            provenance.append(bool(chunk and chunk['retrieval_text'] == s['chunk_text']
                                   and chunk['page_start'] == meta.get('page_start')
                                   and chunk['page_end'] == meta.get('page_end')))
            brief = {k: s.get(k) for k in ('source_id', 'file_id', 'filename')}
            brief.update(page_start=meta.get('page_start'), page_end=meta.get('page_end'),
                         chunk_id=meta.get('chunk_id'))
            if s.get('file_id') not in allowed:
                outside.append(brief)
            if s.get('source_id') in checks.get('cited_ids', []):
                cited.append(brief)
        rows.append(dict(id=cid, query=query, expected=expected, answerable=answerable,
                         answer=response.get('answer'), success=response.get('success', False),
                         seconds=raw['seconds'], frozen_checks=checks,
                         source_provenance=provenance, out_of_scope_candidates=outside,
                         cited_sources=cited,
                         retrieval_trace=response.get('metadata', {}).get('retrieval_trace')))
    latencies = [r['seconds'] for r in rows]
    before = read('collections-before.json')
    after = read('collections-after.json')
    # Preserve response shape as evidence without guessing its schema here.
    manifest = read('manifest.json')
    changed = [name for name, sha in manifest['code_sha256'].items()
               if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != sha]
    return dict(
        scope='development acceptance; raw frozen gates retained; no semantic judge score',
        cases=rows, ingestion=ingestion,
        totals=dict(requests=len(rows), successful_responses=sum(r['success'] for r in rows),
                    frozen_contract_passes=sum(r['frozen_checks'].get('contract_passed', False) for r in rows),
                    answerable=sum(r['answerable'] for r in rows),
                    unanswerable=sum(not r['answerable'] for r in rows),
                    fixed_refusals=sum(r['frozen_checks'].get('fixed_refusal', False) for r in rows),
                    source_occurrences=sum(len(r['source_provenance']) for r in rows),
                    exact_provenance_occurrences=sum(sum(r['source_provenance']) for r in rows),
                    out_of_scope_occurrences=sum(len(r['out_of_scope_candidates']) for r in rows)),
        latency_seconds=dict(min=min(latencies), median=statistics.median(latencies),
                             mean=statistics.mean(latencies), max=max(latencies)),
        backend_files_changed_during_run=changed,
        collections_before=before, collections_after=after)


if __name__ == '__main__':
    audit = build_audit()
    with (OUT/'audit-summary.json').open('x', encoding='utf-8') as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: audit[k] for k in ('totals', 'latency_seconds', 'backend_files_changed_during_run')}, ensure_ascii=False, indent=2))
    for row in audit['cases']:
        if row['out_of_scope_candidates']:
            print(row['id'], json.dumps(row['out_of_scope_candidates'], ensure_ascii=False))
