"""Finance workbench APIs."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (
    AgentRunModel,
    CompanyModel,
    DailyBriefModel,
    DataSyncJobModel,
    DocumentModel,
    EvalCaseModel,
    EvalDatasetModel,
    EvalResultModel,
    FilingModel,
    FilingSectionModel,
    FinancialFactModel,
    JobModel,
    MarketFactModel,
    MembershipModel,
    SentimentFactModel,
    UserModel,
    UserWatchlistModel,
    WorkspaceModel,
)
from app.redis_client import enqueue_job
from app.routers.auth import get_current_admin_workspace, get_current_user, get_current_workspace
from app.schemas import (
    AshareAnnouncementResponse,
    AshareFactsSyncRequest,
    AshareFilingImportRequest,
    AshareMarketSyncRequest,
    CompanyCreateRequest,
    CompanyResponse,
    EvalCaseResponse,
    EvalCaseUpdateRequest,
    EvalDatasetResponse,
    FinanceEvalJsonlExportResponse,
    FinanceEvalJsonlImportRequest,
    FilingBindDocumentRequest,
    FilingResponse,
    FilingSectionResponse,
    FinancialFactResponse,
    FinanceAgentQueryRequest,
    FinanceAgentQueryResponse,
    FinanceEvaluationResultResponse,
    FinanceEvaluationRunRequest,
    MarketFactResponse,
    DailyBriefResponse,
    WatchlistCreateRequest,
    WatchlistResponse,
    SentimentFactResponse,
)
from app.services.finance_agent import run_finance_agent
from app.services.finance_dataset_builder import (
    freeze_dataset,
)
from app.services.finance_evaluation import run_finance_evaluation
from app.services.finance_observability import (
    export_finance_agent_jsonl,
    get_agent_run_trace,
    get_finance_observability_alerts,
    import_finance_agent_jsonl,
)
from app.services.finance_research_summary import build_company_research_summary
from app.services.rag_context import (
    index_announcement_search_context,
    index_daily_brief_context,
    index_watchlist_context,
)
from app.services.document_loader import load_document
from app.services.finance_sections import parse_financial_report_sections
from app.services.ashare_connector import download_announcement, get_annual_report, search_announcements
from app.services.ashare_daily_brief import get_or_create_daily_brief
from app.services.ashare_structured_provider import load_akshare_provider, normalize_financial_value
from app.services.vector_store import count_chunks, collection_count, delete_document as chroma_delete

router = APIRouter(prefix="/api/finance", tags=["Finance"])


_ASHARE_METRIC_LABELS = {
    "Revenues": "营业总收入",
    "NetIncomeLoss": "净利润",
    "OperatingIncomeLoss": "营业利润",
    "Assets": "资产总计",
    "Liabilities": "负债合计",
    "OperatingCashFlow": "经营活动产生的现金流量净额",
}


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    rows = (
        db.query(CompanyModel)
        .filter(CompanyModel.workspace_id == workspace.id)
        .order_by(CompanyModel.ticker.asc())
        .all()
    )
    result = []
    for company in rows:
        item = CompanyResponse.model_validate(company)
        item.filing_count = len(company.filings)
        result.append(item)
    return result


@router.get("/watchlist", response_model=list[WatchlistResponse])
def list_watchlist(
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    user, workspace = ws
    rows = (
        db.query(UserWatchlistModel)
        .filter(UserWatchlistModel.workspace_id == workspace.id, UserWatchlistModel.user_id == user.id)
        .order_by(UserWatchlistModel.priority.asc(), UserWatchlistModel.created_at.asc())
        .all()
    )
    result = []
    for row in rows:
        item = WatchlistResponse.model_validate(row)
        company = (
            db.query(CompanyModel)
            .filter(CompanyModel.workspace_id == workspace.id, CompanyModel.ticker == row.ticker)
            .first()
        )
        item.company = {"id": company.id, "ticker": company.ticker, "name": company.name} if company else None
        result.append(item)
    return result


@router.post("/watchlist", response_model=WatchlistResponse)
def add_watchlist(
    req: WatchlistCreateRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    user, workspace = ws
    ticker = req.ticker.upper().strip()
    _ensure_ashare_company(db, workspace.id, ticker)
    row = (
        db.query(UserWatchlistModel)
        .filter(
            UserWatchlistModel.workspace_id == workspace.id,
            UserWatchlistModel.user_id == user.id,
            UserWatchlistModel.ticker == ticker,
        )
        .first()
    )
    if row:
        row.priority = req.priority
    else:
        row = UserWatchlistModel(user_id=user.id, workspace_id=workspace.id, ticker=ticker, priority=req.priority)
        db.add(row)
    db.commit()
    db.refresh(row)
    item = WatchlistResponse.model_validate(row)
    company = db.query(CompanyModel).filter(CompanyModel.workspace_id == workspace.id, CompanyModel.ticker == ticker).first()
    item.company = {"id": company.id, "ticker": company.ticker, "name": company.name} if company else None
    try:
        index_watchlist_context(db, workspace.id, user.id, ticker, row.priority, company.name if company else ticker)
    except Exception:
        pass
    return item


@router.delete("/watchlist/{ticker}", response_model=dict)
def remove_watchlist(
    ticker: str,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    user, workspace = ws
    deleted = (
        db.query(UserWatchlistModel)
        .filter(
            UserWatchlistModel.workspace_id == workspace.id,
            UserWatchlistModel.user_id == user.id,
            UserWatchlistModel.ticker == ticker.upper(),
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.get("/daily-brief", response_model=DailyBriefResponse)
def get_daily_brief(
    date: str | None = Query(default=None),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    user, workspace = ws
    trade_date = date or datetime.now(timezone.utc).date().isoformat()
    payload = get_or_create_daily_brief(db, workspace.id, user.id, trade_date)
    try:
        index_daily_brief_context(db, workspace.id, user.id, payload)
    except Exception:
        pass
    return payload


@router.post("/companies", response_model=CompanyResponse)
def create_company(
    req: CompanyCreateRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    ticker = req.ticker.upper().strip()
    existing = (
        db.query(CompanyModel)
        .filter(CompanyModel.workspace_id == workspace.id, CompanyModel.ticker == ticker)
        .first()
    )
    if existing:
        item = CompanyResponse.model_validate(existing)
        item.filing_count = len(existing.filings)
        return item

    cik = req.cik
    name = req.name or ticker

    company = CompanyModel(
        workspace_id=workspace.id,
        ticker=ticker,
        name=name,
        cik=cik,
        exchange=req.exchange,
        industry=req.industry,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    item = CompanyResponse.model_validate(company)
    item.filing_count = 0
    return item


@router.get("/companies/{ticker}", response_model=dict)
def get_company(
    ticker: str,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    company = _get_company_or_404(db, workspace.id, ticker)
    return {
        "company": CompanyResponse.model_validate(company).model_dump(),
        "filings": [_filing_response(f).model_dump() for f in company.filings],
    }


@router.delete("/companies/{ticker}", response_model=dict)
def delete_company(
    ticker: str,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    company = _get_company_or_404(db, workspace.id, ticker)
    return _delete_company_graph(db, company)


@router.get("/companies/{ticker}/coverage", response_model=dict)
def get_company_coverage(
    ticker: str,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    company = _get_company_or_404(db, workspace.id, ticker)
    return _build_company_coverage(db, workspace.id, company)


@router.get("/companies/{ticker}/research-summary", response_model=dict)
def get_company_research_summary(
    ticker: str,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    user, workspace = ws
    company = _get_company_or_404(db, workspace.id, ticker)
    return build_company_research_summary(db, workspace.id, company, user.id)


@router.get("/companies/{ticker}/agent-runs", response_model=list[dict])
def list_company_agent_runs(
    ticker: str,
    limit: int = Query(default=10, ge=1, le=50),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    company = _get_company_or_404(db, workspace.id, ticker)
    runs = (
        db.query(AgentRunModel)
        .filter(AgentRunModel.workspace_id == workspace.id, AgentRunModel.company_id == company.id)
        .order_by(AgentRunModel.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": run.id,
            "filing_id": run.filing_id,
            "question": run.question,
            "mode": run.mode,
            "status": run.status,
            "answer_preview": (run.answer or "")[:240],
            "verification": run.verification or {},
            "created_at": run.created_at,
            "completed_at": run.completed_at,
        }
        for run in runs
    ]


@router.get("/agent/runs", response_model=list[dict])
def list_finance_agent_runs(
    company_ticker: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    user, workspace = ws
    q = db.query(AgentRunModel).filter(AgentRunModel.workspace_id == workspace.id)
    if company_ticker:
        company = _get_company_or_404(db, workspace.id, company_ticker)
        q = q.filter(AgentRunModel.company_id == company.id)
    else:
        q = q.filter((AgentRunModel.user_id == user.id) | (AgentRunModel.user_id.is_(None)))
    runs = q.order_by(AgentRunModel.created_at.desc()).limit(limit).all()
    company_ids = {run.company_id for run in runs if run.company_id}
    companies = {
        company.id: company
        for company in db.query(CompanyModel).filter(CompanyModel.id.in_(company_ids)).all()
    } if company_ids else {}
    return [
        {
            "id": run.id,
            "company_id": run.company_id,
            "company": {
                "id": companies[run.company_id].id,
                "ticker": companies[run.company_id].ticker,
                "name": companies[run.company_id].name,
            } if run.company_id in companies else None,
            "filing_id": run.filing_id,
            "question": run.question,
            "mode": run.mode,
            "status": run.status,
            "answer_preview": (run.answer or "")[:500],
            "verification": run.verification or {},
            "created_at": run.created_at,
            "completed_at": run.completed_at,
        }
        for run in runs
    ]


@router.delete("/agent/runs/{run_id}", response_model=dict)
def delete_finance_agent_run(
    run_id: int,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    user, workspace = ws
    run = (
        db.query(AgentRunModel)
        .filter(AgentRunModel.id == run_id, AgentRunModel.workspace_id == workspace.id)
        .first()
    )
    if not run:
        raise HTTPException(404, "AgentRun 不存在")
    membership = (
        db.query(MembershipModel)
        .filter(MembershipModel.user_id == user.id, MembershipModel.workspace_id == workspace.id)
        .first()
    )
    is_admin = bool(membership and membership.role in {"admin", "owner"})
    if run.user_id not in {None, user.id} and not is_admin:
        raise HTTPException(403, "只能删除自己的分析记录")
    db.delete(run)
    db.commit()
    return {"ok": True, "deleted": 1}


@router.get("/ashare/companies/{ticker}/announcements", response_model=list[AshareAnnouncementResponse])
def list_ashare_announcements(
    ticker: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    category: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _user, workspace = ws
    try:
        rows = search_announcements(
            ticker,
            start_date=start_date,
            end_date=end_date,
            category=category,
            keyword=keyword,
        )
        try:
            index_announcement_search_context(db, workspace.id, ticker.upper(), keyword, rows)
        except Exception:
            pass
        return rows
    except Exception as exc:
        raise HTTPException(502, f"CNINFO 公告检索失败: {exc}") from exc


@router.post("/ashare/companies/{ticker}/filings/import", response_model=FilingResponse)
def import_ashare_filing(
    ticker: str,
    req: AshareFilingImportRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    company = _ensure_ashare_company(db, workspace.id, ticker)
    try:
        announcement = get_annual_report(company.ticker, req.fiscal_year)
        if req.announcement_id:
            rows = search_announcements(company.ticker, keyword=req.keyword or str(req.fiscal_year), page_size=50)
            announcement = next((row for row in rows if row.get("announcement_id") == req.announcement_id), announcement)
        if not announcement:
            raise ValueError(f"未找到 {company.ticker} {req.fiscal_year} 年报公告")
        existing = (
            db.query(FilingModel)
            .filter(
                FilingModel.workspace_id == workspace.id,
                FilingModel.company_id == company.id,
                FilingModel.accession_number == announcement.get("announcement_id"),
                FilingModel.filing_type == (announcement.get("filing_type") or "annual_report"),
            )
            .order_by(FilingModel.created_at.desc())
            .first()
        )
        if existing:
            return _filing_response(existing)
        downloaded = download_announcement(announcement)
    except Exception as exc:
        raise HTTPException(502, f"A 股公告导入失败: {exc}") from exc

    doc = DocumentModel(
        filename=downloaded["filename"],
        stored_path=downloaded["stored_path"],
        content_type=downloaded["content_type"],
        size_bytes=downloaded["size_bytes"],
        status="pending",
        tags=f"finance,ashare,{company.ticker},{announcement['filing_type']},{announcement['fiscal_year']}",
    )
    db.add(doc)
    db.flush()

    metadata = _json_safe({k: v for k, v in announcement.items() if k != "raw"})
    filing = FilingModel(
        workspace_id=workspace.id,
        company_id=company.id,
        document_id=doc.id,
        accession_number=announcement.get("announcement_id"),
        filing_type=announcement.get("filing_type") or "annual_report",
        fiscal_year=announcement.get("fiscal_year") or req.fiscal_year,
        filed_at=announcement.get("published_at"),
        source_url=downloaded["source_url"],
        status="queued",
        metadata_json=metadata,
    )
    db.add(filing)
    job = JobModel(document_id=doc.id, type="ingestion", status="pending")
    db.add(job)
    db.commit()
    db.refresh(filing)
    db.refresh(job)
    try:
        synced = _sync_ashare_facts_for_filing(db, company, filing)
        metadata = filing.metadata_json or {}
        metadata["auto_fact_sync"] = {"status": "completed", "upserted": synced, "provider": "akshare"}
        filing.metadata_json = metadata
        db.commit()
    except Exception as exc:
        metadata = filing.metadata_json or {}
        metadata["auto_fact_sync"] = {"status": "failed", "provider": "akshare", "failure_reason": str(exc)}
        filing.metadata_json = metadata
        db.commit()
    enqueue_job(job.id, doc.id, doc.stored_path, doc.content_type)
    return _filing_response(filing)


@router.get("/filings/{filing_id}", response_model=FilingResponse)
def get_filing(
    filing_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filing = db.query(FilingModel).filter(FilingModel.id == filing_id).first()
    if not filing:
        raise HTTPException(404, "财报不存在")
    _verify_workspace_access(db, current_user.id, filing.workspace_id)
    return _filing_response(filing)


@router.delete("/filings/{filing_id}", response_model=dict)
def delete_filing(
    filing_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filing = db.query(FilingModel).filter(FilingModel.id == filing_id).first()
    if not filing:
        raise HTTPException(404, "财报不存在")
    _verify_workspace_access(db, current_user.id, filing.workspace_id)
    return _delete_filing_graph(db, filing)


@router.get("/filings/{filing_id}/sections", response_model=list[FilingSectionResponse])
def get_filing_sections(
    filing_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filing = db.query(FilingModel).filter(FilingModel.id == filing_id).first()
    if not filing:
        raise HTTPException(404, "财报不存在")
    _verify_workspace_access(db, current_user.id, filing.workspace_id)
    return (
        db.query(FilingSectionModel)
        .filter(FilingSectionModel.filing_id == filing_id)
        .order_by(FilingSectionModel.char_start.asc())
        .all()
    )


@router.get("/filings/{filing_id}/facts", response_model=list[FinancialFactResponse])
def get_filing_facts(
    filing_id: int,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filing = db.query(FilingModel).filter(FilingModel.id == filing_id).first()
    if not filing:
        raise HTTPException(404, "财报不存在")
    _verify_workspace_access(db, current_user.id, filing.workspace_id)
    return (
        db.query(FinancialFactModel)
        .filter(FinancialFactModel.filing_id == filing.id)
        .order_by(FinancialFactModel.metric.asc())
        .all()
    )


@router.post("/ashare/companies/{ticker}/facts/sync")
def sync_ashare_financial_facts(
    ticker: str,
    req: AshareFactsSyncRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    if req.provider != "akshare":
        raise HTTPException(400, "第一版仅支持 akshare provider")
    company = _ensure_ashare_company(db, workspace.id, ticker)
    filing = _latest_company_filing(db, workspace.id, company.id, req.fiscal_year)
    if not filing:
        raise HTTPException(400, "请先导入该公司的 A 股年报 filing，再同步结构化财务事实")
    try:
        upserted = _sync_ashare_facts_for_filing(db, company, filing)
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"company_id": company.id, "filing_id": filing.id, "upserted": upserted, "provider": req.provider}


@router.post("/ashare/companies/{ticker}/market/sync")
def sync_ashare_market_facts(
    ticker: str,
    req: AshareMarketSyncRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    if req.provider != "akshare":
        raise HTTPException(400, "第一版仅支持 akshare provider")
    company = _ensure_ashare_company(db, workspace.id, ticker)
    try:
        ak = load_akshare_provider()
        rows = _load_akshare_market_rows(ak, company.ticker)
    except Exception as exc:
        fallback = _sync_hot_rank_market_fact_fallback(db, workspace.id, company)
        if fallback:
            return {
                "company_id": company.id,
                "trade_date": fallback["trade_date"],
                "upserted": 1,
                "provider": "daily_brief_hot_rank",
                "fallback": True,
                "warning": str(exc),
            }
        raise HTTPException(503, str(exc)) from exc

    row = None
    for candidate in reversed(rows):
        date_text = str(candidate.get("日期") or candidate.get("trade_date") or candidate.get("date") or "")
        if not req.trade_date or date_text == req.trade_date:
            row = candidate
            break
    if not row:
        raise HTTPException(404, "未找到指定交易日行情")

    date_text = str(row.get("日期") or row.get("trade_date") or req.trade_date)
    metric_labels = {
        "close": (("收盘", "close", "最新价"), "CNY"),
        "open": (("开盘", "open", "今开"), "CNY"),
        "high": (("最高", "high"), "CNY"),
        "low": (("最低", "low"), "CNY"),
        "volume": (("成交量", "volume"), "shares"),
        "amount": (("成交额", "amount"), "CNY"),
    }
    upserted = 0
    for metric, (labels, unit) in metric_labels.items():
        value = normalize_financial_value(_first_row_value(row, labels))
        if value is None:
            continue
        label = labels[0]
        _upsert_market_fact(db, workspace.id, company.id, company.ticker, date_text, metric, label, value, unit, req.provider)
        upserted += 1
    db.commit()
    return {"company_id": company.id, "trade_date": date_text, "upserted": upserted, "provider": req.provider}


@router.get("/companies/{ticker}/market-facts", response_model=list[MarketFactResponse])
def list_company_market_facts(
    ticker: str,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    company = _get_company_or_404(db, workspace.id, ticker)
    return (
        db.query(MarketFactModel)
        .filter(MarketFactModel.workspace_id == workspace.id, MarketFactModel.company_id == company.id)
        .order_by(MarketFactModel.trade_date.desc(), MarketFactModel.metric.asc())
        .limit(200)
        .all()
    )


@router.get("/sentiment", response_model=list[SentimentFactResponse])
def list_sentiment_facts(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    q = db.query(SentimentFactModel).filter(SentimentFactModel.workspace_id == workspace.id)
    if ticker:
        q = q.filter(SentimentFactModel.ticker == ticker.upper())
    return q.order_by(SentimentFactModel.trade_date.desc(), SentimentFactModel.created_at.desc()).limit(limit).all()


@router.post("/filings/{filing_id}/bind-document", response_model=FilingResponse)
def bind_document_to_filing(
    filing_id: int,
    req: FilingBindDocumentRequest,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filing = db.query(FilingModel).filter(FilingModel.id == filing_id).first()
    if not filing:
        raise HTTPException(404, "财报不存在")
    _verify_workspace_access(db, current_user.id, filing.workspace_id)
    doc = db.query(DocumentModel).filter(DocumentModel.id == req.document_id).first()
    if not doc:
        raise HTTPException(404, "文档不存在")
    filing.document_id = doc.id
    filing.fiscal_year = req.fiscal_year
    filing.filing_type = req.filing_type
    filing.status = "queued"

    if os.path.exists(doc.stored_path):
        try:
            text = load_document(doc.stored_path)
            db.query(FilingSectionModel).filter(FilingSectionModel.filing_id == filing.id).delete()
            for section in parse_financial_report_sections(text):
                db.add(FilingSectionModel(filing_id=filing.id, **section))
        except Exception:
            pass

    job = JobModel(document_id=doc.id, type="reindex", status="pending")
    db.add(job)
    db.commit()
    db.refresh(filing)
    db.refresh(job)
    enqueue_job(job.id, doc.id, doc.stored_path, doc.content_type)
    return _filing_response(filing)


@router.post("/agent/query", response_model=FinanceAgentQueryResponse)
def query_finance_agent(
    req: FinanceAgentQueryRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    user, workspace = ws
    try:
        return run_finance_agent(
            db=db,
            workspace_id=workspace.id,
            company_ticker=req.company_ticker,
            filing_id=req.filing_id,
            question=req.question,
            mode=req.mode,
            user_id=user.id,
        )
    except Exception as exc:
        raise HTTPException(500, f"Agent 分析失败: {exc}") from exc


@router.get("/agent/runs/{run_id}/trace", response_model=dict)
def get_finance_agent_run_trace(
    run_id: int,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    trace = get_agent_run_trace(db, workspace.id, run_id)
    if not trace:
        raise HTTPException(404, "AgentRun 不存在")
    return trace


@router.post("/evaluations/run", response_model=FinanceEvaluationResultResponse)
def run_eval(
    req: FinanceEvaluationRunRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    result = run_finance_evaluation(db, workspace.id, req.dataset_source, req.strategy)
    return result


@router.post("/evaluations/import-jsonl", response_model=dict)
def import_eval_jsonl(
    req: FinanceEvalJsonlImportRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    try:
        return import_finance_agent_jsonl(db, workspace.id, req.dataset_name, req.file_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/evaluations/export-jsonl", response_model=FinanceEvalJsonlExportResponse)
def export_eval_jsonl(
    dataset_name: str = Query(default="finance_agent_offline"),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    try:
        return export_finance_agent_jsonl(db, workspace.id, dataset_name)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/evaluations/results", response_model=list[FinanceEvaluationResultResponse])
def list_eval_results(
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    from app.models import EvalResultModel

    _, workspace = ws
    return (
        db.query(EvalResultModel)
        .filter(EvalResultModel.workspace_id == workspace.id)
        .order_by(EvalResultModel.created_at.desc())
        .limit(30)
        .all()
    )


@router.get("/observability/alerts", response_model=list[dict])
def list_finance_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
):
    _user, _workspace = ws
    return get_finance_observability_alerts(limit=limit)


@router.get("/summary", response_model=dict)
def finance_summary(
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    datasets = db.query(EvalDatasetModel).filter(EvalDatasetModel.workspace_id == workspace.id).all()
    companies = db.query(CompanyModel).filter(CompanyModel.workspace_id == workspace.id).all()
    filings = db.query(FilingModel).filter(FilingModel.workspace_id == workspace.id).all()
    latest_eval = (
        db.query(EvalResultModel)
        .filter(EvalResultModel.workspace_id == workspace.id)
        .order_by(EvalResultModel.created_at.desc())
        .first()
    )
    failure_counts: dict[str, int] = {}
    for dataset in datasets:
        cases = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset.id).all()
        for case in cases:
            metadata = case.metadata_json or {}
            reason = metadata.get("failure_reason") or (metadata.get("quality_flags") or {}).get("failure_reason")
            if reason:
                failure_counts[reason] = failure_counts.get(reason, 0) + 1
    return {
        "company_count": len(companies),
        "filing_count": len(filings),
        "dataset_count": len(datasets),
        "frozen_dataset_count": sum(1 for ds in datasets if ds.frozen_at),
        "case_count": sum(ds.case_count or 0 for ds in datasets),
        "latest_eval": latest_eval.metrics if latest_eval else None,
        "dataset_failure_counts": failure_counts,
        "datasets": [
            {
                "id": ds.id,
                "name": ds.name,
                "source": ds.source,
                "version": ds.version,
                "case_count": ds.case_count,
                "frozen_at": ds.frozen_at,
                "source_url": ds.source_url,
                "license_note": ds.license_note,
                "public_data_only": bool((ds.manifest_json or {}).get("public_data_only")),
            }
            for ds in datasets
        ],
    }


def _test_connector_by_name(name: str) -> dict:
    catalog = {item["name"]: item for item in _build_connector_status_catalog()}
    if name not in catalog:
        raise HTTPException(404, "数据源不存在")
    try:
        if name == "cninfo":
            search_announcements("600519", keyword="2023年年度报告", page_size=1)
        elif name == "akshare":
            load_akshare_provider()
        elif name == "tushare":
            import tushare  # type: ignore  # noqa: F401
        elif name == "ashare_mcp":
            # MCP is optional/configurable in this version; absence is not a connector crash.
            pass
        elif name == "chroma":
            collection_count()
        else:
            raise ValueError("未定义连接测试")
        return {**catalog[name], "status": "available", "failure_reason": None}
    except Exception as exc:
        return {**catalog[name], "status": "unavailable", "failure_reason": str(exc)}


# ── Dataset endpoints ──────────────────────────────────────

@router.get("/datasets", response_model=list[EvalDatasetResponse])
def list_datasets(
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    return (
        db.query(EvalDatasetModel)
        .filter(EvalDatasetModel.workspace_id == workspace.id)
        .order_by(EvalDatasetModel.created_at.desc())
        .all()
    )


@router.get("/datasets/{dataset_id}/cases", response_model=list[EvalCaseResponse])
def list_dataset_cases(
    dataset_id: int,
    status: str | None = None,
    task_type: str | None = None,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    dataset = db.query(EvalDatasetModel).filter(EvalDatasetModel.id == dataset_id, EvalDatasetModel.workspace_id == workspace.id).first()
    if not dataset:
        raise HTTPException(404, "数据集不存在")
    q = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset_id)
    if status:
        q = q.filter(EvalCaseModel.status == status)
    if task_type:
        q = q.filter(EvalCaseModel.task_type == task_type)
    return q.order_by(EvalCaseModel.created_at.desc()).limit(200).all()


@router.post("/datasets/{dataset_id}/freeze")
def freeze_dataset_endpoint(
    dataset_id: int,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    dataset = db.query(EvalDatasetModel).filter(EvalDatasetModel.id == dataset_id, EvalDatasetModel.workspace_id == workspace.id).first()
    if not dataset:
        raise HTTPException(404, "数据集不存在")
    return EvalDatasetResponse.model_validate(freeze_dataset(db, dataset_id))


@router.patch("/eval-cases/{case_id}", response_model=EvalCaseResponse)
def update_eval_case(
    case_id: int,
    req: EvalCaseUpdateRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    case = db.query(EvalCaseModel).filter(EvalCaseModel.id == case_id).first()
    if not case:
        raise HTTPException(404, "评估用例不存在")
    if req.status is not None:
        case.status = req.status
    if req.expected_answer is not None:
        case.expected_answer = req.expected_answer
    if req.expected_numeric is not None:
        case.expected_numeric = req.expected_numeric
    if req.tolerance is not None:
        case.tolerance = req.tolerance
    if req.difficulty is not None:
        case.difficulty = req.difficulty
    if req.rubric_json is not None:
        case.rubric_json = req.rubric_json
    db.commit()
    db.refresh(case)
    return case


# ── Helpers ────────────────────────────────────────────────

def _build_connector_status_catalog() -> list[dict]:
    return [
        {
            "name": "cninfo",
            "label": "巨潮资讯 CNINFO",
            "category": "disclosure",
            "source": "http://www.cninfo.com.cn",
            "capabilities": ["A 股公告搜索", "年报 PDF 下载", "公告元数据"],
        },
        {
            "name": "akshare",
            "label": "AKShare",
            "category": "structured_data",
            "source": "https://akshare.akfamily.xyz",
            "capabilities": ["A 股结构化财务事实", "A 股行情事实", "热度榜", "市场情绪"],
        },
        {
            "name": "tushare",
            "label": "TuShare",
            "category": "structured_data",
            "source": "https://tushare.pro",
            "capabilities": ["A 股财务数据", "行情数据", "可选 provider"],
        },
        {
            "name": "ashare_mcp",
            "label": "A 股 MCP",
            "category": "mcp",
            "source": "local/configurable",
            "capabilities": ["行情工具", "公告工具", "情绪工具"],
        },
        {
            "name": "chroma",
            "label": "Chroma Index",
            "category": "index",
            "source": "local",
            "capabilities": ["公告向量索引", "公司 metadata filter"],
        },
    ]


def _build_connector_status_rows(db: Session, workspace_id: int) -> list[dict]:
    rows = _build_connector_status_catalog()
    filings = db.query(FilingModel).filter(FilingModel.workspace_id == workspace_id).all()
    datasets = db.query(EvalDatasetModel).filter(EvalDatasetModel.workspace_id == workspace_id).all()
    facts = (
        db.query(FinancialFactModel)
        .join(FilingModel, FilingModel.id == FinancialFactModel.filing_id)
        .filter(FilingModel.workspace_id == workspace_id)
        .all()
    )
    market_fact_count = db.query(MarketFactModel).filter(MarketFactModel.workspace_id == workspace_id).count()
    sentiment_fact_count = db.query(SentimentFactModel).filter(SentimentFactModel.workspace_id == workspace_id).count()

    for row in rows:
        name = row["name"]
        row["status"] = "configured"
        row["failure_reason"] = None
        row["last_sync_at"] = None
        row["coverage"] = {}
        if name == "cninfo":
            ashare_filings = [f for f in filings if f.filing_type in {"annual_report", "semi_annual_report", "quarterly_report"}]
            row["coverage"] = {"filings": len(ashare_filings)}
            row["last_sync_at"] = max((f.created_at for f in ashare_filings), default=None)
        elif name == "akshare":
            row["coverage"] = {
                "financial_facts": len([f for f in facts if f.source == "akshare"]),
                "market_facts": market_fact_count,
                "sentiment_facts": sentiment_fact_count,
            }
        elif name == "tushare":
            row["coverage"] = {"configured": 0, "facts": len([f for f in facts if f.source == "tushare"])}
        elif name == "ashare_mcp":
            row["coverage"] = {"configured": 0}
        elif name == "chroma":
            row["coverage"] = {"chunks": collection_count()}
    return rows


def _build_ashare_daily_job_status(db: Session, workspace_id: int) -> dict:
    ashare_filings = (
        db.query(FilingModel)
        .filter(
            FilingModel.workspace_id == workspace_id,
            FilingModel.filing_type.in_(["annual_report", "semi_annual_report", "quarterly_report"]),
        )
        .order_by(FilingModel.created_at.desc())
        .limit(1)
        .all()
    )
    latest_fact = (
        db.query(FinancialFactModel)
        .join(FilingModel, FilingModel.id == FinancialFactModel.filing_id)
        .filter(FilingModel.workspace_id == workspace_id, FinancialFactModel.source == "akshare")
        .order_by(FinancialFactModel.created_at.desc())
        .first()
    )
    latest_market_fact = (
        db.query(MarketFactModel)
        .filter(MarketFactModel.workspace_id == workspace_id)
        .order_by(MarketFactModel.created_at.desc())
        .first()
    )
    latest_sentiment = (
        db.query(SentimentFactModel)
        .filter(SentimentFactModel.workspace_id == workspace_id)
        .order_by(SentimentFactModel.created_at.desc())
        .first()
    )
    latest_job = (
        db.query(DataSyncJobModel)
        .filter(DataSyncJobModel.workspace_id == workspace_id, DataSyncJobModel.job_type == "daily_sync")
        .order_by(DataSyncJobModel.started_at.desc())
        .first()
    )

    timestamps = [
        item for item in [
            ashare_filings[0].created_at if ashare_filings else None,
            latest_fact.created_at if latest_fact else None,
            latest_market_fact.created_at if latest_market_fact else None,
            latest_sentiment.created_at if latest_sentiment else None,
            latest_job.completed_at if latest_job else None,
        ] if item is not None
    ]
    last_run_at = max(timestamps) if timestamps else None

    failure_reason = None
    if ashare_filings:
        auto_sync = (ashare_filings[0].metadata_json or {}).get("auto_fact_sync") or {}
        if auto_sync.get("status") == "failed":
            failure_reason = auto_sync.get("failure_reason") or "A 股结构化事实同步失败"
    if latest_job and latest_job.metrics and latest_job.metrics.get("sentiment_failure_reason"):
        failure_reason = latest_job.metrics.get("sentiment_failure_reason")

    return {
        "name": "A 股公开数据日更",
        "source": "cninfo+akshare",
        "schedule": "03:00 Asia/Shanghai",
        "status": "success" if last_run_at else "configured",
        "last_run_at": last_run_at,
        "next_run_at": _next_daily_run_at(hour=3, utc_offset_hours=8),
        "failure_reason": failure_reason,
    }


def _delete_filing_graph(db: Session, filing: FilingModel) -> dict:
    document = db.query(DocumentModel).filter(DocumentModel.id == filing.document_id).first() if filing.document_id else None
    db.query(EvalCaseModel).filter(EvalCaseModel.gold_filing_id == filing.id).update(
        {"gold_filing_id": None, "gold_document_id": None},
        synchronize_session=False,
    )
    db.query(AgentRunModel).filter(AgentRunModel.filing_id == filing.id).update(
        {"filing_id": None},
        synchronize_session=False,
    )

    sections_deleted = db.query(FilingSectionModel).filter(FilingSectionModel.filing_id == filing.id).delete(synchronize_session=False)
    facts_deleted = db.query(FinancialFactModel).filter(FinancialFactModel.filing_id == filing.id).delete(synchronize_session=False)
    db.delete(filing)
    db.flush()

    documents_deleted = 0
    if document:
        other_refs = db.query(FilingModel).filter(FilingModel.document_id == document.id).count()
        if other_refs == 0:
            if os.path.exists(document.stored_path):
                try:
                    os.remove(document.stored_path)
                except Exception:
                    pass
            try:
                chroma_delete(document.id)
            except Exception:
                pass
            db.delete(document)
            documents_deleted = 1
    db.commit()
    return {
        "ok": True,
        "filings_deleted": 1,
        "sections_deleted": sections_deleted,
        "facts_deleted": facts_deleted,
        "documents_deleted": documents_deleted,
    }


def _delete_company_graph(db: Session, company: CompanyModel) -> dict:
    filings = list(company.filings)
    documents_deleted = 0
    sections_deleted = 0
    facts_deleted = 0
    for filing in filings:
        result = _delete_filing_graph(db, filing)
        documents_deleted += result.get("documents_deleted", 0)
        sections_deleted += result.get("sections_deleted", 0)
        facts_deleted += result.get("facts_deleted", 0)

    db.query(MarketFactModel).filter(MarketFactModel.company_id == company.id).delete(synchronize_session=False)
    db.query(AgentRunModel).filter(AgentRunModel.company_id == company.id).update(
        {"company_id": None},
        synchronize_session=False,
    )
    db.delete(company)
    db.commit()
    return {
        "ok": True,
        "companies_deleted": 1,
        "filings_deleted": len(filings),
        "documents_deleted": documents_deleted,
        "sections_deleted": sections_deleted,
        "facts_deleted": facts_deleted,
    }


def _next_daily_run_at(hour: int, utc_offset_hours: int) -> datetime:
    tz = timezone(timedelta(hours=utc_offset_hours))
    now = datetime.now(tz)
    next_run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


def _build_company_coverage(db: Session, workspace_id: int, company: CompanyModel) -> dict:
    filings = (
        db.query(FilingModel)
        .filter(FilingModel.workspace_id == workspace_id, FilingModel.company_id == company.id)
        .order_by(FilingModel.fiscal_year.desc(), FilingModel.created_at.desc())
        .all()
    )
    document_ids = [f.document_id for f in filings if f.document_id]
    documents = db.query(DocumentModel).filter(DocumentModel.id.in_(document_ids)).all() if document_ids else []
    sections = (
        db.query(FilingSectionModel)
        .filter(FilingSectionModel.filing_id.in_([f.id for f in filings]))
        .all()
        if filings else []
    )
    facts = (
        db.query(FinancialFactModel)
        .filter(FinancialFactModel.filing_id.in_([f.id for f in filings]))
        .all()
        if filings else []
    )
    market_fact_count = (
        db.query(MarketFactModel)
        .filter(MarketFactModel.workspace_id == workspace_id, MarketFactModel.company_id == company.id)
        .count()
    )
    chroma_chunks = sum(count_chunks(doc.id) for doc in documents)
    flags = []
    if not filings:
        flags.append("missing_filing")
    if documents and chroma_chunks == 0:
        flags.append("document_not_indexed")
    if filings and not sections:
        flags.append("missing_section")
    if filings and not facts:
        flags.append("missing_financial_fact")
    return {
        "company_id": company.id,
        "ticker": company.ticker,
        "document_count": len(documents),
        "filing_count": len(filings),
        "chunk_count": sum(doc.chunk_count or 0 for doc in documents),
        "chroma_chunk_count": chroma_chunks,
        "section_count": len(sections),
        "financial_fact_count": len(facts),
        "market_fact_count": market_fact_count,
        "indexed_document_count": len([doc for doc in documents if doc.status == "completed" and (doc.chunk_count or 0) > 0]),
        "failure_flags": flags,
        "filings": [
            {
                "id": filing.id,
                "filing_type": filing.filing_type,
                "fiscal_year": filing.fiscal_year,
                "status": filing.status,
                "document_id": filing.document_id,
                "metadata_json": filing.metadata_json,
            }
            for filing in filings
        ],
    }


def _extract_ashare_financial_facts(rows: list[dict], fiscal_year: int | None, ticker: str) -> list[dict]:
    facts: list[dict] = []
    for row in rows:
        period = _report_period_from_row(row, fiscal_year)
        if fiscal_year and str(fiscal_year) not in period:
            continue
        for metric, label in _ASHARE_METRIC_LABELS.items():
            value = normalize_financial_value(row.get(label))
            if value is None:
                continue
            facts.append({
                "metric": metric,
                "label": label,
                "value": value,
                "period": period,
                "unit": "CNY",
                "source": "akshare",
                "evidence": f"{ticker} {period} {label}",
            })
    return facts


def _sync_ashare_facts_for_filing(db: Session, company: CompanyModel, filing: FilingModel) -> int:
    ak = load_akshare_provider()
    rows = _load_akshare_financial_rows(ak, company.ticker)
    facts = _extract_ashare_financial_facts(rows, filing.fiscal_year, company.ticker)
    for fact in facts:
        _upsert_financial_fact(
            db,
            filing.id,
            metric=fact["metric"],
            label=fact["label"],
            value=fact["value"],
            period=fact["period"],
            source=fact["source"],
            evidence=fact["evidence"],
        )
    db.commit()
    return len(facts)


def _verify_workspace_access(db: Session, user_id: int, workspace_id: int) -> None:
    membership = (
        db.query(MembershipModel)
        .filter(
            MembershipModel.user_id == user_id,
            MembershipModel.workspace_id == workspace_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(403, "你没有该工作空间的访问权限")


def _ensure_ashare_company(db: Session, workspace_id: int, ticker: str) -> CompanyModel:
    code = ticker.upper().strip()
    existing = (
        db.query(CompanyModel)
        .filter(CompanyModel.workspace_id == workspace_id, CompanyModel.ticker == code)
        .first()
    )
    if existing:
        return existing
    company = CompanyModel(
        workspace_id=workspace_id,
        ticker=code,
        name=code,
        cik=None,
        exchange="SSE" if code.startswith(("5", "6", "9")) or code.startswith("688") else "SZSE",
        industry="A-share",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _latest_company_filing(db: Session, workspace_id: int, company_id: int, fiscal_year: int | None) -> FilingModel | None:
    q = db.query(FilingModel).filter(FilingModel.workspace_id == workspace_id, FilingModel.company_id == company_id)
    if fiscal_year:
        q = q.filter(FilingModel.fiscal_year == fiscal_year)
    return q.order_by(FilingModel.fiscal_year.desc(), FilingModel.created_at.desc()).first()


def _report_period_from_row(row: dict, fallback_year: int | None) -> str:
    for key in ("period", "报告期", "报告日", "报表日期", "日期"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return str(fallback_year or "")


def _get_company_or_404(db: Session, workspace_id: int, ticker: str) -> CompanyModel:
    company = (
        db.query(CompanyModel)
        .filter(CompanyModel.workspace_id == workspace_id, CompanyModel.ticker == ticker.upper())
        .first()
    )
    if not company:
        raise HTTPException(404, "公司不存在")
    return company


def _upsert_financial_fact(
    db: Session,
    filing_id: int,
    metric: str,
    label: str,
    value: float | None,
    period: str | None,
    source: str,
    evidence: str | None = None,
):
    existing = (
        db.query(FinancialFactModel)
        .filter(
            FinancialFactModel.filing_id == filing_id,
            FinancialFactModel.metric == metric,
            FinancialFactModel.period == period,
        )
        .first()
    )
    if existing:
        existing.label = label
        existing.value = value
        existing.source = source
        existing.evidence = evidence
        existing.confidence = 1.0
        return existing
    fact = FinancialFactModel(
        filing_id=filing_id,
        metric=metric,
        label=label,
        value=value,
        period=period,
        source=source,
        evidence=evidence,
        confidence=1.0,
    )
    db.add(fact)
    return fact


def _upsert_market_fact(
    db: Session,
    workspace_id: int,
    company_id: int,
    ticker: str,
    trade_date: str,
    metric: str,
    label: str,
    value: float | None,
    unit: str,
    source: str,
):
    existing = (
        db.query(MarketFactModel)
        .filter(
            MarketFactModel.workspace_id == workspace_id,
            MarketFactModel.company_id == company_id,
            MarketFactModel.trade_date == trade_date,
            MarketFactModel.metric == metric,
        )
        .first()
    )
    if existing:
        existing.label = label
        existing.value = value
        existing.unit = unit
        existing.source = source
        existing.ticker = ticker
        existing.confidence = 1.0
        return existing
    fact = MarketFactModel(
        workspace_id=workspace_id,
        company_id=company_id,
        ticker=ticker,
        trade_date=trade_date,
        metric=metric,
        label=label,
        value=value,
        unit=unit,
        source=source,
        confidence=1.0,
    )
    db.add(fact)
    return fact


def _sync_hot_rank_market_fact_fallback(db: Session, workspace_id: int, company: CompanyModel) -> dict | None:
    trade_date = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    brief = get_or_create_daily_brief(db, workspace_id, None, trade_date)
    items = brief.get("items") or []
    if not items:
        cached = (
            db.query(DailyBriefModel)
            .filter(DailyBriefModel.workspace_id == workspace_id, DailyBriefModel.trade_date == trade_date)
            .order_by(DailyBriefModel.generated_at.desc())
            .all()
        )
        for row in cached:
            if row.items:
                items = row.items
                break
    target = _normalize_ashare_code(company.ticker)
    for item in items:
        if _normalize_ashare_code(str(item.get("ticker") or "")) != target:
            continue
        value = normalize_financial_value(item.get("heat_score"))
        if value is None:
            return None
        _upsert_market_fact(
            db,
            workspace_id,
            company.id,
            company.ticker,
            trade_date,
            "heat_score",
            "热度",
            value,
            "score",
            str(item.get("source") or "daily_brief_hot_rank"),
        )
        db.commit()
        return {"trade_date": trade_date, "value": value}
    return None


def _normalize_ashare_code(value: str) -> str:
    text = str(value or "").upper().strip()
    for prefix in ("SH", "SZ", "BJ"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text[-6:] if len(text) >= 6 else text


def _load_akshare_financial_rows(ak, ticker: str) -> list[dict]:
    candidates = [
        ("stock_financial_report_sina", {"stock": ticker, "symbol": "利润表"}),
        ("stock_financial_report_sina", {"stock": ticker, "symbol": "资产负债表"}),
        ("stock_financial_report_sina", {"stock": ticker, "symbol": "现金流量表"}),
    ]
    rows = []
    for fn_name, kwargs in candidates:
        fn = getattr(ak, fn_name, None)
        if not fn:
            continue
        try:
            frame = fn(**kwargs)
        except Exception:
            continue
        if hasattr(frame, "to_dict"):
            rows.extend(frame.to_dict(orient="records"))
    return rows


def _load_akshare_market_rows(ak, ticker: str) -> list[dict]:
    errors: list[str] = []
    fn = getattr(ak, "stock_zh_a_hist", None)
    if fn:
        try:
            frame = fn(symbol=ticker, period="daily", adjust="")
            if hasattr(frame, "to_dict"):
                rows = frame.to_dict(orient="records")
                if rows:
                    return rows
            errors.append("stock_zh_a_hist 返回空数据")
        except Exception as exc:
            errors.append(f"stock_zh_a_hist: {exc}")
    else:
        errors.append("缺少 stock_zh_a_hist")

    tx_fn = getattr(ak, "stock_zh_a_hist_tx", None)
    if tx_fn:
        try:
            end_date = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
            start_date = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=10)).strftime("%Y%m%d")
            frame = tx_fn(symbol=_ashare_market_symbol(ticker), start_date=start_date, end_date=end_date)
            if hasattr(frame, "to_dict"):
                rows = frame.to_dict(orient="records")
                if rows:
                    return [{**row, "source_fallback": "stock_zh_a_hist_tx"} for row in rows]
            errors.append("stock_zh_a_hist_tx 返回空数据")
        except Exception as exc:
            errors.append(f"stock_zh_a_hist_tx: {exc}")
    else:
        errors.append("缺少 stock_zh_a_hist_tx")

    spot_fn = getattr(ak, "stock_zh_a_spot_em", None)
    if spot_fn:
        try:
            spot_frame = spot_fn()
            if not hasattr(spot_frame, "to_dict"):
                raise RuntimeError("返回格式不可识别")
            for row in spot_frame.to_dict(orient="records"):
                if str(row.get("代码") or row.get("code") or "").zfill(6) == ticker:
                    return [{
                        "日期": datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
                        "收盘": row.get("最新价"),
                        "开盘": row.get("今开"),
                        "最高": row.get("最高"),
                        "最低": row.get("最低"),
                        "成交量": row.get("成交量"),
                        "成交额": row.get("成交额"),
                        "source_fallback": "stock_zh_a_spot_em",
                    }]
            errors.append(f"stock_zh_a_spot_em 未找到 {ticker}")
        except Exception as exc:
            errors.append(f"stock_zh_a_spot_em: {exc}")
    else:
        errors.append("缺少 stock_zh_a_spot_em")
    raise RuntimeError("akshare 行情同步失败: " + "；".join(errors))


def _first_row_value(row: dict, keys: tuple[str, ...]):
    for key in keys:
        if row.get(key) not in (None, ""):
            return row.get(key)
    return None


def _ashare_market_symbol(ticker: str) -> str:
    code = str(ticker).zfill(6)
    return ("sh" if code.startswith(("5", "6", "9")) else "sz") + code


def _filing_response(filing: FilingModel) -> FilingResponse:
    response = FilingResponse.model_validate({
        "id": filing.id,
        "workspace_id": filing.workspace_id,
        "company_id": filing.company_id,
        "document_id": filing.document_id,
        "accession_number": filing.accession_number,
        "filing_type": filing.filing_type,
        "fiscal_year": filing.fiscal_year,
        "filed_at": filing.filed_at,
        "source_url": filing.source_url,
        "status": filing.status,
        "metadata_json": filing.metadata_json,
        "created_at": filing.created_at,
        "updated_at": filing.updated_at,
    })
    if filing.company:
        response.company = {
            "id": filing.company.id,
            "ticker": filing.company.ticker,
            "name": filing.company.name,
            "cik": filing.company.cik,
        }
    if filing.document:
        response.document = {
            "id": filing.document.id,
            "filename": filing.document.filename,
            "status": filing.document.status,
            "chunk_count": filing.document.chunk_count,
        }
    return response
