"""设置路由"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import SettingsModel
from app.schemas import ProviderSettingsRequest, SettingsResponse
from app.config import config

router = APIRouter(prefix="/api/settings", tags=["Settings"])


def _settings_response(s: SettingsModel) -> SettingsResponse:
    chat_provider = s.chat_provider or s.provider or config.DEFAULT_CHAT_PROVIDER
    embedding_provider = s.embedding_provider or config.DEFAULT_EMBEDDING_PROVIDER
    return SettingsResponse(
        provider=chat_provider,
        chat_provider=chat_provider,
        embedding_provider=embedding_provider,
        chat_model=s.chat_model or config.DEFAULT_CHAT_MODEL,
        embed_model=s.embed_model or config.DEFAULT_EMBED_MODEL,
        top_k=s.top_k,
        stream=s.stream,
        vision_provider=(s.vision_provider if hasattr(s, "vision_provider") and s.vision_provider else "openai"),
        vision_model=(s.vision_model if hasattr(s, "vision_model") and s.vision_model else config.VISION_MODEL),
    )


@router.get("/provider", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    s = db.query(SettingsModel).first()
    if not s:
        s = SettingsModel(
            provider=config.DEFAULT_CHAT_PROVIDER,
            chat_provider=config.DEFAULT_CHAT_PROVIDER,
            embedding_provider=config.DEFAULT_EMBEDDING_PROVIDER,
            chat_model=config.DEFAULT_CHAT_MODEL,
            embed_model=config.DEFAULT_EMBED_MODEL,
        )
        db.add(s)
        db.commit()
        db.refresh(s)
    return _settings_response(s)


@router.post("/provider", response_model=SettingsResponse)
def update_settings(req: ProviderSettingsRequest, db: Session = Depends(get_db)):
    s = db.query(SettingsModel).first()
    if not s:
        s = SettingsModel(
            provider=config.DEFAULT_CHAT_PROVIDER,
            chat_provider=config.DEFAULT_CHAT_PROVIDER,
            embedding_provider=config.DEFAULT_EMBEDDING_PROVIDER,
            chat_model=config.DEFAULT_CHAT_MODEL,
            embed_model=config.DEFAULT_EMBED_MODEL,
        )
        db.add(s)

    chat_provider = req.chat_provider or req.provider
    if chat_provider is not None:
        if chat_provider not in ("ollama", "openai"):
            raise HTTPException(400, "chat_provider 只支持 ollama 或 openai")
        s.chat_provider = chat_provider
        s.provider = chat_provider
    if req.embedding_provider is not None:
        if req.embedding_provider not in ("ollama", "openai"):
            raise HTTPException(400, "embedding_provider 只支持 ollama 或 openai")
        s.embedding_provider = req.embedding_provider
    if req.chat_model is not None:
        s.chat_model = req.chat_model
    if req.embed_model is not None:
        s.embed_model = req.embed_model
    if req.top_k is not None:
        s.top_k = req.top_k
    if req.stream is not None:
        s.stream = req.stream
    if req.vision_provider is not None:
        if req.vision_provider not in ("openai",):
            raise HTTPException(400, "vision_provider 只支持 openai")
        s.vision_provider = req.vision_provider
    if req.vision_model is not None:
        s.vision_model = req.vision_model

    db.commit()
    db.refresh(s)
    return _settings_response(s)
