"""向量存储 — Chroma 集成"""

import os
import re
import chromadb
from chromadb.config import Settings
from app.config import config


os.makedirs(config.CHROMA_DIR, exist_ok=True)

_client = chromadb.PersistentClient(
    path=config.CHROMA_DIR,
    settings=Settings(anonymized_telemetry=False),
)

def collection_name(
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> str:
    provider = embedding_provider or config.DEFAULT_EMBEDDING_PROVIDER
    model = embedding_model or config.DEFAULT_EMBED_MODEL
    raw = f"documents__{provider}__{model}"
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw).strip("_")
    return safe[:120] or "documents_default"


def get_collection(
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
):
    return _client.get_or_create_collection(
        name=collection_name(embedding_provider, embedding_model)
    )


_collection = get_collection()


def add_chunks(
    chunks: list[dict],
    embeddings: list[list[float]],
    document_id: int,
    filename: str,
    kb_version: int = 1,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    image_asset_map: dict[int, list[dict]] | None = None,
    extra_metadata: dict | None = None,
):
    """批量写入 chunks 到 Chroma"""
    import json

    if not chunks:
        return

    ids = [f"doc_{document_id}_{c['chunk_id']}" for c in chunks]
    metadatas = []
    for c in chunks:
        chunk_meta = c.get("metadata", {})
        meta = {
            "document_id": document_id,
            "filename": filename,
            "chunk_id": c["chunk_id"],
            "chunk_index": chunk_meta["chunk_index"],
            "kb_version": kb_version,
            "embedding_provider": embedding_provider or config.DEFAULT_EMBEDDING_PROVIDER,
            "embedding_model": embedding_model or config.DEFAULT_EMBED_MODEL,
            "image_refs": json.dumps(image_asset_map.get(chunk_meta["chunk_index"], []))
            if image_asset_map else "[]",
        }
        if extra_metadata:
            meta.update({k: v for k, v in extra_metadata.items() if v is not None})
        for key in ("section_item", "section_title"):
            if chunk_meta.get(key):
                meta[key] = chunk_meta[key]
        metadatas.append(meta)
    documents = [c["content"] for c in chunks]

    collection = get_collection(embedding_provider, embedding_model)
    collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)


def query(
    embedding: list[float],
    top_k: int = 5,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    where: dict | None = None,
) -> list[dict]:
    """Dense 检索，返回 [{chunk_id, document_id, filename, content, score}]"""
    collection = get_collection(embedding_provider, embedding_model)
    if collection.count() == 0:
        return []

    query_kwargs = {"query_embeddings": [embedding], "n_results": top_k}
    if where:
        query_kwargs["where"] = where
    results = collection.query(**query_kwargs)
    items = []
    if results["ids"] and results["ids"][0]:
        for i, cid in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            items.append({
                "chunk_id": meta.get("chunk_id", cid),
                "document_id": meta.get("document_id", 0),
                "filename": meta.get("filename", ""),
                "content": results["documents"][0][i] if results["documents"] else "",
                "score": 1.0 - (results["distances"][0][i] if results["distances"] else 0),
            })
    return items


def delete_document(
    document_id: int,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
):
    """删除文档的所有 chunks"""
    collections = []
    if embedding_provider or embedding_model:
        collections = [get_collection(embedding_provider, embedding_model)]
    else:
        collections = _client.list_collections()

    for collection in collections:
        try:
            existing = collection.get(where={"document_id": document_id})
            if existing and existing["ids"]:
                collection.delete(ids=existing["ids"])
        except Exception:
            pass


def count_chunks(
    document_id: int | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> int:
    collection = get_collection(embedding_provider, embedding_model)
    if document_id is not None:
        try:
            result = collection.get(where={"document_id": document_id})
            return len(result["ids"]) if result and result["ids"] else 0
        except Exception:
            return 0
    return collection.count()


def collection_count(
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> int:
    if embedding_provider or embedding_model:
        return get_collection(embedding_provider, embedding_model).count()
    total = 0
    for collection in _client.list_collections():
        try:
            total += collection.count()
        except Exception:
            pass
    return total
