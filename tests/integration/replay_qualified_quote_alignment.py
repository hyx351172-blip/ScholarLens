"""Zero-call v2.1 replay of saved v2 responses; never resume the stopped run."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat import qualified_claim_support_v21 as v21
from tests.integration import run_qualified_claim_support_live as live
from tests.integration.run_selected_claim_support_live import read, digest, verify, write

BASE = live.OUT
OUT = ROOT / 'output/qualified-quote-alignment-replay-v21'
BASE_SUMMARY_SHA256 = '4fd1aafe09317d4dc5d10c766073ce8fa7da193a8ca8e9beb366d65339a5349c'


def build_replay():
    if digest(BASE / 'summary.json') != BASE_SUMMARY_SHA256:
        raise ValueError('frozen_v2_summary_drift')
    # These are local validators only; never call live.run() or make_client().
    entries = live.preflight(BASE, True, 52)
    original = live.verify_summary(BASE, entries)
    rows = {r['key']: r for r in read(BASE / 'results.json')}
    cases, matches = [], Counter()
    for entry in entries:
        key = entry['key']; old = rows.get(key)
        case = dict(key=key, group=entry['group'], original_status=old['status'] if old else 'not_run',
                    replay_status='not_run', decision=None, human_verdict=None)
        if old:
            source = BASE / f'result-{key}.json'
            case.update(source_result=source.relative_to(ROOT).as_posix(), source_sha256=digest(source),
                        raw_response_sha256=hashlib.sha256(old['raw_content'].encode('utf-8')).hexdigest()
                        if isinstance(old.get('raw_content'), str) else None)
            if old.get('finish_reason') != 'stop' or old.get('provider_refusal') or not isinstance(old.get('raw_content'), str):
                case['replay_status'] = 'unavailable_response'
            else:
                try:
                    result = v21.parse_decision(old['raw_content'], entry['packet'])
                    case.update(replay_status='contract_valid', decision=result)
                    matches.update(c['match_mode'] for check in result['checks'].values() for c in check['citations'])
                except ValueError as exc:
                    case.update(replay_status='contract_invalid', error_code=str(exc))
        cases.append(case)
    states = Counter(c['replay_status'] for c in cases)
    summary = dict(version=v21.VERSION, status='offline_replay_completed', planned_claims=len(entries),
                   saved_responses=len(rows), original_v2_contract_valid=original['reviewed_claims'],
                   original_v2_errors=original['errors'], v21_contract_valid=states['contract_valid'],
                   v21_contract_invalid=states['contract_invalid'], unavailable_responses=states['unavailable_response'],
                   not_run=states['not_run'], new_provider_calls=0, citation_match_counts=dict(matches),
                   semantic_accuracy=None, human_verified=False, production_enabled=False,
                   baseline_summary_sha256=BASE_SUMMARY_SHA256,
                   note='Local reinterpretation of saved output, not a new live result or retroactive v2 score.')
    return dict(summary=summary, cases=cases)


def export(out=OUT):
    out = Path(out)
    if out.exists():
        raise FileExistsError('replay_already_exists')
    replay = build_replay()
    frozen = dict(read(BASE / 'manifest.json')['source_sha256'])
    for path in BASE.glob('*.json'):
        frozen[path.relative_to(ROOT).as_posix()] = digest(path)
    for name in ('backend/chat/quote_alignment.py', 'backend/chat/qualified_claim_support_v21.py',
                 'tests/integration/replay_qualified_quote_alignment.py',
                 'tests/test_qualified_quote_alignment.py', 'tests/test_qualified_quote_alignment_replay.py',
                 'docs/specs/qualified_quote_alignment/acceptance.md',
                 'tests/traceability/qualified_quote_alignment/coverage.py'):
        frozen[name] = digest(ROOT / name)
    verify(ROOT, frozen)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'replay.json', replay)
    write(out / 'summary.json', replay['summary'])
    write(out / 'manifest.json', dict(version=v21.VERSION, source_sha256=frozen,
          artifacts_sha256={p.name: digest(p) for p in out.glob('*.json')}, new_provider_calls=0))
    return replay['summary']


def verify_export(out=OUT):
    out = Path(out)
    manifest = read(out / 'manifest.json')
    if manifest['version'] != v21.VERSION or manifest['new_provider_calls'] != 0:
        raise ValueError('replay_protocol_drift')
    verify(ROOT, manifest['source_sha256']); verify(out, manifest['artifacts_sha256'])
    replay = build_replay()
    if read(out / 'replay.json') != replay or read(out / 'summary.json') != replay['summary']:
        raise ValueError('offline_replay_drift')
    return replay['summary']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('replay', 'verify'))
    args = parser.parse_args()
    print(json.dumps(export() if args.stage == 'replay' else verify_export(), ensure_ascii=False, indent=2))
