from fastapi import APIRouter

from backend.config import get_settings
from backend.data.pg import ping as pg_ping

router = APIRouter()


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
