"""Trace 服务 — JSONL 格式记录 (v1.1)"""

import os
import json
import time
from app.config import config


os.makedirs(config.TRACE_DIR, exist_ok=True)

_INGESTION_LOG = os.path.join(config.TRACE_DIR, "ingestion.jsonl")
_QUERY_LOG = os.path.join(config.TRACE_DIR, "query.jsonl")


def log_ingestion(document_id: int, filename: str, stages: list[dict]):
    """记录 ingestion trace
    stages: [{"stage": "load", "duration_ms": 123}, ...]
    """
    entry = {
        "type": "ingestion",
        "document_id": document_id,
        "filename": filename,
        "timestamp": time.time(),
        "stages": stages,
    }
    _append(_INGESTION_LOG, entry)


def log_query(
    question: str,
    answer: str,
    strategy: str,
    candidates: list[dict],
    final_citations: list[dict],
    duration_ms: float,
    cache_hit: bool = False,
):
    """记录 query trace"""
    entry = {
        "type": "query",
        "question": question,
        "answer": answer,
        "strategy": strategy,
        "candidates": [
            {"chunk_id": c["chunk_id"], "filename": c.get("filename", ""), "score": c.get("score", 0)}
            for c in candidates
        ],
        "final_citations": [
            {"chunk_id": c["chunk_id"], "filename": c.get("filename", ""), "score": c.get("score", 0)}
            for c in final_citations
        ],
        "duration_ms": duration_ms,
        "cache_hit": cache_hit,
        "timestamp": time.time(),
    }
    _append(_QUERY_LOG, entry)


def get_ingestion_traces(limit: int = 50) -> list[dict]:
    return _read_tail(_INGESTION_LOG, limit)


def get_query_traces(limit: int = 50) -> list[dict]:
    return _read_tail(_QUERY_LOG, limit)


def _append(filepath: str, entry: dict):
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_tail(filepath: str, limit: int) -> list[dict]:
    if not os.path.exists(filepath):
        return []
    lines = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(json.loads(line))
    return lines[-limit:]
