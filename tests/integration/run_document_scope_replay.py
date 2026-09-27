"""One-shot dev replay of the frozen 16 multi-paper cases; no upload or retries."""
import hashlib
import json
from pathlib import Path
import time

from run_multipaper_journey import ROOT, OUT as BASELINE, api, check_response

OUT = ROOT / 'output/e2e-document-scope-v1'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(name, data):
    with (OUT / name).open('x', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frozen = read(BASELINE / 'manifest.json')
    ingestion = read(BASELINE / 'ingestion.json')
    files = {r['paper']: r['file_id'] for r in ingestion['rows']}
    details = {r['file_id']: {'pages': r['pages'], 'chunks': {
        c['chunk_id']: c for c in read(BASELINE / f"details-{r['paper']}.json")['chunks']}}
        for r in ingestion['rows']}
    mixed = read(BASELINE / 'collection-mixed.json')['collection_id']
    empty = read(BASELINE / 'collection-empty.json')['collection_id']
    inventory = api(8000, f'/knowledge_base/{mixed}/documents')
    assert {d['file_id'] for d in inventory['documents']} == set(files.values())
    assert inventory['total_chunks'] == ingestion['listed_chunks']
    config = api(8502, '/config/default')['config']['llm']
    settings = read(BASELINE / 'run-settings.json')
    assert config['model_name'] == settings['model']
    config.update(temperature=settings['temperature'], max_tokens=settings['max_tokens'])
    paths = [ROOT/'backend/chat/kb_chat.py', ROOT/'backend/chat/document_scope.py',
             ROOT/'backend/chat/answer_guard.py', ROOT/'backend/chat/multi_query_retrieval.py']
    baseline_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in BASELINE.glob('*.json')}
    save('manifest.json', dict(cases=frozen['cases'], model=settings,
        retrieval=frozen['retrieval'], index_reused=True, live_upload_retested=False,
        code_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        baseline_sha256=baseline_hashes, mixed=mixed, empty=empty, health=api(8502, '/health')))
    rows = []
    for cid, targets, query, expected, answerable in frozen['cases']:
        history = []
        if cid == 'H01':
            prior = read(OUT / 'answer-B02.json')
            history = [dict(role='user', content=prior['query']),
                       dict(role='assistant', content=prior['response']['answer'])]
        save(f'attempt-{cid}.json', dict(query=query, history=history, started=time.time()))
        start = time.monotonic()
        response = api(8502, '/chat', 'POST', timeout=240, json=dict(
            query=query, collection_name=empty if cid == 'E01' else mixed, llm_config=config,
            **frozen['retrieval'], stream=False, return_source=True, history=history))
        checks = check_response(response, details, {files[t] for t in targets}, answerable)
        save(f'answer-{cid}.json', dict(query=query, expected=expected, response=response,
            checks=checks, seconds=time.monotonic()-start))
        rows.append(dict(id=cid, answerable=answerable, **checks))
        print(cid, json.dumps(checks, ensure_ascii=False), flush=True)
    assert baseline_hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in BASELINE.glob('*.json')}
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == sha
               for name, sha in read(OUT/'manifest.json')['code_sha256'].items())
    save('summary.json', dict(rows=rows, contract_passes=sum(r['contract_passed'] for r in rows),
        answerable_target_coverage=sum(r['cross_paper_coverage'] is True for r in rows),
        unanswerable_refusals=sum(not r['answerable'] and r['fixed_refusal'] for r in rows),
        answerable_refusals=sum(r['answerable'] and r['fixed_refusal'] for r in rows),
        baseline_unchanged=True, code_unchanged=True))


if __name__ == '__main__':
    main()
