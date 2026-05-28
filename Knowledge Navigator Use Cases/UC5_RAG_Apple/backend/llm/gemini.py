"""Gemini chat + embedding via the official ``google-genai`` SDK."""
from __future__ import annotations

from typing import Iterator

from google import genai
from google.genai import types

from backend.config import get_settings
from backend.llm.base import TokenUsage


class GeminiChat:
    name = "gemini"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_chat_model

    def _config(self, system: str) -> types.GenerateContentConfig:
        settings = get_settings()
        return types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=settings.max_tokens_per_call,
            temperature=0.2,
        )

    def generate(self, system: str, user: str) -> tuple[str, TokenUsage]:
        resp = self._client.models.generate_content(
            model=self._model,
            contents=user,
            config=self._config(system),
        )
        usage = TokenUsage(
            prompt_tokens=getattr(resp.usage_metadata, "prompt_token_count", 0) or 0,
            completion_tokens=getattr(resp.usage_metadata, "candidates_token_count", 0) or 0,
        )
        return (resp.text or "", usage)

    def stream(self, system: str, user: str) -> Iterator[str]:
        for chunk in self._client.models.generate_content_stream(
            model=self._model,
            contents=user,
            config=self._config(system),
        ):
            if chunk.text:
                yield chunk.text


class GeminiEmbedder:
    name = "gemini"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.gemini_embedding_model
        self.dim = settings.gemini_embedding_dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # The SDK accepts a list under ``contents``.
        resp = self._client.models.embed_content(
            model=self._model,
            contents=texts,
        )
        return [list(e.values) for e in resp.embeddings]
