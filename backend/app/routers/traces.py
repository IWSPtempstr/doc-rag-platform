"""Trace 路由 (v1.1)"""

from fastapi import APIRouter, Query
from app.services.trace_service import get_ingestion_traces, get_query_traces

router = APIRouter(prefix="/api/traces", tags=["Traces"])


@router.get("/ingestion")
def list_ingestion_traces(limit: int = Query(default=50, le=200)):
    return get_ingestion_traces(limit)


@router.get("/query")
def list_query_traces(limit: int = Query(default=50, le=200)):
    return get_query_traces(limit)
