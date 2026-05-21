"""SEC EDGAR connector for 10-K imports."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

import requests

from app.config import config

SEC_BASE = "https://www.sec.gov"
DATA_BASE = "https://data.sec.gov"


def _headers() -> dict[str, str]:
    return {"User-Agent": config.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


def _cik10(cik: str | int) -> str:
    return str(cik).strip().zfill(10)


def resolve_ticker(ticker: str) -> dict[str, Any]:
    resp = requests.get(f"{SEC_BASE}/files/company_tickers.json", headers=_headers(), timeout=30)
    resp.raise_for_status()
    rows = resp.json().values()
    wanted = ticker.upper()
    for row in rows:
        if row.get("ticker", "").upper() == wanted:
            return {
                "ticker": wanted,
                "cik": _cik10(row["cik_str"]),
                "name": row.get("title") or wanted,
            }
    raise ValueError(f"SEC ticker not found: {ticker}")


def list_company_filings(cik: str) -> dict[str, Any]:
    resp = requests.get(f"{DATA_BASE}/submissions/CIK{_cik10(cik)}.json", headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def find_10k_filing(ticker: str, year: int | None = None, accession_number: str | None = None) -> dict[str, Any]:
    company = resolve_ticker(ticker)
    submissions = list_company_filings(company["cik"])
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    primary_docs = recent.get("primaryDocument", [])

    candidates = []
    for idx, form in enumerate(forms):
        if form != "10-K":
            continue
        accession = accessions[idx]
        report_date = report_dates[idx] if idx < len(report_dates) else ""
        fiscal_year = _year_from_date(report_date) or _year_from_date(filing_dates[idx])
        if accession_number and accession != accession_number:
            continue
        if year and fiscal_year != year:
            continue
        candidates.append(
            {
                **company,
                "accession_number": accession,
                "filing_date": filing_dates[idx] if idx < len(filing_dates) else None,
                "report_date": report_date,
                "fiscal_year": fiscal_year,
                "primary_document": primary_docs[idx] if idx < len(primary_docs) else "",
            }
        )

    if not candidates:
        raise ValueError(f"No 10-K filing found for {ticker.upper()} year={year or 'latest'}")
    return candidates[0]


def download_filing_document(filing: dict[str, Any], output_dir: str) -> dict[str, Any]:
    accession_dir = filing["accession_number"].replace("-", "")
    primary = filing["primary_document"]
    url = f"{SEC_BASE}/Archives/edgar/data/{int(filing['cik'])}/{accession_dir}/{primary}"
    resp = requests.get(url, headers=_headers(), timeout=60)
    resp.raise_for_status()

    os.makedirs(output_dir, exist_ok=True)
    safe_ticker = re.sub(r"[^A-Z0-9_-]+", "_", filing["ticker"].upper())
    ext = Path(primary).suffix or ".html"
    filename = f"{safe_ticker}_{filing['fiscal_year']}_10K{ext}"
    stored_path = os.path.join(output_dir, filename)
    with open(stored_path, "wb") as f:
        f.write(resp.content)

    return {
        "source_url": url,
        "stored_path": stored_path,
        "filename": filename,
        "content_type": "html" if ext.lower() in (".htm", ".html") else ext.lstrip("."),
        "size_bytes": len(resp.content),
    }


def html_to_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw_html)
    text = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</tr>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_filing_text(path: str) -> str:
    ext = Path(path).suffix.lower()
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8", errors="ignore")
    if ext in (".htm", ".html"):
        return html_to_text(text)
    return text


def parse_sec_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _year_from_date(value: str | None) -> int | None:
    dt = parse_sec_date(value)
    return dt.year if dt else None


# ── XBRL Company Facts ─────────────────────────────────────

def fetch_companyfacts(cik: str) -> dict[str, Any]:
    resp = requests.get(
        f"{DATA_BASE}/api/xbrl/companyfacts/CIK{_cik10(cik)}.json",
        headers=_headers(), timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def extract_usd_facts(cik: str) -> dict[str, list[dict[str, Any]]]:
    """Extract USD-denominated US-GAAP facts per fiscal year for standard metrics."""
    raw = fetch_companyfacts(cik)
    us_gaap = raw.get("facts", {}).get("us-gaap", {}) or raw.get("facts", {}).get("ifrs-full", {})

    metric_tags = {
        "Revenues": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"],
        "NetIncomeLoss": ["NetIncomeLoss", "ProfitLoss"],
        "OperatingIncomeLoss": ["OperatingIncomeLoss"],
        "Assets": ["Assets"],
        "Liabilities": ["Liabilities"],
        "NetCashProvidedByUsedInOperatingActivities": ["NetCashProvidedByUsedInOperatingActivities"],
    }
    result: dict[str, list[dict]] = {}
    for metric_group, tags in metric_tags.items():
        for tag in tags:
            tag_data = us_gaap.get(tag, {})
            entries = tag_data.get("units", {}).get("USD", [])
            if not entries:
                continue
            result[metric_group] = [
                {"fiscal_year": e.get("fy"), "value": e.get("val"), "tag": tag, "filed": e.get("filed")}
                for e in entries if e.get("fp") in ("FY", "Q4")
            ]
            break
    return result


def normalize_facts_for_filing(facts: dict[str, list[dict]], fiscal_year: int) -> dict[str, Any]:
    """Pick the most recently-reported value per metric for a given fiscal year."""
    result: dict[str, Any] = {}
    for metric, entries in facts.items():
        candidates = [e for e in entries if e.get("fiscal_year") == fiscal_year]
        if not candidates:
            continue
        candidates.sort(key=lambda e: e.get("filed", ""), reverse=True)
        result[metric] = {"value": candidates[0]["value"], "tag": candidates[0]["tag"], "fiscal_year": candidates[0]["fiscal_year"]}
    return result

