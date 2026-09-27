"""Bounded, write-once 22-claim review. No retrieval or answer regeneration."""
import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat.selected_claim_support import review_messages, parse_decision, gate_answer
from tests.integration.prepare_selected_claim_support import build_corpus, read, digest, LIVE

BASE = ROOT / 'output/selected-claim-support-v1'
OUT = ROOT / 'output/selected-claim-support-live-v1'
PROTOCOL = dict(model='qwen3-vl-plus', temperature=0, max_tokens=1000, max_retries=0,
                sdk_timeout_seconds=60, total_call_seconds=60, max_calls=22,
                execution='sequential_selected_claim_review', repeats=1, paid_judge=True,
                regenerate_answers=False)


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write('\n')


def value_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def verify(root, hashes):
    for name, expected in hashes.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or digest(path) != expected:
            raise ValueError('frozen_artifact_drift')


def frozen_entries():
    manifest = read(BASE / 'manifest.json')
    verify(ROOT, manifest['source_sha256']); verify(BASE, manifest['artifacts_sha256'])
    corpus = build_corpus()
    packets = read(BASE / 'packets.json')
    if packets != corpus['packets'] or read(BASE / 'controls.json') != corpus['controls']:
        raise ValueError('frozen_corpus_replay_drift')
    return [dict(key=f"{r['case_id']}-{r['packet']['claim_id']}",
                 case_id=r['case_id'], packet=r['packet']) for r in packets]


def request_for(packet):
    return dict(model=PROTOCOL['model'], messages=review_messages(packet), temperature=0,
                max_tokens=1000, response_format={'type': 'json_object'},
                extra_body={'enable_thinking': False}, stream=False)


def prepare(out=OUT):
    if out.exists():
        raise FileExistsError('experiment_already_exists')
    entries = frozen_entries()
    if len(entries) != 22 or len({e['key'] for e in entries}) != 22:
        raise ValueError('claim_denominator_mismatch')
    frozen = dict(read(BASE / 'manifest.json')['source_sha256'])
    for path in BASE.glob('*.json'):
        frozen[path.relative_to(ROOT).as_posix()] = digest(path)
    for name in ('tests/integration/run_selected_claim_support_live.py',
                 'tests/test_selected_claim_support_live.py',
                 'docs/specs/selected_claim_support_live/acceptance.md',
                 'tests/traceability/selected_claim_support_live/coverage.py'):
        frozen[name] = digest(ROOT / name)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'entries.json', entries)
    for entry in entries:
        write(out / f"request-{entry['key']}.json", request_for(entry['packet']))
    artifacts = {p.name: digest(p) for p in out.glob('*.json')}
    write(out / 'manifest.json', dict(protocol=PROTOCOL, planned_calls=22,
          keys=[e['key'] for e in entries], source_sha256=frozen, artifacts_sha256=artifacts))
    return dict(status='prepared_not_run', planned_calls=22, negative_controls=2,
                frozen_sources=len(frozen), total_prompt_characters=sum(
                    len(m['content']) for e in entries for m in request_for(e['packet'])['messages']))


def preflight(out, approved, max_calls):
    if approved is not True or type(max_calls) is not int or max_calls != 22:
        raise ValueError('explicit_22_call_approval_required')
    manifest = read(out / 'manifest.json')
    if manifest.get('protocol') != PROTOCOL or manifest.get('planned_calls') != 22:
        raise ValueError('protocol_drift')
    verify(ROOT, manifest['source_sha256']); verify(out, manifest['artifacts_sha256'])
    entries = read(out / 'entries.json')
    keys = [e['key'] for e in entries]
    if len(keys) != 22 or len(set(keys)) != 22 or keys != manifest.get('keys'):
        raise ValueError('entry_identity_drift')
    for e in entries:
        if request_for(e['packet']) != read(out / f"request-{e['key']}.json"):
            raise ValueError('request_drift')
    for path in out.glob('attempt-*.json'):
        key = path.stem.removeprefix('attempt-')
        if key not in keys or not (out / f'result-{key}.json').exists():
            raise ValueError('unresolved_attempt_no_resume')
        attempt, result = read(path), read(out / f'result-{key}.json')
        expected_hash = value_hash(read(out / f'request-{key}.json'))
        if (attempt.get('key') != key or result.get('key') != key
                or attempt.get('request_sha256') != expected_hash
                or result.get('request_sha256') != expected_hash):
            raise ValueError('attempt_result_identity_drift')
    for path in out.glob('result-*.json'):
        key = path.stem.removeprefix('result-')
        if key not in keys or not (out / f'attempt-{key}.json').exists():
            raise ValueError('orphan_result')
    return entries


def validate_config(config):
    url = urlsplit(config.get('api_url', ''))
    if (url.scheme != 'https' or url.hostname not in (
            'dashscope.aliyuncs.com', 'dashscope-intl.aliyuncs.com', 'dashscope-us.aliyuncs.com')
            or url.username or url.password or url.port not in (None, 443)
            or url.query or url.fragment or url.path.rstrip('/') != '/compatible-mode/v1'
            or config.get('model_name') != PROTOCOL['model'] or not config.get('api_key')):
        raise ValueError('configured_provider_or_model_mismatch')


def make_client():
    # Imported only after approval and the frozen request/code preflight.
    from tests.integration.compare_answer_modes import load_live_config
    from openai import AsyncOpenAI
    config = load_live_config()
    validate_config(config)
    return AsyncOpenAI(api_key=config['api_key'], base_url=config['api_url'],
                       max_retries=0, timeout=60), config['api_key']


async def judge(entry, request, provider):
    if request != request_for(entry['packet']):
        raise ValueError('request_drift')
    result = dict(key=entry['key'], case_id=entry['case_id'], claim_id=entry['packet']['claim_id'],
                  request_sha256=value_hash(request), status='error', decision=None, provider_calls=1,
                  raw_content=None, finish_reason=None, provider_refusal=False, usage=None)
    started = time.monotonic()
    try:
        response = await asyncio.wait_for(provider(**request), timeout=PROTOCOL['total_call_seconds'])
        choice = response.choices[0] if response.choices else None
        usage = response.usage.model_dump() if response.usage else {}
        result.update(raw_content=choice.message.content if choice else None,
                      finish_reason=choice.finish_reason if choice else None,
                      provider_refusal=bool(getattr(choice.message, 'refusal', None)) if choice else False,
                      usage={k: usage.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')})
        if result['finish_reason'] != 'stop' or result['provider_refusal']:
            raise ValueError('incomplete_or_refused_review')
        result['decision'] = parse_decision(result['raw_content'], entry['packet'])
        result['status'] = 'ok'
    except Exception as exc:
        result['error_type'] = type(exc).__name__
        status = getattr(exc, 'status_code', None)
        result['provider_status_code'] = status if type(status) is int else None
    result['seconds'] = round(time.monotonic() - started, 4)
    return result


def summarize(results):
    ok = [r for r in results if r['status'] == 'ok']
    fields = ('prompt_tokens', 'completion_tokens', 'total_tokens')
    measured = [r for r in results if all(type((r.get('usage') or {}).get(k)) is int for k in fields)]
    return dict(experiment='selected-claim-support-live-v1',
        status='stopped_error' if any(r['status'] == 'error' for r in results) else
               'completed' if len(results) == 22 else 'incomplete',
        planned_claims=22, reviewed_claims=len(ok), unreviewed_claims=22 - len(results),
        errors=len(results) - len(ok), provider_calls=sum(r['provider_calls'] for r in results),
        negative_controls=2, model_verdict_counts=dict(Counter(r['decision']['verdict'] for r in ok)),
        model_reason_counts=dict(Counter(r['decision']['reason_code'] for r in ok)),
        finish_reason_counts=dict(Counter(r['finish_reason'] for r in results)),
        usage_measured_calls=len(measured), usage_unknown_calls=len(results) - len(measured),
        measured_token_totals={k: sum(r['usage'][k] for r in measured) if measured else None for k in fields},
        latency_seconds=dict(mean=statistics.mean(r['seconds'] for r in results) if results else None,
                             total=sum(r['seconds'] for r in results)),
        semantic_accuracy=None, human_review_status='pending', automatic_retry=False,
        scope='Model opinions on a development corpus; same model family as generator, NOT human Gold')


def finish(out, entries, results):
    indexed = {r['key']: r for r in results}
    draft = {(r['case_id'], r['claim_id']): r for r in read(BASE / 'review_cards.json')}
    cards = []
    for e in entries:
        result = indexed.get(e['key'])
        p = e['packet']
        cards.append(dict(key=e['key'], question=p['question_for_identity_only'], claim=p['claim'],
                          selected_anchors=p['selected_anchors'], model_review=result,
                          ai_draft_assessment=draft[e['case_id'], p['claim_id']]['ai_draft_assessment'],
                          ai_draft_note=draft[e['case_id'], p['claim_id']]['ai_draft_note'],
                          human_verdict=None, human_note=None))
    gates = []
    for case in read(LIVE / 'inputs.json'):
        saved = read(LIVE / f"result-{case['id']}.json")
        decisions = {r['claim_id']: r['raw_content'] for r in results
                     if r['case_id'] == case['id'] and r['status'] == 'ok'}
        gates.append(dict(case_id=case['id'], result=gate_answer(
            case['query'], case['documents'], saved['raw_content'], decisions)))
    write(out / 'human-review.json', cards)
    write(out / 'gates.json', gates)
    summary = summarize(results)
    summary['gate_status_counts'] = dict(Counter(g['result']['status'] for g in gates))
    summary['artifacts_sha256'] = {p.name: digest(p) for p in out.glob('*.json')}
    write(out / 'summary.json', summary)
    return summary


async def run(approved, max_calls, out=OUT, *, client_factory=None):
    entries = preflight(out, approved, max_calls)
    if (out / 'summary.json').exists():
        summary = read(out / 'summary.json')
        verify(out, summary['artifacts_sha256'])
        return summary
    if (out / 'run-started.json').exists() or list(out.glob('attempt-*.json')):
        raise ValueError('interrupted_run_no_automatic_resume')
    client, secret = (client_factory or make_client)()
    # Persistent exclusive marker intentionally survives interruptions.
    write(out / 'run-started.json', dict(started=time.time(), approved_max_calls=22,
                                        protocol_sha256=value_hash(PROTOCOL)))
    rows = []
    async with client:
        for entry in entries:
            preflight(out, approved, max_calls)
            key = entry['key']; request = read(out / f'request-{key}.json')
            if len(list(out.glob('attempt-*.json'))) >= max_calls:
                raise ValueError('call_budget_exhausted')
            write(out / f'attempt-{key}.json', dict(key=key, started=time.time(),
                  request_sha256=value_hash(request), max_output_tokens=1000))
            result = await judge(entry, request, client.chat.completions.create)
            serialized = json.dumps(result, ensure_ascii=False)
            if secret and secret in serialized:
                result = json.loads(serialized.replace(secret, '[REDACTED]'))
                result.update(status='error', decision=None, error_type='CredentialRedacted')
            write(out / f'result-{key}.json', result); rows.append(result)
            print(key, result['status'], (result['decision'] or {}).get('verdict'), result['seconds'], flush=True)
            if result['status'] != 'ok':
                break
    preflight(out, approved, max_calls)
    return finish(out, entries, rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'run'))
    parser.add_argument('--approved', action='store_true')
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    try:
        result = prepare() if args.stage == 'prepare' else asyncio.run(run(args.approved, args.max_calls))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps(dict(status='error', error_type=type(exc).__name__)))
        raise SystemExit(1)
