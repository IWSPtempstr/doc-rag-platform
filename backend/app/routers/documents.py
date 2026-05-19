"""文档管理路由"""

import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import DocumentModel, JobModel, SettingsModel
from app.schemas import (
    DocumentResponse, DocumentUpdate, UploadResponse, DocumentChunkResponse,
    ReindexResponse, ImageAssetResponse,
)
from app.redis_client import enqueue_job, acquire_document_lock, invalidate_cache
from app.services.vector_store import delete_document as chroma_delete, count_chunks
from app.services.rate_limit import check_upload_rate
from app.services.asset_service import get_assets_for_document
from app.config import config

router = APIRouter(prefix="/api/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".markdown", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

os.makedirs(config.UPLOAD_DIR, exist_ok=True)


@router.post("/upload", response_model=UploadResponse)
def upload_document(
    file: UploadFile = File(...),
    tags: str = Form(""),
    db: Session = Depends(get_db),
):
    # 格式校验
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件格式: {ext}。支持: {', '.join(ALLOWED_EXTENSIONS)}")

    # 限流
    allowed, remaining = check_upload_rate()
    if not allowed:
        raise HTTPException(429, detail={"message": "上传频率过高", "retry_after": 60})

    # 保存文件
    safe_name = f"{int(os.path.getmtime(config.UPLOAD_DIR) or 0)}_{file.filename}"
    stored_path = os.path.join(config.UPLOAD_DIR, safe_name)
    with open(stored_path, "wb") as f:
        content = file.file.read()
        f.write(content)

    is_image = ext in IMAGE_EXTENSIONS

    # 创建 document 记录
    doc = DocumentModel(
        filename=file.filename,
        stored_path=stored_path,
        content_type=f"image/{ext.lstrip('.')}" if is_image else ext.lstrip("."),
        size_bytes=len(content),
        status="pending",
        tags=tags,
    )
    db.add(doc)
    db.flush()

    # 创建 job 记录
    job = JobModel(document_id=doc.id, type="ingestion", status="pending")
    db.add(job)
    db.commit()
    db.refresh(doc)
    db.refresh(job)

    # 入队
    enqueue_job(job.id, doc.id, stored_path, doc.content_type)

    return UploadResponse(
        document_id=doc.id,
        job_id=job.id,
        filename=doc.filename,
        content_type=doc.content_type,
        size_bytes=doc.size_bytes,
        is_image=is_image,
    )


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    tag: str = Query(default=""),
    status: str = Query(default=""),
    search: str = Query(default=""),
    has_images: bool | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(DocumentModel)
    if tag:
        q = q.filter(DocumentModel.tags.contains(tag))
    if status:
        q = q.filter(DocumentModel.status == status)
    if search:
        q = q.filter(DocumentModel.filename.contains(search))
    if has_images is not None:
        q = q.filter(DocumentModel.has_images == has_images)
    docs = q.order_by(DocumentModel.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for doc in docs:
        r = DocumentResponse.model_validate(doc)
        latest_job = (
            db.query(JobModel)
            .filter(JobModel.document_id == doc.id)
            .order_by(JobModel.created_at.desc())
            .first()
        )
        if latest_job:
            r.latest_job = {
                "id": latest_job.id,
                "type": latest_job.type,
                "status": latest_job.status,
                "error": latest_job.error,
            }
        results.append(r)
    return results


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(404, "文档不存在")
    r = DocumentResponse.model_validate(doc)
    latest_job = (
        db.query(JobModel)
        .filter(JobModel.document_id == doc.id)
        .order_by(JobModel.created_at.desc())
        .first()
    )
    if latest_job:
        r.latest_job = {
            "id": latest_job.id,
            "type": latest_job.type,
            "status": latest_job.status,
            "error": latest_job.error,
        }
    return r


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(document_id: int, data: DocumentUpdate, db: Session = Depends(get_db)):
    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(404, "文档不存在")

    if data.filename is not None:
        doc.filename = data.filename
    if data.tags is not None:
        doc.tags = data.tags

    doc.kb_version += 1
    db.commit()
    db.refresh(doc)
    invalidate_cache()
    return doc


@router.delete("/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(404, "文档不存在")

    # 删除本地文件
    if os.path.exists(doc.stored_path):
        os.remove(doc.stored_path)

    # 删除 Chroma 向量
    chroma_delete(document_id)

    db.delete(doc)
    db.commit()
    invalidate_cache()
    return {"ok": True}


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkResponse])
def get_document_chunks(document_id: int, db: Session = Depends(get_db)):
    """v2.0: 获取文档的 chunk 列表，含图片引用"""
    import json

    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(404, "文档不存在")

    from app.services.vector_store import get_collection
    try:
        settings = db.query(SettingsModel).first()
        embedding_provider = (settings.embedding_provider if settings else None) or config.DEFAULT_EMBEDDING_PROVIDER
        embedding_model = (settings.embed_model if settings else None) or config.DEFAULT_EMBED_MODEL
        collection = get_collection(embedding_provider, embedding_model)
        result = collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
        chunks = []
        if result and result["ids"]:
            for i, cid in enumerate(result["ids"]):
                meta = result["metadatas"][i] if result["metadatas"] else {}
                content = result["documents"][i] if result["documents"] else ""
                image_refs_str = meta.get("image_refs", "[]")
                try:
                    image_refs = json.loads(image_refs_str) if isinstance(image_refs_str, str) else image_refs_str
                except (json.JSONDecodeError, TypeError):
                    image_refs = []
                chunks.append(DocumentChunkResponse(
                    chunk_id=meta.get("chunk_id", cid),
                    document_id=document_id,
                    filename=doc.filename,
                    content=content,
                    metadata=meta,
                    image_refs=image_refs,
                ))
        return chunks
    except Exception:
        return []


@router.post("/{document_id}/reindex", response_model=ReindexResponse)
def reindex_document(document_id: int, db: Session = Depends(get_db)):
    """v2.0: 重新索引文档"""
    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(404, "文档不存在")
    if not os.path.exists(doc.stored_path):
        raise HTTPException(400, "源文件不存在，无法重新索引")

    # Reset state
    doc.status = "pending"
    doc.kb_version += 1
    doc.chunk_count = 0
    doc.image_count = 0
    doc.has_images = False

    # Delete old image assets
    from app.models import ImageAssetModel
    old_assets = db.query(ImageAssetModel).filter(
        ImageAssetModel.document_id == document_id
    ).all()
    for asset in old_assets:
        if os.path.exists(asset.stored_path):
            try:
                os.remove(asset.stored_path)
            except Exception:
                pass
        db.delete(asset)

    # Create reindex job
    job = JobModel(document_id=doc.id, type="reindex", status="pending")
    db.add(job)
    db.commit()
    db.refresh(doc)
    db.refresh(job)

    enqueue_job(job.id, doc.id, doc.stored_path, doc.content_type)

    return ReindexResponse(
        document_id=doc.id,
        job_id=job.id,
        message=f"重新索引已提交, job_id={job.id}",
    )


@router.get("/{document_id}/assets", response_model=list[ImageAssetResponse])
def list_document_assets(document_id: int, db: Session = Depends(get_db)):
    """v2.0: 获取文档关联的图片资产"""
    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(404, "文档不存在")
    return get_assets_for_document(db, document_id)


@router.get("/{document_id}/jobs")
def list_document_jobs(document_id: int, db: Session = Depends(get_db)):
    """v2.0: 获取文档的所有处理任务"""
    from app.schemas import JobResponse
    from app.redis_client import get_job_progress

    doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not doc:
        raise HTTPException(404, "文档不存在")

    jobs = (
        db.query(JobModel)
        .filter(JobModel.document_id == document_id)
        .order_by(JobModel.created_at.desc())
        .limit(20)
        .all()
    )
    result = []
    for job in jobs:
        progress = get_job_progress(job.id)
        result.append(JobResponse(
            id=job.id,
            document_id=job.document_id,
            type=job.type,
            status=job.status,
            error=job.error,
            retry_count=job.retry_count,
            created_at=job.created_at,
            updated_at=job.updated_at,
            progress=progress,
        ))
    return result
