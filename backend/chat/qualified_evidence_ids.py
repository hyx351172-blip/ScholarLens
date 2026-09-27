"""Opt-in v3: model selects anchor IDs; only code copies text and coordinates.

The v2 semantic instructions and deterministic guards are unchanged. ID validity
proves membership/provenance, never entailment. No client or production wiring.
"""
import copy
import hashlib
import json

from . import qualified_claim_support as v2
from . import selected_claim_support as v1
from .claim_bound_answer import _pairs

VERSION = 'qualified_evidence_ids_v3'
MAX_ANCHOR_CHARS = 64000
SEMANTIC_POLICY, _separator, _old_contract = v2.POLICY.partition('Every entailed or contradicted check requires')
if not _separator:
    raise RuntimeError('v2_policy_boundary_drift')
POLICY = SEMANTIC_POLICY + '''Every entailed or contradicted check requires 1-3 selected evidence_ids.
Missing/uncertain checks may have []. Copy exact anchor_id strings from
base_packet.selected_anchors. Each ID denotes its ENTIRE existing anchor,
not a model-chosen substring. IDs can refer to existing fixed chunks or existing
sentence/paragraph units; do not invent finer sentence IDs. Multiple selected
anchors remain separate sources, never one concatenated quotation.
Do not output quotations, ellipses, offsets, source text or an overall verdict.
Code resolves each ID to the unmodified original anchor and its coordinates.
Unknown, duplicated and unselected IDs fail validation, even for missing checks.
Existence of an ID proves provenance only, not entailment. Reasons are brief
check-specific explanations, not step-by-step reasoning or verified quotations.
Return JSON with exactly:
{"packet_id":"copy OUTER packet_id","claim_id":"copy base_packet.claim_id",
 "checks":{
  "content":{"status":"entailed|contradicted|missing|uncertain","reason":"brief","evidence_ids":["S1:E0001"]},
  "scope":{"status":"entailed|contradicted|missing|uncertain","reason":"brief","evidence_ids":["S1:E0001"],"basis":"explicit_statement|aggregate_evidence|single_example|inference|none","relation":"same_or_narrower|claim_broader|unknown"},
  "conditions":{"status":"entailed|contradicted|missing|uncertain","reason":"brief","evidence_ids":["S1:E0001"]}
 }}
The caller derives the overall verdict from all three checks.'''


def _validate_base(base):
    try:
        if not isinstance(base, dict) or not isinstance(base.get('selected_anchors'), list):
            raise ValueError('invalid_id_base')
        if not 1 <= len(base['selected_anchors']) <= 8:
            raise ValueError('invalid_id_anchor_count')
        for a in base['selected_anchors']:
            if (not isinstance(a, dict) or not isinstance(a.get('anchor_id'), str)
                    or not 1 <= len(a['anchor_id']) <= 128 or not isinstance(a.get('text'), str)
                    or not a['text'].strip() or not 1 <= len(a['text']) <= MAX_ANCHOR_CHARS
                    or not isinstance(a.get('filename', ''), str)):
                raise ValueError('invalid_id_anchor')
        return v1._validate_packet(base)
    except (TypeError, KeyError, AttributeError, RecursionError, OverflowError, UnicodeError) as exc:
        raise ValueError('invalid_id_base') from exc


def _packet_id(packet):
    return v1._digest(dict(policy=POLICY, packet={k: v for k, v in packet.items() if k != 'packet_id'}))


def from_v1_packet(base):
    _validate_base(base)
    packet = dict(version=VERSION, base_packet=copy.deepcopy(base), risk_cues=v2.risk_cues(base['claim']))
    packet['packet_id'] = _packet_id(packet)
    return packet


def _validate_packet(packet):
    try:
        if (not isinstance(packet, dict) or set(packet) != {'version', 'base_packet', 'risk_cues', 'packet_id'}
                or packet['version'] != VERSION):
            raise ValueError('invalid_id_packet')
        anchors = _validate_base(packet['base_packet'])
        if (packet['risk_cues'] != v2.risk_cues(packet['base_packet']['claim'])
                or packet['packet_id'] != _packet_id(packet)):
            raise ValueError('id_packet_drift')
        return anchors
    except (TypeError, KeyError, RecursionError, OverflowError, UnicodeError) as exc:
        raise ValueError('invalid_id_packet') from exc


def prepare_review(question, documents, raw, *, evidence_mode='sentence_v2'):
    plan = v1.prepare_review(question, documents, raw, evidence_mode=evidence_mode)
    return dict(plan, packets=[from_v1_packet(p) for p in plan['packets']])


def review_messages(packet):
    _validate_packet(packet)
    return [dict(role='system', content=POLICY), dict(role='user', content=json.dumps(packet, ensure_ascii=False))]


def _citations(ids, anchors, required):
    if (not isinstance(ids, list) or not (1 if required else 0) <= len(ids) <= 3
            or any(not isinstance(i, str) or i not in anchors for i in ids)
            or len(ids) != len(set(ids))):
        raise ValueError('invalid_selected_evidence_ids')
    return [dict(anchor_id=i, source_id=anchors[i]['source_id'], filename=anchors[i].get('filename', ''),
                 quote=anchors[i]['text'], source_start=anchors[i]['start'], source_end=anchors[i]['end'],
                 granularity='selected_anchor', provenance='program_resolved_id') for i in ids]


def _verdict(checked, cues):
    # Frozen v2 guard rules, independently regression-tested over their full
    # finite state space. Do not weaken them as part of a citation-format change.
    effective = {name: c['status'] for name, c in checked.items()}
    scope, guards = checked['scope'], []
    if scope['relation'] == 'claim_broader':
        if effective['scope'] != 'contradicted':
            effective['scope'] = 'missing'
        guards.append('claim_scope_broader')
    if scope['relation'] == 'unknown' and effective['scope'] == 'entailed':
        effective['scope'] = 'uncertain'
        guards.append('unknown_scope_alignment')
    if scope['basis'] == 'none' and effective['scope'] == 'entailed':
        effective['scope'] = 'missing'
        guards.append('scope_without_basis')
    if any(c['kind'] == 'generalization' for c in cues) and scope['basis'] in ('single_example', 'inference', 'none'):
        if effective['scope'] == 'entailed':
            effective['scope'] = 'missing'
        guards.append('generalization_without_scope_evidence')
    states = set(effective.values())
    verdict, reason = (('unsupported', 'contradicted') if 'contradicted' in states else
                       ('unsupported', 'not_in_evidence') if 'missing' in states else
                       ('uncertain', 'ambiguous_evidence') if 'uncertain' in states else
                       ('supported', 'entailed'))
    return dict(verdict=verdict, reason_code=reason, effective_checks=effective, guard_codes=guards)


def parse_decision(raw, packet):
    anchors = _validate_packet(packet)
    try:
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 24000:
            raise ValueError('invalid_id_response_size')
        obj = json.loads(raw, object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
        if (not isinstance(obj, dict) or set(obj) != {'packet_id', 'claim_id', 'checks'}
                or obj['packet_id'] != packet['packet_id'] or obj['claim_id'] != packet['base_packet']['claim_id']
                or not isinstance(obj['checks'], dict) or set(obj['checks']) != set(v2.FACETS)):
            raise ValueError('invalid_id_response_fields')
        checked = {}
        for name in v2.FACETS:
            value = obj['checks'][name]
            fields = {'status', 'reason', 'evidence_ids'} | ({'basis', 'relation'} if name == 'scope' else set())
            if (not isinstance(value, dict) or set(value) != fields
                    or not isinstance(value['status'], str) or value['status'] not in v2.STATES
                    or not isinstance(value['reason'], str) or not value['reason'].strip() or len(value['reason']) > 600):
                raise ValueError('invalid_id_check')
            if name == 'scope' and (not isinstance(value['basis'], str) or value['basis'] not in v2.BASES
                                    or not isinstance(value['relation'], str) or value['relation'] not in v2.RELATIONS):
                raise ValueError('invalid_id_scope')
            checked[name] = dict(value, citations=_citations(value['evidence_ids'], anchors,
                                                            value['status'] in ('entailed', 'contradicted')))
        return dict(version=VERSION, packet_id=packet['packet_id'], claim_id=obj['claim_id'], checks=checked,
                    **_verdict(checked, packet['risk_cues']), semantic_verified=False, human_verified=False,
                    citation_granularity='selected_anchor', semantic_policy_version=v2.VERSION,
                    raw_response_sha256=hashlib.sha256(raw.encode('utf-8')).hexdigest())
    except (TypeError, KeyError, RecursionError, OverflowError, UnicodeError) as exc:
        raise ValueError('invalid_id_response') from exc


def gate_answer(question, documents, raw, decisions, *, evidence_mode='sentence_v2'):
    plan = prepare_review(question, documents, raw, evidence_mode=evidence_mode)
    result = dict(version=VERSION, status=plan['status'], release_allowed=False,
                  semantic_verified=False, human_verified=False, answer=plan['candidate_answer'], reviews=[])
    if plan['status'] != 'claim_bound_passed':
        return result
    expected = {p['base_packet']['claim_id'] for p in plan['packets']}
    if not isinstance(decisions, dict) or not set(decisions) <= expected:
        result.update(status='review_invalid', answer=v1.REVIEW_UNAVAILABLE)
        return result
    invalid, missing = False, False
    for p in plan['packets']:
        cid = p['base_packet']['claim_id']
        if cid not in decisions:
            missing = True
            result['reviews'].append(dict(claim_id=cid, status='not_reviewed'))
            continue
        try:
            result['reviews'].append(dict(status='ok', **parse_decision(decisions[cid], p)))
        except ValueError:
            invalid = True
            result['reviews'].append(dict(claim_id=cid, status='invalid'))
    verdicts = {r.get('verdict') for r in result['reviews']}
    status = ('review_invalid' if invalid else 'review_incomplete' if missing else
              'review_unsupported' if 'unsupported' in verdicts else
              'review_uncertain' if 'uncertain' in verdicts else 'review_supported')
    result.update(status=status, release_allowed=status == 'review_supported')
    if not result['release_allowed']:
        result['answer'] = v1.REVIEW_UNAVAILABLE if invalid or missing else v1.REVIEW_BLOCKED
    return result
