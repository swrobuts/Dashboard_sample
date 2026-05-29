from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.schemas import (
    CompareRequest,
    CompareResponse,
    IngestRequest,
    QueryRequest,
    QueryResponse,
    SourcePayload,
    StrategyResult,
)
from backend.config import get_settings
from backend.data import repo
from backend.data.pg import ping as pg_ping
from backend.data.pg import session_scope
from backend.data.wikipedia_loader import fetch_article
from backend.evaluation.judge import judge_answers
from backend.ingest.ue1_simple import run_ue1_ingest
from backend.ingest.ue2_pageindex import run_ue2_ingest
from backend.llm.factory import get_chat_llm
from backend.retrieval.base import RetrievalResult
from backend.retrieval.pageindex import PageIndexRAG
from backend.retrieval.simple import SimpleRAG

log = logging.getLogger(__name__)
router = APIRouter()


# ── Health & metadata ─────────────────────────────────────────────────────

@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "db_ok": pg_ping(),
        "gemini_configured": bool(settings.gemini_api_key),
        "local_llm_url": settings.local_llm_url,
        "wikipedia_url": settings.wikipedia_url,
    }


@router.get("/snapshot")
def snapshot() -> dict:
    settings = get_settings()
    with session_scope() as session:
        snap = repo.latest_snapshot(session, settings.wikipedia_url)
    if snap is None:
        return {"snapshot": None}
    # Make timestamps JSON-friendly.
    snap["fetched_at"] = snap["fetched_at"].isoformat() if snap.get("fetched_at") else None
    return {"snapshot": snap}


@router.get("/strategies")
def strategies() -> dict:
    implemented = {"ue1", "ue2"}
    out = {}
    for s in ("ue1", "ue2", "ue3"):
        with session_scope() as session:
            run = repo.latest_ingest_run(session, s)
            if s == "ue1":
                count = repo.ue1_chunk_count(session)
            elif s == "ue2":
                count = repo.ue2_tree_node_count(session)
            else:
                count = 0
        if run and run.get("started_at"):
            run["started_at"] = run["started_at"].isoformat()
        if run and run.get("finished_at"):
            run["finished_at"] = run["finished_at"].isoformat()
        out[s] = {
            "ingested": (run is not None and run.get("status") == "ok"),
            "implemented": s in implemented,
            "chunk_count": count,   # "chunks" for UE1, "nodes" for UE2 — same field for UI simplicity
            "last_run": run,
        }
    return {"strategies": out}


# ── Ingest ─────────────────────────────────────────────────────────────────

_ingest_lock = asyncio.Lock()


def _run_ingest_with_record(strategy: str, run_id: int, force: bool) -> None:
    """Worker: run the requested strategy's ingest and update meta.ingest_run."""
    try:
        if strategy == "ue1":
            s = run_ue1_ingest(force=force)
            stats = {
                "snapshot_created": s.snapshot_created,
                "document_id": s.document_id,
                "sections": s.sections,
                "chunks": s.chunks,
                "duration_ms": s.duration_ms,
            }
        elif strategy == "ue2":
            s = run_ue2_ingest(force=force)
            stats = {
                "document_id": s.document_id,
                "nodes": s.nodes,
                "leaves": s.leaves,
                "internal": s.internal,
                "llm_calls": s.llm_calls,
                "duration_ms": s.duration_ms,
            }
        else:
            raise ValueError(f"Strategy {strategy!r} not implemented")
        with session_scope() as session:
            repo.finish_ingest_run(session, run_id, status="ok", stats=stats)
    except Exception as exc:  # noqa: BLE001
        log.exception("%s ingest failed", strategy)
        with session_scope() as session:
            repo.finish_ingest_run(session, run_id, status="failed", error=str(exc))


@router.post("/ingest")
async def ingest(req: IngestRequest) -> dict:
    if req.strategy not in ("ue1", "ue2"):
        raise HTTPException(status_code=400, detail=f"Strategy {req.strategy} not implemented yet")
    if _ingest_lock.locked():
        raise HTTPException(status_code=409, detail="Another ingest is already running")

    settings = get_settings()
    # Synchronously fetch + create a snapshot row + start a run record so the
    # caller gets a run_id immediately.
    fetched = await asyncio.to_thread(fetch_article, settings.wikipedia_url)
    with session_scope() as session:
        snapshot_id, _ = repo.insert_or_get_snapshot(
            session,
            url=fetched.url,
            html=fetched.html,
            content_hash=fetched.content_hash,
            revision_id=fetched.revision_id,
            etag=fetched.etag,
        )
        run_id = repo.start_ingest_run(session, strategy=req.strategy, snapshot_id=snapshot_id)

    async def _run_locked() -> None:
        async with _ingest_lock:
            await asyncio.to_thread(_run_ingest_with_record, req.strategy, run_id, req.force)

    asyncio.create_task(_run_locked())
    return {"status": "started", "strategy": req.strategy, "run_id": run_id, "snapshot_id": snapshot_id}


@router.get("/ingest/{run_id}")
def ingest_status(run_id: int) -> dict:
    with session_scope() as session:
        row = repo.ingest_run(session, run_id)
    if row is None:
        raise HTTPException(404, "Run not found")
    if row.get("started_at"):
        row["started_at"] = row["started_at"].isoformat()
    if row.get("finished_at"):
        row["finished_at"] = row["finished_at"].isoformat()
    return row


# ── Query ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Du bist ein präziser Assistent, der ausschließlich auf Basis der "
    "bereitgestellten Auszüge aus dem deutschen Wikipedia-Artikel zu *Apple* "
    "antwortet. Wenn die Auszüge die Frage nicht beantworten, sage das ehrlich. "
    "Zitiere die Sektion in Klammern, z. B. (Geschichte > Gründung)."
)


def _build_user_prompt(query: str, result: RetrievalResult) -> str:
    parts = ["# Frage", query, "", "# Auszüge"]
    for i, ch in enumerate(result.chunks, start=1):
        header = f"## Auszug {i}"
        if ch.section_path:
            header += f" — {ch.section_path}"
        parts.append(header)
        parts.append(ch.text.strip())
        parts.append("")
    parts.append("# Aufgabe")
    parts.append(
        "Beantworte die Frage knapp und korrekt. Stütze jede Aussage auf die "
        "Auszüge oben und nenne in Klammern die Sektion."
    )
    return "\n".join(parts)


def _get_strategy(name: str, llm: str):
    if name == "ue1":
        return SimpleRAG(llm_provider=llm)
    if name == "ue2":
        return PageIndexRAG(llm_provider=llm)
    raise HTTPException(400, f"Strategy {name!r} not implemented yet")


def _run_strategy_and_answer(
    *, strategy: str, query: str, llm: str, k: int
) -> StrategyResult:
    """Shared by /query and /compare: retrieve + generate answer + collect metrics."""
    t0 = time.perf_counter()
    strat = _get_strategy(strategy, llm)
    result = strat.retrieve(query, k=k)
    if not result.chunks:
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return StrategyResult(
            strategy=strategy,
            answer=NO_CONTEXT_ANSWER,
            sources=[],
            trace={**result.trace, "skipped_llm": True, "reason": "no chunks retrieved"},
            latency_ms=latency_ms,
            llm_calls=int(result.trace.get("llm_calls_nav", 0)),
            token_usage={"prompt_tokens": 0, "completion_tokens": 0},
            skipped_llm=True,
        )
    chat = get_chat_llm(llm)
    user_prompt = _build_user_prompt(query, result)
    answer, usage = chat.generate(SYSTEM_PROMPT, user_prompt)
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    return StrategyResult(
        strategy=strategy,
        answer=answer,
        sources=[SourcePayload(**asdict(s)) for s in result.sources],
        trace=result.trace,
        latency_ms=latency_ms,
        llm_calls=int(result.trace.get("llm_calls_nav", 0)) + 1,
        token_usage={
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
        },
        skipped_llm=False,
    )


NO_CONTEXT_ANSWER = (
    "Ich kann diese Frage nicht beantworten, weil die ausgewählte "
    "Retrieval-Strategie zu dieser Frage keine Auszüge aus dem Wikipedia-"
    "Artikel gefunden hat. Mögliche Ursachen: die Navigation hat die "
    "relevante Sektion verfehlt, oder die gewählten Sektionen enthalten "
    "keinen Text. Probiere die Frage mit einer anderen Strategie oder "
    "formuliere sie spezifischer."
)


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    result = _run_strategy_and_answer(
        strategy=req.strategy, query=req.query, llm=req.llm, k=req.k or 8,
    )
    return QueryResponse(
        answer=result.answer,
        sources=result.sources,
        trace={**result.trace, "token_usage": result.token_usage},
        llm=req.llm,
        strategy=req.strategy,
        latency_ms=result.latency_ms,
    )


# ── Compare ────────────────────────────────────────────────────────────────

@router.post("/compare", response_model=CompareResponse)
async def compare(req: CompareRequest) -> CompareResponse:
    if not req.strategies:
        raise HTTPException(400, "At least one strategy must be selected")
    # Deduplicate while preserving order
    seen: set[str] = set()
    strategies = [s for s in req.strategies if not (s in seen or seen.add(s))]
    for s in strategies:
        if s not in ("ue1", "ue2"):
            raise HTTPException(400, f"Strategy {s!r} not implemented yet")

    t0 = time.perf_counter()

    # Run all strategies in parallel — each retrieves + generates its own
    # answer. asyncio.gather + to_thread keeps the event loop free during the
    # blocking LLM/DB calls.
    coros = [
        asyncio.to_thread(
            _run_strategy_and_answer,
            strategy=s,
            query=req.query,
            llm=req.llm,
            k=req.k or 8,
        )
        for s in strategies
    ]
    results: list[StrategyResult] = await asyncio.gather(*coros)

    # Judge runs once all strategies are done; uses Gemini for stable JSON.
    judge_payload = [
        {
            "strategy": r.strategy,
            "answer": r.answer,
            "sources": [s.model_dump() for s in r.sources],
        }
        for r in results
    ]
    evaluation = await asyncio.to_thread(judge_answers, req.query, judge_payload)
    total_latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    return CompareResponse(
        query=req.query,
        llm=req.llm,
        results=results,
        evaluation=evaluation.to_dict(),
        total_latency_ms=total_latency_ms,
    )


@router.post("/query/stream")
def query_stream(req: QueryRequest):
    strategy = _get_strategy(req.strategy, req.llm)
    result = strategy.retrieve(req.query, k=req.k or 8)

    def gen_empty():
        meta = {
            "type": "meta",
            "sources": [],
            "trace": {**result.trace, "skipped_llm": True, "reason": "no chunks retrieved"},
            "strategy": req.strategy,
            "llm": req.llm,
        }
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'token', 'text': NO_CONTEXT_ANSWER}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    if not result.chunks:
        return StreamingResponse(gen_empty(), media_type="text/event-stream")

    chat = get_chat_llm(req.llm)
    user_prompt = _build_user_prompt(req.query, result)

    def gen():
        meta = {
            "type": "meta",
            "sources": [asdict(s) for s in result.sources],
            "trace": result.trace,
            "strategy": req.strategy,
            "llm": req.llm,
        }
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
        for piece in chat.stream(SYSTEM_PROMPT, user_prompt):
            yield f"data: {json.dumps({'type': 'token', 'text': piece}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
