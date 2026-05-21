"""Finance workbench APIs."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import config
from app.db import get_db
from app.models import (
    CompanyModel,
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
    UserModel,
    WorkspaceModel,
)
from app.redis_client import enqueue_job
from app.routers.auth import get_current_user, get_current_workspace
from app.schemas import (
    AshareAnnouncementResponse,
    AshareFactsSyncRequest,
    AshareFilingImportRequest,
    AshareMarketSyncRequest,
    CompanyCreateRequest,
    CompanyResponse,
    EvalCaseResponse,
    EvalCaseUpdateRequest,
    EvalDatasetBuildRequest,
    EvalDatasetImportRequest,
    EvalDatasetResponse,
    FilingBindDocumentRequest,
    FilingImportRequest,
    FilingResponse,
    FilingSectionResponse,
    FinancialFactResponse,
    FinanceAgentQueryRequest,
    FinanceAgentQueryResponse,
    FinanceEvaluationResultResponse,
    FinanceEvaluationRunRequest,
    MarketFactResponse,
)
from app.services.finance_agent import run_finance_agent
from app.services.finance_dataset_builder import (
    _ensure_dataset,
    _next_version,
    freeze_dataset,
    generate_custom_10k_cases,
    generate_sec_10k_cases,
    import_finqa,
    import_financebench,
    import_tatqa,
)
from app.services.finance_evaluation import run_finance_evaluation
from app.services.finance_sections import parse_10k_sections
from app.services.sec_connector import download_filing_document, find_10k_filing, load_filing_text, parse_sec_date, resolve_ticker
from app.services.ashare_connector import download_announcement, get_annual_report, search_announcements
from app.services.ashare_structured_provider import load_akshare_provider, normalize_financial_value

router = APIRouter(prefix="/api/finance", tags=["Finance"])


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
    name = req.name
    if not cik or not name:
        try:
            resolved = resolve_ticker(ticker)
            cik = cik or resolved["cik"]
            name = name or resolved["name"]
        except Exception:
            name = name or ticker

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


@router.post("/companies/{ticker}/filings/import", response_model=FilingResponse)
def import_company_filing(
    ticker: str,
    req: FilingImportRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    company = _ensure_company(db, workspace.id, ticker)
    try:
        filing_info = find_10k_filing(company.ticker, year=req.year, accession_number=req.accession_number)
        downloaded = download_filing_document(
            filing_info,
            os.path.join(config.PUBLIC_DATA_DIR, "sec_edgar", "filings"),
        )
    except Exception as exc:
        raise HTTPException(502, f"SEC EDGAR 导入失败: {exc}") from exc

    doc = DocumentModel(
        filename=downloaded["filename"],
        stored_path=downloaded["stored_path"],
        content_type=downloaded["content_type"],
        size_bytes=downloaded["size_bytes"],
        status="pending",
        tags=f"finance,{company.ticker},10-K,{filing_info['fiscal_year']}",
    )
    db.add(doc)
    db.flush()

    filing = FilingModel(
        workspace_id=workspace.id,
        company_id=company.id,
        document_id=doc.id,
        accession_number=filing_info["accession_number"],
        filing_type="10-K",
        fiscal_year=filing_info["fiscal_year"],
        filed_at=parse_sec_date(filing_info.get("filing_date")),
        source_url=downloaded["source_url"],
        status="queued",
        metadata_json=filing_info,
    )
    db.add(filing)
    job = JobModel(document_id=doc.id, type="ingestion", status="pending")
    db.add(job)
    db.commit()
    db.refresh(filing)
    db.refresh(job)
    enqueue_job(job.id, doc.id, doc.stored_path, doc.content_type)
    return _filing_response(filing)


@router.get("/ashare/companies/{ticker}/announcements", response_model=list[AshareAnnouncementResponse])
def list_ashare_announcements(
    ticker: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    category: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
):
    try:
        return search_announcements(
            ticker,
            start_date=start_date,
            end_date=end_date,
            category=category,
            keyword=keyword,
        )
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

    metadata = {k: v for k, v in announcement.items() if k != "raw"}
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
        ak = load_akshare_provider()
        rows = _load_akshare_financial_rows(ak, company.ticker)
    except Exception as exc:
        raise HTTPException(503, str(exc)) from exc

    upserted = 0
    metric_labels = {
        "Revenues": "营业总收入",
        "NetIncomeLoss": "净利润",
        "OperatingIncomeLoss": "营业利润",
        "Assets": "资产总计",
        "Liabilities": "负债合计",
        "OperatingCashFlow": "经营活动产生的现金流量净额",
    }
    for row in rows:
        period = _report_period_from_row(row, filing.fiscal_year)
        if req.fiscal_year and str(req.fiscal_year) not in period:
            continue
        for metric, label in metric_labels.items():
            value = normalize_financial_value(row.get(label))
            if value is None:
                continue
            _upsert_financial_fact(
                db,
                filing.id,
                metric=metric,
                label=label,
                value=value,
                period=period,
                source="akshare",
                evidence=f"{company.ticker} {period} {label}",
            )
            upserted += 1
    db.commit()
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
        "close": ("收盘", "CNY"),
        "open": ("开盘", "CNY"),
        "high": ("最高", "CNY"),
        "low": ("最低", "CNY"),
        "volume": ("成交量", "shares"),
        "amount": ("成交额", "CNY"),
    }
    upserted = 0
    for metric, (label, unit) in metric_labels.items():
        value = normalize_financial_value(row.get(label))
        if value is None:
            continue
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
            text = load_filing_text(doc.stored_path)
            db.query(FilingSectionModel).filter(FilingSectionModel.filing_id == filing.id).delete()
            for section in parse_10k_sections(text):
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
    _, workspace = ws
    try:
        return run_finance_agent(
            db=db,
            workspace_id=workspace.id,
            company_ticker=req.company_ticker,
            filing_id=req.filing_id,
            question=req.question,
            mode=req.mode,
        )
    except Exception as exc:
        raise HTTPException(500, f"Agent 分析失败: {exc}") from exc


@router.post("/evaluations/run", response_model=FinanceEvaluationResultResponse)
def run_eval(
    req: FinanceEvaluationRunRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    result = run_finance_evaluation(db, workspace.id, req.dataset_source, req.strategy)
    return result


@router.get("/evaluations/results", response_model=list[FinanceEvaluationResultResponse])
def list_eval_results(
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
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


# ── Dataset endpoints ──────────────────────────────────────

@router.get("/datasets", response_model=list[EvalDatasetResponse])
def list_datasets(
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
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
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
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


@router.post("/datasets/build/sec-10k")
def build_sec_10k_dataset(
    req: EvalDatasetBuildRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    ds = _ensure_dataset(db, workspace.id, "sec_10k", "sec_edgar",
        version=_next_version(db, "sec_10k"),
        description=f"SEC EDGAR 10-K 基准库，{len(req.tickers)} 家公司各最近 {req.latest_years} 份",
        source_url="https://www.sec.gov/edgar", license_note="Public domain (SEC EDGAR)")
    return generate_sec_10k_cases(db, ds, req.tickers, req.latest_years)


@router.post("/datasets/import/financebench")
def import_financebench_dataset(
    req: EvalDatasetImportRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    ds = _ensure_dataset(db, workspace.id, "financebench_sample_all", "financebench",
        version=_next_version(db, "financebench_sample_all"),
        description="FinanceBench (HuggingFace PatronusAI/financebench), 150 rows",
        source_url="https://huggingface.co/datasets/PatronusAI/financebench", license_note="Apache 2.0")
    return import_financebench(db, ds)


@router.post("/datasets/import/finqa")
def import_finqa_dataset(
    req: EvalDatasetImportRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    split = req.subset or "train"
    ds = _ensure_dataset(db, workspace.id, "finqa_sample", "finqa",
        version=_next_version(db, "finqa_sample"),
        description=f"FinQA public sample ({split})",
        source_url="https://huggingface.co/datasets/ibm-research/finqa", license_note="Public academic benchmark source")
    return import_finqa(db, ds, split=split, limit=req.limit)


@router.post("/datasets/import/tatqa")
def import_tatqa_dataset(
    req: EvalDatasetImportRequest,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    split = req.subset or "train"
    ds = _ensure_dataset(db, workspace.id, "tatqa_sample", "tatqa",
        version=_next_version(db, "tatqa_sample"),
        description=f"TAT-QA public sample ({split})",
        source_url="https://huggingface.co/datasets/next-tat/TAT-QA", license_note="Public academic benchmark source")
    return import_tatqa(db, ds, split=split, limit=req.limit)


@router.post("/datasets/build/custom-10k")
def build_custom_10k_dataset(
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    ds = _ensure_dataset(db, workspace.id, "custom_10k", "custom",
        version=_next_version(db, "custom_10k"),
        description="自建 10-K 评估用例，基于已导入 filing 的 sections + facts 模板生成")
    return generate_custom_10k_cases(db, ds)


@router.post("/datasets/{dataset_id}/freeze")
def freeze_dataset_endpoint(
    dataset_id: int,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
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
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_workspace),
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


def _ensure_company(db: Session, workspace_id: int, ticker: str) -> CompanyModel:
    existing = (
        db.query(CompanyModel)
        .filter(CompanyModel.workspace_id == workspace_id, CompanyModel.ticker == ticker.upper())
        .first()
    )
    if existing:
        return existing
    resolved = resolve_ticker(ticker)
    company = CompanyModel(
        workspace_id=workspace_id,
        ticker=resolved["ticker"],
        name=resolved["name"],
        cik=resolved["cik"],
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


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
    fn = getattr(ak, "stock_zh_a_hist", None)
    if not fn:
        raise RuntimeError("akshare 缺少 stock_zh_a_hist 接口")
    frame = fn(symbol=ticker, period="daily", adjust="")
    if hasattr(frame, "to_dict"):
        return frame.to_dict(orient="records")
    return []


def _filing_response(filing: FilingModel) -> FilingResponse:
    response = FilingResponse.model_validate(filing)
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
