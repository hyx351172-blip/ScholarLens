"""Freshly approved ten-call v3 diagnostic pilot. No old-response adapter."""
import argparse
import asyncio
from collections import Counter
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat import qualified_evidence_ids as v3
from tests.integration import prepare_qualified_evidence_ids as prep
from tests.integration import run_qualified_claim_support_live as baseline
from tests.integration.run_selected_claim_support_live import read, digest, verify, write, value_hash, make_client

BASE = prep.OUT
OUT = ROOT / 'output/qualified-ids-pilot-v3'
BASE_MANIFEST_SHA256 = '9365298cb07795cca0d4497bea3ca09549125ce076caa4dd6034c4364e02308e'
SELECTION = {
    'SCIFACT-SF-415-6309659': 'Previous ellipsis quotation failure; comparison/condition diagnostic.',
    'SCIFACT-SF-72-6076903': 'Previous whitespace quotation failure.',
    'SCIFACT-SF-525-13639330': 'Observed scope/condition over-rejection diagnostic.',
    'SCIFACT-SF-847-16787954': 'Previously accepted single-example frequency generalization.',
    'SCIFACT-SF-533-12991445': 'Previously supported control with multiple available anchors.',
    'SCIFACT-SF-873-1180972': 'Previously contradicted control.',
    'REGRESSION-B01-C001': 'BERT basic task control.',
    'REGRESSION-L01-C005': 'LoRA formula/operator and constant diagnostic.',
    'REGRESSION-L01-C006': 'LoRA parameter-name evidence gap diagnostic.',
    'REGRESSION-L01-C007': 'LoRA omitted training-condition diagnostic.',
}
KEYS = tuple(SELECTION)
PROTOCOL = dict(version='qualified_ids_pilot_v3', parser_version=v3.VERSION, max_calls=10,
                model='qwen3-vl-plus', temperature=0, max_tokens=1500, max_retries=0,
                sdk_timeout_seconds=60, total_call_seconds=60, sequential=True,
                stop_on_first_error=True, automatic_resume=False, repeats=1,
                gold_in_requests=False, rerun_old_versions=False, regenerate_answers=False,
                selection='targeted_diagnostic_not_random_or_held_out')
request_for = prep.request_for


def _selected():
    lookup = {e['key']: e for e in read(BASE / 'entries.json')}
    entries = [lookup[k] for k in KEYS]
    if Counter(e['group'] for e in entries) != {'scifact': 6, 'selected_claim_regression': 4}:
        raise ValueError('pilot_group_drift')
    return entries


def cohort():
    if digest(BASE / 'manifest.json') != BASE_MANIFEST_SHA256:
        raise ValueError('frozen_v3_manifest_drift')
    prep.verify_prepared()
    return _selected()


def prepare(out=OUT):
    out = Path(out)
    if out.exists():
        raise FileExistsError('pilot_already_exists')
    entries = cohort()
    frozen = dict(read(BASE / 'manifest.json')['source_sha256'])
    for path in BASE.glob('*.json'):
        frozen[path.relative_to(ROOT).as_posix()] = digest(path)
    for name in ('tests/integration/run_qualified_ids_pilot.py', 'tests/test_qualified_ids_pilot.py',
                 'docs/specs/qualified_ids_pilot/acceptance.md', 'tests/traceability/qualified_ids_pilot/coverage.py'):
        frozen[name] = digest(ROOT / name)
    verify(ROOT, frozen)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'entries.json', entries)
    write(out / 'labels.json', [r for r in read(BASE / 'labels.json') if r['key'] in KEYS])
    write(out / 'selection.json', SELECTION)
    for e in entries:
        request = read(BASE / f"request-{e['key']}.json")
        if request != request_for(e['packet']):
            raise ValueError('frozen_request_drift')
        write(out / f"request-{e['key']}.json", request)
    summary = dict(status='prepared_not_run', planned_calls=10, provider_calls=0,
                   groups=dict(Counter(e['group'] for e in entries)), maximum_completion_tokens=15000,
                   total_prompt_characters=sum(len(m['content']) for e in entries for m in request_for(e['packet'])['messages']))
    write(out / 'preparation.json', summary)
    write(out / 'manifest.json', dict(protocol=PROTOCOL, keys=list(KEYS), source_sha256=frozen,
          base_manifest_sha256=BASE_MANIFEST_SHA256,
          artifacts_sha256={p.name: digest(p) for p in out.glob('*.json')}))
    return summary


def preflight(out, approved, max_calls):
    if approved is not True or type(max_calls) is not int or max_calls != 10:
        raise ValueError('explicit_ten_call_approval_required')
    out = Path(out); manifest = read(out / 'manifest.json')
    if (manifest.get('protocol') != PROTOCOL or manifest.get('keys') != list(KEYS)
            or manifest.get('base_manifest_sha256') != BASE_MANIFEST_SHA256
            or digest(BASE / 'manifest.json') != BASE_MANIFEST_SHA256):
        raise ValueError('pilot_protocol_drift')
    verify(ROOT, manifest['source_sha256']); verify(out, manifest['artifacts_sha256'])
    entries = read(out / 'entries.json')
    if (entries != _selected() or read(out / 'selection.json') != SELECTION
            or read(out / 'labels.json') != [r for r in read(BASE / 'labels.json') if r['key'] in KEYS]):
        raise ValueError('pilot_input_drift')
    for e in entries:
        if read(out / f"request-{e['key']}.json") != request_for(e['packet']):
            raise ValueError('request_drift')
    attempts = {p.stem.removeprefix('attempt-') for p in out.glob('attempt-*.json')}
    results = {p.stem.removeprefix('result-') for p in out.glob('result-*.json')}
    if attempts != results or attempts != set(KEYS[:len(attempts)]):
        raise ValueError('orphan_or_out_of_order_no_resume')
    for key in attempts:
        a, r = read(out / f'attempt-{key}.json'), read(out / f'result-{key}.json')
        expected = value_hash(read(out / f'request-{key}.json'))
        if (a.get('key') != key or r.get('key') != key or a.get('request_sha256') != expected
                or r.get('request_sha256') != expected or a.get('max_output_tokens') != 1500
                or r.get('provider_calls') != 1 or r.get('parser_version') != v3.VERSION):
            raise ValueError('pilot_attempt_result_drift')
    return entries


async def judge(entry, request, provider):
    if request != request_for(entry['packet']):
        raise ValueError('request_drift')
    result = dict(key=entry['key'], group=entry['group'], original_key=entry['original_key'],
                  claim_id=entry['packet']['base_packet']['claim_id'], request_sha256=value_hash(request),
                  parser_version=v3.VERSION, status='error', decision=None, provider_calls=1,
                  raw_content=None, finish_reason=None, provider_refusal=False, usage=None)
    started, stage = time.monotonic(), 'provider'
    try:
        response = await asyncio.wait_for(provider(**request), timeout=PROTOCOL['total_call_seconds'])
        stage = 'response'
        choice = response.choices[0] if response.choices else None
        usage = response.usage.model_dump() if response.usage else {}
        result.update(raw_content=choice.message.content if choice else None,
                      finish_reason=choice.finish_reason if choice else None,
                      provider_refusal=bool(getattr(choice.message, 'refusal', None)) if choice else False,
                      usage={k: usage.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')})
        if result['finish_reason'] != 'stop' or result['provider_refusal']:
            raise ValueError('incomplete_or_refused')
        stage = 'contract'
        result['decision'] = v3.parse_decision(result['raw_content'], entry['packet'])
        result['status'] = 'ok'
    except Exception as exc:
        result.update(error_type=type(exc).__name__, error_stage=stage)
        status = getattr(exc, 'status_code', None)
        result['provider_status_code'] = status if type(status) is int else None
    result['seconds'] = round(time.monotonic() - started, 4)
    return result


def inspect_results(entries, results):
    if entries != _selected() or tuple(r.get('key') for r in results) != KEYS[:len(results)] or len(results) > 10:
        raise ValueError('invalid_pilot_results_or_cohort')
    lookup = {e['key']: e for e in entries}; decisions, outcomes = {}, dict.fromkeys(KEYS, 'MISSING')
    for r in results:
        key = r['key']; e = lookup[key]
        if (r.get('request_sha256') != value_hash(request_for(e['packet']))
                or r.get('group') != e['group'] or r.get('original_key') != e['original_key']
                or r.get('claim_id') != e['packet']['base_packet']['claim_id']
                or r.get('status') not in ('ok', 'error') or r.get('provider_calls') != 1
                or r.get('parser_version') != v3.VERSION):
            raise ValueError('pilot_result_identity_drift')
        outcomes[key] = 'ERROR'
        if r['status'] != 'ok' or r.get('finish_reason') != 'stop' or r.get('provider_refusal'):
            continue
        try:
            decisions[key] = v3.parse_decision(r.get('raw_content'), e['packet'])
        except ValueError:
            continue
        d = decisions[key]
        outcomes[key] = baseline.MAPPING.get((d['verdict'], d['reason_code']), 'UNCERTAIN')
    return decisions, outcomes


def summarize(entries, results):
    decisions, outcomes = inspect_results(entries, results)
    prior = baseline.old_decisions(entries)
    labels = {r['key']: r['gold_label'] for r in read(BASE / 'labels.json')}
    sci, reg, transitions = [], [], Counter()
    for e in entries:
        key = e['key']; before = prior[key]
        if e['group'] == 'scifact':
            if labels[key] not in baseline.LABELS:
                raise ValueError('invalid_pilot_label')
            old = baseline.MAPPING.get((before['verdict'], before['reason_code']), 'UNCERTAIN')
            sci.append(dict(key=key, gold=labels[key], v1=old, v3=outcomes[key], v3_correct=labels[key] == outcomes[key]))
        else:
            after = decisions[key]['verdict'] if key in decisions else outcomes[key]
            transitions[f"{before['verdict']} -> {after}"] += 1
            reg.append(dict(key=key, v1=before['verdict'], v3=after, gold_label=None, human_verdict=None))
    sci_counts = Counter(c['v3'] for c in sci); received = 6 - sci_counts['MISSING']
    fields = ('prompt_tokens', 'completion_tokens', 'total_tokens')
    measured = [r for r in results if all(type((r.get('usage') or {}).get(k)) is int and r['usage'][k] >= 0 for k in fields)]
    errors = sum(o == 'ERROR' for o in outcomes.values())
    return dict(experiment='qualified-ids-pilot-v3', status='stopped_error' if errors else 'completed' if len(results) == 10 else 'incomplete',
                planned_calls=10, provider_calls=len(results), valid_contracts=len(decisions), errors=errors,
                not_run=10-len(results), contract_valid_per_planned=len(decisions)/10 if results else None,
                scifact=dict(total=6, received=received, errors=sci_counts['ERROR'], missing=sci_counts['MISSING'],
                             uncertain=sci_counts['UNCERTAIN'], v3_correct=sum(c['v3_correct'] for c in sci),
                             v1_correct=sum(c['v1'] == c['gold'] for c in sci), cases=sci,
                             descriptive_accuracy_full_denominator=sum(c['v3_correct'] for c in sci)/6 if received else None),
                regression=dict(total=4, received=sum(c['v3'] != 'MISSING' for c in reg),
                                missing=sum(c['v3'] == 'MISSING' for c in reg), errors=sum(c['v3'] == 'ERROR' for c in reg),
                                transitions=dict(transitions), cases=reg, semantic_accuracy=None),
                model_verdict_counts=dict(Counter(d['verdict'] for d in decisions.values())),
                guard_counts=dict(Counter(c for d in decisions.values() for c in d['guard_codes'])),
                resolved_citations=sum(len(c['citations']) for d in decisions.values() for c in d['checks'].values()),
                finish_reason_counts=dict(Counter(r.get('finish_reason') or 'missing' for r in results)),
                error_stage_counts=dict(Counter(r.get('error_stage', 'reparse') for r in results if outcomes[r['key']] == 'ERROR')),
                usage_measured_calls=len(measured), usage_unknown_calls=len(results)-len(measured),
                measured_token_totals={k: sum(r['usage'][k] for r in measured) if measured else None for k in fields},
                latency_seconds=dict(mean=statistics.mean(r['seconds'] for r in results) if results else None,
                                     total=sum(r['seconds'] for r in results)),
                new_old_version_calls=0, pooled_accuracy=None, production_enabled=False, automatic_retry=False,
                historical_simulations_in_live_metrics=False,
                scope='Targeted 6+4 diagnostic pilot, not representative/held-out/full-52/official benchmark quality.')


def finish(out, entries, results):
    summary = summarize(entries, results); indexed = {r['key']: r for r in results}
    prior = baseline.old_decisions(entries); labels = {r['key']: r for r in read(out / 'labels.json')}
    cards = [dict(key=e['key'], group=e['group'], claim=e['packet']['base_packet']['claim'],
                  selected_anchors=e['packet']['base_packet']['selected_anchors'], gold=labels[e['key']],
                  v1_decision=prior[e['key']], v3_result=indexed.get(e['key']), human_verdict=None, human_note=None) for e in entries]
    write(out / 'results.json', results); write(out / 'review-cards.json', cards)
    write(out / 'metrics.json', {k: summary[k] for k in ('scifact', 'regression')})
    summary['artifacts_sha256'] = {p.name: digest(p) for p in out.glob('*.json')}
    write(out / 'summary.json', summary)
    return summary


def verify_summary(out, entries):
    summary = read(out / 'summary.json'); verify(out, summary['artifacts_sha256'])
    results = read(out / 'results.json')
    individual = [read(out / f"result-{k}.json") for k in KEYS if (out / f"result-{k}.json").exists()]
    if results != individual or {k: v for k, v in summary.items() if k != 'artifacts_sha256'} != summarize(entries, results):
        raise ValueError('cached_summary_drift')
    return summary


async def run(approved, max_calls, out=OUT, *, client_factory=None):
    out = Path(out); entries = preflight(out, approved, max_calls)
    if (out / 'summary.json').exists():
        return verify_summary(out, entries)
    if (out / 'run-started.json').exists() or list(out.glob('attempt-*.json')):
        raise ValueError('interrupted_run_no_resume')
    client, secret = (client_factory or make_client)()
    results = []
    async with client:
        write(out / 'run-started.json', dict(started=time.time(), approved_max_calls=10,
                                            protocol_sha256=value_hash(PROTOCOL)))
        for entry in entries:
            preflight(out, approved, max_calls)
            if len(list(out.glob('attempt-*.json'))) >= max_calls:
                raise ValueError('call_budget_exhausted')
            key = entry['key']; request = read(out / f'request-{key}.json')
            write(out / f'attempt-{key}.json', dict(key=key, started=time.time(), request_sha256=value_hash(request), max_output_tokens=1500))
            result = await judge(entry, request, client.chat.completions.create)
            serialized = json.dumps(result, ensure_ascii=False)
            if secret and secret in serialized:
                result = json.loads(serialized.replace(secret, '[REDACTED]'))
                result.update(status='error', decision=None, error_type='CredentialRedacted', error_stage='redaction')
            write(out / f'result-{key}.json', result); results.append(result)
            print(key, result['status'], (result['decision'] or {}).get('verdict'), result['seconds'], flush=True)
            if result['status'] != 'ok':
                break
    preflight(out, approved, max_calls)
    return finish(out, entries, results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'run', 'verify'))
    parser.add_argument('--approved', action='store_true'); parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    try:
        if args.stage == 'prepare':
            result = prepare()
        elif args.stage == 'verify':
            result = verify_summary(OUT, preflight(OUT, True, 10))
        else:
            result = asyncio.run(run(args.approved, args.max_calls))
        if args.stage != 'prepare':
            result = {k: result[k] for k in ('status', 'provider_calls', 'valid_contracts', 'errors', 'measured_token_totals')}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps(dict(status='error', error_type=type(exc).__name__)))
        raise SystemExit(1)
