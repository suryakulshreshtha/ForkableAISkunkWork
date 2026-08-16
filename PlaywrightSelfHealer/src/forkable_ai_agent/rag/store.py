"""A small, dependency-free vector store.

Persistence is one JSONL file plus a JSON manifest. That is deliberate: a
corpus of engineering docs is thousands of chunks, not millions, so a linear
cosine scan is microseconds of work and the index stays greppable, diffable and
trivially portable between air-gapped machines. Swapping in FAISS or Chroma
later only means re-implementing :meth:`VectorStore.search`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .embeddings import cosine


@dataclass
class Document:
    id: str
    text: str
    source: str = ""
    heading: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    vector: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Document:
        return cls(
            id=data["id"],
            text=data["text"],
            source=data.get("source", ""),
            heading=data.get("heading", ""),
            meta=data.get("meta", {}) or {},
            vector=[float(x) for x in data.get("vector", [])],
        )


def doc_id(source: str, order: int, text: str) -> str:
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=6).hexdigest()
    return f"{Path(source).stem}:{order}:{digest}"


class VectorStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.docs: list[Document] = []
        self.manifest: dict[str, Any] = {}

    # ------------------------------------------------------------------
    def add(self, docs: Sequence[Document]) -> None:
        known = {d.id for d in self.docs}
        for doc in docs:
            if doc.id not in known:
                self.docs.append(doc)
                known.add(doc.id)

    def clear(self) -> None:
        self.docs = []

    def __len__(self) -> int:
        return len(self.docs)

    # ------------------------------------------------------------------
    def save(self, manifest: dict[str, Any] | None = None) -> Path:
        self.path.mkdir(parents=True, exist_ok=True)
        jsonl = self.path / "docs.jsonl"
        with jsonl.open("w", encoding="utf-8") as fh:
            for doc in self.docs:
                fh.write(json.dumps(doc.to_dict(), ensure_ascii=False) + "\n")
        self.manifest = manifest or self.manifest
        self.manifest.setdefault("count", len(self.docs))
        self.manifest["count"] = len(self.docs)
        (self.path / "manifest.json").write_text(
            json.dumps(self.manifest, indent=2), encoding="utf-8"
        )
        return jsonl

    def load(self) -> bool:
        jsonl = self.path / "docs.jsonl"
        if not jsonl.exists():
            return False
        self.docs = []
        with jsonl.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    self.docs.append(Document.from_dict(json.loads(line)))
        manifest_path = self.path / "manifest.json"
        if manifest_path.exists():
            self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return True

    # ------------------------------------------------------------------
    def search(self, query_vector: Sequence[float], top_k: int = 5) -> list[tuple[Document, float]]:
        scored = [(doc, cosine(query_vector, doc.vector)) for doc in self.docs if doc.vector]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
