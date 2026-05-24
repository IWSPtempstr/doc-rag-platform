import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    AgentRunModel,
    CompanyModel,
    DocumentModel,
    EvalCaseModel,
    EvalDatasetModel,
    FilingModel,
    FilingSectionModel,
    FinancialFactModel,
    MarketFactModel,
)
from app.routers.finance import _delete_company_graph, _delete_filing_graph


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_delete_filing_graph_removes_unique_document_and_gold_links(monkeypatch):
    db = _session()
    fd, path = tempfile.mkstemp()
    os.close(fd)
    doc = DocumentModel(filename="a.pdf", stored_path=path, content_type="application/pdf")
    company = CompanyModel(workspace_id=1, ticker="AAPL", name="Apple")
    db.add_all([doc, company])
    db.flush()
    filing = FilingModel(workspace_id=1, company_id=company.id, document_id=doc.id, filing_type="annual_report", fiscal_year=2023)
    db.add(filing)
    db.flush()
    db.add(FilingSectionModel(filing_id=filing.id, item_code="1A", title="Risk"))
    db.add(FinancialFactModel(filing_id=filing.id, metric="Revenues", label="Revenue", value=100.0))
    dataset = EvalDatasetModel(workspace_id=1, name="custom_10k", source="custom")
    db.add(dataset)
    db.flush()
    db.add(EvalCaseModel(dataset_id=dataset.id, question="q", gold_filing_id=filing.id, gold_document_id=doc.id))
    deleted_docs = []
    monkeypatch.setattr("app.routers.finance.chroma_delete", lambda document_id: deleted_docs.append(document_id))

    result = _delete_filing_graph(db, filing)
    db.commit()

    assert result["filings_deleted"] == 1
    assert result["documents_deleted"] == 1
    assert deleted_docs == [doc.id]
    assert db.query(FilingModel).count() == 0
    assert db.query(FilingSectionModel).count() == 0
    assert db.query(FinancialFactModel).count() == 0
    assert db.query(DocumentModel).count() == 0
    case = db.query(EvalCaseModel).first()
    assert case.gold_filing_id is None
    assert case.gold_document_id is None
    assert not os.path.exists(path)


def test_delete_company_graph_removes_finance_children_and_nulls_agent_runs(monkeypatch):
    db = _session()
    doc = DocumentModel(filename="a.pdf", stored_path="/tmp/missing.pdf", content_type="application/pdf")
    company = CompanyModel(workspace_id=1, ticker="600519", name="Kweichow Moutai")
    db.add_all([doc, company])
    db.flush()
    filing = FilingModel(workspace_id=1, company_id=company.id, document_id=doc.id, filing_type="annual_report", fiscal_year=2023)
    db.add(filing)
    db.flush()
    db.add(MarketFactModel(workspace_id=1, company_id=company.id, ticker="600519", trade_date="2026-05-22", metric="close", label="收盘"))
    db.add(AgentRunModel(workspace_id=1, company_id=company.id, filing_id=filing.id, question="q"))
    monkeypatch.setattr("app.routers.finance.chroma_delete", lambda document_id: None)

    result = _delete_company_graph(db, company)
    db.commit()

    assert result["companies_deleted"] == 1
    assert result["filings_deleted"] == 1
    assert result["documents_deleted"] == 1
    assert db.query(CompanyModel).count() == 0
    assert db.query(FilingModel).count() == 0
    assert db.query(MarketFactModel).count() == 0
    run = db.query(AgentRunModel).first()
    assert run.company_id is None
    assert run.filing_id is None
