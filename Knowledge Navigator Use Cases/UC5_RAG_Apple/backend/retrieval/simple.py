"""UE1 — Simple top-k retrieval over the section-aware chunks."""
from __future__ import annotations

import time

from backend.config import get_settings
from backend.data.pg import session_scope
from backend.data.repo import topk_ue1
from backend.llm.factory import get_embedding_llm
from backend.retrieval.base import Chunk, RetrievalResult, SourceRef


class SimpleRAG:
    name = "ue1"

    def retrieve(self, query: str, k: int | None = None) -> RetrievalResult:
        settings = get_settings()
        k = k or settings.ue1_top_k

        embedder = get_embedding_llm()
        t0 = time.perf_counter()
        query_embedding = embedder.embed([query])[0]
        embed_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        with session_scope() as session:
            rows = topk_ue1(session, query_embedding, k)
        search_ms = (time.perf_counter() - t0) * 1000

        chunks = [Chunk(text=r.text, section_path=r.section_path, chunk_id=r.chunk_id) for r in rows]
        sources = [
            SourceRef(chunk_id=r.chunk_id, section_path=r.section_path,
                      text=r.text, distance=r.distance)
            for r in rows
        ]
        trace = {
            "strategy": self.name,
            "k": k,
            "embedder": embedder.name,
            "embed_ms": round(embed_ms, 1),
            "search_ms": round(search_ms, 1),
            "distances": [round(r.distance, 4) for r in rows],
            "sections": [r.section_path for r in rows],
        }
        return RetrievalResult(chunks=chunks, sources=sources, trace=trace)
