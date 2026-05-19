"""Redis 客户端和工具函数"""

import redis
import hashlib
import json
import time
from app.config import config

r = redis.from_url(config.REDIS_URL, decode_responses=True)


# ---- 任务队列 ----
def enqueue_job(job_id: int, document_id: int, file_path: str, content_type: str):
    r.xadd("rag:jobs", {
        "job_id": str(job_id),
        "document_id": str(document_id),
        "file_path": file_path,
        "content_type": content_type,
    })


# ---- 任务进度 ----
def set_job_progress(job_id: int, stage: str, message: str = ""):
    r.hset(f"job:{job_id}:progress", mapping={"stage": stage, "message": message, "ts": str(time.time())})
    r.expire(f"job:{job_id}:progress", 86400)


def get_job_progress(job_id: int) -> dict:
    data = r.hgetall(f"job:{job_id}:progress")
    return data if data else {"stage": "unknown", "message": ""}


# ---- RAG 缓存 ----
def cache_key(
    chat_provider: str,
    chat_model: str,
    top_k: int,
    question: str,
    kb_version: int,
    embedding_provider: str | None = None,
    embed_model: str | None = None,
) -> str:
    raw = (
        f"chat_provider:{chat_provider}|chat_model:{chat_model}|"
        f"embedding_provider:{embedding_provider or ''}|embedding_model:{embed_model or ''}|"
        f"top_k:{top_k}|{question}|kb:{kb_version}"
    )
    return f"rag:cache:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def get_cached_answer(key: str) -> dict | None:
    data = r.get(key)
    return json.loads(data) if data else None


def set_cached_answer(key: str, data: dict, ttl: int | None = None):
    ttl = ttl or config.RAG_CACHE_TTL_SECONDS
    r.setex(key, ttl, json.dumps(data, ensure_ascii=False))


def invalidate_cache():
    """知识库变更时清除所有缓存"""
    keys = r.keys("rag:cache:*")
    if keys:
        r.delete(*keys)


# ---- 限流 ----
def check_rate_limit(scope: str, max_per_minute: int) -> tuple[bool, int]:
    window = int(time.time() // 60)
    key = f"rate:{scope}:{window}"
    count = r.incr(key)
    r.expire(key, 120)
    if count > max_per_minute:
        return False, max_per_minute
    return True, max_per_minute - count


# ---- 防重复锁 ----
def acquire_document_lock(document_id: int, ttl: int = 600) -> bool:
    return r.set(f"lock:document:{document_id}", "1", nx=True, ex=ttl) or False


def release_document_lock(document_id: int):
    r.delete(f"lock:document:{document_id}")
