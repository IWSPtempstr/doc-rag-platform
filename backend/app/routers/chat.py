"""问答路由"""

import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import ChatSessionModel, ChatMessageModel, SettingsModel
from app.schemas import ChatQueryRequest, ChatQueryResponse, ChatSessionResponse, Citation
from app.services.rag_service import rag_query
from app.services.rate_limit import check_chat_rate
from app.services.trace_service import log_query
from app.config import config

router = APIRouter(prefix="/api/chat", tags=["Chat"])


def _get_settings(db: Session) -> SettingsModel:
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
    return s


@router.post("/query", response_model=ChatQueryResponse)
def query(req: ChatQueryRequest, db: Session = Depends(get_db)):
    # 限流
    allowed, remaining = check_chat_rate()
    if not allowed:
        raise HTTPException(429, detail={"message": "请求频率过高", "retry_after": 60})

    settings = _get_settings(db)
    top_k = req.top_k or settings.top_k
    chat_provider = settings.chat_provider or settings.provider
    embedding_provider = settings.embedding_provider
    model = settings.chat_model
    embedding_model = settings.embed_model

    t0 = time.time()
    try:
        result = rag_query(
            question=req.question,
            top_k=top_k,
            model=model,
            chat_provider=chat_provider,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
        )
    except RuntimeError as e:
        message = str(e)
        status_code = 503 if "未配置" in message else 502
        raise HTTPException(status_code, detail={"message": message})
    except Exception as e:
        raise HTTPException(500, detail={"message": f"RAG 查询失败: {e}"})
    duration_ms = (time.time() - t0) * 1000

    # 保存到 session
    session_title = req.question[:100]
    chat_session = ChatSessionModel(title=session_title)
    db.add(chat_session)
    db.flush()

    user_msg = ChatMessageModel(
        session_id=chat_session.id, role="user", content=req.question,
    )
    assistant_msg = ChatMessageModel(
        session_id=chat_session.id,
        role="assistant",
        content=result["answer"],
        citations=result.get("citations", []),
        model=result.get("model", ""),
        cache_hit=result.get("cache_hit", False),
    )
    db.add_all([user_msg, assistant_msg])
    db.commit()

    # Trace
    log_query(
        question=req.question,
        answer=result["answer"],
        strategy="dense",
        candidates=result.get("citations", []),
        final_citations=result.get("citations", []),
        duration_ms=duration_ms,
        cache_hit=result.get("cache_hit", False),
    )

    return ChatQueryResponse(
        answer=result["answer"],
        citations=[Citation(**c) for c in result.get("citations", [])],
        model=result.get("model", ""),
        provider=result.get("provider", ""),
        chat_provider=result.get("chat_provider", result.get("provider", "")),
        embedding_provider=result.get("embedding_provider", ""),
        embedding_model=result.get("embedding_model", ""),
        cache_hit=result.get("cache_hit", False),
        session_id=chat_session.id,
    )


@router.get("/sessions", response_model=list[ChatSessionResponse])
def list_sessions(db: Session = Depends(get_db)):
    sessions = db.query(ChatSessionModel).order_by(ChatSessionModel.updated_at.desc()).limit(50).all()
    result = []
    for s in sessions:
        msgs = [
            {"role": m.role, "content": m.content, "citations": m.citations, "cache_hit": m.cache_hit}
            for m in s.messages
        ]
        result.append(ChatSessionResponse(
            id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at, messages=msgs,
        ))
    return result


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
def get_session(session_id: int, db: Session = Depends(get_db)):
    s = db.query(ChatSessionModel).filter(ChatSessionModel.id == session_id).first()
    if not s:
        raise HTTPException(404, "会话不存在")
    msgs = [
        {"role": m.role, "content": m.content, "citations": m.citations, "cache_hit": m.cache_hit}
        for m in s.messages
    ]
    return ChatSessionResponse(
        id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at, messages=msgs,
    )
