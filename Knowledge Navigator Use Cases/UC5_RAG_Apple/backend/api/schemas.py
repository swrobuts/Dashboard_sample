from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Strategy = Literal["ue1", "ue2", "ue3"]
LLMProvider = Literal["gemini", "local"]


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    strategy: Strategy = "ue1"
    llm: LLMProvider = "gemini"
    k: int | None = Field(default=None, ge=1, le=32)


class IngestRequest(BaseModel):
    strategy: Strategy = "ue1"
    force: bool = False


class SourcePayload(BaseModel):
    chunk_id: int | None
    section_path: str | None
    text: str
    distance: float | None = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourcePayload]
    trace: dict
    llm: LLMProvider
    strategy: Strategy
    latency_ms: float
