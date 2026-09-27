"""Offline preparation and separately authorized, write-once v3 live evaluation."""
import argparse
import asyncio
from collections import Counter
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.integration.evaluate_multipaper_claims import read, save_new, sha, verify_hashes
from tests.integration.anchored_claim_audit import prepare_units, judge_messages, local_decision, run_units
from tests.integration.isolated_claim_audit import summarize

V2 = ROOT/'output/e2e-claim-audit-v2-final'
OUT = ROOT/'output/e2e-claim-audit-v3'


def prepare(out=OUT, previous=V2):
    old_manifest = read(previous/'manifest.json')
    verify_hashes(ROOT, old_manifest['file_sha256'])
    old_cases = read(previous/'inputs.json')
    cases, counts, notes = [], Counter(), []
    anchor_count = forced_count = 0
    for old in old_cases:
        case = copy.deepcopy(old)
        case['units'] = prepare_units(case['answer'], old['units'])
        for before, unit in zip(old['units'], case['units']):
            if any(before[k] != unit[k] for k in before):
                raise ValueError('v2 unit changed')
            counts[unit['subject_status']] += 1
            anchor_count += len(unit['anchors'])
            forced_count += sum(a['forced_split'] for a in unit['anchors'])
            payload = json.loads(judge_messages(case['query'], unit)[1]['content'])
            if {a['source_id'] for a in payload['cited_anchors']} != {s['source_id'] for s in unit['evidence']}:
                raise ValueError('source ownership changed')
            notes.append(dict(case_id=case['id'], unit_id=unit['id'],
                subject_status=unit['subject_status'], subject_context=unit['subject_context']))
        cases.append(case)
    needed = sum(local_decision(u) is None for c in cases for u in c['units'])
    files = set(ROOT/name for name in old_manifest['file_sha256'])
    files.update(previous.glob('*.json')); files.update(previous.glob('*.md'))
    files.update((Path(__file__), ROOT/'tests/integration/anchored_claim_audit.py'))
    snapshot = {str(p.relative_to(ROOT)):sha(p) for p in sorted(files)}
    # No mkdir until all input/source/provenance checks have passed.
    out.mkdir(exist_ok=False)
    save_new(out/'inputs.json', cases)
    snapshot[str((out/'inputs.json').relative_to(ROOT))] = sha(out/'inputs.json')
    manifest = dict(experiment='multipaper-claim-audit-v3', split='development',
        stage='prepared_only', previous_experiment='multipaper-claim-audit-v2',
        file_sha256=snapshot, planned_provider_requests=needed,
        response_format={'type':'json_object'}, enable_thinking=False,
        max_tokens=1000, timeout_seconds=60, max_retries=0,
        policy='new approval required; isolated noun hints; exact anchors; no retries or baseline relabeling')
    save_new(out/'manifest.json', manifest)
    stats = dict(total_cases=len(cases), total_units=sum(len(c['units']) for c in cases),
        fixed_refusals=sum(c['fixed_refusal'] for c in cases), subject_status_counts=dict(counts),
        anchor_occurrences=anchor_count, forced_split_occurrences=forced_count,
        planned_provider_requests=needed, actual_provider_requests=0,
        unit_denominator_unchanged=True, semantic_scores_available=False,
        note='Subject hints are heuristic; anchor integrity is not semantic entailment.')
    save_new(out/'preparation.json', stats)
    save_new(out/'subject-review.json', dict(status='PENDING_NOT_GOLD', items=[dict(
        **n, subject_approved=None, reviewer='', notes='') for n in notes]))
    for case in cases:
        lines = [f"# {case['id']} — v3 anchored review", '', case['query'], '',
                 'Offline preparation only. Subject hints are not evidence; human review is pending.', '']
        for u in case['units']:
            lines += [f"## {u['id']}", '', u['text'], '',
                f"Answer span: {u['start']}:{u['end']}; citations: {', '.join(u['citation_ids'])}",
                f"Subject status: {u['subject_status']}; hint: {json.dumps(u['subject_context'], ensure_ascii=False)}", '']
            sources = {s['source_id']:s for s in u['evidence']}
            for a in u['anchors']:
                source = sources[a['source_id']]; meta=source.get('metadata') or {}
                lines += [f"### {a['anchor_id']} · {source.get('filename')} · pages {meta.get('page_start')}-{meta.get('page_end')}",
                    f"Source offsets: {a['start']}:{a['end']}; forced split: {a['forced_split']}", '',
                    a['text'], '']
        with (out/f"evidence-{case['id']}.md").open('x', encoding='utf-8') as handle:
            handle.write('\n'.join(lines)+'\n')
    verify_hashes(ROOT, snapshot)
    return stats


async def run(max_calls):
    # Do not read any API configuration until budget and frozen data pass.
    manifest = read(OUT/'manifest.json')
    verify = lambda: verify_hashes(ROOT, manifest['file_sha256'])
    verify()
    if type(max_calls) is not int or max_calls != manifest['planned_provider_requests']:
        raise ValueError('fresh explicit budget must equal prepared call count')
    if (OUT/'summary.json').exists():
        raise FileExistsError('completed run cannot be overwritten')
    from openai import AsyncOpenAI
    from tests.integration.run_multipaper_journey import api
    config = api(8502, '/config/default')['config']['llm']
    settings = dict(model=config['model_name'], max_calls=max_calls, temperature=0,
        response_format=manifest['response_format'], enable_thinking=False, max_tokens=1000,
        max_retries=0, timeout_seconds=60, judge='AI_DEVELOPMENT_NOT_HUMAN_GOLD')
    settings_path = OUT/'run-settings.json'
    if settings_path.exists():
        if read(settings_path) != settings:
            raise ValueError('run settings changed')
    else:
        save_new(settings_path, settings)
    cases = read(OUT/'inputs.json')
    async with AsyncOpenAI(api_key=config['api_key'], base_url=config['api_url'],
                           max_retries=0, timeout=60) as client:
        results = await run_units(client, config['model_name'], cases, OUT, max_calls, verify)
    summary = summarize(cases, results)
    summary.update(experiment='multipaper-claim-audit-v3', baseline_unchanged=True,
        usage={k:sum((r.get('usage') or {}).get(k, 0) or 0 for r in results.values())
               for k in ('prompt_tokens','completion_tokens','total_tokens')})
    save_new(OUT/'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('prepare','run'))
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    result = prepare() if args.stage == 'prepare' else asyncio.run(run(args.max_calls))
    print(json.dumps(result, ensure_ascii=False, indent=2))
