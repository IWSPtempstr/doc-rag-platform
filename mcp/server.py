"""MCP Server — 文档 RAG 平台 MCP 工具 (v1.1)"""

import json
import sys
import os
from datetime import date, datetime

# 添加 backend 到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.rag_service import rag_query
from app.services.vector_store import query as dense_query, collection_count
from app.services.embedding_provider import embed_single
from app.db import SessionLocal, ensure_sqlite_schema
from app.models import CompanyModel, DocumentModel, CollectionModel, FilingModel, MarketFactModel, SettingsModel
from app.config import config
from app.services.ashare_connector import download_announcement, get_annual_report, search_announcements


# --- MCP 协议实现 ---
# 这是一个简化版 JSON-RPC 风格的 MCP server，兼容 stdin/stdout 传输
# 完整的 FastMCP 实现可参考 phase4-mcp/server.py


def make_response(ok: bool, data=None, error: str | None = None, trace_id: str | None = None) -> str:
    return json.dumps(
        {"ok": ok, "data": data, "error": error, "trace_id": trace_id},
        ensure_ascii=False,
        default=_json_default,
    )


def _json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


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

        elif tool_name == "search_ashare_announcements":
            data = search_announcements(
                ticker=arguments.get("ticker", ""),
                start_date=arguments.get("start_date"),
                end_date=arguments.get("end_date"),
                category=arguments.get("category"),
                keyword=arguments.get("keyword"),
                page_size=arguments.get("page_size", 30),
            )
            return make_response(True, data)

        elif tool_name == "get_ashare_annual_report":
            report = get_annual_report(
                arguments.get("ticker", ""),
                int(arguments.get("fiscal_year")),
            )
            return make_response(True, report)

        elif tool_name == "download_ashare_announcement":
            announcement = arguments.get("announcement") or {}
            downloaded = download_announcement(announcement)
            return make_response(True, downloaded)

        elif tool_name == "get_ashare_filings_by_company":
            ticker = str(arguments.get("ticker", "")).upper()
            filing_type = arguments.get("filing_type")
            fiscal_year = arguments.get("fiscal_year")
            company = db.query(CompanyModel).filter(CompanyModel.ticker == ticker).first()
            if not company:
                return make_response(True, [])
            q = db.query(FilingModel).filter(FilingModel.company_id == company.id)
            if filing_type:
                q = q.filter(FilingModel.filing_type == filing_type)
            if fiscal_year:
                q = q.filter(FilingModel.fiscal_year == int(fiscal_year))
            filings = q.order_by(FilingModel.fiscal_year.desc(), FilingModel.created_at.desc()).limit(50).all()
            data = [
                {
                    "id": filing.id,
                    "ticker": ticker,
                    "filing_type": filing.filing_type,
                    "fiscal_year": filing.fiscal_year,
                    "document_id": filing.document_id,
                    "source_url": filing.source_url,
                    "status": filing.status,
                    "metadata_json": filing.metadata_json,
                }
                for filing in filings
            ]
            return make_response(True, data)

        elif tool_name == "list_ashare_market_facts":
            ticker = str(arguments.get("ticker", "")).upper()
            metric = arguments.get("metric")
            q = db.query(MarketFactModel).filter(MarketFactModel.ticker == ticker)
            if metric:
                q = q.filter(MarketFactModel.metric == metric)
            facts = q.order_by(MarketFactModel.trade_date.desc()).limit(arguments.get("limit", 50)).all()
            data = [
                {
                    "id": fact.id,
                    "ticker": fact.ticker,
                    "trade_date": fact.trade_date,
                    "metric": fact.metric,
                    "label": fact.label,
                    "value": fact.value,
                    "unit": fact.unit,
                    "source": fact.source,
                    "metadata_json": fact.metadata_json,
                }
                for fact in facts
            ]
            return make_response(True, data)

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
    {
        "name": "search_ashare_announcements",
        "description": "搜索 A 股巨潮资讯公告，返回标准化公告元数据",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "6 位 A 股代码，如 600519"},
                "start_date": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
                "category": {"type": "string", "description": "CNINFO 分类代码"},
                "keyword": {"type": "string", "description": "公告标题关键词"},
                "page_size": {"type": "integer", "description": "返回数量", "default": 30},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_ashare_annual_report",
        "description": "获取指定 A 股公司指定年份的完整年度报告公告元数据",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "6 位 A 股代码，如 600519"},
                "fiscal_year": {"type": "integer", "description": "财年，如 2023"},
            },
            "required": ["ticker", "fiscal_year"],
        },
    },
    {
        "name": "download_ashare_announcement",
        "description": "下载已标准化的 A 股公告 PDF 到公开数据目录",
        "inputSchema": {
            "type": "object",
            "properties": {
                "announcement": {"type": "object", "description": "search_ashare_announcements 返回的公告对象"},
            },
            "required": ["announcement"],
        },
    },
    {
        "name": "get_ashare_filings_by_company",
        "description": "查询已入库 A 股公司的 filings",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "6 位 A 股代码"},
                "filing_type": {"type": "string", "description": "filing 类型，如 annual_report"},
                "fiscal_year": {"type": "integer", "description": "财年"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "list_ashare_market_facts",
        "description": "查询已入库 A 股行情事实",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "6 位 A 股代码"},
                "metric": {"type": "string", "description": "指标，如 close/open/volume"},
                "limit": {"type": "integer", "description": "返回数量", "default": 50},
            },
            "required": ["ticker"],
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
