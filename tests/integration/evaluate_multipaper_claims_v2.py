"""Write-once v2 packet and explicitly budgeted, isolated live judging.

prepare performs no network requests. run consumes provider tokens and requires
a fresh user-approved request budget; it never retries or overwrites v1 results.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.integration.evaluate_multipaper_claims import build_case, read, save_new, sha, verify_hashes
from tests.integration.isolated_claim_audit import split_claims, judge_messages, local_decision, run_units, summarize
from tests.integration.run_multipaper_journey import api

BASE = ROOT/'output/e2e-document-scope-v1'
V1 = ROOT/'output/e2e-claim-audit-v1'
OUT = ROOT/'output/e2e-claim-audit-v2-final'


def prepare():
    frozen = read(BASE/'manifest.json')
    old_inputs = {c['id']: c for c in read(V1/'inputs.json')}
    cases = []
    for cid, _, query, _, answerable in frozen['cases']:
        record = read(BASE/f'answer-{cid}.json')
        case = build_case(cid, record, answerable, query)
        case['units'] = [] if case['fixed_refusal'] else split_claims(
            case['answer'], record['response']['sources'])
        if not case['fixed_refusal'] and not case['units']:
            raise ValueError('No units from substantive answer')
        for unit in case['units']:
            assert case['answer'][unit['start']:unit['end']] == unit['text']
            unit['parent_v1_ids'] = [u['id'] for u in old_inputs[cid]['units'] if unit['text'] in u['claim']]
            # Structural check: serialized API data has exactly one claim and
            # only the ID-addressed evidence for this unit, never the answer.
            payload = json.loads(judge_messages(query, unit)[1]['content'])
            assert set(payload) == {'question', 'claim_id', 'claim', 'cited_evidence'}
            assert {s['source_id'] for s in payload['cited_evidence']} <= set(unit['citation_ids'])
        cases.append(case)
    needed = sum(local_decision(u) is None for c in cases for u in c['units'])
    paths = [BASE/'manifest.json', *BASE.glob('answer-*.json'), *V1.glob('*.json'), *V1.glob('*.md'),
             Path(__file__), ROOT/'tests/integration/isolated_claim_audit.py',
             ROOT/'tests/integration/evaluate_multipaper_claims.py', ROOT/'scripts/evaluate_answer_citations.py']
    OUT.mkdir(exist_ok=False)
    save_new(OUT/'inputs.json', cases)
    paths.append(OUT/'inputs.json')
    manifest = dict(experiment='multipaper-claim-audit-v2', split='development',
        prepared_only=True, planned_provider_requests=needed,
        file_sha256={str(p.relative_to(ROOT)): sha(p) for p in paths},
        response_format={'type': 'json_object'}, enable_thinking=False,
        max_tokens_per_call=1000, timeout_seconds=60, max_retries=0,
        policy='one isolated claim per request; no retries, plain-text fallback, regeneration, or v1 relabeling')
    save_new(OUT/'manifest.json', manifest)
    comparison = dict(v1_units=sum(len(c['units']) for c in old_inputs.values()),
        v2_units=sum(len(c['units']) for c in cases), planned_provider_requests=needed,
        local_no_evidence_units=sum(local_decision(u) is not None for c in cases for u in c['units']),
        context_dependent_units=sum('context_dependent' in u['warnings'] for c in cases for u in c['units']),
        potentially_composite_units=sum('may_remain_composite' in u['warnings'] for c in cases for u in c['units']),
        note='Changed segmentation denominator is not an answer-quality improvement. No live results yet.',
        cases=[dict(id=c['id'], v1_units=len(old_inputs[c['id']]['units']), v2_units=len(c['units'])) for c in cases])
    save_new(OUT/'segmentation.json', comparison)
    save_new(OUT/'human-review.json', dict(status='PENDING_NOT_GOLD', cases=[dict(id=c['id'],
        units=[dict(id=u['id'], boundary_approved=None, citation_binding_approved=None,
                    verdict=None, reviewer='', notes='') for u in c['units']]) for c in cases]))
    for case in cases:
        lines = [f"# {case['id']} - isolated clauses", '', case['query'], '',
                 'Extractive heuristic, not certified atomic. Human review is pending.', '']
        for unit in case['units']:
            lines += [f"## {unit['id']} (v1: {','.join(unit['parent_v1_ids']) or 'newly retained'})", '', unit['text'], '',
                f"Offsets: {unit['start']}:{unit['end']}; binding: {unit['binding']}; citation span: {unit['citation_span']}",
                f"Warnings: {', '.join(unit['warnings']) or 'none'}", '']
            for source in unit['evidence']:
                meta = source.get('metadata') or {}
                lines += [f"### {source['source_id']} {source.get('filename')} ({meta.get('page_start')}-{meta.get('page_end')})", '',
                          f"Chunk: {meta.get('chunk_id')}", '', source['chunk_text'], '']
        with (OUT/f"evidence-{case['id']}.md").open('x', encoding='utf-8') as handle:
            handle.write('\n'.join(lines)+'\n')
    verify_hashes(ROOT, manifest['file_sha256'])
    print(json.dumps(comparison, ensure_ascii=False, indent=2))


async def run(max_calls):
    from openai import AsyncOpenAI
    manifest = read(OUT/'manifest.json')
    verify = lambda: verify_hashes(ROOT, manifest['file_sha256'])
    verify()
    if max_calls is None or max_calls < manifest['planned_provider_requests']:
        raise ValueError('A freshly authorized --max-calls budget covering the packet is required')
    if (OUT/'summary.json').exists():
        raise FileExistsError('Completed run cannot be overwritten')
    config = api(8502, '/config/default')['config']['llm']
    settings = dict(model=config['model_name'], max_calls=max_calls, temperature=0,
        response_format=manifest['response_format'], enable_thinking=False, max_tokens=1000,
        max_retries=0, timeout_seconds=60, judge='AI_DEVELOPMENT_NOT_HUMAN_GOLD')
    settings_path = OUT/'run-settings.json'
    if settings_path.exists():
        if read(settings_path) != settings: raise ValueError('Run settings changed')
    else:
        save_new(settings_path, settings)
    cases = read(OUT/'inputs.json')
    async with AsyncOpenAI(api_key=config['api_key'], base_url=config['api_url'],
                           max_retries=0, timeout=60) as client:
        results = await run_units(client, config['model_name'], cases, OUT, max_calls, verify)
    report = summarize(cases, results)
    report['usage'] = {key: sum((r.get('usage') or {}).get(key, 0) or 0 for r in results.values())
                       for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
    report['baseline_unchanged'] = True
    save_new(OUT/'summary.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'run'])
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    if args.stage == 'prepare': prepare()
    else: asyncio.run(run(args.max_calls))
