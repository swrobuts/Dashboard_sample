# backend/llm_client.py
"""
LLM-Abstraktionsschicht für Cloud (Anthropic), Lokal (LM Studio) und Hybrid-Betrieb.

Stellt eine einheitliche Schnittstelle bereit, sodass die Endpunkte in main.py
unabhängig vom gewählten Provider funktionieren.

Hybrid-Routing:
    - Einfache Tasks (triage, attachment_summary) → Lokal (LM Studio)
    - Komplexe Tasks (chat, graph, entities)      → Cloud (Anthropic)
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Generator, Literal

import anthropic
import openai

# ── Konfiguration ────────────────────────────────────────────────────────────

LOCAL_LLM_ENDPOINT = os.getenv("LOCAL_LLM_ENDPOINT", "http://localhost:1234/v1")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5-32b-instruct")
CLOUD_MODEL = "claude-opus-4-6"

TaskKind = Literal["triage", "attachment_summary", "entities", "chat", "graph", "train_extract"]

# Tasks die im Hybrid-Modus lokal laufen (schnell, einfache Struktur)
_LOCAL_TASKS: set[TaskKind] = {"triage", "attachment_summary", "train_extract"}

# Tasks die im Hybrid-Modus in der Cloud laufen (komplex, zuverlässiger)
_CLOUD_TASKS: set[TaskKind] = {"chat", "graph", "entities"}

# Tasks die JSON-Output brauchen (für response_format bei lokalen Modellen)
_JSON_TASKS: set[TaskKind] = {"triage", "entities", "graph"}


def _strip_fences(text: str) -> str:
    """Entfernt Markdown-Code-Fences falls das LLM JSON in ```json ... ``` verpackt."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


# ── Cloud Client (Anthropic) ────────────────────────────────────────────────

class CloudLLMClient:
    """Nutzt die Anthropic Claude API — bisheriges Standardverhalten."""

    def __init__(self, api_key: str = ""):
        self._client = anthropic.Anthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY", "")
        )
        self.mode = "cloud"

    def create(
        self,
        task: TaskKind,
        prompt: str,
        max_tokens: int = 512,
        system: str | None = None,
    ) -> str:
        """Synchroner Aufruf — gibt rohen Text zurück."""
        kwargs: dict = {
            "model": CLOUD_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)
        return response.content[0].text

    def stream(
        self,
        task: TaskKind,
        prompt: str,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> Generator[str, None, None]:
        """Streaming — gibt Text-Chunks zurück."""
        kwargs: dict = {
            "model": CLOUD_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

    def check_health(self) -> dict:
        return {"status": "ok", "provider": "anthropic", "model": CLOUD_MODEL}


# ── Local Client (LM Studio / OpenAI-kompatibel) ────────────────────────────

class LocalLLMClient:
    """Nutzt einen lokalen OpenAI-kompatiblen Server (LM Studio, Ollama, vLLM)."""

    def __init__(self, endpoint: str = "", model: str = ""):
        self._endpoint = endpoint or LOCAL_LLM_ENDPOINT
        self._model = model or LOCAL_LLM_MODEL
        self._client = openai.OpenAI(
            base_url=self._endpoint,
            api_key="lm-studio",  # LM Studio braucht keinen echten Key
        )
        self.mode = "local"

    def create(
        self,
        task: TaskKind,
        prompt: str,
        max_tokens: int = 512,
        system: str | None = None,
    ) -> str:
        """Synchroner Aufruf via OpenAI-kompatible API."""
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": 0.1,  # niedrig für konsistente Klassifikation
        }
        # JSON-Mode für strukturierte Ausgaben (nicht alle Modelle unterstützen das)
        if task in _JSON_TASKS:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.BadRequestError:
            # Modell unterstützt response_format nicht → ohne JSON-Mode wiederholen
            kwargs.pop("response_format", None)
            response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def stream(
        self,
        task: TaskKind,
        prompt: str,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> Generator[str, None, None]:
        """Streaming via OpenAI-kompatible API."""
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=messages,
            temperature=0.3,
            stream=True,
        )
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def check_health(self) -> dict:
        """Prüft ob der lokale LLM-Server erreichbar ist."""
        try:
            self._client.models.list()
            return {
                "status": "ok",
                "provider": "local",
                "endpoint": self._endpoint,
                "model": self._model,
            }
        except Exception as exc:
            return {
                "status": "unreachable",
                "provider": "local",
                "endpoint": self._endpoint,
                "error": str(exc)[:200],
            }


# ── Hybrid Client (routet pro Task) ─────────────────────────────────────────

class HybridLLMClient:
    """Routet einfache Tasks lokal, komplexe Tasks in die Cloud.

    Fallback: Wenn der lokale Server nicht erreichbar ist, werden auch
    die einfachen Tasks an die Cloud delegiert (mit Log-Warning).
    """

    def __init__(self, cloud: CloudLLMClient, local: LocalLLMClient):
        self._cloud = cloud
        self._local = local
        self.mode = "hybrid"

    def _pick(self, task: TaskKind) -> CloudLLMClient | LocalLLMClient:
        """Wählt den Client basierend auf Task-Typ."""
        if task in _LOCAL_TASKS:
            return self._local
        return self._cloud

    def _fallback_cloud(self, task: TaskKind, exc: Exception) -> CloudLLMClient:
        """Loggt Warnung und gibt Cloud-Client als Fallback zurück."""
        logging.warning(
            f"[Hybrid] Lokaler LLM-Server nicht erreichbar für Task '{task}': "
            f"{type(exc).__name__}: {exc} — Fallback auf Cloud"
        )
        return self._cloud

    def create(
        self,
        task: TaskKind,
        prompt: str,
        max_tokens: int = 512,
        system: str | None = None,
    ) -> str:
        client = self._pick(task)
        try:
            return client.create(task=task, prompt=prompt, max_tokens=max_tokens, system=system)
        except (openai.APIConnectionError, openai.APITimeoutError, ConnectionError) as exc:
            if client is self._local:
                return self._fallback_cloud(task, exc).create(
                    task=task, prompt=prompt, max_tokens=max_tokens, system=system
                )
            raise

    def stream(
        self,
        task: TaskKind,
        prompt: str,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> Generator[str, None, None]:
        client = self._pick(task)
        try:
            yield from client.stream(task=task, prompt=prompt, max_tokens=max_tokens, system=system)
        except (openai.APIConnectionError, openai.APITimeoutError, ConnectionError) as exc:
            if client is self._local:
                yield from self._fallback_cloud(task, exc).stream(
                    task=task, prompt=prompt, max_tokens=max_tokens, system=system
                )
            else:
                raise

    def check_health(self) -> dict:
        return {
            "status": "ok",
            "provider": "hybrid",
            "cloud": self._cloud.check_health(),
            "local": self._local.check_health(),
        }


# ── Factory ──────────────────────────────────────────────────────────────────

# Singletons — werden einmal erzeugt und von allen Sessions geteilt
_cloud_client: CloudLLMClient | None = None
_local_client: LocalLLMClient | None = None


def _get_cloud() -> CloudLLMClient:
    global _cloud_client
    if _cloud_client is None:
        _cloud_client = CloudLLMClient()
    return _cloud_client


def _get_local() -> LocalLLMClient:
    global _local_client
    if _local_client is None:
        _local_client = LocalLLMClient()
    return _local_client


def get_llm_client(mode: str = "cloud") -> CloudLLMClient | LocalLLMClient | HybridLLMClient:
    """Erzeugt den passenden LLM-Client für den gewählten Modus.

    Args:
        mode: "cloud" | "local" | "hybrid"

    Returns:
        LLMClient-Instanz mit .create() und .stream() Methoden.
    """
    if mode == "local":
        return _get_local()
    if mode == "hybrid":
        return HybridLLMClient(cloud=_get_cloud(), local=_get_local())
    # Default: cloud
    return _get_cloud()
