"""RAG 服务 — 完整 RAG 流程编排"""

import requests
import json
from app.config import config
from app.services.retriever import retrieve, BM25Sparse
from app.services.cache_service import get_cache, set_cache


def build_prompt(context: str, question: str) -> str:
    return f"""你是一个知识库助手。请只根据以下上下文回答问题。如果上下文中没有相关信息，请如实说"未在文档中找到相关信息"。

上下文：
{context}

问题：{question}

回答："""


def generate_answer(
    question: str,
    context_chunks: list[dict],
    model: str | None = None,
    provider: str | None = None,
    stream: bool = False,
) -> str:
    """调用 LLM 生成回答"""
    context = "\n\n---\n\n".join(
        f"[来源: {c['filename']}]\n{c['content']}" for c in context_chunks
    )
    prompt = build_prompt(context, question)

    if provider == "ollama":
        return _call_ollama(model or config.OLLAMA_CHAT_MODEL, prompt, stream)
    if provider == "openai":
        return _call_openai(model or config.OPENAI_CHAT_MODEL, prompt, stream)
    raise ValueError(f"不支持的 chat provider: {provider}")


def _call_ollama(model: str, prompt: str, stream: bool = False) -> str:
    resp = requests.post(
        f"{config.OLLAMA_BASE_URL}/api/generate",
        json={"model": model, "prompt": prompt, "stream": stream},
        timeout=120,
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise RuntimeError(f"Ollama 生成失败: {resp.text}") from e
    if stream:
        lines = resp.text.strip().split("\n")
        return "".join(json.loads(line).get("response", "") for line in lines if line)
    return resp.json().get("response", "")


def _openai_base_url() -> str:
    return (config.CHAT_API_BASE or "https://api.openai.com/v1").rstrip("/")


def _call_openai(model: str, prompt: str, stream: bool = False) -> str:
    base_url = _openai_base_url()
    if not config.CHAT_API_KEY:
        raise RuntimeError("CHAT_API_KEY 未配置")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.CHAT_API_KEY}",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
    }
    resp = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=120)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise RuntimeError(f"API 生成失败: {resp.text}") from e
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def rag_query(
    question: str,
    top_k: int = 5,
    model: str | None = None,
    provider: str | None = None,
    chat_provider: str | None = None,
    kb_version: int = 1,
    strategy: str = "dense",
    bm25_index: BM25Sparse | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> dict:
    """完整 RAG 查询：检索 + 生成 + 缓存"""

    chat_provider = chat_provider or provider or config.DEFAULT_CHAT_PROVIDER
    embedding_provider = embedding_provider or config.DEFAULT_EMBEDDING_PROVIDER
    chat_model = model or (config.OLLAMA_CHAT_MODEL if chat_provider == "ollama" else config.DEFAULT_CHAT_MODEL)
    embed_model = embedding_model or (
        config.OLLAMA_EMBED_MODEL if embedding_provider == "ollama" else config.OPENAI_EMBED_MODEL
    )

    # 1. 查缓存
    cached = get_cache(
        chat_provider,
        chat_model,
        top_k,
        question,
        kb_version,
        embedding_provider=embedding_provider,
        embed_model=embed_model,
    )
    if cached:
        cached["cache_hit"] = True
        return cached

    # 2. 检索
    chunks = retrieve(
        question,
        top_k=top_k,
        strategy=strategy,
        bm25_index=bm25_index,
        provider=embedding_provider,
        embedding_model=embed_model,
    )

    # 3. 生成
    answer = generate_answer(question, chunks, model=chat_model, provider=chat_provider)

    result = {
        "answer": answer,
        "citations": [
            {
                "chunk_id": c["chunk_id"],
                "document_id": c["document_id"],
                "filename": c["filename"],
                "content": c["content"],
                "score": c.get("score", c.get("rrf_score", 0)),
            }
            for c in chunks
        ],
        "model": chat_model,
        "provider": chat_provider,
        "chat_provider": chat_provider,
        "embedding_provider": embedding_provider,
        "embedding_model": embed_model,
        "cache_hit": False,
    }

    # 4. 写缓存
    set_cache(
        chat_provider,
        chat_model,
        top_k,
        question,
        kb_version,
        result,
        embedding_provider=embedding_provider,
        embed_model=embed_model,
    )

    return result
