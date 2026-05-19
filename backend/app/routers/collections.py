"""Collections 路由 (v1.1) — 从 Chroma 动态发现 + SQLite 元数据"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import CollectionModel
from app.schemas import CollectionResponse
from app.services.vector_store import _client as chroma_client

router = APIRouter(prefix="/api/collections", tags=["Collections"])


def _sync_chroma_collections(db: Session) -> list[dict]:
    """将 Chroma 中实际存在的 collection 同步到 SQLite，并返回合并列表"""
    try:
        chroma_cols = chroma_client.list_collections()
    except Exception:
        chroma_cols = []

    result = []
    for col in chroma_cols:
        try:
            doc_count = col.count()
        except Exception:
            doc_count = 0

        # 如果 DB 里没有这个名字，插入
        existing = db.query(CollectionModel).filter(CollectionModel.name == col.name).first()
        if not existing:
            existing = CollectionModel(name=col.name, description="", document_count=doc_count)
            db.add(existing)
        else:
            existing.document_count = doc_count
        db.commit()
        db.refresh(existing)

        result.append({
            "id": existing.id,
            "name": existing.name,
            "description": existing.description,
            "document_count": existing.document_count,
        })
    return result


@router.get("", response_model=list[CollectionResponse])
def list_collections(db: Session = Depends(get_db)):
    merged = _sync_chroma_collections(db)
    return [CollectionResponse(**m) for m in merged]


@router.get("/{collection_id}", response_model=CollectionResponse)
def get_collection(collection_id: int, db: Session = Depends(get_db)):
    _sync_chroma_collections(db)
    c = db.query(CollectionModel).filter(CollectionModel.id == collection_id).first()
    if not c:
        raise HTTPException(404, "集合不存在")
    return c
