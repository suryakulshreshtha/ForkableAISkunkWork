"""Chunking, embedding, hybrid retrieval and persistence."""

from __future__ import annotations

from forkable_ai_agent.rag import HashingEmbedder, KnowledgeBase, chunk_document, cosine
from forkable_ai_agent.rag.bm25 import BM25
from forkable_ai_agent.rag.embeddings import tokenize


def test_hashing_embedder_is_deterministic_and_normalised():
    embedder = HashingEmbedder(dim=256)
    a, b = embedder.embed(["self healing locators"] * 2)
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9


def test_hashing_embedder_separates_topics():
    embedder = HashingEmbedder(dim=512)
    locators, timeouts, locators2 = embedder.embed([
        "prefer data-testid over css selectors",
        "the action timed out waiting for navigation",
        "css selectors are worse than data-testid",
    ])
    assert cosine(locators, locators2) > cosine(locators, timeouts)


def test_chunker_keeps_headings():
    chunks = chunk_document("# One\nalpha text\n\n## Two\nbeta text\n", chunk_chars=200, overlap=20)
    assert [c.heading for c in chunks] == ["One", "Two"]
    assert chunks[0].text.startswith("One")


def test_bm25_ranks_exact_identifiers():
    corpus = [tokenize(t) for t in (
        "use data-testid for stable hooks",
        "cooking pasta requires salted water",
    )]
    scores = BM25(corpus).score("data-testid")
    assert scores[0] > scores[1]


def test_index_search_and_persist(settings):
    kb = KnowledgeBase(settings)
    manifest = kb.index()
    assert manifest["count"] > 0

    hits = kb.search("what should I do when a selector is ambiguous?")
    assert hits
    assert any("locator" in h.citation or "failure" in h.citation for h in hits)

    reloaded = KnowledgeBase(settings)
    assert reloaded.load()
    assert len(reloaded.store.docs) == manifest["count"]


def test_answer_without_a_model_returns_evidence(settings):
    kb = KnowledgeBase(settings)
    kb.index()
    answer, hits = kb.answer("how does the offline guard work?")
    assert hits
    assert "socket" in answer.lower() or "loopback" in answer.lower()
