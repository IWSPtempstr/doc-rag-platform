"""Synthetic RAG context documents for A-share workflow events."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import config
from app.models import DocumentModel, JobModel
from app.redis_client import enqueue_job


def ensure_rag_context_document(
    db: Session,
    *,
    workspace_id: int,
    ticker: str | None,
    kind: str,
    title: str,
    lines: list[str],
    extra_tags: list[str] | None = None,
) -> DocumentModel:
    """Create or refresh a small text document and enqueue indexing if changed."""
    normalized_ticker = _normalize_ashare_code(ticker) if ticker else None
    safe_ticker = _safe_part(normalized_ticker or "market")
    safe_kind = _safe_part(kind)
    base_dir = Path(config.UPLOAD_DIR) / "ashare" / "rag_context"
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{safe_kind}_{safe_ticker}.txt"
    stored_path = base_dir / filename
    content = _render_context(title, lines)

    previous = stored_path.read_text(encoding="utf-8") if stored_path.exists() else None
    if previous != content:
        stored_path.write_text(content, encoding="utf-8")

    tags = [
        "finance",
        "ashare",
        "rag_context",
        f"workspace:{workspace_id}",
        f"context_kind:{kind}",
    ]
    if normalized_ticker:
        tags.append(f"ticker:{normalized_ticker}")
        tags.append(f"company_ticker:{normalized_ticker}")
    tags.extend(extra_tags or [])

    doc = (
        db.query(DocumentModel)
        .filter(DocumentModel.stored_path == str(stored_path))
        .first()
    )
    if not doc:
        doc = DocumentModel(
            filename=filename,
            stored_path=str(stored_path),
            content_type="text/plain",
            size_bytes=os.path.getsize(stored_path),
            status="pending",
            tags=",".join(tags),
        )
        db.add(doc)
        db.flush()
    else:
        doc.size_bytes = os.path.getsize(stored_path)
        doc.tags = "、".join(tags) if False else ",".join(tags)
        if previous != content:
            doc.status = "pending"

    if previous != content or not doc.jobs:
        job = JobModel(document_id=doc.id, type="reindex" if doc.jobs else "ingestion", status="pending")
        db.add(job)
        db.commit()
        db.refresh(job)
        enqueue_job(job.id, doc.id, doc.stored_path, doc.content_type)
    else:
        db.commit()
    db.refresh(doc)
    return doc


def index_daily_brief_context(db: Session, workspace_id: int, user_id: int | None, payload: dict[str, Any]) -> None:
    trade_date = payload.get("trade_date") or datetime.now(timezone.utc).date().isoformat()
    items = payload.get("items") or []
    lines = [
        f"日期: {trade_date}",
        f"摘要: {payload.get('summary') or ''}",
        f"用户: {user_id or 'workspace'}",
        "条目:",
    ]
    for item in items:
        lines.append(
            " - "
            f"{item.get('ticker') or item.get('symbol') or ''} "
            f"{item.get('name') or ''}; "
            f"分区={item.get('section')}; "
            f"排名={item.get('rank')}; "
            f"热度={item.get('heat_score')}; "
            f"覆盖={','.join(item.get('coverage_tags') or [])}; "
            f"来源={item.get('source')}"
        )
    suffix = f"user_{user_id}" if user_id else "workspace"
    ensure_rag_context_document(
        db,
        workspace_id=workspace_id,
        ticker=None,
        kind=f"daily_brief_{trade_date}_{suffix}",
        title=f"A 股每日简报 {trade_date}",
        lines=lines,
        extra_tags=[f"trade_date:{trade_date}", "daily_brief"],
    )
    for item in items[:20]:
        ticker = _normalize_ashare_code(str(item.get("ticker") or item.get("symbol") or "").upper().strip())
        if ticker:
            ensure_rag_context_document(
                db,
                workspace_id=workspace_id,
                ticker=ticker,
                kind=f"brief_item_{trade_date}_{ticker}",
                title=f"{ticker} 今日简报上下文",
                lines=[
                    f"日期: {trade_date}",
                    f"公司: {ticker} {item.get('name') or ''}",
                    f"简报分区: {item.get('section')}",
                    f"热度排名: {item.get('rank')}",
                    f"热度值: {item.get('heat_score')}",
                    f"数据覆盖: {','.join(item.get('coverage_tags') or [])}",
                    f"来源: {item.get('source')}",
                    "说明: 该内容来自每日简报和热榜/关注列表，可作为 RAG 检索入口，不构成交易建议。",
                ],
                extra_tags=[f"trade_date:{trade_date}", "daily_brief_item"],
            )


def index_watchlist_context(db: Session, workspace_id: int, user_id: int, ticker: str, priority: int, company_name: str | None) -> None:
    ensure_rag_context_document(
        db,
        workspace_id=workspace_id,
        ticker=ticker,
        kind=f"watchlist_{user_id}_{ticker}",
        title=f"{ticker} 关注公司上下文",
        lines=[
            f"用户: {user_id}",
            f"公司: {ticker} {company_name or ticker}",
            f"关注优先级: {priority}",
            "说明: 用户已关注该公司。每日简报和个性化分析应优先检查公告、财务事实、行情热度和市场情绪。",
        ],
        extra_tags=[f"user:{user_id}", "watchlist"],
    )


def index_announcement_search_context(
    db: Session,
    workspace_id: int,
    ticker: str,
    keyword: str | None,
    rows: list[dict[str, Any]],
) -> None:
    lines = [f"公司: {ticker}", f"搜索关键词: {keyword or ''}", f"结果数量: {len(rows)}", "公告结果:"]
    for row in rows[:20]:
        lines.append(
            " - "
            f"{row.get('announcement_title')}; "
            f"公告ID={row.get('announcement_id')}; "
            f"类型={row.get('filing_type')}; "
            f"年度={row.get('fiscal_year')}; "
            f"发布时间={row.get('published_at')}; "
            f"下载={row.get('download_url')}"
        )
    ensure_rag_context_document(
        db,
        workspace_id=workspace_id,
        ticker=ticker,
        kind=f"announcement_search_{ticker}",
        title=f"{ticker} 公告搜索上下文",
        lines=lines,
        extra_tags=["announcement_search"],
    )


def _render_context(title: str, lines: list[str]) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    return "\n".join([title, f"生成时间: {timestamp}", "", *lines, ""])


def _safe_part(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value))[:120]


def _normalize_ashare_code(value: str | None) -> str:
    text = str(value or "").upper().strip()
    for prefix in ("SH", "SZ", "BJ"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text[-6:] if len(text) >= 6 else text
