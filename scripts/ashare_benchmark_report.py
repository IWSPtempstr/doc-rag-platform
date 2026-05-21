#!/usr/bin/env python
"""Generate A-share coverage and evaluation-readiness report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")

from app.db import SessionLocal  # noqa: E402
from app.models import CompanyModel, FilingModel, FinancialFactModel, MarketFactModel  # noqa: E402
from app.services.vector_store import count_chunks  # noqa: E402


def build_report(workspace_id: int) -> dict:
    db = SessionLocal()
    try:
        companies = (
            db.query(CompanyModel)
            .filter(CompanyModel.workspace_id == workspace_id)
            .all()
        )
        rows = []
        for company in companies:
            if not _is_ashare(company):
                continue
            filings = db.query(FilingModel).filter(FilingModel.company_id == company.id).all()
            filing_rows = []
            for filing in filings:
                metadata = filing.metadata_json or {}
                if metadata.get("market") != "CN" and filing.filing_type not in {"annual_report", "semi_annual_report", "quarterly_report"}:
                    continue
                financial_fact_count = db.query(FinancialFactModel).filter(FinancialFactModel.filing_id == filing.id).count()
                chunk_count = count_chunks(filing.document_id) if filing.document_id else 0
                filing_rows.append({
                    "filing_id": filing.id,
                    "filing_type": filing.filing_type,
                    "fiscal_year": filing.fiscal_year,
                    "document_id": filing.document_id,
                    "document_status": filing.document.status if filing.document else None,
                    "chunk_count": chunk_count,
                    "section_count": len(filing.sections),
                    "financial_fact_count": financial_fact_count,
                    "index_ready": bool(filing.document_id and chunk_count > 0),
                })
            market_fact_count = db.query(MarketFactModel).filter(MarketFactModel.company_id == company.id).count()
            rows.append({
                "ticker": company.ticker,
                "name": company.name,
                "exchange": company.exchange,
                "filing_count": len(filing_rows),
                "market_fact_count": market_fact_count,
                "filings": filing_rows,
            })
        return {"workspace_id": workspace_id, "companies": rows}
    finally:
        db.close()


def print_markdown(report: dict) -> None:
    print("# A-share Finance Workbench Report")
    print()
    print(f"Workspace: `{report['workspace_id']}`")
    print()
    print("## Coverage")
    for company in report["companies"]:
        print(f"- `{company['ticker']}` {company['name']} ({company.get('exchange') or '-'})")
        print(f"  filings={company['filing_count']}, market_facts={company['market_fact_count']}")
        for filing in company["filings"]:
            print(
                "  - "
                f"filing #{filing['filing_id']} {filing['filing_type']} {filing['fiscal_year']}: "
                f"document={filing['document_id']} status={filing['document_status']} "
                f"chunks={filing['chunk_count']} sections={filing['section_count']} "
                f"facts={filing['financial_fact_count']} index_ready={filing['index_ready']}"
            )


def _is_ashare(company: CompanyModel) -> bool:
    return company.exchange in {"SSE", "SZSE", "BSE"} or (company.ticker or "").isdigit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", type=int, default=1)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "ashare_benchmark_report.md")
    args = parser.parse_args()
    report = build_report(args.workspace_id)
    if args.format == "json":
        text = json.dumps(report, ensure_ascii=False, indent=2)
    else:
        import io
        old_stdout = sys.stdout
        buffer = io.StringIO()
        sys.stdout = buffer
        try:
            print_markdown(report)
        finally:
            sys.stdout = old_stdout
        text = buffer.getvalue()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(str(args.output))


if __name__ == "__main__":
    main()
