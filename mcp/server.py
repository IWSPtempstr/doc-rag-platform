"""MCP Server — 文档 RAG 平台 MCP 工具 (v1.1)"""

import json
import sys
import os

# 添加 backend 到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.rag_service import rag_query
from app.services.vector_store import query as dense_query, collection_count
from app.services.embedding_provider import embed_single
from app.db import SessionLocal, ensure_sqlite_schema
from app.models import DocumentModel, CollectionModel, SettingsModel
from app.config import config


# --- MCP 协议实现 ---
# 这是一个简化版 JSON-RPC 风格的 MCP server，兼容 stdin/stdout 传输
# 完整的 FastMCP 实现可参考 phase4-mcp/server.py


def make_response(ok: bool, data=None, error: str | None = None, trace_id: str | None = None) -> str:
    return json.dumps({"ok": ok, "data": data, "error": error, "trace_id": trace_id}, ensure_ascii=False)


def get_runtime_settings(db):
    settings = db.query(SettingsModel).first()
    if not settings:
        return {
            "chat_provider": config.DEFAULT_CHAT_PROVIDER,
            "embedding_provider": config.DEFAULT_EMBEDDING_PROVIDER,
            "chat_model": config.DEFAULT_CHAT_MODEL,
            "embed_model": config.DEFAULT_EMBED_MODEL,
        }
    return {
        "chat_provider": settings.chat_provider or settings.provider or config.DEFAULT_CHAT_PROVIDER,
        "embedding_provider": settings.embedding_provider or config.DEFAULT_EMBEDDING_PROVIDER,
        "chat_model": settings.chat_model or config.DEFAULT_CHAT_MODEL,
        "embed_model": settings.embed_model or config.DEFAULT_EMBED_MODEL,
    }


def handle_tool_call(tool_name: str, arguments: dict) -> str:
    db = SessionLocal()
    try:
        runtime = get_runtime_settings(db)
        if tool_name == "search_documents":
            query_text = arguments.get("query", "")
            top_k = arguments.get("top_k", 5)
            embedding = embed_single(
                query_text,
                model=runtime["embed_model"],
                provider=runtime["embedding_provider"],
            )
            chunks = dense_query(
                embedding,
                top_k,
                embedding_provider=runtime["embedding_provider"],
                embedding_model=runtime["embed_model"],
            )
            return make_response(True, chunks)

        elif tool_name == "ask_knowledge_base":
            question = arguments.get("question", "")
            result = rag_query(
                question=question,
                top_k=arguments.get("top_k", 5),
                chat_provider=runtime["chat_provider"],
                model=runtime["chat_model"],
                embedding_provider=runtime["embedding_provider"],
                embedding_model=runtime["embed_model"],
            )
            return make_response(True, result)

        elif tool_name == "query_knowledge_hub":
            question = arguments.get("query", "")
            top_k = arguments.get("top_k", 5)
            result = rag_query(
                question=question,
                top_k=top_k,
                chat_provider=runtime["chat_provider"],
                model=runtime["chat_model"],
                embedding_provider=runtime["embedding_provider"],
                embedding_model=runtime["embed_model"],
            )
            return make_response(True, result)

        elif tool_name == "list_collections":
            collections = db.query(CollectionModel).all()
            data = [{"id": c.id, "name": c.name, "description": c.description, "document_count": c.document_count} for c in collections]
            return make_response(True, data)

        elif tool_name == "get_document_summary":
            doc_id = arguments.get("document_id")
            doc = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
            if doc:
                data = {
                    "id": doc.id,
                    "filename": doc.filename,
                    "content_type": doc.content_type,
                    "size_bytes": doc.size_bytes,
                    "status": doc.status,
                    "tags": doc.tags,
                    "chunk_count": doc.chunk_count,
                    "kb_version": doc.kb_version,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                }
                return make_response(True, data)
            return make_response(False, error="文档不存在")

        else:
            return make_response(False, error=f"未知工具: {tool_name}")

    except Exception as e:
        return make_response(False, error=str(e))
    finally:
        db.close()


# MCP 工具定义
TOOLS = [
    {
        "name": "search_documents",
        "description": "搜索文档知识库，返回相关 chunk",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询"},
                "top_k": {"type": "integer", "description": "返回结果数量", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "ask_knowledge_base",
        "description": "向知识库提问，返回 AI 生成的答案和引用",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "问题"},
                "top_k": {"type": "integer", "description": "检索数量", "default": 5},
            },
            "required": ["question"],
        },
    },
    {
        "name": "query_knowledge_hub",
        "description": "v1.1: 通用知识库查询",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "查询内容"},
                "top_k": {"type": "integer", "description": "检索数量", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_collections",
        "description": "v1.1: 列出所有文档集合",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_document_summary",
        "description": "v1.1: 获取文档摘要信息",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "integer", "description": "文档 ID"},
            },
            "required": ["document_id"],
        },
    },
]


def main():
    """stdin/stdout JSON-RPC 循环"""
    ensure_sqlite_schema()
    print("[mcp-server] 启动，等待请求...", file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            method = req.get("method", "")

            if method == "tools/list":
                resp = {"jsonrpc": "2.0", "id": req.get("id"), "result": {"tools": TOOLS}}
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = handle_tool_call(tool_name, arguments)
                parsed = json.loads(result)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req.get("id"),
                    "result": {"content": [{"type": "text", "text": json.dumps(parsed, ensure_ascii=False, indent=2)}]},
                }
            else:
                resp = {"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32601, "message": f"未知方法: {method}"}}

            print(json.dumps(resp, ensure_ascii=False), flush=True)
        except Exception as e:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
            print(json.dumps(err, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
