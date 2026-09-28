"""Evaluation-only v3.1 subject refinement; no semantic verdicts or retrieval.

Keep v3's unit boundaries, citation ownership and anchor protocol. These narrow
Chinese syntax heuristics are review aids, not a general coreference resolver.
"""
import re

from tests.integration.anchored_claim_audit import prepare_units as prepare_v3
from tests.integration.isolated_claim_audit import _masks, _citation_groups, _sentence_ranges


MATH = re.compile(r'(?<![\\$])\$(?!\$)(?P<body>[^$\n]+)\$(?!\$)')
SYMBOL = re.compile(r'\s*(?P<noun>(?:\\Delta\s+[A-Za-z]|\\[A-Za-z]+|[A-Za-z])(?:_(?:\{[A-Za-z0-9]+\}|[A-Za-z0-9]+))?)')
MATH_PREFIX = re.compile(r'^(?:(?:其中|而|且)[，,]?\s*)?$')
JOINT = re.compile(r'\s*(?:、|与|和|及)\s*')
ALTERNATIVE = re.compile(r'\s*(?:或|或者)\s*')
TASK = re.compile(r'^(?P<noun>[\u4e00-\u9fff]{2,24}(?:任务|模型|学习|检测|重建|预测))'
                  r'\s*(?:[（(][^）)\n]{1,100}[）)]\s*)?[:：]')
SCOPE = re.compile(r'^(?P<noun>(?:当前|本次)(?:(?:检索|召回)(?:到的|的)?)?'
                   r'(?:证据|片段|检索结果))(?=\s*(?:未|仅|描述|包含|涵盖|表明|显示))')
PROPERTY = re.compile(r'^其(?:维度|形状|长度|大小|尺寸)')
INTRODUCE = re.compile(r'(?:加入|引入|生成|输出|构造|得到|采用)(?:了)?\s*')
OBJECT = re.compile(r'[\u4e00-\u9fffA-Za-z0-9_-]{2,32}(?:编码|向量|矩阵|表示|嵌入|特征|分布|张量)')


def _span(unit, start, end, method):
    return dict(text=unit['text'][start:end], start=unit['start']+start,
                end=unit['start']+end, from_unit_id=unit['id'], method=method)


def _symbol(unit, literal):
    match = SYMBOL.match(literal['body'])
    if not match:
        return None
    # A leading character of an unrecognized identifier is not a named entity.
    rest = literal['body'][match.end():]
    if rest and (rest[0].isalnum() or rest[0] == '_'):
        return None
    return _span(unit, literal.start('body')+match.start('noun'),
                 literal.start('body')+match.end('noun'), 'explicit_math_entity')


def _explicit_objects(unit):
    text = unit['text']
    literals = list(MATH.finditer(text))
    if not literals:
        return None
    first = literals[0]
    prefix = text[:first.start()]
    # Ambiguous alternatives must not be collapsed to the first named symbol,
    # even if the frozen v3 heuristic classified it as a single explicit subject.
    if MATH_PREFIX.fullmatch(prefix):
        joined = [first]
        for literal in literals[1:]:
            separator = text[joined[-1].end():literal.start()]
            if ALTERNATIVE.fullmatch(separator):
                return 'unresolved', 'ambiguous_math_alternatives', []
            if not JOINT.fullmatch(separator):
                break
            joined.append(literal)
        entities = [_symbol(unit, m) for m in joined]
        if len(joined) >= 2 and all(entities):
            return 'explicit', 'explicit_coordinated_entities', entities
    if re.fullmatch(r'(?:且|而)?\s*秩\s*', prefix):
        symbol = SYMBOL.match(first['body'])
        if symbol and re.fullmatch(r'\s*(?:\\ll|\\leq|\\geq|<|>|=|≤|≥)\s*\S.*',
                                   first['body'][symbol.end():]):
            entity = _symbol(unit, first)
            if entity:
                return 'explicit', 'explicit_rank_relation', [entity]
    if re.fullmatch(r'(?:且|而)?\s*(?:仅|只)?(?:更新|优化|训练|冻结)(?:可训练)?(?:参数|矩阵|权重)\s*', prefix):
        # Only literal parameter names, not expressions or dangling prose, count.
        entities = []
        for i, literal in enumerate(literals):
            if i and not JOINT.fullmatch(text[literals[i-1].end():literal.start()]):
                return None
            entity = _symbol(unit, literal)
            if not entity or literal['body'].strip() != entity['text']:
                return None
            entities.append(entity)
        if not text[literals[-1].end():].strip(' \t。.!?！？'):
            return 'explicit', 'explicit_operation_objects', entities
    return None


def _antecedent(previous, unit):
    text = previous['text']
    for pattern, method in ((TASK, 'task_label'), (SCOPE, 'retrieved_evidence_scope')):
        match = pattern.match(text)
        if match:
            if method == 'task_label' and re.search(r'[和与或]|以及', match['noun']):
                return None
            return _span(previous, match.start('noun'), match.end('noun'), method)
    if PROPERTY.match(unit['text']):
        verbs = list(INTRODUCE.finditer(text))
        if not verbs:
            return None
        start, end = verbs[-1].end(), len(text.rstrip())
        tail = text[start:end]
        paren = re.search(r'\s*[（(][^）)\n]*[）)]$', tail)
        if paren:
            end = start + paren.start()
            tail = text[start:end]
        # Check the whole introduced object before stripping a modifier: otherwise
        # "固定的 X 与可学习的 Y" would incorrectly become only Y.
        if re.search(r'[和与或、，,；;]|以及', tail):
            return None
        if '的' in tail:
            start += tail.rfind('的')+1
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end-1].isspace():
            end -= 1
        if OBJECT.fullmatch(text[start:end]):
            return _span(previous, start, end, 'introduced_object_property')
    return None


def prepare_units(answer, original_units):
    units = prepare_v3(answer, original_units)
    literal, protected = _masks(answer)
    ranges = list(_sentence_ranges(answer, protected, _citation_groups(answer, literal)))
    previous, last_sentence, rejected = None, None, set()
    for unit in units:
        sentence = next(i for i, (a, b) in enumerate(ranges) if a <= unit['start'] < unit['end'] <= b)
        old_status = unit['subject_status']
        diagnostic = dict(v3_status=old_status, rule='unchanged_v3', entity_spans=[])
        if unit['subject_context'] and unit['subject_context']['from_unit_id'] in rejected:
            unit.update(subject_status='unresolved', subject_context=None)
            diagnostic['rule'] = 'rejected_antecedent'
        explicit = _explicit_objects(unit)
        if explicit and (old_status == 'unresolved' or explicit[0] == 'unresolved'):
            status, rule, entities = explicit
            unit.update(subject_status=status, subject_context=None, detected_subject=None)
            diagnostic.update(rule=rule, entity_spans=entities)
            if status == 'unresolved':
                rejected.add(unit['id'])
        elif old_status == 'unresolved' and previous and sentence == last_sentence:
            hint = _antecedent(previous, unit)
            if hint:
                unit.update(subject_status='inherited', subject_context=hint)
                diagnostic['rule'] = hint['method']
        unit['subject_resolution'] = diagnostic
        for span in diagnostic['entity_spans'] + ([unit['subject_context']] if unit['subject_context'] else []):
            if answer[span['start']:span['end']] != span['text']:
                raise ValueError('subject provenance mismatch')
        previous, last_sentence = unit, sentence
    return units
