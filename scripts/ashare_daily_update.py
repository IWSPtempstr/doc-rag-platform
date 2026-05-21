#!/usr/bin/env python
"""Daily A-share public-data update.

Imports newly published CNINFO annual reports for tracked A-share companies and
syncs latest market facts when the optional akshare package is available.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")

from app.config import config  # noqa: E402
from app.db import SessionLocal, ensure_sqlite_schema  # noqa: E402
from app.models import CompanyModel, DocumentModel, FilingModel, JobModel, MarketFactModel  # noqa: E402
from app.redis_client import enqueue_job  # noqa: E402
from app.services.ashare_connector import download_announcement, search_announcements  # noqa: E402
from app.services.ashare_structured_provider import load_akshare_provider, normalize_financial_value  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", type=int, default=int(os.getenv("DEFAULT_WORKSPACE_ID", "1")))
    parser.add_argument("--tickers", nargs="*", default=None)
    parser.add_argument("--lookback-days", type=int, default=1)
    parser.add_argument("--sync-market", action="store_true")
    args = parser.parse_args()

    ensure_sqlite_schema()
    summary = run_update(args.workspace_id, args.tickers, args.lookback_days, args.sync_market)
    out_dir = Path(config.PUBLIC_DATA_DIR) / "ashare" / "daily_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def run_update(workspace_id: int, tickers: list[str] | None, lookback_days: int, sync_market: bool) -> dict:
    db = SessionLocal()
    try:
        tracked = tickers or _tracked_ashare_tickers(db, workspace_id)
        start = (date.today() - timedelta(days=lookback_days)).isoformat()
        end = date.today().isoformat()
        result = {
            "workspace_id": workspace_id,
            "date_range": [start, end],
            "tickers": tracked,
            "announcements_seen": 0,
            "filings_imported": 0,
            "jobs_queued": 0,
            "market_facts_upserted": 0,
            "errors": [],
        }
        for ticker in tracked:
            try:
                rows = search_announcements(ticker, start_date=start, end_date=end, keyword="年度报告", page_size=20)
            except Exception as exc:
                result["errors"].append({"ticker": ticker, "stage": "search", "error": str(exc)})
                continue
            result["announcements_seen"] += len(rows)
            company = _ensure_company(db, workspace_id, ticker, rows[0]["company_name"] if rows else ticker)
            for row in rows:
                if row.get("filing_type") != "annual_report":
                    continue
                if _filing_exists(db, workspace_id, row.get("announcement_id")):
                    continue
                try:
                    downloaded = download_announcement(row)
                    doc = DocumentModel(
                        filename=downloaded["filename"],
                        stored_path=downloaded["stored_path"],
                        content_type=downloaded["content_type"],
                        size_bytes=downloaded["size_bytes"],
                        status="pending",
                        tags=f"finance,ashare,{ticker},{row['filing_type']},{row['fiscal_year']}",
                    )
                    db.add(doc)
                    db.flush()
                    filing = FilingModel(
                        workspace_id=workspace_id,
                        company_id=company.id,
                        document_id=doc.id,
                        accession_number=row.get("announcement_id"),
                        filing_type=row.get("filing_type") or "annual_report",
                        fiscal_year=row.get("fiscal_year"),
                        filed_at=row.get("published_at"),
                        source_url=downloaded["source_url"],
                        status="queued",
                        metadata_json={k: v for k, v in row.items() if k != "raw"},
                    )
                    db.add(filing)
                    job = JobModel(document_id=doc.id, type="ingestion", status="pending")
                    db.add(job)
                    db.commit()
                    try:
                        enqueue_job(job.id, doc.id, doc.stored_path, doc.content_type)
                        result["jobs_queued"] += 1
                    except Exception as exc:
                        result["errors"].append({"ticker": ticker, "stage": "enqueue", "error": str(exc)})
                    result["filings_imported"] += 1
                except Exception as exc:
                    db.rollback()
                    result["errors"].append({"ticker": ticker, "stage": "import", "error": str(exc)})
            if sync_market:
                try:
                    result["market_facts_upserted"] += _sync_latest_market_facts(db, workspace_id, company)
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    result["errors"].append({"ticker": ticker, "stage": "market", "error": str(exc)})
        return result
    finally:
        db.close()


def _tracked_ashare_tickers(db, workspace_id: int) -> list[str]:
    rows = db.query(CompanyModel).filter(CompanyModel.workspace_id == workspace_id).all()
    tickers = [
        row.ticker for row in rows
        if row.exchange in {"SSE", "SZSE", "BSE"} or re.fullmatch(r"\d{6}", row.ticker or "")
    ]
    return sorted(set(tickers))


def _ensure_company(db, workspace_id: int, ticker: str, name: str) -> CompanyModel:
    company = (
        db.query(CompanyModel)
        .filter(CompanyModel.workspace_id == workspace_id, CompanyModel.ticker == ticker)
        .first()
    )
    if company:
        if company.name == company.ticker and name:
            company.name = name
        return company
    exchange = "SSE" if ticker.startswith(("5", "6", "9")) or ticker.startswith("688") else "SZSE"
    company = CompanyModel(workspace_id=workspace_id, ticker=ticker, name=name or ticker, exchange=exchange, industry="A-share")
    db.add(company)
    db.flush()
    return company


def _filing_exists(db, workspace_id: int, announcement_id: str | None) -> bool:
    if not announcement_id:
        return False
    return (
        db.query(FilingModel)
        .filter(FilingModel.workspace_id == workspace_id, FilingModel.accession_number == announcement_id)
        .first()
        is not None
    )


def _sync_latest_market_facts(db, workspace_id: int, company: CompanyModel) -> int:
    ak = load_akshare_provider()
    frame = ak.stock_zh_a_hist(symbol=company.ticker, period="daily", adjust="")
    rows = frame.to_dict(orient="records") if hasattr(frame, "to_dict") else []
    if not rows:
        return 0
    row = rows[-1]
    trade_date = str(row.get("日期") or row.get("date") or date.today().isoformat())
    upserted = 0
    for metric, (label, unit) in {
        "open": ("开盘", "CNY"),
        "close": ("收盘", "CNY"),
        "high": ("最高", "CNY"),
        "low": ("最低", "CNY"),
        "volume": ("成交量", "shares"),
        "amount": ("成交额", "CNY"),
    }.items():
        value = normalize_financial_value(row.get(label))
        if value is None:
            continue
        fact = (
            db.query(MarketFactModel)
            .filter(
                MarketFactModel.workspace_id == workspace_id,
                MarketFactModel.company_id == company.id,
                MarketFactModel.trade_date == trade_date,
                MarketFactModel.metric == metric,
            )
            .first()
        )
        if not fact:
            fact = MarketFactModel(
                workspace_id=workspace_id,
                company_id=company.id,
                ticker=company.ticker,
                trade_date=trade_date,
                metric=metric,
                label=label,
            )
            db.add(fact)
        fact.value = value
        fact.unit = unit
        fact.source = "akshare"
        fact.confidence = 1.0
        fact.metadata_json = {"market": "CN"}
        upserted += 1
    return upserted


if __name__ == "__main__":
    main()
