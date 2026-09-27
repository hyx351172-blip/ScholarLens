"""Opt-in offline v2.1 parser; keep v2 policy, packets and results immutable.

Only uniquely aligned citations are canonicalized in a LOCAL object, then the
unchanged v2 parser enforces structure and computes all semantic decisions.
No prompt/client, monkeypatch, production dispatch or automatic API retry.
"""
import hashlib
import json

from . import qualified_claim_support as v2
from .claim_bound_answer import _pairs
from .quote_alignment import align_quote, VERSION as ALIGNMENT_VERSION

VERSION = 'qualified_claim_support_v2_1'


def parse_decision(raw, packet):
    anchors = v2._validate_packet(packet)
    try:
        if not isinstance(raw, str) or not raw.strip() or len(raw) > 24000:
            raise ValueError('invalid_qualified_decision_size')
        obj = json.loads(raw, object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
        if (not isinstance(obj, dict) or set(obj) != {'packet_id', 'claim_id', 'checks'}
                or obj['packet_id'] != packet['packet_id'] or obj['claim_id'] != packet['base_packet']['claim_id']
                or not isinstance(obj['checks'], dict) or set(obj['checks']) != set(v2.FACETS)):
            raise ValueError('invalid_qualified_decision_fields')
        alignments = {}
        for name in v2.FACETS:
            check = obj['checks'][name]
            if not isinstance(check, dict) or not isinstance(check.get('citations'), list) or len(check['citations']) > 3:
                raise ValueError('invalid_qualified_check')
            alignments[name] = []
            for citation in check['citations']:
                if (not isinstance(citation, dict) or set(citation) != {'anchor_id', 'quote'}
                        or not isinstance(citation['anchor_id'], str) or citation['anchor_id'] not in anchors):
                    raise ValueError('invalid_citation')
                anchor = anchors[citation['anchor_id']]
                aligned = align_quote(citation['quote'], anchor['text'], source_start=anchor['start'])
                alignments[name].append(aligned)
                citation['quote'] = aligned['quote']
        # Do not reconstruct a permissive response: retain all other fields and
        # let v2 reject extra fields, invalid metadata, repeated spans and gates.
        decision = v2.parse_decision(json.dumps(obj, ensure_ascii=False, allow_nan=False), packet)
        for name in v2.FACETS:
            for citation, aligned in zip(decision['checks'][name]['citations'], alignments[name]):
                if (citation['source_start'] != aligned['source_start']
                        or citation['source_end'] != aligned['source_end']):
                    raise ValueError('alignment_offset_mismatch')
                citation.update(model_quote=aligned['model_quote'], match_mode=aligned['match_mode'])
        decision.update(version=VERSION, input_contract_version=v2.VERSION,
                        alignment_version=ALIGNMENT_VERSION,
                        raw_response_sha256=hashlib.sha256(raw.encode('utf-8')).hexdigest())
        return decision
    except (TypeError, KeyError, RecursionError, OverflowError, UnicodeError) as exc:
        raise ValueError('invalid_qualified_aligned_decision') from exc
