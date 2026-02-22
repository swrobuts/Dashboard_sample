# backend/web_search.py
from __future__ import annotations
import logging
import re

import httpx

# Trigger pattern — if user message matches, run web search
WEB_SEARCH_TRIGGER_RE = re.compile(
    r'recherchiere|suche\s+mal|was\s+ist|wer\s+ist|was\s+bedeutet',
    re.IGNORECASE,
)

_DDGO_URL = "https://api.duckduckgo.com/"
_TIMEOUT = 5.0


def search_web(query: str, max_results: int = 3) -> list[dict]:
    """Query DuckDuckGo Instant Answer API (no key needed).

    Returns list of {"snippet": str, "url": str}.
    Returns [] on any error (non-blocking).
    """
    try:
        resp = httpx.get(
            _DDGO_URL,
            params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logging.warning(f"[WebSearch] DuckDuckGo fehlgeschlagen: {exc}")
        return []

    results: list[dict] = []
    if data.get("Abstract"):
        results.append({"snippet": data["Abstract"], "url": data.get("AbstractURL", "")})
    remaining = max(0, max_results - len(results))
    for topic in data.get("RelatedTopics", [])[:remaining]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append({"snippet": topic["Text"], "url": topic.get("FirstURL", "")})
            if len(results) >= max_results:
                break
        elif isinstance(topic, dict) and "Topics" in topic:
            logging.debug(f"[WebSearch] Themengruppe übersprungen: {topic.get('Name', '?')}")
    return results


def build_web_context(query: str, max_results: int = 3) -> tuple[str, list[dict]]:
    """Run search and return (context_block, raw_results).

    context_block is empty string if no results.
    raw_results are used for fact extraction.
    """
    results = search_web(query, max_results=max_results)
    if not results:
        return "", []
    lines = [f"\n=== WEBSUCHE: '{query}' ==="]
    for r in results:
        lines.append(f"  {r['snippet']}")
        if r["url"]:
            lines.append(f"  Quelle: {r['url']}")
    return "\n".join(lines), results
