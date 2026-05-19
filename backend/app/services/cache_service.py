"""RAG 缓存服务"""

import json
from app.redis_client import cache_key, get_cached_answer, set_cached_answer, invalidate_cache


def get_cache(
    chat_provider: str,
    chat_model: str,
    top_k: int,
    question: str,
    kb_version: int,
    embedding_provider: str | None = None,
    embed_model: str | None = None,
) -> dict | None:
    key = cache_key(
        chat_provider,
        chat_model,
        top_k,
        question,
        kb_version,
        embedding_provider=embedding_provider,
        embed_model=embed_model,
    )
    return get_cached_answer(key)


def set_cache(
    chat_provider: str,
    chat_model: str,
    top_k: int,
    question: str,
    kb_version: int,
    data: dict,
    embedding_provider: str | None = None,
    embed_model: str | None = None,
):
    key = cache_key(
        chat_provider,
        chat_model,
        top_k,
        question,
        kb_version,
        embedding_provider=embedding_provider,
        embed_model=embed_model,
    )
    set_cached_answer(key, data)


def invalidate() -> int:
    """知识库变更时清除所有缓存，返回清除的 key 数量"""
    invalidate_cache()
    return 0
