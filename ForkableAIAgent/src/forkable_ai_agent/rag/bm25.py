"""BM25 in ~60 lines of stdlib Python.

Dense vectors miss exact identifiers - ``data-testid``, ``TimeoutError``,
``getByRole`` - which is exactly the vocabulary of a test corpus. BM25 catches
those, so the retriever blends both.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

from .embeddings import tokenize


class BM25:
    def __init__(self, corpus_tokens: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs: list[Counter] = [Counter(doc) for doc in corpus_tokens]
        self.lengths = [sum(doc.values()) for doc in self.docs]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.docs else 0.0
        self.doc_freq: dict[str, int] = {}
        for doc in self.docs:
            for term in doc:
                self.doc_freq[term] = self.doc_freq.get(term, 0) + 1
        self.n = len(self.docs)

    def idf(self, term: str) -> float:
        freq = self.doc_freq.get(term, 0)
        if freq == 0:
            return 0.0
        return math.log(1 + (self.n - freq + 0.5) / (freq + 0.5))

    def score(self, query: str) -> list[float]:
        terms = tokenize(query)
        scores = [0.0] * self.n
        if not terms or self.avg_len == 0:
            return scores
        for term in terms:
            idf = self.idf(term)
            if idf == 0.0:
                continue
            for i, doc in enumerate(self.docs):
                freq = doc.get(term, 0)
                if not freq:
                    continue
                denom = freq + self.k1 * (
                    1 - self.b + self.b * self.lengths[i] / self.avg_len
                )
                scores[i] += idf * (freq * (self.k1 + 1)) / denom
        return scores
