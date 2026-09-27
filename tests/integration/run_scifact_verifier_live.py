"""One authorized 30-request SciFact smoke run. No regeneration or retuning."""
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

from tests.integration import prepare_scifact_verifier as sf
from tests.integration.run_selected_claim_support_live import (
    read, digest, write, verify, value_hash, request_for, judge, make_client,
)

BASE = sf.OUT
OUT = ROOT / 'output/scifact-verifier-live-v1'
PROTOCOL = dict(version='scifact_verifier_live_v1', max_calls=30, repeats=1,
                model='qwen3-vl-plus', temperature=0, max_tokens=1000, max_retries=0,
                sdk_timeout_seconds=60, total_call_seconds=60, sequential=True,
                regenerate_answers=False, gold_in_requests=False, automatic_resume=False)


def prepare(out=OUT):
    out = Path(out)
    if out.exists():
        raise FileExistsError('experiment_already_exists')
    base_manifest = sf.verify_prepared(BASE)
    entries = read(BASE / 'entries.json')
    if len(entries) != 30 or base_manifest['planned_calls'] != 30:
        raise ValueError('thirty_frozen_cases_required')
    frozen = dict(base_manifest['source_sha256'])
    for path in BASE.glob('*.json'):
        frozen[path.relative_to(ROOT).as_posix()] = digest(path)
    for name in ('tests/integration/run_scifact_verifier_live.py',
                 'tests/test_scifact_verifier_live.py',
                 'docs/specs/scifact_verifier_live/acceptance.md',
                 'tests/traceability/scifact_verifier_live/coverage.py'):
        frozen[name] = digest(ROOT / name)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'entries.json', entries)
    for entry in entries:
        request = read(BASE / f"request-{entry['key']}.json")
        if request != request_for(entry['packet']):
            raise ValueError('frozen_request_drift')
        write(out / f"request-{entry['key']}.json", request)
    write(out / 'manifest.json', dict(protocol=PROTOCOL, planned_calls=30,
          keys=[e['key'] for e in entries], source_sha256=frozen,
          artifacts_sha256={p.name: digest(p) for p in out.glob('*.json')}))
    return dict(status='prepared_not_run', planned_calls=30, provider_calls=0,
                frozen_sources=len(frozen))


def preflight(out, approved, max_calls):
    if approved is not True or type(max_calls) is not int or max_calls != 30:
        raise ValueError('explicit_30_call_approval_required')
    out = Path(out)
    manifest = read(out / 'manifest.json')
    if manifest.get('protocol') != PROTOCOL or manifest.get('planned_calls') != 30:
        raise ValueError('protocol_drift')
    verify(ROOT, manifest['source_sha256']); verify(out, manifest['artifacts_sha256'])
    entries = read(out / 'entries.json')
    keys = [e['key'] for e in entries]
    if len(keys) != 30 or len(set(keys)) != 30 or keys != manifest['keys']:
        raise ValueError('entry_identity_drift')
    if entries != read(BASE / 'entries.json'):
        raise ValueError('base_entry_drift')
    for e in entries:
        if request_for(e['packet']) != read(out / f"request-{e['key']}.json"):
            raise ValueError('request_drift')
    attempts = list(out.glob('attempt-*.json'))
    results = list(out.glob('result-*.json'))
    attempted = {p.stem.removeprefix('attempt-') for p in attempts}
    completed = {p.stem.removeprefix('result-') for p in results}
    if attempted != completed or attempted != set(keys[:len(attempts)]):
        raise ValueError('orphan_or_out_of_order_attempt_no_resume')
    for key in attempted:
        attempt, result = read(out / f'attempt-{key}.json'), read(out / f'result-{key}.json')
        expected = value_hash(read(out / f'request-{key}.json'))
        if (attempt.get('key') != key or result.get('key') != key
                or attempt.get('request_sha256') != expected or result.get('request_sha256') != expected
                or attempt.get('max_output_tokens') != 1000 or result.get('provider_calls') != 1):
            raise ValueError('attempt_result_identity_drift')
    return entries


def summarize(entries, results):
    metrics = sf.score(entries, read(BASE / 'gold.json'), results)
    fields = ('prompt_tokens', 'completion_tokens', 'total_tokens')
    measured = [r for r in results if all(type((r.get('usage') or {}).get(k)) is int for k in fields)]
    ok = [r for r in results if r['status'] == 'ok']
    return dict(experiment='scifact-verifier-live-v1',
                status='stopped_error' if metrics['errors'] else 'completed' if len(results) == 30 else 'incomplete',
                planned_claims=30, reviewed_claims=len(ok), provider_calls=sum(r['provider_calls'] for r in results),
                unreviewed_claims=30 - len(results), errors=metrics['errors'],
                model_verdict_counts=dict(Counter(r['decision']['verdict'] for r in ok)),
                model_reason_counts=dict(Counter(r['decision']['reason_code'] for r in ok)),
                # JSON object keys are strings: None would become "null" on disk
                # and spuriously fail the deterministic cached-summary replay.
                finish_reason_counts=dict(Counter(r['finish_reason'] or 'missing' for r in results)),
                usage_measured_calls=len(measured), usage_unknown_calls=len(results) - len(measured),
                measured_token_totals={k: sum(r['usage'][k] for r in measured) if measured else None for k in fields},
                latency_seconds=dict(mean=statistics.mean(r['seconds'] for r in results) if results else None,
                                     total=sum(r['seconds'] for r in results)),
                metrics=metrics, automatic_retry=False, official_scifact_score=False,
                scope='Balanced dev smoke classification of supplied full abstracts; NOT end-to-end RAG',
                human_review_status='dataset_labels_not_project_reverified')


def review_cards(entries, results):
    """Gold is consulted locally after calls, never passed to the reviewer."""
    gold = {r['key']: r for r in read(BASE / 'gold.json')}
    wanted = {r['doc_id'] for r in gold.values()}
    documents = {}
    with (sf.DATA / 'corpus.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            doc = json.loads(line)
            if doc['doc_id'] in wanted:
                documents[doc['doc_id']] = doc
    indexed = {r['key']: r for r in results}
    cards = []
    for entry in entries:
        label = gold[entry['key']]
        abstract = documents[label['doc_id']]['abstract']
        if '\n'.join(abstract) != ''.join(a['text'] for a in entry['packet']['selected_anchors']):
            raise ValueError('review_abstract_drift')
        cards.append(dict(key=entry['key'], claim=entry['packet']['claim'], gold=label,
                          selected_anchors=entry['packet']['selected_anchors'],
                          gold_rationale_texts=[[abstract[i] for i in rationale] for rationale in label['rationale_sets']],
                          model_review=indexed.get(entry['key']), human_verdict=None, human_note=None))
    return cards


def finish(out, entries, results):
    summary = summarize(entries, results)
    write(out / 'results.json', results)
    write(out / 'metrics.json', summary['metrics'])
    write(out / 'review-cards.json', review_cards(entries, results))
    summary['artifacts_sha256'] = {p.name: digest(p) for p in out.glob('*.json')}
    write(out / 'summary.json', summary)
    return summary


async def run(approved, max_calls, out=OUT, *, client_factory=None):
    out = Path(out)
    entries = preflight(out, approved, max_calls)
    if (out / 'summary.json').exists():
        summary = read(out / 'summary.json')
        verify(out, summary['artifacts_sha256'])
        recalculated = summarize(entries, read(out / 'results.json'))
        if {k: v for k, v in summary.items() if k != 'artifacts_sha256'} != recalculated:
            raise ValueError('cached_summary_drift')
        return summary
    if (out / 'run-started.json').exists() or list(out.glob('attempt-*.json')):
        raise ValueError('interrupted_run_no_automatic_resume')
    client, secret = (client_factory or make_client)()
    results = []
    async with client:
        # Atomic exclusive marker: a concurrent invocation cannot reach the API.
        write(out / 'run-started.json', dict(started=time.time(), approved_max_calls=30,
                                            protocol_sha256=value_hash(PROTOCOL)))
        for entry in entries:
            preflight(out, approved, max_calls)
            if len(list(out.glob('attempt-*.json'))) >= max_calls:
                raise ValueError('call_budget_exhausted')
            key = entry['key']
            request = read(out / f'request-{key}.json')
            write(out / f'attempt-{key}.json', dict(key=key, started=time.time(),
                  request_sha256=value_hash(request), max_output_tokens=1000))
            result = await judge(dict(entry, case_id=key), request, client.chat.completions.create)
            serialized = json.dumps(result, ensure_ascii=False)
            if secret and secret in serialized:
                result = json.loads(serialized.replace(secret, '[REDACTED]'))
                result.update(status='error', decision=None, error_type='CredentialRedacted')
            write(out / f'result-{key}.json', result)
            results.append(result)
            print(key, result['status'], (result['decision'] or {}).get('verdict'), result['seconds'], flush=True)
            if result['status'] != 'ok':
                break
    preflight(out, approved, max_calls)
    return finish(out, entries, results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'run'))
    parser.add_argument('--approved', action='store_true')
    parser.add_argument('--max-calls', type=int)
    args = parser.parse_args()
    try:
        result = prepare() if args.stage == 'prepare' else asyncio.run(run(args.approved, args.max_calls))
        if args.stage == 'run':
            result = {k: result[k] for k in ('status', 'provider_calls', 'reviewed_claims', 'errors', 'measured_token_totals', 'metrics')}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps(dict(status='error', error_type=type(exc).__name__)))
        raise SystemExit(1)
