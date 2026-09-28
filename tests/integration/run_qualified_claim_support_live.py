"""One approved v2 run on frozen 30 + 22 claims; never rerun the v1 reviewer."""
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

from backend.chat import qualified_claim_support as v2
from backend.chat import selected_claim_support as v1
from tests.integration import prepare_qualified_claim_support as prep
from tests.integration import run_selected_claim_support_live as old
from tests.integration.run_selected_claim_support_live import read, digest, write, verify, value_hash, make_client

BASE = prep.OUT
OUT = ROOT / 'output/qualified-claim-support-live-v2'
BASE_MANIFEST_SHA256 = '39d9786d2fab005a8ebdfc55c2779c3a73314bf63ed9651721e66e1446f3a219'
PROTOCOL = dict(version='qualified_claim_support_live_v2', max_calls=52, repeats=1,
                model='qwen3-vl-plus', temperature=0, max_tokens=1500, max_retries=0,
                sdk_timeout_seconds=60, total_call_seconds=60, sequential=True,
                rerun_v1=False, regenerate_answers=False, gold_in_requests=False,
                automatic_resume=False, stop_on_first_error=True)
LABELS = ('SUPPORT', 'CONTRADICT', 'NOT_ENOUGH_INFO')
MAPPING = {('supported', 'entailed'): 'SUPPORT', ('unsupported', 'contradicted'): 'CONTRADICT',
           ('unsupported', 'not_in_evidence'): 'NOT_ENOUGH_INFO'}
request_for = prep.request_for


def prepare(out=OUT):
    out = Path(out)
    if out.exists():
        raise FileExistsError('experiment_already_exists')
    if digest(BASE / 'manifest.json') != BASE_MANIFEST_SHA256:
        raise ValueError('approved_preparation_manifest_drift')
    base_manifest = prep.verify_prepared()
    entries = read(BASE / 'entries.json')
    frozen = dict(base_manifest['source_sha256'])
    for path in BASE.glob('*.json'):
        frozen[path.relative_to(ROOT).as_posix()] = digest(path)
    for name in ('tests/integration/run_qualified_claim_support_live.py',
                 'tests/test_qualified_claim_support_live.py',
                 'docs/specs/qualified_claim_support_live/acceptance.md',
                 'tests/traceability/qualified_claim_support_live/coverage.py'):
        frozen[name] = digest(ROOT / name)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'entries.json', entries)
    write(out / 'labels.json', read(BASE / 'labels.json'))
    for entry in entries:
        request = read(BASE / f"request-{entry['key']}.json")
        if request != request_for(entry['packet']):
            raise ValueError('frozen_request_drift')
        write(out / f"request-{entry['key']}.json", request)
    write(out / 'manifest.json', dict(protocol=PROTOCOL, planned_calls=52,
          base_manifest_sha256=BASE_MANIFEST_SHA256, keys=[e['key'] for e in entries],
          source_sha256=frozen, artifacts_sha256={p.name: digest(p) for p in out.glob('*.json')}))
    return dict(status='prepared_not_run', planned_calls=52, provider_calls=0, frozen_sources=len(frozen))


def preflight(out, approved, max_calls):
    if approved is not True or type(max_calls) is not int or max_calls != 52:
        raise ValueError('explicit_52_call_approval_required')
    out = Path(out)
    manifest = read(out / 'manifest.json')
    if (manifest.get('protocol') != PROTOCOL or manifest.get('planned_calls') != 52
            or manifest.get('base_manifest_sha256') != BASE_MANIFEST_SHA256
            or digest(BASE / 'manifest.json') != BASE_MANIFEST_SHA256):
        raise ValueError('protocol_drift')
    verify(ROOT, manifest['source_sha256']); verify(out, manifest['artifacts_sha256'])
    entries = read(out / 'entries.json')
    keys = [e['key'] for e in entries]
    if (len(keys) != 52 or len(set(keys)) != 52 or keys != manifest['keys']
            or entries != read(BASE / 'entries.json')
            or read(out / 'labels.json') != read(BASE / 'labels.json')):
        raise ValueError('entry_identity_drift')
    for e in entries:
        if request_for(e['packet']) != read(out / f"request-{e['key']}.json"):
            raise ValueError('request_drift')
    attempts = list(out.glob('attempt-*.json'))
    attempted = {p.stem.removeprefix('attempt-') for p in attempts}
    completed = {p.stem.removeprefix('result-') for p in out.glob('result-*.json')}
    if attempted != completed or attempted != set(keys[:len(attempts)]):
        raise ValueError('orphan_or_out_of_order_attempt_no_resume')
    for key in attempted:
        attempt, result = read(out / f'attempt-{key}.json'), read(out / f'result-{key}.json')
        expected = value_hash(read(out / f'request-{key}.json'))
        if (attempt.get('key') != key or result.get('key') != key
                or attempt.get('request_sha256') != expected or result.get('request_sha256') != expected
                or attempt.get('max_output_tokens') != 1500 or result.get('provider_calls') != 1):
            raise ValueError('attempt_result_identity_drift')
    return entries


async def judge(entry, request, provider):
    if request != request_for(entry['packet']):
        raise ValueError('request_drift')
    result = dict(key=entry['key'], group=entry['group'], original_key=entry['original_key'],
                  claim_id=entry['packet']['base_packet']['claim_id'], request_sha256=value_hash(request),
                  status='error', decision=None, provider_calls=1, raw_content=None,
                  finish_reason=None, provider_refusal=False, usage=None)
    started = time.monotonic()
    stage = 'provider'
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
            raise ValueError('incomplete_or_refused_review')
        stage = 'contract'
        result['decision'] = v2.parse_decision(result['raw_content'], entry['packet'])
        result['status'] = 'ok'
    except Exception as exc:
        # Exception messages may contain request data, URLs or credentials.
        result.update(error_type=type(exc).__name__, error_stage=stage)
        status = getattr(exc, 'status_code', None)
        result['provider_status_code'] = status if type(status) is int else None
    result['seconds'] = round(time.monotonic() - started, 4)
    return result


def inspect_results(entries, results):
    lookup = {e['key']: e for e in entries}
    if len(lookup) != len(entries):
        raise ValueError('duplicate_entries')
    decisions, outcomes, seen = {}, dict.fromkeys(lookup, 'MISSING'), set()
    for r in results:
        key = r.get('key')
        if key not in lookup or key in seen:
            raise ValueError('unknown_or_duplicate_result')
        seen.add(key)
        e = lookup[key]
        if (r.get('request_sha256') != value_hash(request_for(e['packet']))
                or r.get('group') != e['group'] or r.get('original_key') != e['original_key']
                or r.get('claim_id') != e['packet']['base_packet']['claim_id']
                or r.get('status') not in ('ok', 'error') or r.get('provider_calls') != 1):
            raise ValueError('invalid_result_identity')
        outcomes[key] = 'ERROR'
        if r['status'] != 'ok' or r.get('finish_reason') != 'stop' or r.get('provider_refusal'):
            continue
        try:
            decisions[key] = v2.parse_decision(r.get('raw_content'), e['packet'])
        except ValueError:
            continue
        d = decisions[key]
        outcomes[key] = MAPPING.get((d['verdict'], d['reason_code']), 'UNCERTAIN')
    return decisions, outcomes


def score_scifact(entries, outcomes, labels):
    """Independent v2 three-way scoring; do not forge v1-shaped raw decisions."""
    keys = [e['key'] for e in entries if e['group'] == 'scifact']
    gold = {r['key']: r['gold_label'] for r in labels if r['group'] == 'scifact'}
    if len(keys) != 30 or set(gold) != set(keys) or any(v not in LABELS for v in gold.values()):
        raise ValueError('scifact_denominator_or_label_drift')
    columns = LABELS + ('UNCERTAIN', 'ERROR', 'MISSING')
    confusion = {label: dict.fromkeys(columns, 0) for label in LABELS}
    for key in keys:
        confusion[gold[key]][outcomes[key]] += 1
    counts = Counter(outcomes[k] for k in keys)
    received = 30 - counts['MISSING']
    per_class = {}
    for label in LABELS:
        tp, actual, predicted = confusion[label][label], sum(confusion[label].values()), counts[label]
        p, r = tp / predicted if predicted else 0, tp / actual if actual else 0
        per_class[label] = dict(support=actual, precision=p if received else None,
                               recall=r if received else None,
                               f1=(2 * p * r / (p + r) if p + r else 0) if received else None)
    correct = sum(confusion[label][label] for label in LABELS)
    negative = sum(gold[k] != 'SUPPORT' for k in keys)
    positive = 30 - negative
    false_accept = sum(gold[k] != 'SUPPORT' and outcomes[k] == 'SUPPORT' for k in keys)
    positive_block = sum(gold[k] == 'SUPPORT' and outcomes[k] != 'SUPPORT' for k in keys)
    return dict(total=30, received=received, complete=received == 30,
                classified=sum(counts[label] for label in LABELS), uncertain=counts['UNCERTAIN'],
                errors=counts['ERROR'], missing=counts['MISSING'], correct=correct,
                accuracy_full_denominator=correct / 30 if received else None,
                macro_f1=sum(v['f1'] for v in per_class.values()) / 3 if received else None,
                per_class=per_class, confusion=confusion,
                false_accept_count=false_accept, false_accept_denominator=negative,
                false_accept_rate=false_accept / negative if received else None,
                positive_block_count=positive_block, positive_block_denominator=positive,
                positive_block_rate=positive_block / positive if received else None,
                positive_negative_verdict_count=sum(gold[k] == 'SUPPORT' and outcomes[k] in LABELS[1:] for k in keys),
                official_scifact_score=False, project_human_verified=False,
                cases=[dict(key=k, gold=gold[k], predicted=outcomes[k], correct=gold[k] == outcomes[k]) for k in keys])


def old_decisions(entries):
    """Read and revalidate saved v1 results only; this function has no client."""
    result = {}
    for e in entries:
        folder = prep.SCI_LIVE if e['group'] == 'scifact' else prep.CLAIM_LIVE
        row = read(folder / f"result-{e['original_key']}.json")
        packet = e['packet']['base_packet']
        if (row['key'] != e['original_key'] or row['status'] != 'ok'
                or row['finish_reason'] != 'stop' or row['provider_refusal']
                or row['request_sha256'] != value_hash(old.request_for(packet))):
            raise ValueError('v1_baseline_drift')
        result[e['key']] = v1.parse_decision(row['raw_content'], packet)
    return result


def summarize(entries, results):
    decisions, outcomes = inspect_results(entries, results)
    prior = old_decisions(entries)
    metrics = score_scifact(entries, outcomes, read(BASE / 'labels.json'))
    baseline = read(prep.SCI_LIVE / 'metrics.json')
    transitions, regression_cases, pairs = Counter(), [], []
    for e in entries:
        key = e['key']; before = prior[key]
        if e['group'] == 'scifact':
            pairs.append(dict(key=key, v1=MAPPING.get((before['verdict'], before['reason_code']), 'UNCERTAIN'), v2=outcomes[key]))
        else:
            after = decisions[key]['verdict'] if key in decisions else outcomes[key]
            transitions[f"{before['verdict']} -> {after}"] += 1
            regression_cases.append(dict(key=key, v1=before['verdict'], v2=after, gold_label=None, human_verdict=None))
    regression = dict(total=22, received=sum(c['v2'] != 'MISSING' for c in regression_cases),
                      missing=sum(c['v2'] == 'MISSING' for c in regression_cases),
                      errors=sum(c['v2'] == 'ERROR' for c in regression_cases),
                      transitions=dict(transitions), cases=regression_cases, semantic_accuracy=None,
                      scope='Model verdict transitions only; no human Gold, not accuracy')
    fields = ('prompt_tokens', 'completion_tokens', 'total_tokens')
    measured = [r for r in results if all(type((r.get('usage') or {}).get(k)) is int and r['usage'][k] >= 0 for k in fields)]
    errors = sum(outcomes[k] == 'ERROR' for k in outcomes)
    return dict(experiment='qualified-claim-support-live-v2',
                status='stopped_error' if errors else 'completed' if len(results) == 52 else 'incomplete',
                planned_claims=52, reviewed_claims=len(decisions), provider_calls=sum(r['provider_calls'] for r in results),
                unreviewed_claims=52 - len(results), errors=errors,
                model_verdict_counts=dict(Counter(d['verdict'] for d in decisions.values())),
                model_reason_counts=dict(Counter(d['reason_code'] for d in decisions.values())),
                guard_counts=dict(Counter(c for d in decisions.values() for c in d['guard_codes'])),
                finish_reason_counts=dict(Counter(r.get('finish_reason') or 'missing' for r in results)),
                usage_measured_calls=len(measured), usage_unknown_calls=len(results) - len(measured),
                measured_token_totals={k: sum(r['usage'][k] for r in measured) if measured else None for k in fields},
                latency_seconds=dict(mean=statistics.mean(r['seconds'] for r in results) if results else None,
                                     total=sum(r['seconds'] for r in results)),
                scifact_v1=baseline, scifact_v2=metrics, scifact_pairs=pairs, regression=regression,
                automatic_retry=False, v1_new_calls=0, pooled_accuracy=None, production_enabled=False,
                scope='Fixed supplied evidence; NOT retrieval, full RAG or an official benchmark score')


def finish(out, entries, results):
    summary = summarize(entries, results)
    before, indexed = old_decisions(entries), {r['key']: r for r in results}
    labels = {r['key']: r for r in read(BASE / 'labels.json')}
    cards = [dict(key=e['key'], group=e['group'], claim=e['packet']['base_packet']['claim'],
                  selected_anchors=e['packet']['base_packet']['selected_anchors'], gold=labels[e['key']],
                  v1_decision=before[e['key']], v2_result=indexed.get(e['key']),
                  human_verdict=None, human_note=None) for e in entries]
    write(out / 'results.json', results)
    write(out / 'metrics.json', dict(scifact_v1=summary['scifact_v1'], scifact_v2=summary['scifact_v2'],
                                    scifact_pairs=summary['scifact_pairs'], regression=summary['regression']))
    write(out / 'review-cards.json', cards)
    summary['artifacts_sha256'] = {p.name: digest(p) for p in out.glob('*.json')}
    write(out / 'summary.json', summary)
    return summary


def verify_summary(out, entries):
    summary = read(out / 'summary.json')
    verify(out, summary['artifacts_sha256'])
    rows = read(out / 'results.json')
    individual = [read(out / f"result-{e['key']}.json") for e in entries if (out / f"result-{e['key']}.json").exists()]
    if rows != individual or {k: v for k, v in summary.items() if k != 'artifacts_sha256'} != summarize(entries, rows):
        raise ValueError('cached_summary_drift')
    return summary


async def run(approved, max_calls, out=OUT, *, client_factory=None):
    out = Path(out)
    entries = preflight(out, approved, max_calls)
    if (out / 'summary.json').exists():
        return verify_summary(out, entries)
    if (out / 'run-started.json').exists() or list(out.glob('attempt-*.json')):
        raise ValueError('interrupted_run_no_automatic_resume')
    # Reused client enforces Aliyun HTTPS/model allowlist, SDK retries=0, timeout=60.
    client, secret = (client_factory or make_client)()
    results = []
    async with client:
        write(out / 'run-started.json', dict(started=time.time(), approved_max_calls=52,
                                            protocol_sha256=value_hash(PROTOCOL)))
        for entry in entries:
            preflight(out, approved, max_calls)
            if len(list(out.glob('attempt-*.json'))) >= max_calls:
                raise ValueError('call_budget_exhausted')
            key = entry['key']; request = read(out / f'request-{key}.json')
            write(out / f'attempt-{key}.json', dict(key=key, started=time.time(),
                  request_sha256=value_hash(request), max_output_tokens=1500))
            result = await judge(entry, request, client.chat.completions.create)
            serialized = json.dumps(result, ensure_ascii=False)
            if secret and secret in serialized:
                result = json.loads(serialized.replace(secret, '[REDACTED]'))
                result.update(status='error', decision=None, error_type='CredentialRedacted', error_stage='redaction')
            write(out / f'result-{key}.json', result)
            results.append(result)
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
            result = verify_summary(OUT, preflight(OUT, True, 52))
        else:
            result = asyncio.run(run(args.approved, args.max_calls))
        if args.stage != 'prepare':
            result = {k: result[k] for k in ('status', 'provider_calls', 'reviewed_claims', 'errors', 'measured_token_totals')}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps(dict(status='error', error_type=type(exc).__name__)))
        raise SystemExit(1)
