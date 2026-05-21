"""检索器 — Dense + BM25 + RRF + 可选 Rerank (v1.1)"""

import math
from collections import defaultdict
from app.services.embedding_provider import embed_single
from app.services.vector_store import query as dense_query
from app.config import config


class BM25Sparse:
    """简易 BM25 实现，用于关键词检索"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: list[dict] = []
        self.doc_lengths: list[int] = []
        self.avgdl: float = 0
        self.idf: dict[str, float] = {}
        self.term_freqs: list[dict[str, int]] = []
        self._built = False

    def index(self, chunks: list[dict]):
        """从 chunks 构建 BM25 索引"""
        self.documents = chunks
        self.doc_lengths = []
        self.term_freqs = []
        df: dict[str, int] = defaultdict(int)
        N = len(chunks)

        for c in chunks:
            tokens = _tokenize(c["content"])
            tf = defaultdict(int)
            for t in tokens:
                tf[t] += 1
            self.term_freqs.append(dict(tf))
            self.doc_lengths.append(len(tokens))
            for t in set(tokens):
                df[t] += 1

        self.avgdl = sum(self.doc_lengths) / max(N, 1)

        for term, count in df.items():
            self.idf[term] = math.log(1 + (N - count + 0.5) / (count + 0.5))

        self._built = True

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """返回 [(doc_index, score)]"""
        if not self._built:
            return []

        query_tokens = _tokenize(query)
        scores = []
        for i, tf in enumerate(self.term_freqs):
            score = 0.0
            for token in query_tokens:
                if token in self.idf:
                    term_freq = tf.get(token, 0)
                    dl = self.doc_lengths[i]
                    numerator = term_freq * (self.k1 + 1)
                    denominator = term_freq + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1))
                    score += self.idf[token] * numerator / denominator
            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


def _tokenize(text: str) -> list[str]:
    """简易中文+英文分词"""
    import re
    tokens = re.findall(r"[一-鿿]|[a-zA-Z0-9]+", text.lower())
    return [t for t in tokens if len(t) > 1 or t.isalpha()]


def rrf_fusion(dense_results: list[dict], sparse_results: list[dict], k: int = 60) -> list[dict]:
    """RRF (Reciprocal Rank Fusion) 融合两个排序列表"""
    rrf_scores: dict[str, float] = {}
    chunk_map: dict[str, dict] = {}

    for rank, item in enumerate(dense_results):
        cid = item["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1.0 / (k + rank + 1)
        chunk_map[cid] = item

    for rank, item in enumerate(sparse_results):
        cid = item["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0) + 1.0 / (k + rank + 1)
        chunk_map[cid] = item

    fused = []
    for cid, score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
        item = chunk_map[cid].copy()
        item["rrf_score"] = score
        fused.append(item)

    return fused


def retrieve(
    query: str,
    top_k: int = 5,
    strategy: str = "hybrid",
    bm25_index: BM25Sparse | None = None,
    provider: str | None = None,
    embedding_model: str | None = None,
    where: dict | None = None,
) -> list[dict]:
    """
    统一检索入口。
    strategy: "dense" | "hybrid" | "hybrid_rerank"
    """
    # Dense retrieval
    q_embedding = embed_single(query, model=embedding_model, provider=provider)
    try:
        dense_results = dense_query(
            q_embedding,
            top_k=max(top_k, 10),
            embedding_provider=provider,
            embedding_model=embedding_model,
            where=where,
        )
    except Exception as e:
        raise RuntimeError(
            "向量库与当前 embedding provider/model 不匹配，请使用当前 embedding 配置重新索引文档"
        ) from e

    # BM25 sparse
    sparse_results: list[dict] = []
    if strategy in ("hybrid", "hybrid_rerank") and bm25_index and bm25_index._built:
        sparse_hits = bm25_index.search(query, top_k=10)
        for idx, score in sparse_hits:
            doc = bm25_index.documents[idx]
            sparse_results.append({
                "chunk_id": doc["chunk_id"],
                "document_id": doc.get("document_id", 0),
                "filename": doc.get("filename", ""),
                "content": doc["content"],
                "score": score,
            })

    # RRF fusion
    if sparse_results:
        fused = rrf_fusion(dense_results, sparse_results)
    else:
        fused = dense_results

    # Optional rerank
    if strategy == "hybrid_rerank" and config.RERANK_ENABLED:
        fused = _rerank(query, fused)

    return fused[:top_k]


def _rerank(query: str, candidates: list[dict]) -> list[dict]:
    """可选 Re-Ranker，当前使用基于 score 的降序排列作为 fallback"""
    return sorted(candidates, key=lambda x: x.get("score", x.get("rrf_score", 0)), reverse=True)
