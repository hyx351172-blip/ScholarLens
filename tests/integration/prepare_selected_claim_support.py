"""Offline-only, write-once development corpus. No API or credential imports."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat.selected_claim_support import prepare_review, review_messages

LIVE = ROOT / 'output/evidence-units-live-v1'
DRAFT = ROOT / 'docs/evaluation/evidence-units-live-v1-review.json'
IDS = ('B01', 'L01', 'L03', 'X02', 'A04', 'E01')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_history():
    manifest, summary = read(LIVE / 'manifest.json'), read(LIVE / 'summary.json')
    checks = {}
    for base, hashes in ((ROOT, manifest['file_sha256']), (LIVE, summary['artifacts_sha256'])):
        for name, expected in hashes.items():
            path = (base / name).resolve()
            if not path.is_relative_to(base.resolve()) or digest(path) != expected:
                raise ValueError('historical_artifact_drift: ' + name)
            checks[path.relative_to(ROOT).as_posix()] = expected
    checks['output/evidence-units-live-v1/summary.json'] = digest(LIVE / 'summary.json')
    checks[DRAFT.relative_to(ROOT).as_posix()] = digest(DRAFT)
    return checks


def build_corpus():
    checks = verify_history()
    cases, draft = read(LIVE / 'inputs.json'), read(DRAFT)
    if tuple(c['id'] for c in cases) != IDS:
        raise ValueError('case_selection_drift')
    notes = {(r['case'], r['claim_id']): r for r in draft['claims']}
    if len(notes) != len(draft['claims']):
        raise ValueError('duplicate_draft_review')
    packets, cards, controls = [], [], []
    for case in cases:
        result = read(LIVE / f"result-{case['id']}.json")
        if result['id'] != case['id'] or result['status'] != 'ok':
            raise ValueError('invalid_saved_result')
        plan = prepare_review(case['query'], case['documents'], result['raw_content'])
        if plan['candidate_answer'] != result['answer'] or plan['status'] != result['guard_status']:
            raise ValueError('historical_answer_replay_drift')
        if plan['packets'] and plan['binding'] != result['binding']:
            raise ValueError('historical_binding_replay_drift')
        if not plan['packets']:
            if case['id'] not in ('A04', 'E01'):
                raise ValueError('unexpected_missing_positive')
            controls.append(dict(case_id=case['id'], status=plan['status'],
                                 original_answer=result['answer'], review_needed=False))
        for p in plan['packets']:
            key = case['id'], p['claim_id']
            if key not in notes:
                raise ValueError('missing_draft_review')
            packets.append(dict(case_id=case['id'], packet=p, messages=review_messages(p)))
            cards.append(dict(case_id=case['id'], claim_id=p['claim_id'], packet_id=p['packet_id'],
                              claim=p['claim'], selected_anchors=p['selected_anchors'],
                              ai_draft_assessment=notes[key]['assessment'], ai_draft_note=notes[key]['note'],
                              human_verdict=None, human_note=None))
    if len(packets) != 22 or len(notes) != 22 or len(controls) != 2:
        raise ValueError('denominator_drift')
    # Ensure nothing changed while deriving the corpus.
    if verify_history() != checks:
        raise ValueError('concurrent_history_drift')
    return dict(packets=packets, review_cards=cards, controls=controls, source_sha256=checks,
                summary=dict(experiment='selected-claim-support-v1', cases=6, claims=len(packets),
                             controls=len(controls), provider_calls=0,
                             selected_anchor_occurrences=sum(len(p['packet']['selected_anchors']) for p in packets),
                             semantic_accuracy=None, human_review_status='pending',
                             scope='Development replay and packet preparation, NOT semantic evaluation'))


def export_corpus(out):
    value = build_corpus()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    def save(name, obj):
        with (out / name).open('x', encoding='utf-8') as handle:
            json.dump(obj, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
    for name in ('packets', 'review_cards', 'controls', 'summary'):
        save(name + '.json', value[name])
    sources = dict(value['source_sha256'])
    for name in ('backend/chat/selected_claim_support.py', 'tests/integration/prepare_selected_claim_support.py',
                 'tests/test_selected_claim_support.py', 'docs/specs/selected_claim_support/acceptance.md',
                 'tests/traceability/selected_claim_support/coverage.py'):
        sources[name] = digest(ROOT / name)
    save('manifest.json', dict(source_sha256=sources, artifacts_sha256={
        p.name: digest(p) for p in sorted(out.glob('*.json'))}))
    return value['summary']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/selected-claim-support-v1')
    args = parser.parse_args()
    print(json.dumps(export_corpus(args.output), ensure_ascii=False, indent=2))
