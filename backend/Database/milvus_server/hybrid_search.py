"""Dependency-free lexical ranking and score-safe Dense/BM25 fusion.

This is an application-side BM25 index, not a Milvus sparse-vector schema.
It deliberately does not import Milvus, load credentials or call an API.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any

TOKENIZER_VERSION = 'nfkc-casefold-words-cjk-bigrams-v1'
_TOKENS = re.compile(r'[\u3400-\u9fff]+|[^\W_\u3400-\u9fff]+', re.UNICODE)


def tokenize(text: str) -> list[str]:
    words = _TOKENS.findall(unicodedata.normalize('NFKC', str(text or '')).casefold())
    tokens: list[str] = []
    for word in words:
        if '\u3400' <= word[0] <= '\u9fff' and len(word) > 1:
            tokens.extend(word[index:index+2] for index in range(len(word)-1))
        else:
            tokens.append(word)
    return tokens


def identity(document: dict[str, Any]) -> str:
    # A Milvus row's primary id uniquely identifies the same row on both routes.
    if document.get('id') is not None:
        return str(document['id'])
    metadata = document.get('metadata') or {}
    chunk_id = metadata.get('chunk_id')
    if not chunk_id:
        raise ValueError('retrieval candidate has no stable id')
    file_id = document.get('file_id') or document.get('filename') or metadata.get('file_id', '')
    return f'{file_id}:{chunk_id}'


class BM25Index:
    def __init__(self, documents: list[dict[str, Any]], *, k1: float = 1.2, b: float = .75):
        if not math.isfinite(k1) or k1 <= 0 or not math.isfinite(b) or not 0 <= b <= 1:
            raise ValueError('invalid BM25 parameters')
        self.k1, self.b = k1, b
        self.documents = list(documents)
        self.ids = [identity(document) for document in documents]
        if len(self.ids) != len(set(self.ids)):
            raise ValueError('duplicate corpus row identity')
        self.lengths: list[int] = []
        self.postings: dict[str, dict[int, int]] = defaultdict(dict)
        for position, document in enumerate(documents):
            frequencies = Counter(tokenize(document.get('chunk_text', '')))
            self.lengths.append(sum(frequencies.values()))
            for token, frequency in frequencies.items():
                self.postings[token][position] = frequency
        self.average_length = sum(self.lengths) / len(documents) if documents else 0.0

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        if top_k <= 0:
            raise ValueError('top_k must be positive')
        scores: dict[int, float] = defaultdict(float)
        n = len(self.documents)
        for token in sorted(set(tokenize(query))):
            postings = self.postings.get(token, {})
            if not postings:
                continue
            df = len(postings)
            idf = math.log1p((n - df + .5) / (df + .5))
            for position, frequency in postings.items():
                norm = 1 - self.b + self.b * self.lengths[position] / (self.average_length or 1)
                scores[position] += idf * frequency * (self.k1 + 1) / (frequency + self.k1 * norm)
        ranked = sorted(scores, key=lambda pos: (-scores[pos], self.ids[pos]))[:top_k]
        return [dict(self.documents[pos], bm25_score=scores[pos]) for pos in ranked if scores[pos] > 0]


def fuse_rrf(dense: list[dict[str, Any]], lexical: list[dict[str, Any]], top_k: int,
             *, rrf_k: int = 60) -> list[dict[str, Any]]:
    if rrf_k <= 0 or top_k <= 0:
        raise ValueError('rrf_k and top_k must be positive')
    fused: dict[str, dict[str, Any]] = {}
    for branch, hits in (('dense', dense), ('bm25', lexical)):
        seen: set[str] = set()
        rank = 0
        for document in hits:
            key = identity(document)
            if key in seen:
                continue
            seen.add(key)
            rank += 1
            if key not in fused:
                fused[key] = dict(document, dense_score=None, bm25_score=None,
                                  hybrid_rrf_score=0.0, branch_ranks={},
                                  retrieval_mode='hybrid', score_type='hybrid_rrf')
            item = fused[key]
            item['branch_ranks'][branch] = rank
            item['hybrid_rrf_score'] += 1 / (rrf_k + rank)
            if branch == 'dense':
                item['dense_score'] = float(document['score'])
            else:
                item['bm25_score'] = float(document['bm25_score'])
    for item in fused.values():
        item['score'] = item['hybrid_rrf_score']
    return sorted(fused.values(), key=lambda item: (
        -item['hybrid_rrf_score'], min(item['branch_ranks'].values()), identity(item)))[:top_k]
