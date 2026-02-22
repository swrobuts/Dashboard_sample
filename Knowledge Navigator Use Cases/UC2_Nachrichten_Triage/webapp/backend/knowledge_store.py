# backend/knowledge_store.py
from __future__ import annotations
import os
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction


class KnowledgeStore:
    """Persistent semantic mail index backed by ChromaDB + OpenAI embeddings."""

    COLLECTION = "phil_mails"

    def __init__(self, persist_path: str = "./data/chroma", openai_api_key: str = ""):
        ef = OpenAIEmbeddingFunction(
            api_key=openai_api_key or os.getenv("OPENAI_API_KEY", ""),
            model_name="text-embedding-3-small",
        )
        self._client = chromadb.PersistentClient(path=persist_path)
        self.collection = self._client.get_or_create_collection(
            self.COLLECTION,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    def index_mail(
        self,
        mail_id: str,
        subject: str,
        sender: str,
        date: str,
        kategorie: str,
        summary: str,
        body_snippet: str,
    ) -> None:
        """Embed and upsert a mail into the collection."""
        document = f"Betreff: {subject}\nVon: {sender}\nZusammenfassung: {summary}\n{body_snippet[:300]}"
        self.collection.upsert(
            ids=[mail_id],
            documents=[document],
            metadatas=[{
                "subject": subject,
                "sender": sender,
                "date": date,
                "kategorie": kategorie,
                "summary": summary,
            }],
        )

    def search(self, query: str, n_results: int = 3) -> list[dict]:
        """Return top-n semantically similar mails. Empty list if store is empty."""
        if self.collection.count() == 0:
            return []
        n = min(n_results, self.collection.count())
        res = self.collection.query(
            query_texts=[query],
            n_results=n,
            include=["metadatas", "distances"],
        )
        results = []
        for i, meta in enumerate(res["metadatas"][0]):
            score = 1.0 - (res["distances"][0][i])  # cosine: 1=identical
            results.append({
                "id": res["ids"][0][i],
                "subject": meta.get("subject", ""),
                "sender": meta.get("sender", ""),
                "date": meta.get("date", ""),
                "kategorie": meta.get("kategorie", ""),
                "summary": meta.get("summary", ""),
                "score": round(score, 3),
            })
        return results
