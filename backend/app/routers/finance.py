"""Finance workbench APIs."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import config
from app.db import get_db
from app.models import (
    CompanyModel,
    DocumentModel,
    FilingModel,
    FilingSectionModel,
    JobModel,
    MembershipModel,
    UserModel,
    WorkspaceModel,
)
from app.redis_client import enqueue_job
from app.routers.auth import get_current_user, get_current_workspace
from app.schemas import (
    CompanyCreateRequest,
    CompanyResponse,
    FilingBindDocumentRequest,
    FilingImportRequest,
    FilingResponse,
    FilingSectionResponse,
    FinanceAgentQueryRequest,
    FinanceAgentQueryResponse,
    FinanceEvaluationResultResponse,
    FinanceEvaluationRunRequest,
)
from app.services.finance_agent import run_finance_agent
from app.services.finance_evaluation import run_finance_evaluation
from app.services.finance_sections import parse_10k_sections
from app.services.sec_connector import download_filing_document, find_10k_filing, load_filing_text, parse_sec_date, resolve_ticker

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
        downloaded = download_filing_document(filing_info, config.UPLOAD_DIR)
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


def _get_company_or_404(db: Session, workspace_id: int, ticker: str) -> CompanyModel:
    company = (
        db.query(CompanyModel)
        .filter(CompanyModel.workspace_id == workspace_id, CompanyModel.ticker == ticker.upper())
        .first()
    )
    if not company:
        raise HTTPException(404, "公司不存在")
    return company


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
