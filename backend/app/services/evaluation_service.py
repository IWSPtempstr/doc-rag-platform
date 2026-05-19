"""Evaluation 服务 — Golden Questions 评估 (v1.1)"""

import os
import json
import time
from datetime import datetime, timezone
from app.config import config
from app.services.rag_service import rag_query
from app.services.retriever import BM25Sparse

os.makedirs(config.EVAL_DIR, exist_ok=True)

# 默认 Golden Questions
DEFAULT_GOLDEN_QUESTIONS = [
    {"question": "什么是RAG？", "keywords": ["RAG", "检索", "生成", "Retrieval", "Augmented"]},
    {"question": "如何配置Ollama？", "keywords": ["Ollama", "配置", "安装"]},
    {"question": "MCP协议的全称是什么？", "keywords": ["MCP", "Model", "Context", "Protocol"]},
    {"question": "Redis Streams的作用是什么？", "keywords": ["Redis", "Stream", "消息", "队列"]},
    {"question": "ChromaDB的用途？", "keywords": ["Chroma", "向量", "数据库", "embedding"]},
    {"question": "FastAPI中Depends的作用？", "keywords": ["FastAPI", "Depends", "依赖", "注入"]},
    {"question": "什么是embedding？", "keywords": ["embedding", "向量", "嵌入"]},
    {"question": "如何提升RAG系统的检索精度？", "keywords": ["RAG", "检索", "精度", "HyDE", "rerank"]},
    {"question": "Docker Compose如何编排多服务？", "keywords": ["Docker", "Compose", "服务", "容器"]},
    {"question": "SQLAlchemy中session的生命周期？", "keywords": ["SQLAlchemy", "session", "事务"]},
]


def run_evaluation(
    strategy: str = "dense",
    questions: list[dict] | None = None,
    bm25_index: BM25Sparse | None = None,
    chat_provider: str | None = None,
    chat_model: str | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> dict:
    """运行评估，返回摘要和详细结果"""
    questions = questions or DEFAULT_GOLDEN_QUESTIONS
    results = []
    hits = 0

    for gq in questions:
        t0 = time.time()
        rag_result = rag_query(
            question=gq["question"],
            top_k=5,
            strategy=strategy,
            bm25_index=bm25_index,
            chat_provider=chat_provider,
            model=chat_model,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
        )

        keywords = gq.get("keywords", [])
        hit = any(kw.lower() in rag_result["answer"].lower() for kw in keywords)
        if hit:
            hits += 1

        results.append({
            "question": gq["question"],
            "answer": rag_result["answer"],
            "citations": rag_result["citations"],
            "hit": hit,
            "expected_keywords": keywords,
            "duration_s": round(time.time() - t0, 3),
        })

    hit_rate = hits / len(questions) if questions else 0

    return {
        "strategy": strategy,
        "chat_provider": chat_provider or config.DEFAULT_CHAT_PROVIDER,
        "chat_model": chat_model or config.DEFAULT_CHAT_MODEL,
        "embedding_provider": embedding_provider or config.DEFAULT_EMBEDDING_PROVIDER,
        "embedding_model": embedding_model or config.DEFAULT_EMBED_MODEL,
        "total": len(questions),
        "hits": hits,
        "hit_rate": round(hit_rate, 4),
        "results": results,
    }


def save_evaluation_result(strategy: str, eval_data: dict) -> str:
    """保存评估结果到 JSON 文件"""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"eval_{strategy}_{timestamp}.json"
    filepath = os.path.join(config.EVAL_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(eval_data, f, ensure_ascii=False, indent=2)
    return filepath


def load_evaluation_results(limit: int = 20) -> list[dict]:
    """加载最近的评估结果"""
    files = sorted(
        [f for f in os.listdir(config.EVAL_DIR) if f.endswith(".json")],
        reverse=True,
    )
    results = []
    for f in files[:limit]:
        filepath = os.path.join(config.EVAL_DIR, f)
        with open(filepath, "r", encoding="utf-8") as fp:
            results.append(json.load(fp))
    return results
