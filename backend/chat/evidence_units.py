"""Opt-in, lossless evidence units. Boundary heuristics are NOT entailment.

Old catalog/output modules remain unchanged for historical experiment replay.
No retrieval, rewriting, implicit citation expansion or network work occurs here.
"""
import json
import re

try:
    from backend.chat import claim_bound_answer as original
    from backend.chat import claim_bound_output_v2 as output
except ModuleNotFoundError:  # Direct service launch.
    import claim_bound_answer as original
    import claim_bound_output_v2 as output


VERSION = 'sentence_v2'
INCOMPLETE_SELECTION = '模型引用的原文续段不完整，本次未展示答案。请重试。'
ABBREVIATIONS = re.compile(
    r'\b(?:e\.g\.|i\.e\.|et al\.|Figs?\.|Eqs?\.|Secs?\.|Dr\.|Prof\.|vs\.|etc\.|No\.)'
    r'|\.{2,}', re.I)
URL = re.compile(r'(?:https?://|www\.|doi:)\S+', re.I)
ROW = re.compile(r'^[ \t]*(?:\|[^\n]*\|[ \t]*|#{1,6}[ \t]+[^\n]*)\r?$', re.M)

POLICY = original.POLICY.replace('S1:E0001', 'S1:U0001') + '''
本次 evidence_catalog_version 为 sentence_v2。U 编号表示原文句/段单元，P 编号表示过长单元的续段。
不要把旧 E 编号用于本次回答。单元边界是程序启发式，不代表内容完整或结论已被验证。
仅回答问题所需的事实，不额外补充无关公式或参数细节。逐条核对本条的数值、维度、
采样条件、否定词和比较对象：它们必须实际出现在本条显式选择的证据中，或者由这些证据
明确支持；信息在其他未选择单元、其他结论引用或模型记忆中都不算本条证据。
同一条同时谈维度和初始化时，应显式选择分别包含这些事实的全部必要单元，或省略无依据细节。
若选择 parts>1 的片段，必须在这一条 evidence_ids 中列出该 unit_id 的所有 parts。
程序不会补上相邻引用，也不能借另一条的引用。仍遵守每条最多 8 个编号，容纳不下时省略该结论。
区分训练样本的采样比例与模型作出预测的概率；不要把本研究的适配范围说成方法的默认或普遍限制。
分式或运算符在原文不清晰时省略该细节，不要补写除号、乘号或依靠常识还原公式。
以上核对只用于选择和删减结论，不输出核对过程；输出字段仍只有 status、claims、text、evidence_ids。
'''


def _protection(text):
    chars, cuts = bytearray(len(text)), bytearray(len(text)+1)
    spans = [(m.start(), m.end()) for regex in (original.MATH, ABBREVIATIONS)
             for m in regex.finditer(text)]
    spans.extend((m.start(), m.start()+len(m.group().rstrip('.,;!?。！？；')))
                 for m in URL.finditer(text))
    for start, end in spans:
        chars[start:end] = b'\1'*(end-start)
        cuts[start+1:end] = b'\1'*max(0, end-start-1)
    return chars, cuts


def unit_spans(text):
    """Ordered source spans; soft line breaks aren't paragraph boundaries."""
    protected, unsafe = _protection(text)
    ends = {len(text)}
    for match in ROW.finditer(text):
        start, end = match.span()
        if unsafe[start] or unsafe[end]:
            continue
        ends.update((start, end+1 if end < len(text) and text[end] == '\n' else end))
        # Rows/headings stay atomic here; long rows may be explicitly fragmented later.
        protected[start:end] = b'\1'*(end-start)
    for match in re.finditer(r'\n[ \t\r]*\n(?:[ \t\r]*\n)*', text):
        if not unsafe[match.end()]:
            ends.add(match.end())
    for i, char in enumerate(text):
        if protected[i]:
            continue
        terminal = char in '。！？!?'
        if char == '.':
            # Internal decimal/version/name periods aren't sentence boundaries.
            terminal = i+1 == len(text) or text[i+1].isspace() or text[i+1] in '\"\'”’)]}'
        if terminal:
            end = i+1
            while end < len(text) and text[end] in '\"\'”’)]}':
                end += 1
            while end < len(text) and text[end].isspace():
                end += 1
            if not unsafe[end]:
                ends.add(end)
    spans, start = [], 0
    for end in sorted(ends):
        if end <= start:
            continue
        if not text[start:end].strip():
            if spans:
                spans[-1] = (spans[-1][0], end)
                start = end
            continue
        spans.append((start, end))
        start = end
    return spans


def _parts(text, start, end, max_chars, unsafe):
    result = []
    while start < end:
        stop = min(end, start+max_chars)
        if stop < end:
            whitespace = [p for p in range(start+1, stop+1)
                          if text[p-1].isspace() and not unsafe[p]]
            if whitespace:
                stop = whitespace[-1]
            else:
                while stop > start and unsafe[stop]:
                    stop -= 1
            if stop == start:
                raise ValueError('protected_span_too_long')
        result.append((start, stop))
        if len(result) > 8:
            raise ValueError('too_many_unit_parts')
        start = stop
    return result


def build_catalog(documents, max_chars=960, max_anchors=1600):
    if type(max_chars) is not int or not 16 <= max_chars <= 4096:
        raise ValueError('invalid_anchor_size')
    if type(max_anchors) is not int or not 1 <= max_anchors <= 1600:
        raise ValueError('invalid_catalog_limit')
    # Reuse the historical input validation, not its cuts or IDs.
    original.build_catalog(documents)
    catalog = []
    for index, doc in enumerate(documents, 1):
        text, source = doc['chunk_text'], f'S{index}'
        _, unsafe = _protection(text)
        for unit, (start, end) in enumerate(unit_spans(text), 1):
            parts = _parts(text, start, end, max_chars, unsafe)
            unit_id = f'{source}:U{unit:04d}'
            for part, (lo, hi) in enumerate(parts, 1):
                anchor = unit_id if len(parts) == 1 else f'{unit_id}:P{part:02d}'
                catalog.append(dict(anchor_id=anchor, source_id=source, filename=doc.get('filename',''),
                    start=lo, end=hi, text=text[lo:hi], unit_id=unit_id, part=part, parts=len(parts)))
                if len(catalog) > max_anchors:
                    raise ValueError('evidence_catalog_too_large')
    return catalog


def build_messages(question, catalog, history=(), preference=None):
    messages = original.build_messages(question, catalog, history, preference)
    payload = json.loads(messages[1]['content'])
    payload['evidence_catalog_version'] = VERSION
    return [dict(role='system', content=POLICY),
            dict(role='user', content=json.dumps(payload, ensure_ascii=False))]


def render_claim_answer(raw, catalog):
    answer, binding = output.render_claim_answer(raw, catalog)
    binding['evidence_catalog_version'] = VERSION
    if binding['status'] != 'claim_bound_passed':
        return answer, binding
    lookup = {a['anchor_id']: a for a in catalog}
    members = {}
    for a in catalog:
        members.setdefault(a['unit_id'], set()).add(a['anchor_id'])
    for claim in binding['claims']:
        selected = {a['anchor_id'] for a in claim['evidence']}
        if any(not members[lookup[anchor]['unit_id']] <= selected for anchor in selected):
            rejected = output.empty_binding('incomplete_evidence_unit')
            rejected['evidence_catalog_version'] = VERSION
            return INCOMPLETE_SELECTION, rejected
        for evidence in claim['evidence']:
            original_anchor = lookup[evidence['anchor_id']]
            evidence.update({key: original_anchor[key] for key in ('unit_id','part','parts')})
    return answer, binding
