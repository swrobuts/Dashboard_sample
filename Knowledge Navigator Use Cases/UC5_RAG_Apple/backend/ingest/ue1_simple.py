"""UE1 ingest pipeline: Wikipedia → raw → clean → ue1.chunk + embeddings."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from backend.config import get_settings
from backend.data import repo
from backend.data.chunker import Chunk, chunk_section
from backend.data.cleaner import CleanSection, clean_html
from backend.data.pg import session_scope
from backend.data.wikipedia_loader import fetch_article
from backend.llm.factory import get_embedding_llm

log = logging.getLogger(__name__)


@dataclass
class UE1IngestStats:
    snapshot_created: bool
    document_id: int
    sections: int
    chunks: int
    duration_ms: float


def _walk_sections(
    session,
    sections: list[CleanSection],
    *,
    document_id: int,
    parent_id: int | None,
    order_counter: list[int],
    out_sections: list[tuple[int, str, str]],
) -> None:
    """Persist sections recursively, populate ``out_sections`` with
    (section_id, path, text). A single SQLAlchemy session must be reused for
    the whole tree — otherwise child INSERTs reference parent rows that the
    new session can't see yet (foreign-key violation under READ COMMITTED)."""
    for sec in sections:
        section_id = repo.insert_section(
            session,
            document_id=document_id,
            parent_id=parent_id,
            level=sec.level,
            heading=sec.heading,
            path=sec.path,
            order_idx=order_counter[0],
            text_=sec.text,
        )
        # Flush so the next INSERT (child) sees the parent within the same
        # transaction even before commit.
        session.flush()
        order_counter[0] += 1
        if sec.text.strip():
            out_sections.append((section_id, sec.path, sec.text))
        _walk_sections(
            session,
            sec.children,
            document_id=document_id,
            parent_id=section_id,
            order_counter=order_counter,
            out_sections=out_sections,
        )


def run_ue1_ingest(force: bool = False) -> UE1IngestStats:
    settings = get_settings()
    t0 = time.perf_counter()

    log.info("UE1 ingest: fetching %s", settings.wikipedia_url)
    fetched = fetch_article(settings.wikipedia_url)

    # ── raw ──
    with session_scope() as session:
        snapshot_id, created = repo.insert_or_get_snapshot(
            session,
            url=fetched.url,
            html=fetched.html,
            content_hash=fetched.content_hash,
            revision_id=fetched.revision_id,
            etag=fetched.etag,
        )

    # If snapshot unchanged and not forced, check whether ue1.chunk already
    # has rows for the corresponding document. If so, skip.
    if not created and not force:
        with session_scope() as session:
            existing_doc = session.execute(
                __import__("sqlalchemy").text(
                    "SELECT id FROM clean.document WHERE snapshot_id = :s"
                ),
                {"s": snapshot_id},
            ).scalar()
            if existing_doc and repo.ue1_chunk_count(session, int(existing_doc)) > 0:
                log.info("UE1 ingest: snapshot unchanged and chunks present — skipping")
                return UE1IngestStats(
                    snapshot_created=False,
                    document_id=int(existing_doc),
                    sections=0,
                    chunks=repo.ue1_chunk_count(session, int(existing_doc)),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )

    # ── clean ──
    log.info("UE1 ingest: cleaning HTML to Markdown + sections")
    clean = clean_html(fetched.html, fetched.title)
    with session_scope() as session:
        document_id = repo.upsert_clean_document(
            session,
            snapshot_id=snapshot_id,
            title=clean.title,
            markdown=clean.markdown,
        )

    flat_sections: list[tuple[int, str, str]] = []
    with session_scope() as session:
        _walk_sections(
            session,
            clean.sections,
            document_id=document_id,
            parent_id=None,
            order_counter=[0],
            out_sections=flat_sections,
        )
    log.info("UE1 ingest: persisted %d sections", len(flat_sections))

    # ── ue1.chunk ──
    with session_scope() as session:
        repo.delete_ue1_chunks(session, document_id)

    all_chunks: list[tuple[int, Chunk]] = []
    chunk_idx = 0
    for section_id, path, text_ in flat_sections:
        chunks = chunk_section(
            section_path=path,
            text=text_,
            max_tokens=settings.ue1_chunk_tokens,
            overlap_tokens=settings.ue1_chunk_overlap,
            start_idx=chunk_idx,
        )
        for c in chunks:
            all_chunks.append((section_id, c))
        chunk_idx += len(chunks)
    log.info("UE1 ingest: produced %d chunks, embedding via Gemini", len(all_chunks))

    # Embed in batches of 100 (Gemini SDK accepts batches).
    embedder = get_embedding_llm()
    BATCH = 100
    embeddings: list[list[float]] = []
    for i in range(0, len(all_chunks), BATCH):
        batch = [c.text for _, c in all_chunks[i:i + BATCH]]
        embeddings.extend(embedder.embed(batch))

    with session_scope() as session:
        for (section_id, chunk), embedding in zip(all_chunks, embeddings):
            repo.insert_ue1_chunk(
                session,
                document_id=document_id,
                section_id=section_id,
                order_idx=chunk.order_idx,
                chunk_text=chunk.text,
                token_count=chunk.token_count,
                embedding=embedding,
            )

    duration_ms = (time.perf_counter() - t0) * 1000
    log.info("UE1 ingest: done in %.1f ms", duration_ms)
    return UE1IngestStats(
        snapshot_created=created,
        document_id=document_id,
        sections=len(flat_sections),
        chunks=len(all_chunks),
        duration_ms=duration_ms,
    )


def run_ue1_with_run_record(force: bool = False) -> int:
    """Convenience: write a meta.ingest_run row around the ingest."""
    settings = get_settings()
    fetched = fetch_article(settings.wikipedia_url)

    with session_scope() as session:
        snapshot_id, _ = repo.insert_or_get_snapshot(
            session,
            url=fetched.url,
            html=fetched.html,
            content_hash=fetched.content_hash,
            revision_id=fetched.revision_id,
            etag=fetched.etag,
        )
        run_id = repo.start_ingest_run(session, strategy="ue1", snapshot_id=snapshot_id)

    try:
        stats = run_ue1_ingest(force=force)
        with session_scope() as session:
            repo.finish_ingest_run(
                session, run_id, status="ok",
                stats={
                    "snapshot_created": stats.snapshot_created,
                    "document_id": stats.document_id,
                    "sections": stats.sections,
                    "chunks": stats.chunks,
                    "duration_ms": stats.duration_ms,
                },
            )
    except Exception as exc:  # noqa: BLE001
        log.exception("UE1 ingest failed")
        with session_scope() as session:
            repo.finish_ingest_run(session, run_id, status="failed", error=str(exc))
        raise
    return run_id
