"""健康检查路由"""

import requests
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db import get_db, engine
from app.models import SettingsModel
from app.schemas import HealthResponse
from app.config import config
from app.redis_client import r
from app.services.vector_store import collection_count

router = APIRouter(prefix="/api", tags=["Health"])


def _check_openai_compatible(base_url: str, api_key: str) -> str:
    if not api_key:
        return "down"
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=10)
    resp.raise_for_status()
    return "ok"


def _check_ollama() -> str:
    resp = requests.get(f"{config.OLLAMA_BASE_URL}/api/tags", timeout=5)
    resp.raise_for_status()
    return "ok"


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    # SQLite
    try:
        db.execute(text("SELECT 1"))
        sqlite_status = "ok"
    except Exception:
        sqlite_status = "down"

    # Redis
    try:
        r.ping()
        redis_queue_length = r.xlen("rag:jobs")
        redis_status = "ok"
    except Exception:
        redis_status = "down"
        redis_queue_length = 0

    # Chroma
    try:
        count = collection_count()
        chroma_status = "ok"
    except Exception:
        chroma_status = "down"

    # Providers
    settings = db.query(SettingsModel).first()
    chat_provider = (settings.chat_provider if settings else None) or (settings.provider if settings else None) or config.DEFAULT_CHAT_PROVIDER
    embedding_provider = (settings.embedding_provider if settings else None) or config.DEFAULT_EMBEDDING_PROVIDER

    try:
        if chat_provider == "ollama":
            chat_provider_status = _check_ollama()
        else:
            chat_provider_status = _check_openai_compatible(config.CHAT_API_BASE, config.CHAT_API_KEY)
    except Exception:
        chat_provider_status = "down"

    try:
        if embedding_provider == "ollama":
            embedding_provider_status = _check_ollama()
        else:
            embedding_provider_status = _check_openai_compatible(
                config.EMBEDDING_API_BASE,
                config.EMBEDDING_API_KEY,
            )
    except Exception:
        embedding_provider_status = "down"

    provider_status = "ok" if chat_provider_status == "ok" and embedding_provider_status == "ok" else "down"

    # 整体状态
    if sqlite_status == "down":
        overall = "down"
    elif any(s == "down" for s in [redis_status, chroma_status, chat_provider_status, embedding_provider_status]):
        overall = "degraded"
    else:
        overall = "ok"

    return HealthResponse(
        status=overall,
        sqlite=sqlite_status,
        redis=redis_status,
        chroma=chroma_status,
        provider=provider_status,
        chat_provider=chat_provider_status,
        embedding_provider=embedding_provider_status,
        redis_queue_length=redis_queue_length,
    )
