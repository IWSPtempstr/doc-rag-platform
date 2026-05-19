"""Embedding Provider — 支持 Ollama 和 OpenAI-compatible API"""

import requests
from app.config import config


def get_embeddings(
    texts: list[str],
    model: str | None = None,
    provider: str | None = None,
) -> list[list[float]]:
    """对文本列表生成 embeddings"""
    provider = provider or config.DEFAULT_EMBEDDING_PROVIDER
    if provider == "ollama":
        return _get_ollama_embeddings(texts, model or config.OLLAMA_EMBED_MODEL)
    if provider == "openai":
        return _get_openai_embeddings(texts, model or config.OPENAI_EMBED_MODEL)
    raise ValueError(f"不支持的 embedding provider: {provider}")


def _get_ollama_embeddings(texts: list[str], model: str) -> list[list[float]]:
    embeddings = []
    for text in texts:
        try:
            resp = requests.post(
                f"{config.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=60,
            )
            resp.raise_for_status()
            embeddings.append(resp.json()["embedding"])
        except Exception as e:
            raise RuntimeError(f"Embedding 生成失败 (model={model}): {e}")

    return embeddings


def _openai_base_url() -> str:
    return (config.EMBEDDING_API_BASE or "https://api.openai.com/v1").rstrip("/")


def _openai_headers() -> dict:
    if not config.EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY 未配置")
    headers = {"Content-Type": "application/json"}
    headers["Authorization"] = f"Bearer {config.EMBEDDING_API_KEY}"
    return headers


def _get_openai_embeddings(texts: list[str], model: str) -> list[list[float]]:
    """OpenAI-compatible embeddings API."""
    try:
        resp = requests.post(
            f"{_openai_base_url()}/embeddings",
            headers=_openai_headers(),
            json={"model": model, "input": texts},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]
    except Exception as e:
        raise RuntimeError(f"API Embedding 生成失败 (model={model}): {e}")


def embed_single(
    text: str,
    model: str | None = None,
    provider: str | None = None,
) -> list[float]:
    """对单段文本生成 embedding"""
    return get_embeddings([text], model=model, provider=provider)[0]
