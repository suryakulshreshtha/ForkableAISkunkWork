"""Embedding backends.

``HashingEmbedder`` is the offline floor: a stable feature-hashing embedder
built only on the standard library. It needs no model weights, no download and
no GPU, and it is deterministic across processes because hashing uses
``blake2b`` rather than the salted builtin ``hash``.

``OllamaEmbedder`` upgrades retrieval quality when a local daemon is serving an
embedding model such as ``nomic-embed-text``. ``build_embedder`` picks the best
one available and always degrades quietly.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Sequence
from typing import Protocol

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bucket(feature: str, dim: int) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    index = value % dim
    sign = 1.0 if (value >> 63) & 1 else -1.0
    return index, sign


def l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        return vector
    return [v / norm for v in vector]


class HashingEmbedder:
    """Feature-hashing embedder over word unigrams, bigrams and char 4-grams."""

    name = "hashing"

    def __init__(self, dim: int = 512, char_ngrams: bool = True) -> None:
        self.dim = dim
        self.char_ngrams = char_ngrams

    def _features(self, text: str) -> Iterable[tuple[str, float]]:
        tokens = tokenize(text)
        for token in tokens:
            yield f"w:{token}", 1.0
        for a, b in zip(tokens, tokens[1:], strict=False):
            yield f"b:{a}_{b}", 0.7
        if self.char_ngrams:
            compact = " ".join(tokens)
            for i in range(len(compact) - 3):
                yield f"c:{compact[i:i + 4]}", 0.35

    def embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for feature, weight in self._features(text):
            index, sign = _bucket(feature, self.dim)
            vector[index] += sign * weight
        return l2_normalize(vector)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


class OllamaEmbedder:
    """Dense embeddings from a local Ollama model, normalised for cosine use."""

    name = "ollama"

    def __init__(self, client, dim_hint: int = 768) -> None:
        self.client = client
        self.dim = dim_hint

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self.client.embed(list(texts))
        out = [l2_normalize([float(x) for x in vec]) for vec in vectors]
        if out and out[0]:
            self.dim = len(out[0])
        return out


def build_embedder(settings, llm=None):
    """Choose an embedder honouring ``settings.rag.embedder``."""
    preference = (settings.rag.embedder or "auto").lower()
    if preference == "hashing":
        return HashingEmbedder(dim=settings.rag.embed_dim)

    if llm is not None and getattr(llm, "name", "") == "ollama":
        try:
            probe = llm.embed(["forkable probe"])
            if probe and probe[0]:
                return OllamaEmbedder(llm, dim_hint=len(probe[0]))
        except Exception:
            pass
    if preference == "ollama":
        # Explicitly requested but unusable: say so by falling back loudly.
        return HashingEmbedder(dim=settings.rag.embed_dim)
    return HashingEmbedder(dim=settings.rag.embed_dim)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False))
