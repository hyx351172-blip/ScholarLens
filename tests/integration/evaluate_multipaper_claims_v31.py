"""Offline, write-once v3.1 packet. Live execution requires separate approval."""
import argparse
import asyncio
from collections import Counter
import copy
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.integration.evaluate_multipaper_claims import read, save_new, sha, verify_hashes
from tests.integration.anchored_claim_audit import judge_messages, local_decision, run_units
from tests.integration.subject_scope_audit import prepare_units
from tests.integration.isolated_claim_audit import summarize

PREVIOUS = ROOT/'output/e2e-claim-audit-v3'
OUT = ROOT/'output/e2e-claim-audit-v3-1'
EXPERIMENT = 'multipaper-claim-audit-v3.1'
PROTOCOL = dict(response_format={'type':'json_object'}, enable_thinking=False,
                temperature=0, max_tokens=1000, timeout_seconds=60, max_retries=0)
FREEZE_PATHS = (
    'tests/integration/evaluate_multipaper_claims_v31.py',
    'tests/integration/subject_scope_audit.py',
    'tests/test_subject_scope_audit.py',
    'tests/traceability/subject_scope_audit/coverage.py',
    'docs/specs/subject_scope_audit/acceptance.md',
)
MUTABLE_SUBJECT_FIELDS = {'subject_context', 'subject_status', 'detected_subject'}


def _validate_cases(cases):
    seen = set()
    for case in cases:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', case['id']) or case['id'] in seen:
            raise ValueError('unique safe case ID required')
        seen.add(case['id'])


def prepare(out=OUT, previous=PREVIOUS):
    old_manifest = read(previous/'manifest.json')
    if old_manifest.get('experiment') != 'multipaper-claim-audit-v3':
        raise ValueError('frozen v3 predecessor required')
    verify_hashes(ROOT, old_manifest['file_sha256'])
    old_cases = read(previous/'inputs.json')
    _validate_cases(old_cases)
    cases, notes, deltas = [], [], []
    before_counts, after_counts, rules = Counter(), Counter(), Counter()
    anchor_count = forced_count = 0
    for old in old_cases:
        case = copy.deepcopy(old)
        case['units'] = prepare_units(case['answer'], old['units'])
        if len(case['units']) != len(old['units']):
            raise ValueError('claim denominator changed')
        for before, unit in zip(old['units'], case['units']):
            if any(before[k] != unit[k] for k in before if k not in MUTABLE_SUBJECT_FIELDS):
                raise ValueError('non-subject v3 data changed')
            # Validation also enforces anchor provenance and source ownership.
            changed = judge_messages(case['query'], before) != judge_messages(case['query'], unit)
            before_counts[before['subject_status']] += 1
            after_counts[unit['subject_status']] += 1
            anchor_count += len(unit['anchors'])
            forced_count += sum(a['forced_split'] for a in unit['anchors'])
            note = dict(case_id=case['id'], unit_id=unit['id'], text=unit['text'],
                start=unit['start'], end=unit['end'], citation_ids=unit['citation_ids'],
                previous_status=before['subject_status'], previous_context=before['subject_context'],
                subject_status=unit['subject_status'], subject_context=unit['subject_context'],
                subject_resolution=unit['subject_resolution'], request_changed=changed)
            notes.append(note)
            if changed:
                deltas.append(note)
                rules[unit['subject_resolution']['rule']] += 1
        cases.append(case)
    needed = sum(local_decision(u) is None for c in cases for u in c['units'])
    files = {ROOT/name for name in old_manifest['file_sha256']}
    files.update(previous.glob('*.json')); files.update(previous.glob('*.md'))
    files.update(ROOT/name for name in FREEZE_PATHS)
    snapshot = {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)}
    stats = dict(total_cases=len(cases), total_units=sum(len(c['units']) for c in cases),
        fixed_refusals=sum(c['fixed_refusal'] for c in cases),
        previous_subject_status_counts=dict(before_counts), subject_status_counts=dict(after_counts),
        changed_requests=len(deltas), changed_rule_counts=dict(rules),
        anchor_occurrences=anchor_count, forced_split_occurrences=forced_count,
        planned_provider_requests=needed, actual_provider_requests=0,
        unit_denominator_unchanged=True, semantic_scores_available=False,
        note='Development preprocessing diagnostics, NOT semantic accuracy or human Gold.')
    # All validations above are offline; never load model configuration here.
    out.mkdir(exist_ok=False)
    save_new(out/'inputs.json', cases)
    save_new(out/'preparation.json', stats)
    save_new(out/'subject-deltas.json', dict(status='AI_DRAFT_NOT_HUMAN_GOLD', items=deltas))
    save_new(out/'subject-review.json', dict(status='PENDING_NOT_GOLD', items=[dict(
        **n, subject_approved=None, semantic_verdict=None, reviewer='', notes='') for n in notes]))
    for case in cases:
        lines = [f"# {case['id']} — v3.1 anchored review", '', case['query'], '',
                 'Preparation only. Hints are not evidence. Human decisions remain pending.', '']
        for unit in case['units']:
            lines += [f"## {unit['id']}", '', unit['text'], '',
                f"Answer span: {unit['start']}:{unit['end']}; citations: {', '.join(unit['citation_ids'])}",
                f"Subject: {unit['subject_status']}; hint: {json.dumps(unit['subject_context'], ensure_ascii=False)}",
                f"Resolution: {json.dumps(unit['subject_resolution'], ensure_ascii=False)}", '']
            sources = {s['source_id']:s for s in unit['evidence']}
            for anchor in unit['anchors']:
                source = sources[anchor['source_id']]; meta = source.get('metadata') or {}
                lines += [f"### {anchor['anchor_id']} · {source.get('filename')} · pages {meta.get('page_start')}-{meta.get('page_end')}",
                    f"Source offsets: {anchor['start']}:{anchor['end']}; forced split: {anchor['forced_split']}",
                    '', anchor['text'], '']
        with (out/f"evidence-{case['id']}.md").open('x',encoding='utf-8') as handle:
            handle.write('\n'.join(lines)+'\n')
    # Freeze review drafts too: later human decisions belong in a separate file.
    snapshot.update({p.relative_to(ROOT).as_posix():sha(p) for p in sorted(out.iterdir()) if p.is_file()})
    manifest = dict(experiment=EXPERIMENT, split='development', stage='prepared_only',
        previous_experiment='multipaper-claim-audit-v3', file_sha256=snapshot,
        planned_provider_requests=needed, **PROTOCOL,
        policy='fresh approval required; no retries, baseline relabeling or fabricated human decisions')
    save_new(out/'manifest.json', manifest)
    verify_hashes(ROOT, snapshot)
    return stats


async def run(max_calls, out=OUT):
    manifest = read(out/'manifest.json')
    if (manifest.get('experiment') != EXPERIMENT or manifest.get('stage') != 'prepared_only'
            or any(manifest.get(k) != v for k, v in PROTOCOL.items())):
        raise ValueError('frozen experiment/protocol mismatch')
    verify = lambda: verify_hashes(ROOT, manifest['file_sha256'])
    verify()
    cases = read(out/'inputs.json')
    _validate_cases(cases)
    needed = sum(local_decision(u) is None for c in cases for u in c['units'])
    if (type(max_calls) is not int or type(manifest['planned_provider_requests']) is not int
            or max_calls != needed or max_calls != manifest['planned_provider_requests']):
        raise ValueError('fresh explicit budget must equal frozen packet call count')
    if (out/'summary.json').exists():
        raise FileExistsError('completed run cannot be overwritten')
    from openai import AsyncOpenAI
    from tests.integration.run_multipaper_journey import api
    config = api(8502, '/config/default')['config']['llm']
    settings = dict(model=config['model_name'], max_calls=max_calls, **PROTOCOL,
        judge='AI_DEVELOPMENT_NOT_HUMAN_GOLD', experiment=EXPERIMENT)
    settings_path = out/'run-settings.json'
    if settings_path.exists():
        if read(settings_path) != settings:
            raise ValueError('run settings changed')
    else:
        save_new(settings_path, settings)
    async with AsyncOpenAI(api_key=config['api_key'], base_url=config['api_url'],
                           max_retries=0, timeout=60) as client:
        results = await run_units(client, config['model_name'], cases, out, max_calls, verify)
    summary = summarize(cases, results)
    summary.update(experiment=EXPERIMENT, baseline_unchanged=True,
        usage={k:sum((r.get('usage') or {}).get(k, 0) or 0 for r in results.values())
               for k in ('prompt_tokens','completion_tokens','total_tokens')})
    save_new(out/'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('prepare','run'))
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    result = prepare() if args.stage == 'prepare' else asyncio.run(run(args.max_calls))
    print(json.dumps(result, ensure_ascii=False, indent=2))
