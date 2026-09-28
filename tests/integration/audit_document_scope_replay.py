"""Audit the frozen replay after edge hardening; one empty-KB live smoke.

Does not regenerate the 16 answers or overwrite their run manifest. This records
scope equivalence only, not full behavioral equivalence of two code revisions.
"""
import hashlib
import json
import statistics
import sys

from run_document_scope_replay import BASELINE, OUT, ROOT, read
from run_multipaper_journey import api, check_response

sys.path.insert(0, str(ROOT))
from backend.chat.document_scope import resolve_document_scope


def save(name, data):
    with (OUT / name).open('x', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def main():
    assert not (OUT / 'final-postflight.json').exists(), 'Preserve previous audit'
    manifest = read(OUT / 'manifest.json')
    catalog = read(BASELINE / 'documents.json')['documents']
    ingestion = read(BASELINE / 'ingestion.json')
    files = {r['paper']: r['file_id'] for r in ingestion['rows']}
    details = {r['file_id']: {'pages': r['pages'], 'chunks': {
        c['chunk_id']: c for c in read(BASELINE / f"details-{r['paper']}.json")['chunks']}}
        for r in ingestion['rows']}
    rows, latencies, old_latencies = [], [], []
    for cid, targets, query, _, answerable in manifest['cases']:
        record = read(OUT / f'answer-{cid}.json')
        scope = resolve_document_scope(query, [] if cid == 'E01' else catalog).to_dict()
        prior = record['response']['metadata']['retrieval_trace']['document_scope']
        assert all(prior[k] == value for k, value in scope.items()), cid
        checks = check_response(record['response'], details, {files[t] for t in targets}, answerable)
        assert checks == record['checks'] and checks['contract_passed'], cid
        rows.append(dict(id=cid, scope_unchanged=True, **checks))
        latencies.append(record['seconds'])
        old_latencies.append(read(BASELINE / f'answer-{cid}.json')['seconds'])
    baseline_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in BASELINE.glob('*.json')}
    assert baseline_hashes == manifest['baseline_sha256']
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in manifest['code_sha256']}
    # Final service was restarted before this request. Disable the planner so
    # this checks catalog/scope/empty retrieval, not paid answer generation.
    config = api(8502, '/config/default')['config']['llm']
    smoke = api(8502, '/chat', 'POST', timeout=60, json=dict(
        query='根据这些论文总结方法。', collection_name=manifest['empty'],
        llm_config=config, top_k=10, score_threshold=.1, use_multi_query=False,
        use_reranker=False, stream=False, return_source=True, history=[]))
    save('smoke-final-collection-reference.json', smoke)
    smoke_checks = check_response(smoke, {}, set(), False)
    assert smoke_checks['contract_passed'] and smoke_checks['fixed_refusal']
    assert not smoke['sources']
    assert smoke['metadata']['retrieval_trace']['document_scope']['status'] == 'unrestricted'
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value
               for name, value in hashes.items())
    result = dict(
        scope_equivalence_passes=len(rows), saved_response_contract_passes=len(rows),
        source_occurrences=sum(r['source_count'] for r in rows),
        exact_source_joins=sum(sum(r['exact_source_joins']) for r in rows),
        cross_paper_passes=sum(r['cross_paper_coverage'] is True for r in rows if r['id'].startswith('X')),
        baseline_unchanged=True, final_code_sha256=hashes,
        edge_hardening_changed_files=[name for name in hashes if hashes[name] != manifest['code_sha256'][name]],
        live_smoke_passed=True, live_smoke_checks=smoke_checks,
        latency_seconds=dict(mean=statistics.mean(latencies), median=statistics.median(latencies),
                             min=min(latencies), max=max(latencies)),
        baseline_latency_seconds=dict(mean=statistics.mean(old_latencies), median=statistics.median(old_latencies)),
        caveat='16 live answers preceded final edge hardening; scope equivalence and one live smoke follow it. Not a second 16-case live replay.',
        rows=rows,
    )
    save('final-postflight.json', result)
    print(json.dumps({k: v for k, v in result.items() if k not in {'rows', 'final_code_sha256'}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
