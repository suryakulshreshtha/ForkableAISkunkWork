"""Optional ChromaDB backend.

The sibling ForkedUpAIExperiments projects already standardise on ChromaDB +
``nomic-embed-text``. If you want this agent's knowledge to live in the same
store, install ``chromadb`` and set ``rag.backend = "chroma"``; otherwise the
built-in JSONL store is used and nothing extra is required.

Chroma is deliberately *not* a hard dependency: it pulls a large tree that is
painful to mirror onto an air-gapped machine, and the built-in store handles a
corpus this size without breaking a sweat.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .store import Document

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMA_AVAILABLE = True
except ImportError:  # pragma: no cover - optional extra
    chromadb = None  # type: ignore[assignment]
    ChromaSettings = None  # type: ignore[assignment]
    CHROMA_AVAILABLE = False


class ChromaStore:
    """Drop-in replacement for :class:`VectorStore` backed by a local Chroma collection."""

    def __init__(self, path: str | Path, collection: str = "forkable_knowledge") -> None:
        if not CHROMA_AVAILABLE:
            raise ImportError(
                "chromadb is not installed. Either 'pip install chromadb' or leave "
                "rag.backend on the built-in store."
            )
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        # PersistentClient with telemetry off: no phone-home from an offline box.
        self.client = chromadb.PersistentClient(
            path=str(self.path),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self.collection = self.client.get_or_create_collection(
            name=collection, metadata={"hnsw:space": "cosine"}
        )
        self.docs: list[Document] = []
        self.manifest: dict[str, Any] = {"backend": "chroma"}

    def __len__(self) -> int:
        return self.collection.count()

    def clear(self) -> None:
        name = self.collection.name
        self.client.delete_collection(name)
        self.collection = self.client.get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )
        self.docs = []

    def add(self, docs: Sequence[Document]) -> None:
        if not docs:
            return
        self.docs.extend(docs)
        self.collection.add(
            ids=[d.id for d in docs],
            documents=[d.text for d in docs],
            embeddings=[d.vector for d in docs],
            metadatas=[{"source": d.source, "heading": d.heading} for d in docs],
        )

    def save(self, manifest: dict[str, Any] | None = None) -> Path:
        self.manifest.update(manifest or {})
        return self.path  # PersistentClient writes as it goes

    def load(self) -> bool:
        if self.collection.count() == 0:
            return False
        payload = self.collection.get(include=["documents", "metadatas", "embeddings"])
        self.docs = [
            Document(
                id=doc_id,
                text=text,
                source=(meta or {}).get("source", ""),
                heading=(meta or {}).get("heading", ""),
                vector=list(vector or []),
            )
            for doc_id, text, meta, vector in zip(
                payload.get("ids", []),
                payload.get("documents", []),
                payload.get("metadatas", []),
                payload.get("embeddings", []),
                strict=False,
            )
        ]
        return True

    def search(self, query_vector: Sequence[float], top_k: int = 5) -> list[tuple[Document, float]]:
        result = self.collection.query(
            query_embeddings=[list(query_vector)],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        out: list[tuple[Document, float]] = []
        for doc_id, text, meta, distance in zip(
            result.get("ids", [[]])[0],
            result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0],
            result.get("distances", [[]])[0],
            strict=False,
        ):
            document = Document(
                id=doc_id, text=text,
                source=(meta or {}).get("source", ""),
                heading=(meta or {}).get("heading", ""),
            )
            out.append((document, 1.0 - float(distance)))  # cosine distance -> similarity
        return out
