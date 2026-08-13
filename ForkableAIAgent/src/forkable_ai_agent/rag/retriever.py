"""Hybrid retrieval (dense + BM25) and the KnowledgeBase facade."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bm25 import BM25
from .chunker import chunk_document
from .embeddings import build_embedder, tokenize
from .store import Document, VectorStore, doc_id

TEXT_SUFFIXES = {".md", ".txt", ".rst", ".markdown"}


@dataclass
class Hit:
    document: Document
    score: float
    dense: float = 0.0
    lexical: float = 0.0

    @property
    def citation(self) -> str:
        head = f"#{self.document.heading}" if self.document.heading else ""
        return f"{self.document.source}{head}"


def _minmax(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    low, high = min(values), max(values)
    if high - low < 1e-12:
        return [0.0 for _ in values]
    return [(v - low) / (high - low) for v in values]


class KnowledgeBase:
    """Index, search and answer over local Markdown/text knowledge."""

    def __init__(self, settings, llm=None) -> None:
        self.settings = settings
        self.llm = llm
        self.embedder = build_embedder(settings, llm)
        self.store = self._build_store()
        self._bm25: BM25 | None = None

    def _build_store(self):
        index_path = self.settings.path(self.settings.rag.index_dir)
        if (self.settings.rag.backend or "builtin").lower() == "chroma":
            from .chroma_store import CHROMA_AVAILABLE, ChromaStore

            if CHROMA_AVAILABLE:
                return ChromaStore(index_path / "chroma")
        return VectorStore(index_path)

    # ------------------------------------------------------------------
    def _rebuild_bm25(self) -> None:
        self._bm25 = BM25([tokenize(d.text) for d in self.store.docs])

    def load(self) -> bool:
        loaded = self.store.load()
        if loaded:
            self._rebuild_bm25()
        return loaded

    def index(self, extra_dirs: Sequence[str] = ()) -> dict[str, Any]:
        """(Re)build the index from the knowledge directory."""
        roots = [self.settings.path(self.settings.rag.knowledge_dir)]
        roots += [self.settings.path(d) for d in extra_dirs]

        files: list[Path] = []
        for root in roots:
            if root.is_file():
                files.append(root)
            elif root.exists():
                files.extend(
                    p for p in sorted(root.rglob("*"))
                    if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES
                )

        self.store.clear()
        pending: list[Document] = []
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel = str(path.relative_to(self.settings.path(".")) if str(path).startswith(str(self.settings.path("."))) else path)
            for chunk in chunk_document(
                text,
                chunk_chars=self.settings.rag.chunk_chars,
                overlap=self.settings.rag.chunk_overlap,
            ):
                pending.append(
                    Document(
                        id=doc_id(rel, chunk.order, chunk.text),
                        text=chunk.text,
                        source=rel,
                        heading=chunk.heading,
                        meta={"chars": len(chunk.text)},
                    )
                )

        if pending:
            vectors = self.embedder.embed([d.text for d in pending])
            for doc, vec in zip(pending, vectors, strict=False):
                doc.vector = vec
        self.store.add(pending)
        manifest = {
            "embedder": getattr(self.embedder, "name", "unknown"),
            "dim": getattr(self.embedder, "dim", 0),
            "files": len(files),
            "count": len(pending),
            "built_at": time.time(),
        }
        self.store.save(manifest)
        self._rebuild_bm25()
        return manifest

    # ------------------------------------------------------------------
    def search(self, query: str, top_k: int | None = None) -> list[Hit]:
        if not self.store.docs and not self.load():
            return []
        if self._bm25 is None:
            self._rebuild_bm25()

        k = top_k or self.settings.rag.top_k
        alpha = self.settings.rag.hybrid_alpha
        query_vec = self.embedder.embed([query])[0]

        dense_raw = [
            sum(a * b for a, b in zip(query_vec, doc.vector, strict=False)) if doc.vector else 0.0
            for doc in self.store.docs
        ]
        lexical_raw = self._bm25.score(query) if self._bm25 else [0.0] * len(self.store.docs)
        dense = _minmax(dense_raw)
        lexical = _minmax(lexical_raw)

        hits = [
            Hit(
                document=doc,
                score=alpha * dense_norm + (1 - alpha) * lexical_norm,
                dense=dense_score,
                lexical=lexical_score,
            )
            for doc, dense_norm, lexical_norm, dense_score, lexical_score in zip(
                self.store.docs, dense, lexical, dense_raw, lexical_raw, strict=False
            )
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return [h for h in hits[:k] if h.score > 0][:k]

    # ------------------------------------------------------------------
    def context_block(self, hits: Sequence[Hit], max_chars: int = 4000) -> str:
        parts: list[str] = []
        used = 0
        for i, hit in enumerate(hits, 1):
            block = f"[{i}] source: {hit.citation}\n{hit.document.text}"
            if used + len(block) > max_chars:
                break
            parts.append(block)
            used += len(block)
        return "\n\n".join(parts)

    def answer(self, question: str, top_k: int | None = None) -> tuple[str, list[Hit]]:
        """Grounded answer. Without a live model this returns the evidence itself."""
        hits = self.search(question, top_k=top_k)
        if not hits:
            return ("Nothing in the local knowledge base matches that question.", [])

        context = self.context_block(hits)
        if self.llm is None or getattr(self.llm, "name", "") == "rules":
            lead = hits[0].document.text.strip()
            return (
                "No local model is loaded, so here is the top matching passage "
                f"verbatim from {hits[0].citation}:\n\n{lead}",
                hits,
            )

        system = (
            "You answer questions about a Playwright test automation codebase. "
            "Use only the provided context. Cite sources as [1], [2]. "
            "If the context is insufficient, say so."
        )
        prompt = (
            "# task: qa\n"
            f"Context:\n{context}\n\n"
            f"Question: {question}\n"
            "Answer concisely with citations."
        )
        try:
            response = self.llm.generate(prompt, system=system)
            return (response.text or "(empty response)", hits)
        except Exception as exc:
            return (f"Local model failed ({exc}); top passage:\n\n{hits[0].document.text}", hits)
