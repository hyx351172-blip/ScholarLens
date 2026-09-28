"""Independent v2.1 run on 51 unattempted packets; no resumption of old runs."""
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

from backend.chat import qualified_claim_support_v21 as v21
from tests.integration import replay_qualified_quote_alignment as replay
from tests.integration import run_qualified_claim_support_live as base
from tests.integration.run_selected_claim_support_live import read, digest, verify, write, value_hash, make_client

BASE = base.OUT
OUT = ROOT / 'output/qualified-support-remaining-v21'
EXCLUDED_KEY = 'SCIFACT-SF-72-6076903'
REPLAY_MANIFEST_SHA256 = '30152cd21a756067906aa6c73d5cf8037c35e82842cc39852d6de7d202598c89'
PROTOCOL = dict(base.PROTOCOL, version='qualified_support_remaining_v21', max_calls=51,
                parser_version=v21.VERSION, request_policy_version=base.v2.VERSION,
                exclude_attempted_key=EXCLUDED_KEY, historical_replay_in_live_metrics=False)
request_for = base.request_for


def load_cohort():
    if digest(replay.OUT / 'manifest.json') != REPLAY_MANIFEST_SHA256:
        raise ValueError('frozen_replay_manifest_drift')
    replay.verify_export()
    all_entries = read(BASE / 'entries.json')
    attempted = {r['key'] for r in read(BASE / 'results.json')}
    if attempted != {EXCLUDED_KEY}:
        raise ValueError('historical_attempts_drift')
    entries = [e for e in all_entries if e['key'] not in attempted]
    if (len(entries) != 51 or len({e['key'] for e in entries}) != 51
            or Counter(e['group'] for e in entries) != {'scifact': 29, 'selected_claim_regression': 22}):
        raise ValueError('remaining_cohort_drift')
    return entries


def prepare(out=OUT):
    out = Path(out)
    if out.exists():
        raise FileExistsError('batch_already_exists')
    entries = load_cohort()
    frozen = dict(read(replay.OUT / 'manifest.json')['source_sha256'])
    for path in replay.OUT.glob('*.json'):
        frozen[path.relative_to(ROOT).as_posix()] = digest(path)
    for name in ('tests/integration/run_qualified_support_remaining.py', 'tests/test_qualified_support_remaining.py',
                 'docs/specs/qualified_support_remaining/acceptance.md', 'tests/traceability/qualified_support_remaining/coverage.py'):
        frozen[name] = digest(ROOT / name)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'entries.json', entries)
    write(out / 'labels.json', [r for r in read(BASE / 'labels.json') if r['key'] != EXCLUDED_KEY])
    write(out / 'excluded.json', historical_replay())
    for entry in entries:
        request = read(BASE / f"request-{entry['key']}.json")
        if request != request_for(entry['packet']):
            raise ValueError('original_request_drift')
        write(out / f"request-{entry['key']}.json", request)
    summary = dict(status='prepared_not_run', planned_calls=51, provider_calls=0,
                   groups=dict(Counter(e['group'] for e in entries)), max_tokens_per_call=1500,
                   maximum_completion_tokens=51 * 1500, excluded_key=EXCLUDED_KEY,
                   total_prompt_characters=sum(len(m['content']) for e in entries for m in request_for(e['packet'])['messages']))
    write(out / 'preparation.json', summary)
    write(out / 'manifest.json', dict(protocol=PROTOCOL, planned_calls=51, keys=[e['key'] for e in entries],
          source_sha256=frozen, artifacts_sha256={p.name: digest(p) for p in out.glob('*.json')},
          replay_manifest_sha256=REPLAY_MANIFEST_SHA256))
    return summary


def preflight(out, approved, max_calls):
    if approved is not True or type(max_calls) is not int or max_calls != 51:
        raise ValueError('explicit_51_call_approval_required')
    out = Path(out); manifest = read(out / 'manifest.json')
    if (manifest.get('protocol') != PROTOCOL or manifest.get('planned_calls') != 51
            or manifest.get('replay_manifest_sha256') != REPLAY_MANIFEST_SHA256
            or digest(replay.OUT / 'manifest.json') != REPLAY_MANIFEST_SHA256):
        raise ValueError('batch_protocol_drift')
    verify(ROOT, manifest['source_sha256']); verify(out, manifest['artifacts_sha256'])
    entries = read(out / 'entries.json'); keys = [e['key'] for e in entries]
    if (len(keys) != 51 or len(set(keys)) != 51 or keys != manifest['keys']
            or entries != [e for e in read(BASE / 'entries.json') if e['key'] != EXCLUDED_KEY]
            or read(out / 'labels.json') != [r for r in read(BASE / 'labels.json') if r['key'] != EXCLUDED_KEY]
            or read(out / 'excluded.json') != historical_replay()):
        raise ValueError('cohort_identity_drift')
    for entry in entries:
        if read(out / f"request-{entry['key']}.json") != request_for(entry['packet']):
            raise ValueError('request_drift')
    attempts = {p.stem.removeprefix('attempt-') for p in out.glob('attempt-*.json')}
    results = {p.stem.removeprefix('result-') for p in out.glob('result-*.json')}
    if attempts != results or attempts != set(keys[:len(attempts)]):
        raise ValueError('orphan_or_out_of_order_no_resume')
    for key in attempts:
        a, r = read(out / f'attempt-{key}.json'), read(out / f'result-{key}.json')
        expected = value_hash(read(out / f'request-{key}.json'))
        if (a.get('key') != key or r.get('key') != key or a.get('request_sha256') != expected
                or r.get('request_sha256') != expected or a.get('max_output_tokens') != 1500
                or r.get('provider_calls') != 1 or r.get('parser_version') != v21.VERSION):
            raise ValueError('attempt_result_drift')
    return entries


async def judge(entry, request, provider):
    # Reuse the frozen transport: exact request, one call, 60-second deadline.
    # Its strict-v2 parser may reject whitespace; only complete contract-stage
    # outputs can then be interpreted with v2.1. No second API request is made.
    result = await base.judge(entry, request, provider)
    result.update(strict_v2_status=result['status'], parser_version=v21.VERSION)
    if result['status'] == 'ok' or result.get('error_stage') == 'contract':
        try:
            result['decision'] = v21.parse_decision(result['raw_content'], entry['packet'])
            result['status'] = 'ok'
            for field in ('error_type', 'error_stage', 'provider_status_code'):
                result.pop(field, None)
        except ValueError:
            result.update(status='error', decision=None, error_type='ValueError', error_stage='contract')
    return result


def inspect_results(entries, results):
    lookup = {e['key']: e for e in entries}
    if len(lookup) != 51 or len(entries) != 51 or EXCLUDED_KEY in lookup:
        raise ValueError('invalid_remaining_cohort')
    decisions, outcomes, seen = {}, dict.fromkeys(lookup, 'MISSING'), set()
    for result in results:
        key = result.get('key')
        if key not in lookup or key in seen:
            raise ValueError('unknown_or_duplicate_result')
        seen.add(key); e = lookup[key]
        if (result.get('request_sha256') != value_hash(request_for(e['packet']))
                or result.get('group') != e['group'] or result.get('original_key') != e['original_key']
                or result.get('claim_id') != e['packet']['base_packet']['claim_id']
                or result.get('status') not in ('ok', 'error') or result.get('provider_calls') != 1
                or result.get('parser_version') != v21.VERSION):
            raise ValueError('result_identity_drift')
        outcomes[key] = 'ERROR'
        if result['status'] != 'ok' or result.get('finish_reason') != 'stop' or result.get('provider_refusal'):
            continue
        try:
            decisions[key] = v21.parse_decision(result.get('raw_content'), e['packet'])
        except ValueError:
            continue
        d = decisions[key]
        outcomes[key] = base.MAPPING.get((d['verdict'], d['reason_code']), 'UNCERTAIN')
    return decisions, outcomes


def score29(entries, outcomes):
    keys = [e['key'] for e in entries if e['group'] == 'scifact']
    gold = {r['key']: r['gold_label'] for r in read(BASE / 'labels.json') if r['key'] in keys}
    if len(keys) != 29 or set(gold) != set(keys) or any(v not in base.LABELS for v in gold.values()):
        raise ValueError('scifact29_denominator_drift')
    columns = base.LABELS + ('UNCERTAIN', 'ERROR', 'MISSING')
    confusion = {label: dict.fromkeys(columns, 0) for label in base.LABELS}
    for key in keys:
        confusion[gold[key]][outcomes[key]] += 1
    counts = Counter(outcomes[k] for k in keys); received = 29 - counts['MISSING']
    classes = {}
    for label in base.LABELS:
        tp, actual, predicted = confusion[label][label], sum(confusion[label].values()), counts[label]
        p, r = tp / predicted if predicted else 0, tp / actual if actual else 0
        classes[label] = dict(support=actual, precision=p if received else None, recall=r if received else None,
                             f1=(2 * p * r / (p + r) if p + r else 0) if received else None)
    correct = sum(confusion[c][c] for c in base.LABELS)
    positive = sum(gold[k] == 'SUPPORT' for k in keys); negative = 29 - positive
    false_accept = sum(gold[k] != 'SUPPORT' and outcomes[k] == 'SUPPORT' for k in keys)
    block = sum(gold[k] == 'SUPPORT' and outcomes[k] != 'SUPPORT' for k in keys)
    return dict(total=29, received=received, complete=received == 29,
                classified=sum(counts[c] for c in base.LABELS), uncertain=counts['UNCERTAIN'],
                errors=counts['ERROR'], missing=counts['MISSING'], correct=correct,
                accuracy_full_denominator=correct / 29 if received else None,
                macro_f1=sum(c['f1'] for c in classes.values()) / 3 if received else None,
                false_accept_count=false_accept, false_accept_denominator=negative,
                false_accept_rate=false_accept / negative if received else None,
                positive_block_count=block, positive_block_denominator=positive,
                positive_block_rate=block / positive if received else None,
                positive_negative_verdict_count=sum(gold[k] == 'SUPPORT' and outcomes[k] in base.LABELS[1:] for k in keys),
                per_class=classes, confusion=confusion, official_scifact_score=False,
                cases=[dict(key=k, gold=gold[k], predicted=outcomes[k], correct=gold[k] == outcomes[k]) for k in keys])


def historical_replay():
    case = next(c for c in read(replay.OUT / 'replay.json')['cases'] if c['key'] == EXCLUDED_KEY)
    return dict(key=EXCLUDED_KEY, origin='historical_response_offline_replay_not_live',
                verdict=case['decision']['verdict'], reason_code=case['decision']['reason_code'],
                new_provider_calls=0, included_in_live_metrics=False, source_result=case['source_result'],
                source_sha256=case['source_sha256'], raw_response_sha256=case['raw_response_sha256'])


def summarize(entries, results):
    decisions, outcomes = inspect_results(entries, results)
    prior = base.old_decisions(entries)
    old_outcomes = {key: base.MAPPING.get((d['verdict'], d['reason_code']), 'UNCERTAIN') for key, d in prior.items()}
    regressions, transitions = [], Counter()
    for e in entries:
        if e['group'] == 'selected_claim_regression':
            key = e['key']; before = prior[key]['verdict']
            after = decisions[key]['verdict'] if key in decisions else outcomes[key]
            transitions[f'{before} -> {after}'] += 1
            regressions.append(dict(key=key, v1=before, v21=after, gold_label=None, human_verdict=None))
    fields = ('prompt_tokens', 'completion_tokens', 'total_tokens')
    measured = [r for r in results if all(type((r.get('usage') or {}).get(k)) is int and r['usage'][k] >= 0 for k in fields)]
    errors = sum(o == 'ERROR' for o in outcomes.values())
    return dict(experiment='qualified-support-remaining-v21',
                status='stopped_error' if errors else 'completed' if len(results) == 51 else 'incomplete',
                planned_claims=51, provider_calls=len(results), reviewed_claims=len(decisions),
                errors=errors, unreviewed_claims=51 - len(results),
                scifact_v21=score29(entries, outcomes), scifact_v1_same29=score29(entries, old_outcomes),
                regression=dict(total=22, received=sum(c['v21'] != 'MISSING' for c in regressions),
                                missing=sum(c['v21'] == 'MISSING' for c in regressions),
                                errors=sum(c['v21'] == 'ERROR' for c in regressions), transitions=dict(transitions),
                                cases=regressions, semantic_accuracy=None),
                historical_replay=historical_replay(), mixed52_live_accuracy=None,
                model_verdict_counts=dict(Counter(d['verdict'] for d in decisions.values())),
                guard_counts=dict(Counter(c for d in decisions.values() for c in d['guard_codes'])),
                citation_match_counts=dict(Counter(c['match_mode'] for d in decisions.values()
                                                  for check in d['checks'].values() for c in check['citations'])),
                finish_reason_counts=dict(Counter(r.get('finish_reason') or 'missing' for r in results)),
                usage_measured_calls=len(measured), usage_unknown_calls=len(results) - len(measured),
                measured_token_totals={k: sum(r['usage'][k] for r in measured) if measured else None for k in fields},
                latency_seconds=dict(mean=statistics.mean(r['seconds'] for r in results) if results else None,
                                     total=sum(r['seconds'] for r in results)),
                automatic_retry=False, new_v1_calls=0, production_enabled=False,
                scope='29 live SciFact + 22 unlabelled regression; excluded replay is not a live sample.')


def finish(out, entries, results):
    summary = summarize(entries, results)
    indexed = {r['key']: r for r in results}; prior = base.old_decisions(entries)
    labels = {r['key']: r for r in read(out / 'labels.json')}
    cards = [dict(key=e['key'], group=e['group'], claim=e['packet']['base_packet']['claim'],
                  selected_anchors=e['packet']['base_packet']['selected_anchors'], gold=labels[e['key']],
                  v1_decision=prior[e['key']], v21_result=indexed.get(e['key']), human_verdict=None, human_note=None) for e in entries]
    write(out / 'results.json', results)
    write(out / 'review-cards.json', cards)
    write(out / 'metrics.json', {k: summary[k] for k in ('scifact_v21', 'scifact_v1_same29', 'regression', 'historical_replay')})
    summary['artifacts_sha256'] = {p.name: digest(p) for p in out.glob('*.json')}
    write(out / 'summary.json', summary)
    return summary


def verify_summary(out, entries):
    summary = read(out / 'summary.json'); verify(out, summary['artifacts_sha256'])
    results = read(out / 'results.json')
    individual = [read(out / f"result-{e['key']}.json") for e in entries if (out / f"result-{e['key']}.json").exists()]
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
        write(out / 'run-started.json', dict(started=time.time(), approved_max_calls=51,
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
    parser.add_argument('--approved', action='store_true')
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    try:
        if args.stage == 'prepare':
            result = prepare()
        elif args.stage == 'verify':
            result = verify_summary(OUT, preflight(OUT, True, 51))
        else:
            result = asyncio.run(run(args.approved, args.max_calls))
        if args.stage != 'prepare':
            result = {k: result[k] for k in ('status', 'provider_calls', 'reviewed_claims', 'errors', 'measured_token_totals')}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps(dict(status='error', error_type=type(exc).__name__)))
        raise SystemExit(1)
