# tests/test_knowledge_store.py
"""
Tests for KnowledgeStore.

ChromaDB ≥0.5 wraps __call__ in __init_subclass__, so mocker.patch.object on
the embedding function instance does not intercept the real OpenAI network call.
Instead we inject a lightweight stub EmbeddingFunction at fixture time.
"""
import pytest
import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from backend.knowledge_store import KnowledgeStore


class _FakeEF(EmbeddingFunction):
    """Always returns a fixed 1536-dim vector — no network, no API key."""

    def __call__(self, input: Documents) -> Embeddings:  # type: ignore[override]
        return [[0.1] * 1536 for _ in input]


@pytest.fixture
def store(tmp_path):
    """ChromaDB store backed by a fake embedding function (no OpenAI key needed)."""
    ks = KnowledgeStore.__new__(KnowledgeStore)
    ef = _FakeEF()
    ks._client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    ks.collection = ks._client.get_or_create_collection(
        KnowledgeStore.COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    return ks


def test_index_and_search(store):
    store.index_mail(
        mail_id="abc123",
        subject="Projektstatus Update",
        sender="mueller@example.com",
        date="2026-02-01",
        kategorie="Aktion nötig",
        summary="Projekt verzögert sich um zwei Wochen.",
        body_snippet="Hallo, leider müssen wir den Termin verschieben.",
    )
    results = store.search("Projektverzögerung", n_results=1)
    assert len(results) == 1
    assert results[0]["id"] == "abc123"
    assert results[0]["subject"] == "Projektstatus Update"


def test_search_empty_store(store):
    results = store.search("anything", n_results=3)
    assert results == []


def test_index_upsert_idempotent(store):
    for _ in range(2):
        store.index_mail("id1", "Betreff", "a@b.de", "2026-01-01", "Info", "Summary", "Body")
    assert store.collection.count() == 1
