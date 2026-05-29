"""UE2 — Hybrid PageIndex + classical RAG retrieval.

Two phases per query:

1. **PageIndex navigation:** an LLM walks the section tree top-down, at each
   level seeing only the children's summaries and choosing up to
   ``UE2_NODES_PER_LEVEL`` to descend into. Cuts off at ``UE2_MAX_DEPTH`` or
   when leaves are reached.

2. **Vector retrieval (constrained):** pgvector cosine top-k against
   ``ue1.chunk``, restricted to sections whose path is at or below any of the
   nodes selected in phase 1.

The trace returned to the frontend shows every navigation step so the user
can see *why* certain regions of the article were searched.
"""
from __future__ import annotations

import json
import logging
import re
import time

from backend.config import get_settings
from backend.data import repo
from backend.data.pg import session_scope
from backend.llm.factory import get_chat_llm, get_embedding_llm
from backend.retrieval.base import Chunk, RetrievalResult, SourceRef

log = logging.getLogger(__name__)

NAV_SYSTEM = (
    "Du bist ein Retrieval-Routing-Agent. Du bekommst eine Frage und eine "
    "Liste nummerierter Abschnitte mit Kurzzusammenfassungen aus dem deutschen "
    "Wikipedia-Artikel über Apple. Wähle die Abschnitte aus, die am "
    "wahrscheinlichsten Antworten auf die Frage enthalten — strikt nach "
    "Relevanz, nicht nach Vollständigkeit. Antworte AUSSCHLIESSLICH mit einem "
    "JSON-Array der IDs, z.B. [3, 7]. Keine Erklärung, kein Markdown, nichts "
    "anderes als das Array. Wenn nichts relevant ist, antworte mit []."
)


class PageIndexRAG:
    """Strategy used by /api/query when strategy=ue2."""

    name = "ue2"

    def __init__(self, llm_provider: str = "gemini") -> None:
        self._chat = get_chat_llm(llm_provider)
        self._embedder = get_embedding_llm()
        self._llm_provider = llm_provider

    # ── public ─────────────────────────────────────────────────────────────

    def retrieve(self, query: str, k: int | None = None) -> RetrievalResult:
        settings = get_settings()
        k = k or settings.ue2_top_k

        with session_scope() as session:
            document_id = repo.latest_document_id_for_url(session, settings.wikipedia_url)
            if document_id is None:
                raise RuntimeError("No document available — run an ingest first.")
            top_nodes = repo.ue2_top_level_nodes(session, document_id)

        # ── Phase 1: tree navigation ──
        t0 = time.perf_counter()
        navigation_steps: list[dict] = []
        selected_at_each_level: list[list[repo.TreeNode]] = []
        frontier = top_nodes
        llm_calls_nav = 0
        for depth in range(settings.ue2_max_depth):
            if not frontier:
                break
            chosen = self._select_nodes(query, frontier, settings.ue2_nodes_per_level)
            llm_calls_nav += 1
            navigation_steps.append({
                "depth": depth + 1,
                "candidates": [
                    {"id": n.id, "path": n.path, "summary": n.summary[:120]}
                    for n in frontier
                ],
                "selected_ids": [n.id for n in chosen],
                "selected_paths": [n.path for n in chosen],
            })
            if not chosen:
                break
            selected_at_each_level.append(chosen)
            # Descend
            next_frontier: list[repo.TreeNode] = []
            with session_scope() as session:
                for n in chosen:
                    next_frontier.extend(repo.ue2_children_of(session, n.id))
            frontier = next_frontier

        # If nothing was selected at all, fall back to the top-level so we
        # still return something rather than an empty answer.
        if not selected_at_each_level:
            log.info("UE2: navigation selected nothing — falling back to top-level")
            selected_at_each_level = [top_nodes]

        navigation_ms = (time.perf_counter() - t0) * 1000

        # The *deepest* selected nodes are the most specific. We use those as
        # the subtree roots; the path-prefix filter automatically includes all
        # their descendants.
        deepest = selected_at_each_level[-1]
        section_paths = [n.path for n in deepest]

        # ── Phase 2: vector top-k constrained to those subtrees ──
        t0 = time.perf_counter()
        query_emb = self._embedder.embed([query])[0]
        with session_scope() as session:
            rows = repo.topk_ue1_in_subtree(session, query_emb, k, section_paths)
        vector_ms = (time.perf_counter() - t0) * 1000

        chunks = [
            Chunk(text=r.text, section_path=r.section_path, chunk_id=r.chunk_id)
            for r in rows
        ]
        sources = [
            SourceRef(chunk_id=r.chunk_id, section_path=r.section_path,
                      text=r.text, distance=r.distance)
            for r in rows
        ]

        trace = {
            "strategy": self.name,
            "llm_provider": self._llm_provider,
            "navigation": navigation_steps,
            "selected_subtree_paths": section_paths,
            "k": k,
            "topk_chunks": len(rows),
            "llm_calls_nav": llm_calls_nav,
            "navigation_ms": round(navigation_ms, 1),
            "vector_ms": round(vector_ms, 1),
            "distances": [round(r.distance, 4) for r in rows],
        }
        return RetrievalResult(chunks=chunks, sources=sources, trace=trace)

    # ── internals ──────────────────────────────────────────────────────────

    def _select_nodes(
        self,
        query: str,
        candidates: list[repo.TreeNode],
        max_select: int,
    ) -> list[repo.TreeNode]:
        if not candidates:
            return []
        listing = "\n".join(
            f"{n.id}. [{n.path}] {n.summary}" for n in candidates
        )
        prompt = (
            f"Frage:\n{query}\n\n"
            f"Verfügbare Abschnitte (ID. [Pfad] Zusammenfassung):\n{listing}\n\n"
            f"Wähle bis zu {max_select} IDs aus, die am wahrscheinlichsten Antworten "
            f"enthalten. Antwort als JSON-Array der IDs, ohne weiteren Text."
        )
        try:
            answer, _ = self._chat.generate(NAV_SYSTEM, prompt)
        except Exception as exc:  # noqa: BLE001
            log.warning("UE2 navigation LLM call failed: %s — using all candidates", exc)
            return candidates[:max_select]

        ids = _parse_id_list(answer)
        if not ids:
            log.info("UE2 navigation: empty or unparseable response %r", answer[:120])
            return []
        keep = {n.id: n for n in candidates}
        chosen = [keep[i] for i in ids if i in keep]
        return chosen[:max_select]


_JSON_ARRAY_RE = re.compile(r"\[\s*(?:\d+(?:\.\d+)?\s*(?:,\s*\d+(?:\.\d+)?\s*)*)?\]")


def _parse_id_list(answer: str) -> list[int]:
    """Defensively extract a JSON list of integer IDs from a model response."""
    if not answer:
        return []
    # Strip code fences if the model wrapped the array.
    cleaned = answer.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    m = _JSON_ARRAY_RE.search(cleaned)
    if not m:
        return []
    try:
        ids = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return [int(x) for x in ids if isinstance(x, (int, float))]
