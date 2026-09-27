"""Offline v2 preparation on the unchanged 30 + 22 frozen claim packets."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat import qualified_claim_support as v2
from tests.integration.prepare_selected_claim_support import read, digest
from tests.integration.run_selected_claim_support_live import write

SCI_BASE = ROOT / 'output/scifact-verifier-v1'
SCI_LIVE = ROOT / 'output/scifact-verifier-live-v1'
CLAIM_LIVE = ROOT / 'output/selected-claim-support-live-v1'
REVIEW = ROOT / 'docs/evaluation/scifact-disagreement-review-v1.json'
OUT = ROOT / 'output/qualified-claim-support-v2'
PROPOSAL = dict(model='qwen3-vl-plus', temperature=0, max_tokens=1500,
                max_calls=52, max_retries=0, timeout_seconds=60,
                approved=False, execution='not_implemented_no_calls_in_preparation')


def verify(root, hashes):
    for name, expected in hashes.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or digest(path) != expected:
            raise ValueError('frozen_history_drift')


def verify_history():
    manifest, summary = read(SCI_LIVE / 'manifest.json'), read(SCI_LIVE / 'summary.json')
    checks = {}
    for root, hashes in ((ROOT, manifest['source_sha256']), (SCI_LIVE, summary['artifacts_sha256'])):
        verify(root, hashes)
        checks.update({(root / name).relative_to(ROOT).as_posix(): expected for name, expected in hashes.items()})
    checks[(SCI_LIVE / 'summary.json').relative_to(ROOT).as_posix()] = digest(SCI_LIVE / 'summary.json')
    return checks


def validate_review(review):
    metrics = read(SCI_LIVE / 'metrics.json')
    wrong = {r['key']: r for r in metrics['cases'] if not r['correct']}
    entries = {r['key']: r for r in read(SCI_BASE / 'entries.json')}
    rows = review.get('cases', [])
    if (review.get('reviewer_type') != 'assistant_source_review_not_human_adjudication'
            or review.get('labels_changed') is not False or review.get('cases_removed') is not False
            or review.get('original_denominator') != metrics['total']
            or review.get('original_correct') != metrics['correct']
            or len(rows) != len(wrong) or {r['key'] for r in rows} != set(wrong)):
        raise ValueError('invalid_disagreement_review')
    for row in rows:
        source = ''.join(a['text'] for a in entries[row['key']]['packet']['selected_anchors'])
        if (row.get('original_label') != wrong[row['key']]['gold']
                or row.get('model_label') != wrong[row['key']]['predicted']
                or row.get('gold_action') != 'unchanged' or row.get('human_verdict') is not None
                or row.get('human_note') is not None or not row.get('evidence_quotes')
                or any(not isinstance(q, str) or not q.strip() or q not in source for q in row['evidence_quotes'])):
            raise ValueError('untraceable_or_adjudicated_review')


def request_for(packet):
    return dict(model=PROPOSAL['model'], messages=v2.review_messages(packet), temperature=0,
                max_tokens=PROPOSAL['max_tokens'], response_format={'type': 'json_object'},
                extra_body={'enable_thinking': False}, stream=False)


def build_preparation():
    frozen = verify_history()
    review = read(REVIEW)
    validate_review(review)
    groups = [('scifact', read(SCI_BASE / 'entries.json')),
              ('selected_claim_regression', read(CLAIM_LIVE / 'entries.json'))]
    gold = {r['key']: r for r in read(SCI_BASE / 'gold.json')}
    entries, labels = [], []
    for group, rows in groups:
        if len(rows) != (30 if group == 'scifact' else 22):
            raise ValueError('denominator_drift')
        for row in rows:
            packet = v2.from_v1_packet(row['packet'])
            prefix = 'SCIFACT' if group == 'scifact' else 'REGRESSION'
            key = f"{prefix}-{row['key']}"
            entries.append(dict(key=key, group=group, original_key=row['key'],
                                v1_packet_id=row['packet']['packet_id'], packet=packet,
                                messages=v2.review_messages(packet)))
            labels.append(dict(key=key, group=group,
                               gold_label=gold[row['key']]['label'] if group == 'scifact' else None,
                               label_source='frozen_scifact_dev' if group == 'scifact' else 'no_human_gold',
                               human_verdict=None))
    if len({r['key'] for r in entries}) != 52:
        raise ValueError('duplicate_input')
    verify(ROOT, frozen)
    counts = Counter(c['kind'] for row in entries for c in row['packet']['risk_cues'])
    return dict(entries=entries, labels=labels, disagreement_review=review, source_sha256=frozen,
                summary=dict(status='prepared_not_run', version=v2.VERSION, cases=52,
                             groups={g: len(rows) for g, rows in groups}, provider_calls=0,
                             risk_cue_occurrences=dict(counts),
                             claims_with_generalization_cue=sum(any(c['kind'] == 'generalization' for c in r['packet']['risk_cues']) for r in entries),
                             claims_with_condition_cue=sum(any(c['kind'] == 'condition' for c in r['packet']['risk_cues']) for r in entries),
                             required_checks_per_claim=3,
                             semantic_accuracy=None, false_accept_rate=None,
                             input_evidence_unchanged=True, labels_changed=False,
                             total_prompt_characters=sum(len(m['content']) for r in entries for m in r['messages']),
                             future_call_proposal=PROPOSAL))


def prepare(out=OUT):
    out = Path(out)
    if out.exists():
        raise FileExistsError('preparation_already_exists')
    value = build_preparation()
    frozen = dict(value['source_sha256'])
    own = ['backend/chat/qualified_claim_support.py', 'tests/test_qualified_claim_support.py',
           'tests/integration/prepare_qualified_claim_support.py', 'tests/test_prepare_qualified_claim_support.py',
           'docs/specs/qualified_claim_support/acceptance.md', 'tests/traceability/qualified_claim_support/coverage.py',
           REVIEW.relative_to(ROOT).as_posix()]
    for name in own:
        frozen[name] = digest(ROOT / name)
    out.mkdir(parents=True, exist_ok=False)
    for name in ('entries', 'labels', 'disagreement_review', 'summary'):
        write(out / f'{name}.json', value[name])
    for row in value['entries']:
        write(out / f"request-{row['key']}.json", request_for(row['packet']))
    write(out / 'manifest.json', dict(version=v2.VERSION, cases=52, keys=[r['key'] for r in value['entries']],
          source_sha256=frozen, artifacts_sha256={p.name: digest(p) for p in out.glob('*.json')},
          future_call_proposal=PROPOSAL))
    return value['summary']


def verify_prepared(out=OUT):
    out = Path(out)
    manifest = read(out / 'manifest.json')
    verify(ROOT, manifest['source_sha256']); verify(out, manifest['artifacts_sha256'])
    if manifest['version'] != v2.VERSION or manifest['cases'] != 52 or manifest['future_call_proposal'] != PROPOSAL:
        raise ValueError('preparation_protocol_drift')
    rebuilt = build_preparation()
    for name in ('entries', 'labels', 'disagreement_review', 'summary'):
        if read(out / f'{name}.json') != rebuilt[name]:
            raise ValueError('offline_replay_drift')
    if manifest['keys'] != [r['key'] for r in rebuilt['entries']]:
        raise ValueError('key_order_drift')
    for row in rebuilt['entries']:
        if read(out / f"request-{row['key']}.json") != request_for(row['packet']):
            raise ValueError('request_drift')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'verify'))
    args = parser.parse_args()
    result = prepare() if args.stage == 'prepare' else dict(status='verified', cases=verify_prepared()['cases'], provider_calls=0)
    print(json.dumps(result, ensure_ascii=False, indent=2))
