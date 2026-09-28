"""Conservative, catalog-grounded document scope, independent of LLM planning.

This is evidence selection, not an authorization boundary. Only explicit catalog
aliases are recognized; semantic title paraphrases are deliberately not guessed.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Sequence


def _normalize(value: str) -> str:
    return re.sub(r'[\s_-]+', ' ', value.casefold()).strip()


def _aliases(document: dict[str, Any]) -> set[str]:
    filename = str(document.get('filename') or '')
    stem = re.sub(r'\.pdf$', '', filename, flags=re.I)
    stem = re.sub(r'^(?:\d{4}\.\d{4,5}(?:v\d+)?|PMC\d+)[_ -]*', '', stem, flags=re.I)
    values = {filename, stem}
    values.add(re.sub(r'[\s_-]+(?:technical[\s_-]+)?(?:report|paper)$', '', stem, flags=re.I))
    for name in ('title', 'paper_title'):
        title = str(document.get(name) or '')
        if title:
            values.update((title, re.split(r'[:：]', title, maxsplit=1)[0]))
    return {_normalize(v) for v in values if len(v.strip()) >= 3}


def _restriction_fragment(query: str) -> tuple[str, bool]:
    # An explicit current-paper restriction precedes baseline models or negated
    # previous turns. Do not narrow a genuine "compare A and B" to its first name.
    query = re.split(r'[。！？;；,，]\s*(?:不要|无需|不用|不再|do not\b|ignore previous\b)', query, maxsplit=1, flags=re.I)[0]
    prefix = re.match(
        r'^\s*(?:请\s*)?(?:(?:仅|只)?(?:依据|根据)|只看|仅使用|(?:现在)?切换到|在(?=[^，,:：]{1,100}(?:论文|摘要))\s*|'
        r'(?:based\s+only\s+on|based\s+on|according\s+to|using\s+only|switch\s+to|in\s+the\s+paper)\s+)',
        query, re.I)
    if prefix:
        rest = query[prefix.end():].strip()
        quoted_name = r'[《“"]([^》”"]+)[》”"]'
        quoted = re.match(quoted_name + r'(?:\s*(?:和|与|、|and|&|,)\s*' + quoted_name + r')*', rest, re.I)
        if quoted:
            return quoted.group(0), True
        fragment = re.split(r'论文|摘要|文章|[:：,，;；?？]|\b(?:paper|abstract)\b', rest, maxsplit=1, flags=re.I)[0]
        return fragment.strip(), True
    # "LoRA 摘要中，相比 ..." is still local to one paper even if the
    # comparison baseline also happens to exist in the corpus.
    local = re.match(r'^(.+?)(?:论文|摘要)(?:中|里)[,，:：\s]*', query)
    if local and not re.search(r'比较|对比|相比|\bcompare\b', local.group(1), re.I):
        return local.group(1), True
    return query, False


@dataclass(frozen=True)
class DocumentScope:
    status: str
    documents: tuple[dict[str, Any], ...] = ()
    reason: str = 'no_explicit_catalog_alias'

    @property
    def file_ids(self) -> tuple[str, ...]:
        return tuple(sorted({str(d['file_id']) for d in self.documents if d.get('file_id')}))

    @property
    def filenames(self) -> tuple[str, ...]:
        return tuple(sorted({str(d['filename']) for d in self.documents}))

    @property
    def filter_expr(self) -> str | None:
        if self.status != 'resolved':
            return None
        clauses = []
        if self.file_ids:
            clauses.append('file_id in ' + json.dumps(self.file_ids, ensure_ascii=False))
        legacy = sorted({d['filename'] for d in self.documents if not d.get('file_id')})
        if legacy:
            clauses.append('filename in ' + json.dumps(legacy, ensure_ascii=False))
        return '(' + ' or '.join(clauses) + ')'

    def allows(self, hit: dict[str, Any]) -> bool:
        if self.status == 'unrestricted':
            return True
        if self.status != 'resolved':
            return False
        metadata = hit.get('metadata') or {}
        file_id = hit.get('file_id') or (metadata.get('file_id') if isinstance(metadata, dict) else None)
        return any((file_id == d['file_id']) if d.get('file_id')
                   else (hit.get('filename') == d['filename']) for d in self.documents)

    def to_dict(self) -> dict[str, Any]:
        return dict(status=self.status, reason=self.reason, file_ids=list(self.file_ids),
                    filenames=list(self.filenames), filter_expr=self.filter_expr)


def resolve_document_scope(query: str, catalog: Sequence[dict[str, Any]]) -> DocumentScope:
    fragment, restricted = _restriction_fragment(query)
    # Collection-relative language isn't the title of a missing paper. Keep
    # scanning the full question so later named comparison targets still count.
    if restricted and re.fullmatch(
        r'(?:这些|所有|全部|上述|提供的|上传的|已有的|(?:当前)?知识库(?:中|里)?(?:的)?|'
        r'(?:these|all|the|the provided|the uploaded) papers?|the knowledge base)',
        fragment.strip(), re.I,
    ):
        fragment, restricted = query, False
    text = _normalize(fragment)
    documents = [d for d in catalog if isinstance(d, dict) and d.get('filename')]
    if restricted:
        for quoted in re.findall(r'[《“"]([^》”"]+)[》”"]', fragment):
            if not any(_normalize(quoted) in _aliases(d) for d in documents):
                return DocumentScope('unresolved', reason='explicit_title_not_in_catalog')
    matches = []
    for index, document in enumerate(documents):
        for alias in _aliases(document):
            pattern = r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])'
            for match in re.finditer(pattern, text):
                matches.append((match.start(), match.end(), index))
    # A full filename/title beats aliases nested inside it, while identical
    # aliases from different documents remain ambiguous rather than first-win.
    matches = [m for m in matches if not any(
        n[0] <= m[0] and n[1] >= m[1] and n[1] - n[0] > m[1] - m[0]
        for n in matches)]
    positions: dict[tuple[int, int], set[int]] = {}
    for start, end, index in matches:
        positions.setdefault((start, end), set()).add(index)
    if any(len(indices) > 1 for indices in positions.values()):
        return DocumentScope('ambiguous', reason='catalog_alias_not_unique')
    selected = sorted({m[2] for m in matches})
    if len(selected) == 1 and not restricted and re.match(r'^\s*(?:请)?(?:比较|对比|compare\b)', query, re.I):
        return DocumentScope('unresolved', reason='incomplete_comparison_scope')
    if selected:
        return DocumentScope('resolved', tuple(documents[i] for i in selected), 'explicit_catalog_alias')
    if restricted:
        return DocumentScope('unresolved', reason='explicit_restriction_not_in_catalog')
    return DocumentScope('unrestricted')
