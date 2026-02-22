# backend/knowledge_store.py
from __future__ import annotations
import os
import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction


class KnowledgeStore:
    """Persistent semantic mail index backed by ChromaDB + OpenAI embeddings."""

    COLLECTION = "phil_mails"
    _BODY_LIMIT = 300  # keep embeddings short; ChromaDB has no hard limit but costs money

    def __init__(self, persist_path: str = "./data/chroma", openai_api_key: str = ""):
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "KnowledgeStore: OPENAI_API_KEY is not set. "
                "Pass openai_api_key= or set the environment variable."
            )
        ef = OpenAIEmbeddingFunction(
            api_key=api_key,
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
        document = (
            f"Betreff: {subject}\n"
            f"Von: {sender}\n"
            f"Zusammenfassung: {summary}\n"
            f"{body_snippet[:self._BODY_LIMIT]}"
        )
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

    def index_attachment(
        self,
        mail_id: str,
        filename: str,
        summary: str,
        body_snippet: str,
    ) -> None:
        """Embed and upsert an attachment into the mail collection.

        Uses the same ChromaDB collection as mails.
        ID format: ``att-<mail_id>-<filename>``.
        Metadata includes ``doc_type=attachment`` for later filtering.
        """
        document = (
            f"Dateiname: {filename}\n"
            f"Zusammenfassung: {summary}\n"
            f"{body_snippet[:self._BODY_LIMIT]}"
        )
        att_id = f"att-{mail_id}-{filename}"
        self.collection.upsert(
            ids=[att_id],
            documents=[document],
            metadatas=[{
                "mail_id": mail_id,
                "filename": filename,
                "summary": summary,
                "doc_type": "attachment",
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
