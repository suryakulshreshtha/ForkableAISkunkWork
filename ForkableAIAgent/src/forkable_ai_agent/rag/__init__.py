"""Offline RAG: hashing/Ollama embeddings, JSONL vector store, BM25 hybrid search."""

from .chroma_store import CHROMA_AVAILABLE, ChromaStore
from .chunker import Chunk, chunk_document
from .embeddings import Embedder, HashingEmbedder, OllamaEmbedder, build_embedder, cosine
from .retriever import Hit, KnowledgeBase
from .store import Document, VectorStore

__all__ = [
    "Chunk",
    "chunk_document",
    "Embedder",
    "HashingEmbedder",
    "OllamaEmbedder",
    "build_embedder",
    "cosine",
    "Hit",
    "KnowledgeBase",
    "Document",
    "VectorStore",
    "ChromaStore",
    "CHROMA_AVAILABLE",
]
