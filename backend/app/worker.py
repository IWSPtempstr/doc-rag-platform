"""Worker — Redis Streams 消费者，处理文档 indexing"""

import os
import time
import traceback
from app.config import config
from app.db import SessionLocal, ensure_sqlite_schema
from app.models import DocumentModel, JobModel, SettingsModel
from app.redis_client import r, set_job_progress, acquire_document_lock, release_document_lock, invalidate_cache
from app.services.document_loader import load_document, load_document_v2
from app.services.splitter import split_text, split_text_v2
from app.services.embedding_provider import get_embeddings
from app.services.vector_store import add_chunks, delete_document
from app.services.trace_service import log_ingestion
from app.services.vision_service import generate_caption
from app.models import ImageAssetModel

JOB_MAX_RETRIES = config.JOB_MAX_RETRIES
STREAM_KEY = "rag:jobs"
GROUP_NAME = "workers"
CONSUMER_NAME = f"worker-{os.getpid()}"

ensure_sqlite_schema()

# 确保 consumer group 存在
try:
    r.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
except Exception:
    pass  # group 已存在


def process_job(job_id: int, document_id: int, file_path: str, content_type: str):
    """处理单个 ingestion 任务 — v2.0 multimodal pipeline"""
    stages = []
    db = SessionLocal()
    try:
        # 1. 获取分布式锁
        if not acquire_document_lock(document_id):
            return

        # 2. 更新状态
        job = db.query(JobModel).filter(JobModel.id == job_id).first()
        doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
        settings = db.query(SettingsModel).first()
        embedding_provider = (settings.embedding_provider if settings else None) or config.DEFAULT_EMBEDDING_PROVIDER
        embed_model = (settings.embed_model if settings else None) or config.DEFAULT_EMBED_MODEL
        vision_model = (settings.vision_model if settings else None) or config.VISION_MODEL
        if not job or not doc:
            return

        job.status = "processing"
        doc.status = "processing"
        db.commit()

        # 3. 加载 (v2: returns {text, images})
        set_job_progress(job_id, "load", "正在加载文档...")
        t0 = time.time()
        doc_data = load_document_v2(file_path)
        text = doc_data["text"]
        image_assets = doc_data.get("images", [])
        stages.append({
            "stage": "load",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "image_count": len(image_assets),
        })

        # 3.5. Vision Caption (v2.0)
        image_asset_records = []
        if image_assets:
            set_job_progress(job_id, "caption", f"正在为 {len(image_assets)} 张图片生成描述...")
            t0 = time.time()
            captioned = 0
            for img in image_assets:
                try:
                    cap = generate_caption(img["stored_path"], model=vision_model)
                    captioned += 1
                except Exception:
                    cap = None

                asset_model = ImageAssetModel(
                    document_id=document_id,
                    filename=img["filename"],
                    stored_path=img["stored_path"],
                    source_page=img.get("source_page"),
                    content_type=img["content_type"],
                    size_bytes=img["size_bytes"],
                    caption=cap,
                    caption_model=vision_model if cap else None,
                    caption_provider="openai" if cap else None,
                )
                db.add(asset_model)
                db.flush()
                image_asset_records.append({
                    "id": asset_model.id,
                    "source_page": img.get("source_page"),
                    "caption": cap,
                    "filename": img["filename"],
                })
            db.commit()
            stages.append({
                "stage": "caption",
                "duration_ms": round((time.time() - t0) * 1000, 2),
                "captioned": captioned,
                "total": len(image_assets),
            })

        # 4. 切片 — v2 enhanced splitter with page_map
        set_job_progress(job_id, "split", "正在切片...")
        t0 = time.time()
        if image_asset_records:
            page_map = _build_page_map(text)
            chunks = split_text_v2(text, page_map=page_map)
        else:
            chunks = split_text(text)
        stages.append({
            "stage": "split",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "chunk_count": len(chunks),
        })

        if not chunks and not image_asset_records:
            raise ValueError("文档内容为空，无法切片")

        # 4.5. 关联图片到 chunks
        image_asset_map = _associate_images_to_chunks(chunks, image_asset_records)

        if chunks:
            # 5. Embedding
            set_job_progress(job_id, "embed", f"正在向量化 ({len(chunks)} chunks)...")
            t0 = time.time()
            contents = [c["content"] for c in chunks]
            embeddings = get_embeddings(contents, model=embed_model, provider=embedding_provider)
            stages.append({
                "stage": "embed",
                "duration_ms": round((time.time() - t0) * 1000, 2),
                "embedding_provider": embedding_provider,
                "embedding_model": embed_model,
            })

            # 6. 写入 Chroma
            set_job_progress(job_id, "index", "正在写入向量库...")
            t0 = time.time()
            delete_document(document_id, embedding_provider=embedding_provider, embedding_model=embed_model)
            add_chunks(
                chunks,
                embeddings,
                document_id,
                doc.filename,
                doc.kb_version,
                embedding_provider=embedding_provider,
                embedding_model=embed_model,
                image_asset_map=image_asset_map,
            )
            stages.append({"stage": "index", "duration_ms": round((time.time() - t0) * 1000, 2)})
        else:
            stages.append({"stage": "embed", "duration_ms": 0, "note": "no text, image-only document"})
            stages.append({"stage": "index", "duration_ms": 0, "note": "no text chunks"})

        # 7. 完成
        set_job_progress(job_id, "completed", "处理完成")
        doc.status = "completed"
        doc.chunk_count = len(chunks)
        doc.image_count = len(image_asset_records)
        doc.has_images = len(image_asset_records) > 0
        job.status = "completed"
        db.commit()
        invalidate_cache()

        # Trace
        log_ingestion(document_id, doc.filename, stages)

    except Exception as e:
        job = db.query(JobModel).filter(JobModel.id == job_id).first()
        if job:
            job.retry_count += 1
            if job.retry_count >= JOB_MAX_RETRIES:
                job.status = "failed"
                job.error = str(e)
                doc = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
                if doc:
                    doc.status = "failed"
                set_job_progress(job_id, "failed", f"处理失败: {e}")
            else:
                job.status = "pending"
                set_job_progress(job_id, "retry", f"第 {job.retry_count} 次重试")
                r.xadd(STREAM_KEY, {
                    "job_id": str(job_id),
                    "document_id": str(document_id),
                    "file_path": file_path,
                    "content_type": content_type,
                })
            db.commit()
        traceback.print_exc()
    finally:
        release_document_lock(document_id)
        db.close()


def _build_page_map(text: str) -> dict[int, int]:
    """Build a char_offset -> page_number mapping from v2 PDF text.

    The v2 PDF loader joins pages with '\n\n'. We count characters per page
    to build the offset->page mapping used by the splitter.
    """
    page_map = {}
    offset = 0
    pages = text.split("\n\n")
    for page_num, page_text in enumerate(pages):
        page_map[offset] = page_num + 1
        offset += len(page_text) + 2  # +2 for the \n\n separator
    return page_map


def _associate_images_to_chunks(
    chunks: list[dict], image_assets: list[dict]
) -> dict[int, list[dict]]:
    """Map chunk_index -> list of asset info dicts by page proximity."""
    mapping: dict[int, list[dict]] = {}
    for img in image_assets:
        src_page = img.get("source_page")
        best_chunk_idx = 0
        if src_page is not None and chunks:
            for c in chunks:
                page_range = c["metadata"].get("page_range")
                if page_range and src_page in page_range:
                    best_chunk_idx = c["metadata"]["chunk_index"]
                    break
            else:
                best_chunk_idx = chunks[0]["metadata"]["chunk_index"]
        mapping.setdefault(best_chunk_idx, []).append({
            "asset_id": img["id"],
            "filename": img["filename"],
            "caption": img.get("caption"),
            "source_page": src_page,
        })
    return mapping


def main():
    print(f"[worker] 启动 consumer: {CONSUMER_NAME}, group: {GROUP_NAME}")
    while True:
        try:
            results = r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {STREAM_KEY: ">"}, count=1, block=5000)
            if not results:
                continue

            for stream_name, messages in results:
                for msg_id, data in messages:
                    job_id = int(data.get("job_id", 0))
                    document_id = int(data.get("document_id", 0))
                    file_path = data.get("file_path", "")
                    content_type = data.get("content_type", "")
                    print(f"[worker] 处理 job={job_id} doc={document_id}")
                    process_job(job_id, document_id, file_path, content_type)
                    r.xack(STREAM_KEY, GROUP_NAME, msg_id)

        except KeyboardInterrupt:
            print("[worker] 退出")
            break
        except Exception:
            traceback.print_exc()
            time.sleep(1)


if __name__ == "__main__":
    main()
