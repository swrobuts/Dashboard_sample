# backend/memory_store.py
from __future__ import annotations
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import chromadb
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

_BASE_CONFIDENCE: dict[str, float] = {
    "chat": 0.70,
    "mail": 0.60,
    "calendar": 0.60,
    "task": 0.60,
    "web": 0.80,
}
_CONFIDENCE_UP   = 0.05
_CONFIDENCE_DOWN = 0.10
_CONFIDENCE_MIN  = 0.10
_CONFIDENCE_MAX  = 1.00
_INJECT_THRESHOLD = 0.30

COLLECTION = "phil_facts"


class MemoryStore:
    """Persistent fact memory: SQLite for metadata, ChromaDB for semantic retrieval."""

    def __init__(
        self,
        db_path: str = "./data/memory.db",
        chroma_path: str = "/tmp/phil_chroma",
        openai_api_key: str = "",
    ):
        import os
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id              TEXT PRIMARY KEY,
                text            TEXT NOT NULL,
                category        TEXT NOT NULL,
                source          TEXT NOT NULL,
                source_ref      TEXT,
                confidence      REAL DEFAULT 0.7,
                positive_votes  INTEGER DEFAULT 0,
                negative_votes  INTEGER DEFAULT 0,
                created_at      TEXT NOT NULL,
                corrected_at    TEXT,
                correction_note TEXT
            )
        """)
        self._conn.commit()

        self._chroma_collection = None
        if _CHROMA_AVAILABLE:
            api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
            if api_key:
                try:
                    ef = OpenAIEmbeddingFunction(
                        api_key=api_key,
                        model_name="text-embedding-3-small",
                    )
                    client = chromadb.PersistentClient(path=chroma_path)
                    self._chroma_collection = client.get_or_create_collection(
                        COLLECTION,
                        embedding_function=ef,
                        metadata={"hnsw:space": "cosine"},
                    )
                except Exception as exc:
                    logging.warning(f"[Memory] ChromaDB init fehlgeschlagen: {exc}")

    def upsert_fact(
        self,
        fact_id: str,
        text: str,
        category: str,
        source: str,
        source_ref: str | None = None,
        confidence: float | None = None,
    ) -> None:
        base = confidence if confidence is not None else _BASE_CONFIDENCE.get(source, 0.65)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("""
            INSERT INTO facts (id, text, category, source, source_ref, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                category=excluded.category,
                source_ref=excluded.source_ref
        """, (fact_id, text, category, source, source_ref, base, now))
        self._conn.commit()
        if self._chroma_collection is not None:
            try:
                self._chroma_collection.upsert(
                    ids=[fact_id],
                    documents=[text],
                    metadatas=[{"category": category, "source": source}],
                )
            except Exception as exc:
                logging.warning(f"[Memory] ChromaDB upsert fehlgeschlagen: {exc}")

    def apply_feedback(self, fact_id: str, rating: str) -> None:
        col = "positive_votes" if rating == "up" else "negative_votes"
        delta = _CONFIDENCE_UP if rating == "up" else -_CONFIDENCE_DOWN
        self._conn.execute(f"""
            UPDATE facts
            SET {col} = {col} + 1,
                confidence = MAX({_CONFIDENCE_MIN}, MIN({_CONFIDENCE_MAX}, confidence + ?))
            WHERE id = ?
        """, (delta, fact_id))
        self._conn.commit()

    def delete_fact(self, fact_id: str) -> None:
        self._conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        self._conn.commit()
        if self._chroma_collection is not None:
            try:
                self._chroma_collection.delete(ids=[fact_id])
            except Exception as exc:
                logging.warning(f"[Memory] ChromaDB delete fehlgeschlagen: {exc}")

    def update_fact(
        self,
        fact_id: str,
        text: str | None = None,
        correction_note: str | None = None,
    ) -> None:
        if text is None and correction_note is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("""
            UPDATE facts
            SET text = COALESCE(?, text),
                correction_note = COALESCE(?, correction_note),
                corrected_at = ?
            WHERE id = ?
        """, (text, correction_note, now, fact_id))
        self._conn.commit()
        if text and self._chroma_collection is not None:
            try:
                row = self._conn.execute(
                    "SELECT category, source FROM facts WHERE id = ?", (fact_id,)
                ).fetchone()
                if row:
                    self._chroma_collection.upsert(
                        ids=[fact_id],
                        documents=[text],
                        metadatas=[{"category": row[0], "source": row[1]}],
                    )
            except Exception as exc:
                logging.warning(f"[Memory] ChromaDB update fehlgeschlagen: {exc}")

    def list_facts(
        self,
        category: str | None = None,
        min_confidence: float | None = None,
        source_ref: str | None = None,
    ) -> list[dict]:
        query = "SELECT id, text, category, source, source_ref, confidence, positive_votes, negative_votes, created_at, corrected_at, correction_note FROM facts WHERE 1=1"
        params: list = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if min_confidence is not None:
            query += " AND confidence >= ?"
            params.append(min_confidence)
        if source_ref:
            query += " AND source_ref = ?"
            params.append(source_ref)
        query += " ORDER BY confidence DESC, created_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        cols = ["id", "text", "category", "source", "source_ref", "confidence",
                "positive_votes", "negative_votes", "created_at", "corrected_at", "correction_note"]
        return [dict(zip(cols, r)) for r in rows]

    def search_facts(self, query: str, n_results: int = 10) -> list[dict]:
        if self._chroma_collection is not None and self._chroma_collection.count() > 0:
            try:
                n = min(n_results, self._chroma_collection.count())
                res = self._chroma_collection.query(
                    query_texts=[query],
                    n_results=n,
                    include=["metadatas", "distances"],
                )
                ids = res["ids"][0]
                if not ids:
                    return []
                placeholders = ",".join("?" * len(ids))
                rows = self._conn.execute(
                    f"SELECT id, text, category, source, confidence FROM facts WHERE id IN ({placeholders}) AND confidence >= ?",
                    ids + [_INJECT_THRESHOLD],
                ).fetchall()
                id_order = {fid: i for i, fid in enumerate(ids)}
                rows.sort(key=lambda r: id_order.get(r[0], 999))
                return [{"id": r[0], "text": r[1], "category": r[2], "source": r[3], "confidence": r[4]} for r in rows]
            except Exception as exc:
                logging.warning(f"[Memory] ChromaDB search fehlgeschlagen: {exc}")
        rows = self._conn.execute(
            "SELECT id, text, category, source, confidence FROM facts WHERE confidence >= ? ORDER BY confidence DESC LIMIT ?",
            (_INJECT_THRESHOLD, n_results),
        ).fetchall()
        return [{"id": r[0], "text": r[1], "category": r[2], "source": r[3], "confidence": r[4]} for r in rows]

    def stats(self) -> dict:
        total = self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        by_cat = self._conn.execute(
            "SELECT category, COUNT(*), AVG(confidence) FROM facts GROUP BY category"
        ).fetchall()
        return {
            "total": total,
            "by_category": [
                {"category": r[0], "count": r[1], "avg_confidence": round(r[2], 3)}
                for r in by_cat
            ],
        }

    def build_context_block(self, query: str) -> str:
        facts = self.search_facts(query, n_results=10)
        if not facts:
            return ""
        lines = ["\n=== PHIL'S GEDÄCHTNIS (gespeicherte Fakten) ==="]
        for f in facts:
            pct = int(f["confidence"] * 100)
            lines.append(f"  [{f['category']}] {f['text']}  (Konfidenz: {pct}%)")
        return "\n".join(lines)
