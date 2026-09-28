"""Offline v3 preparation and explicitly synthetic adapters; NO live runner."""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.chat import qualified_evidence_ids as v3
from backend.chat import qualified_claim_support_v21 as v21
from backend.chat.quote_alignment import align_quote
from backend.chat.claim_bound_answer import _pairs
from tests.integration import run_qualified_support_remaining as previous
from tests.integration.run_selected_claim_support_live import read, digest, verify, write

OUT = ROOT / 'output/qualified-evidence-ids-v3'
PREVIOUS_SUMMARY_SHA256 = '8b2add6c861f6b87fd72b91fa79839de3be228957e21892fdbea52399c8c5796'
PROPOSAL = dict(model='qwen3-vl-plus', max_calls=52, max_tokens=1500, temperature=0,
                max_retries=0, timeout_seconds=60, approved=False,
                execution='not_implemented_no_calls_in_preparation')
OWN = ('backend/chat/qualified_evidence_ids.py', 'tests/test_qualified_evidence_ids.py',
       'tests/integration/prepare_qualified_evidence_ids.py', 'tests/test_prepare_qualified_evidence_ids.py',
       'docs/specs/qualified_evidence_ids/acceptance.md', 'tests/traceability/qualified_evidence_ids/coverage.py')


def request_for(packet):
    return dict(model=PROPOSAL['model'], messages=v3.review_messages(packet), temperature=0,
                max_tokens=1500, response_format={'type': 'json_object'},
                extra_body={'enable_thinking': False}, stream=False)


def adapt_for_simulation(raw, old_packet, new_packet):
    """TEST ADAPTER, not a parser fallback or a semantic re-review.

    Deliberately discard old quote selections in favor of WHOLE cited anchors.
    This changes citation granularity and is not equivalent to the old response.
    Only the offline preparation command calls this function.
    """
    anchors = previous.base.v2._validate_packet(old_packet)
    v3._validate_packet(new_packet)
    if new_packet['base_packet'] != old_packet['base_packet']:
        raise ValueError('simulation_evidence_drift')
    try:
        if not isinstance(raw, str) or len(raw) > 24000:
            raise ValueError('invalid_simulation_input')
        obj = json.loads(raw, object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
        if (not isinstance(obj, dict) or set(obj) != {'packet_id', 'claim_id', 'checks'}
                or obj['packet_id'] != old_packet['packet_id']
                or obj['claim_id'] != old_packet['base_packet']['claim_id']
                or not isinstance(obj['checks'], dict) or set(obj['checks']) != set(previous.base.v2.FACETS)):
            raise ValueError('invalid_simulation_identity')
        injected, collapsed = copy.deepcopy(obj), 0
        injected['packet_id'] = new_packet['packet_id']
        for check in injected['checks'].values():
            if not isinstance(check, dict) or 'citations' not in check:
                raise ValueError('invalid_old_check')
            citations = check.pop('citations')
            if not isinstance(citations, list) or len(citations) > 3 or 'evidence_ids' in check:
                raise ValueError('invalid_old_citations')
            ids = []
            for citation in citations:
                if (not isinstance(citation, dict) or set(citation) != {'anchor_id', 'quote'}
                        or not isinstance(citation['anchor_id'], str) or citation['anchor_id'] not in anchors
                        or not isinstance(citation['quote'], str) or not citation['quote'].strip()
                        or len(citation['quote']) > 1200):
                    raise ValueError('invalid_old_citation')
                if citation['anchor_id'] not in ids:
                    ids.append(citation['anchor_id'])
                else:
                    collapsed += 1
            check['evidence_ids'] = ids
        raw_injected = json.dumps(injected, ensure_ascii=False)
        v3.parse_decision(raw_injected, new_packet)
        return dict(injected_response=raw_injected, duplicate_citations_collapsed=collapsed)
    except (KeyError, TypeError, RecursionError, OverflowError) as exc:
        raise ValueError('invalid_simulation_input') from exc


def _simulation(entry, old_entry, result, source):
    if result.get('finish_reason') != 'stop' or result.get('provider_refusal'):
        raise ValueError('incomplete_saved_response')
    raw, packet = result['raw_content'], entry['packet']
    try:
        v3.parse_decision(raw, packet)
    except ValueError:
        rejected = True
    else:
        raise ValueError('old_response_unexpectedly_accepted')
    old_error = None
    try:
        v21.parse_decision(raw, old_entry['packet'])
    except ValueError as exc:
        old_error = str(exc)
    anchors = previous.base.v2._validate_packet(old_entry['packet'])
    audit = []
    for facet, check in json.loads(raw)['checks'].items():
        for index, c in enumerate(check['citations']):
            a = anchors[c['anchor_id']]
            item = dict(facet=facet, index=index, anchor_id=c['anchor_id'])
            try:
                matched = align_quote(c['quote'], a['text'], source_start=a['start'])
                item['match_mode'] = matched['match_mode']
            except ValueError as exc:
                item['error'] = str(exc)
            audit.append(item)
    simulation = adapt_for_simulation(raw, old_entry['packet'], packet)
    return dict(key=entry['key'], origin='schema_adapter_simulation_not_model_review',
                source_result=source.relative_to(ROOT).as_posix(), source_sha256=digest(source),
                raw_response_sha256=hashlib.sha256(raw.encode('utf-8')).hexdigest(),
                original_status=result['status'], old_v21_error=old_error, old_quote_audit=audit,
                unmodified_old_rejected=rejected, new_provider_calls=0, human_verdict=None,
                **simulation, decision=v3.parse_decision(simulation['injected_response'], packet))


def build_preparation():
    if digest(previous.OUT / 'summary.json') != PREVIOUS_SUMMARY_SHA256:
        raise ValueError('frozen_remaining_summary_drift')
    old_remaining = previous.preflight(previous.OUT, True, 51)
    previous.verify_summary(previous.OUT, old_remaining)
    old_entries = read(previous.BASE / 'entries.json')
    entries = [dict(key=e['key'], group=e['group'], original_key=e['original_key'],
                    v1_packet_id=e['packet']['base_packet']['packet_id'],
                    packet=v3.from_v1_packet(e['packet']['base_packet'])) for e in old_entries]
    if (len(entries) != 52 or len({e['key'] for e in entries}) != 52
            or Counter(e['group'] for e in entries) != {'scifact': 30, 'selected_claim_regression': 22}):
        raise ValueError('cohort_drift')
    labels = read(previous.BASE / 'labels.json')
    saved = {}
    for directory in (previous.BASE, previous.OUT):
        for r in read(directory / 'results.json'):
            if r['key'] in saved:
                raise ValueError('duplicate_historical_response')
            saved[r['key']] = r, directory / f"result-{r['key']}.json"
    if len(saved) != 6:
        raise ValueError('historical_response_count_drift')
    old_lookup = {e['key']: e for e in old_entries}
    simulations = [_simulation(e, old_lookup[e['key']], *saved[e['key']]) for e in entries if e['key'] in saved]
    summary = dict(version=v3.VERSION, status='offline_prepared_not_run', cases=52,
                   groups=dict(Counter(e['group'] for e in entries)), new_provider_calls=0,
                   v3_live_responses=0, v3_not_run=52, historical_responses=len(saved),
                   simulated_contract_valid=len(simulations), unmodified_old_rejected=len(simulations),
                   semantic_accuracy=None, input_evidence_unchanged=True, labels_changed=False,
                   semantic_policy_changed=False, citation_granularity='selected_anchor',
                   human_verified=False, production_enabled=False, future_call_proposal=PROPOSAL,
                   total_prompt_characters=sum(len(m['content']) for e in entries for m in request_for(e['packet'])['messages']),
                   note='Six explicit schema-adapter simulations are not six v3 model runs or semantic improvements.')
    return dict(entries=entries, labels=labels, simulations=simulations, summary=summary)


def prepare(out=OUT):
    out = Path(out)
    if out.exists():
        raise FileExistsError('preparation_already_exists')
    value = build_preparation()
    frozen = dict(read(previous.OUT / 'manifest.json')['source_sha256'])
    for path in previous.OUT.glob('*.json'):
        frozen[path.relative_to(ROOT).as_posix()] = digest(path)
    for name in OWN:
        frozen[name] = digest(ROOT / name)
    verify(ROOT, frozen)
    out.mkdir(parents=True, exist_ok=False)
    for name in ('entries', 'labels', 'simulations', 'summary'):
        write(out / f'{name}.json', value[name])
    for entry in value['entries']:
        write(out / f"request-{entry['key']}.json", request_for(entry['packet']))
    write(out / 'manifest.json', dict(version=v3.VERSION, future_call_proposal=PROPOSAL,
          keys=[e['key'] for e in value['entries']], source_sha256=frozen,
          artifacts_sha256={p.name: digest(p) for p in out.glob('*.json')}))
    return value['summary']


def verify_prepared(out=OUT):
    out = Path(out); manifest = read(out / 'manifest.json')
    if manifest.get('version') != v3.VERSION or manifest.get('future_call_proposal') != PROPOSAL:
        raise ValueError('id_protocol_drift')
    verify(ROOT, manifest['source_sha256']); verify(out, manifest['artifacts_sha256'])
    rebuilt = build_preparation()
    for name in ('entries', 'labels', 'simulations', 'summary'):
        if read(out / f'{name}.json') != rebuilt[name]:
            raise ValueError('offline_rebuild_drift')
    if manifest['keys'] != [e['key'] for e in rebuilt['entries']]:
        raise ValueError('cohort_order_drift')
    for entry in rebuilt['entries']:
        if read(out / f"request-{entry['key']}.json") != request_for(entry['packet']):
            raise ValueError('request_drift')
    return rebuilt['summary']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'verify'))
    args = parser.parse_args()
    print(json.dumps(prepare() if args.stage == 'prepare' else verify_prepared(), ensure_ascii=False, indent=2))
