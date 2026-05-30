"""UE3 — GraphRAG retrieval in three flavours.

* **local**  — entity-centric. Find top-k entities most similar to the query
  (via ue3.entity_summary embedding), traverse 1 hop in Neo4j to pull in
  related entities, gather the chunks that MENTION any of these entities.
* **global** — community-centric. Find top-k communities by summary
  embedding similarity; each community contributes its summary as a pseudo-
  chunk so the answering LLM can map-reduce.
* **hybrid** (default) — runs both and unions/dedupes the chunks.

All three return the standard ``RetrievalResult`` so /api/query and
/api/compare see UE3 the same way they see UE1/UE2.
"""
from __future__ import annotations

import logging
import time

from backend.config import get_settings
from backend.data import repo
from backend.data.neo4j_client import neo4j_session
from backend.data.pg import session_scope
from backend.llm.factory import get_embedding_llm
from backend.retrieval.base import Chunk, RetrievalResult, SourceRef

log = logging.getLogger(__name__)

VALID_MODES = ("local", "global", "hybrid")


class GraphRAG:
    name = "ue3"

    def __init__(self, llm_provider: str = "gemini", mode: str | None = None) -> None:
        self._llm_provider = llm_provider
        self._mode = (mode or get_settings().ue3_default_mode).lower()
        if self._mode not in VALID_MODES:
            self._mode = "hybrid"

    def retrieve(self, query: str, k: int | None = None) -> RetrievalResult:
        settings = get_settings()
        k = k or settings.ue3_top_k_chunks

        embedder = get_embedding_llm()
        t0 = time.perf_counter()
        query_emb = embedder.embed([query])[0]
        embed_ms = (time.perf_counter() - t0) * 1000

        local_chunks: list[dict] = []
        global_chunks: list[dict] = []
        matched_entities: list[dict] = []
        matched_communities: list[dict] = []

        t_local = 0.0
        t_global = 0.0

        if self._mode in ("local", "hybrid"):
            t0 = time.perf_counter()
            local_chunks, matched_entities = _local_retrieve(query_emb, k=k)
            t_local = (time.perf_counter() - t0) * 1000

        if self._mode in ("global", "hybrid"):
            t0 = time.perf_counter()
            global_chunks, matched_communities = _global_retrieve(query_emb, k=k)
            t_global = (time.perf_counter() - t0) * 1000

        # Merge local + global chunks (local first), dedupe by chunk identity.
        merged: list[dict] = []
        seen_keys: set[tuple[str, int | None]] = set()
        for c in [*local_chunks, *global_chunks]:
            key = (c["kind"], c.get("chunk_id"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(c)
        merged = merged[:k]

        chunks = [
            Chunk(
                text=c["text"],
                section_path=c.get("section_path"),
                chunk_id=c.get("chunk_id"),
            )
            for c in merged
        ]
        sources = [
            SourceRef(
                chunk_id=c.get("chunk_id"),
                section_path=c.get("section_path") or c.get("kind"),
                text=c["text"],
                distance=c.get("distance"),
            )
            for c in merged
        ]

        trace = {
            "strategy": self.name,
            "mode": self._mode,
            "llm_provider": self._llm_provider,
            "k": k,
            "embed_ms": round(embed_ms, 1),
            "local_ms": round(t_local, 1),
            "global_ms": round(t_global, 1),
            "matched_entities": [
                {"key": e["entity_key"], "name": e["name"], "type": e["type"],
                 "distance": round(e["distance"], 4)}
                for e in matched_entities
            ],
            "matched_communities": [
                {"id": c["community_id"], "level": c["level"],
                 "distance": round(c["distance"], 4)}
                for c in matched_communities
            ],
            "local_chunk_count": len(local_chunks),
            "global_chunk_count": len(global_chunks),
            "final_chunk_count": len(merged),
        }
        return RetrievalResult(chunks=chunks, sources=sources, trace=trace)


# ── local ──────────────────────────────────────────────────────────────────

def _local_retrieve(
    query_emb: list[float],
    *,
    k: int,
) -> tuple[list[dict], list[dict]]:
    """Entity match → 1-hop expand → collect MENTIONS chunks → cap k."""
    settings = get_settings()
    with session_scope() as session:
        entity_matches = repo.topk_entities_by_embedding(
            session, query_emb, settings.ue3_top_k_entities,
        )
    if not entity_matches:
        return [], []

    matched_dicts = [
        {"entity_key": e.entity_key, "name": e.name, "type": e.type,
         "description": e.description, "distance": e.distance}
        for e in entity_matches
    ]

    seed_keys = [e.entity_key for e in entity_matches]
    # Expand 1 hop via Neo4j.
    with neo4j_session() as session:
        result = session.run(
            "UNWIND $keys AS k "
            "MATCH (seed:Entity {id: k}) "
            "OPTIONAL MATCH (seed)-[:RELATED_TO]-(neighbor:Entity) "
            "WITH seed, collect(DISTINCT neighbor.id) AS neighbors "
            "RETURN seed.id AS sid, neighbors",
            keys=seed_keys,
        )
        all_entity_keys: set[str] = set(seed_keys)
        for row in result:
            for nb in row["neighbors"]:
                if nb:
                    all_entity_keys.add(nb)

        # Fetch chunks that mention any of these entities, with the mention
        # count so we can rank.
        chunk_rows = session.run(
            "UNWIND $keys AS k "
            "MATCH (e:Entity {id: k})<-[:MENTIONS]-(c:Chunk) "
            "WITH c, count(DISTINCT e) AS hits "
            "ORDER BY hits DESC, c.id ASC "
            "LIMIT $limit "
            "RETURN c.id AS id, c.text AS text, c.section_path AS section, hits",
            keys=list(all_entity_keys),
            limit=k * settings.ue3_max_chunks_per_entity,
        ).data()

    # Top-k by hit count, capped at requested k
    chunk_rows = chunk_rows[:k]
    chunks = [
        {
            "kind": "entity_chunk",
            "chunk_id": int(row["id"]),
            "text": row["text"] or "",
            "section_path": row["section"] or "",
            # Approximate "distance" as 1 / hits so smaller is better
            "distance": 1.0 / max(int(row["hits"]), 1),
        }
        for row in chunk_rows
    ]
    return chunks, matched_dicts


# ── global ─────────────────────────────────────────────────────────────────

def _global_retrieve(
    query_emb: list[float],
    *,
    k: int,
) -> tuple[list[dict], list[dict]]:
    """Community summaries as pseudo-chunks for map-reduce style answering."""
    settings = get_settings()
    with session_scope() as session:
        comms = repo.topk_communities_by_embedding(
            session, query_emb, settings.ue3_top_k_communities,
        )
    matched = [
        {"community_id": c.community_id, "level": c.level,
         "summary": c.summary, "distance": c.distance}
        for c in comms
    ]
    chunks = [
        {
            "kind": "community_summary",
            "chunk_id": None,
            "text": f"[Community {c.community_id}]\n{c.summary}",
            "section_path": f"Community {c.community_id}",
            "distance": c.distance,
        }
        for c in comms
    ]
    return chunks, matched
