"""Explicit live regression: existing KB, four generations, no document writes.

Run manually; never executed by unittest discovery. Credentials stay in memory.
"""
import json
from pathlib import Path
import time

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/answer-guard-live-v1'


def main():
    session = requests.Session()
    session.trust_env = False
    for port in (8000, 8501):
        session.get(f'http://127.0.0.1:{port}/health', timeout=10).raise_for_status()
    collection = json.loads((ROOT / 'output/e2e-v1/collection.json').read_text(encoding='utf-8'))['collection_id']
    listing = session.get(f'http://127.0.0.1:8000/knowledge_base/{collection}/documents', timeout=30)
    listing.raise_for_status()
    assert listing.json().get('total_chunks', 0) > 0, 'Existing test KB must contain chunks'
    config_response = session.get('http://127.0.0.1:8501/config/default', timeout=10)
    config_response.raise_for_status()
    config = config_response.json()['config']['llm']
    config.update(temperature=0, max_tokens=1000)
    for case in ('conclusion', 'unanswerable'):
        previous = json.loads((ROOT / f'output/e2e-v1/answer-{case}.json').read_text(encoding='utf-8'))
        for streaming in (False, True):
            target = OUT / f'{case}-{"stream" if streaming else "json"}.json'
            if target.exists():
                print(target.name, 'already saved; no duplicate API call', flush=True)
                continue
            started = time.monotonic()
            response = session.post('http://127.0.0.1:8501/chat', timeout=180, stream=streaming, json={
                'query': previous['query'], 'collection_name': collection, 'llm_config': config,
                'top_k': 10, 'score_threshold': .1, 'use_multi_query': True,
                'use_reranker': False, 'stream': streaming, 'return_source': True,
            })
            response.raise_for_status()
            if streaming:
                response.encoding = 'utf-8'
                events = [json.loads(line) for line in response.iter_lines(decode_unicode=True) if line]
                assert not any(event['type'] == 'error' for event in events), 'Stream error'
                result = {'answer': ''.join(e['data'] for e in events if e['type'] == 'content'),
                          'metadata': next(e['data'] for e in events if e['type'] == 'metadata'),
                          'sources': next((e['data'] for e in events if e['type'] == 'sources'), [])}
            else:
                result = response.json()
            assert 'answer_guard' in result['metadata'], 'Running service has not loaded output guard'
            saved = {'case': case, 'stream': streaming, 'seconds': time.monotonic() - started, 'response': result}
            target.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(target.name, result['metadata']['answer_guard'], round(saved['seconds'], 2), result['answer'], flush=True)


if __name__ == '__main__':
    main()
