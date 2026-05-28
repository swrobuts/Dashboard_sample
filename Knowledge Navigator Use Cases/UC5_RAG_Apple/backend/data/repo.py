"""Thin data-access helpers — every retrieval strategy goes through these,
so the SQL stays in one place and the business logic stays declarative."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from pgvector.sqlalchemy import Vector  # noqa: F401  (registers the type)
from sqlalchemy import text
from sqlalchemy.orm import Session


# ── raw ────────────────────────────────────────────────────────────────────

def insert_or_get_snapshot(
    session: Session,
    *,
    url: str,
    html: str,
    content_hash: str,
    revision_id: str | None,
    etag: str | None,
) -> tuple[int, bool]:
    """Insert a snapshot or return the existing one if the hash matches.

    Returns (snapshot_id, created).
    """
    existing = session.execute(
        text(
            "SELECT id FROM raw.wikipedia_snapshot "
            "WHERE url = :url AND content_hash = :h"
        ),
        {"url": url, "h": content_hash},
    ).scalar()
    if existing is not None:
        return int(existing), False

    new_id = session.execute(
        text(
            "INSERT INTO raw.wikipedia_snapshot "
            "(url, html, content_hash, revision_id, etag) "
            "VALUES (:url, :html, :h, :rev, :etag) "
            "RETURNING id"
        ),
        {"url": url, "html": html, "h": content_hash, "rev": revision_id, "etag": etag},
    ).scalar()
    return int(new_id), True


def latest_snapshot(session: Session, url: str) -> dict | None:
    row = session.execute(
        text(
            "SELECT id, url, fetched_at, revision_id, content_hash "
            "FROM raw.wikipedia_snapshot WHERE url = :url "
            "ORDER BY fetched_at DESC LIMIT 1"
        ),
        {"url": url},
    ).mappings().first()
    return dict(row) if row else None


# ── clean ──────────────────────────────────────────────────────────────────

def upsert_clean_document(
    session: Session,
    *,
    snapshot_id: int,
    title: str,
    markdown: str,
) -> int:
    existing = session.execute(
        text("SELECT id FROM clean.document WHERE snapshot_id = :s"),
        {"s": snapshot_id},
    ).scalar()
    if existing is not None:
        # Keep the document idempotent for the same snapshot.
        session.execute(
            text("DELETE FROM clean.section WHERE document_id = :d"),
            {"d": existing},
        )
        return int(existing)
    new_id = session.execute(
        text(
            "INSERT INTO clean.document (snapshot_id, title, markdown) "
            "VALUES (:s, :t, :m) RETURNING id"
        ),
        {"s": snapshot_id, "t": title, "m": markdown},
    ).scalar()
    return int(new_id)


def insert_section(
    session: Session,
    *,
    document_id: int,
    parent_id: int | None,
    level: int,
    heading: str,
    path: str,
    order_idx: int,
    text_: str,
) -> int:
    new_id = session.execute(
        text(
            "INSERT INTO clean.section "
            "(document_id, parent_id, level, heading, path, order_idx, text) "
            "VALUES (:d, :p, :l, :h, :path, :o, :txt) RETURNING id"
        ),
        {"d": document_id, "p": parent_id, "l": level, "h": heading,
         "path": path, "o": order_idx, "txt": text_},
    ).scalar()
    return int(new_id)


# ── ue1 ────────────────────────────────────────────────────────────────────

def delete_ue1_chunks(session: Session, document_id: int) -> None:
    session.execute(
        text("DELETE FROM ue1.chunk WHERE document_id = :d"),
        {"d": document_id},
    )


def insert_ue1_chunk(
    session: Session,
    *,
    document_id: int,
    section_id: int | None,
    order_idx: int,
    chunk_text: str,
    token_count: int,
    embedding: list[float],
) -> None:
    session.execute(
        text(
            "INSERT INTO ue1.chunk "
            "(document_id, section_id, order_idx, text, token_count, embedding) "
            "VALUES (:d, :s, :o, :t, :tc, :e)"
        ),
        {"d": document_id, "s": section_id, "o": order_idx,
         "t": chunk_text, "tc": token_count, "e": str(embedding)},
    )


@dataclass
class RetrievedChunk:
    chunk_id: int
    section_id: int | None
    section_path: str | None
    text: str
    distance: float
    order_idx: int


def topk_ue1(session: Session, query_embedding: Sequence[float], k: int) -> list[RetrievedChunk]:
    rows = session.execute(
        text(
            "SELECT c.id, c.section_id, s.path AS section_path, c.text, "
            "       c.order_idx, "
            "       c.embedding <=> CAST(:q AS vector) AS distance "
            "FROM ue1.chunk c "
            "LEFT JOIN clean.section s ON s.id = c.section_id "
            "ORDER BY distance ASC LIMIT :k"
        ),
        {"q": str(list(query_embedding)), "k": k},
    ).mappings().all()
    return [
        RetrievedChunk(
            chunk_id=int(r["id"]),
            section_id=int(r["section_id"]) if r["section_id"] is not None else None,
            section_path=r["section_path"],
            text=r["text"],
            distance=float(r["distance"]),
            order_idx=int(r["order_idx"]),
        )
        for r in rows
    ]


def ue1_chunk_count(session: Session, document_id: int | None = None) -> int:
    if document_id is None:
        return int(session.execute(text("SELECT COUNT(*) FROM ue1.chunk")).scalar() or 0)
    return int(
        session.execute(
            text("SELECT COUNT(*) FROM ue1.chunk WHERE document_id = :d"),
            {"d": document_id},
        ).scalar()
        or 0
    )


# ── meta ───────────────────────────────────────────────────────────────────

def start_ingest_run(session: Session, *, strategy: str, snapshot_id: int) -> int:
    new_id = session.execute(
        text(
            "INSERT INTO meta.ingest_run (strategy, snapshot_id, status) "
            "VALUES (:s, :sn, 'running') RETURNING id"
        ),
        {"s": strategy, "sn": snapshot_id},
    ).scalar()
    return int(new_id)


def finish_ingest_run(
    session: Session,
    run_id: int,
    *,
    status: str,
    stats: dict | None = None,
    error: str | None = None,
) -> None:
    session.execute(
        text(
            "UPDATE meta.ingest_run "
            "SET finished_at = NOW(), status = :st, stats = :stats, error = :err "
            "WHERE id = :id"
        ),
        {"st": status, "stats": json.dumps(stats or {}), "err": error, "id": run_id},
    )


def latest_ingest_run(session: Session, strategy: str) -> dict | None:
    row = session.execute(
        text(
            "SELECT id, strategy, snapshot_id, started_at, finished_at, status, stats, error "
            "FROM meta.ingest_run "
            "WHERE strategy = :s "
            "ORDER BY started_at DESC LIMIT 1"
        ),
        {"s": strategy},
    ).mappings().first()
    return dict(row) if row else None


def ingest_run(session: Session, run_id: int) -> dict | None:
    row = session.execute(
        text(
            "SELECT id, strategy, snapshot_id, started_at, finished_at, status, stats, error "
            "FROM meta.ingest_run WHERE id = :id"
        ),
        {"id": run_id},
    ).mappings().first()
    return dict(row) if row else None
