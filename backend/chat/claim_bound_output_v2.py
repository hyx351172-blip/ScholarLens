"""Versioned output guard; semicolon clauses are warnings, not missing evidence.

The v1 module stays immutable for frozen experiment replay. This module changes
neither anchor generation nor prompting, and does not verify entailment.
"""
import json
import re

try:
    from backend.chat.claim_bound_answer import MATH, ABBREVIATIONS, MAX_OUTPUT_CHARS, _pairs
    from backend.chat.answer_guard import INSUFFICIENT_EVIDENCE
except ModuleNotFoundError:  # Direct service launch from backend/chat.
    from claim_bound_answer import MATH, ABBREVIATIONS, MAX_OUTPUT_CHARS, _pairs
    from answer_guard import INSUFFICIENT_EVIDENCE


CLAIM_FORMAT_ERROR = '模型回答未通过格式或引用校验，本次未展示答案。请重试。'
CLAIM_EVIDENCE_ERROR = '检索结果未通过输入校验，暂时无法生成回答。请缩小问题范围或重试。'
CLAIM_GENERATION_ERROR = '模型未返回可用的完整回答，本次未展示答案。请重试。'


def empty_binding(status, reason=None):
    value = dict(status=status, version='claim_bound_v2', semantic_verified=False,
                 claims=[], warnings=[])
    if reason:
        value['reason'] = reason
    return value


def _prose(text):
    visible = MATH.sub(lambda m: ' ' * len(m.group()), text)
    return ABBREVIATIONS.sub(lambda m: ' ' * len(m.group()), visible)


def _single_sentence(text):
    visible = _prose(text)
    for i, char in enumerate(visible):
        boundary = char in '。！？!?'
        if char == '.':
            decimal = (i > 0 and i + 1 < len(visible)
                       and visible[i - 1].isdigit() and visible[i + 1].isdigit())
            boundary = not decimal
        if boundary and visible[i + 1:].strip(' \t。.!?！？；;”’"\''):
            return False
    return True


def _compound_clause(text):
    visible = _prose(text)
    return any(char in ';；' and visible[i + 1:].strip(' \t。.!?！？；;”’"\'')
               for i, char in enumerate(visible))


def render_claim_answer(raw, catalog):
    """Hard-check every row before rendering; preserve complete claim text/IDs."""
    try:
        if not isinstance(raw, str) or not raw.strip() or len(raw) > MAX_OUTPUT_CHARS:
            raise ValueError('invalid_output_size')
        obj = json.loads(raw, object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
        if not isinstance(obj, dict) or set(obj) != {'status', 'claims'}:
            raise ValueError('invalid_envelope')
        if obj['status'] == 'insufficient' and obj['claims'] == []:
            return INSUFFICIENT_EVIDENCE, empty_binding('claim_bound_insufficient')
        rows = obj['claims']
        if obj['status'] != 'answered' or not isinstance(rows, list) or not 1 <= len(rows) <= 20:
            raise ValueError('invalid_claims')
        lookup = {a['anchor_id']: a for a in catalog}
        if len(lookup) != len(catalog):
            raise ValueError('duplicate_catalog_id')
        checked, seen = [], set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {'text', 'evidence_ids'}:
                raise ValueError('invalid_claim_fields')
            text, ids = row['text'], row['evidence_ids']
            if not isinstance(text, str) or not text.strip() or len(text) > 1200 or text in seen:
                raise ValueError('invalid_claim_text')
            if (re.search(r'[\x00-\x1f\x7f\u0085\u2028\u2029]|[\[［【]\s*[SsＳｓ]|`|<[^>]+>', text)
                    or re.match(r'\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s)', text)
                    or not _single_sentence(text)):
                raise ValueError('unbound_or_multisentence_text')
            if (not isinstance(ids, list) or not 1 <= len(ids) <= 8
                    or any(not isinstance(i, str) for i in ids)
                    or len(ids) != len(set(ids)) or any(i not in lookup for i in ids)):
                raise ValueError('invalid_evidence_ids')
            seen.add(text)
            checked.append((text, [lookup[i] for i in ids]))
        parts, bound, warnings, offset = [], [], [], 0
        for i, (text, evidence) in enumerate(checked, 1):
            claim_id = f'C{i:03d}'
            source_ids = list(dict.fromkeys(a['source_id'] for a in evidence))
            if parts:
                offset += 2
            bound.append(dict(claim_id=claim_id, text=text, answer_start=offset,
                answer_end=offset + len(text), source_ids=source_ids,
                evidence=[{k: a[k] for k in ('anchor_id', 'source_id', 'start', 'end')} for a in evidence]))
            if _compound_clause(text):
                warnings.append(dict(claim_id=claim_id, code='compound_clause'))
            part = text + ' ' + ''.join(f'[{sid}]' for sid in source_ids)
            parts.append(part)
            offset += len(part)
        meta = empty_binding('claim_bound_passed')
        meta.update(claims=bound, warnings=warnings)
        return '\n\n'.join(parts), meta
    except (ValueError, TypeError, KeyError, RecursionError):
        return CLAIM_FORMAT_ERROR, empty_binding('invalid_claim_structure')
