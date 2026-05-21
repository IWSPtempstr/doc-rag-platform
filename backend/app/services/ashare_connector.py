"""A-share disclosure connector.

The connector normalizes public CNINFO announcements into the same
Document/Filing ingestion pipeline used by SEC filings.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import config

CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_BASE = "http://static.cninfo.com.cn"

ANNUAL_REPORT_KEYWORDS = ("年度报告", "年报")
DISCLOSURE_TYPE_MAP = {
    "半年度报告": "semi_annual_report",
    "年度报告": "annual_report",
    "季度报告": "quarterly_report",
    "公告": "announcement",
    "问询函": "inquiry_letter",
    "回复": "inquiry_reply",
    "处罚": "penalty",
    "分红": "dividend",
    "回购": "buyback",
    "权益变动": "shareholder_change",
}


def infer_ashare_exchange(ticker: str) -> str:
    code = re.sub(r"\D", "", ticker or "")
    if code.startswith(("5", "6", "9")) or code.startswith("688"):
        return "SSE"
    if code.startswith(("0", "2", "3")):
        return "SZSE"
    if code.startswith(("4", "8")):
        return "BSE"
    return "CN"


def infer_cninfo_org_id(ticker: str) -> str:
    code = re.sub(r"\D", "", ticker or "").zfill(6)
    seven_digit = code.zfill(7)
    if infer_ashare_exchange(code) == "SSE":
        return f"gssh{seven_digit}"
    return f"gssz{seven_digit}"


def normalize_cninfo_announcement(row: dict[str, Any]) -> dict[str, Any]:
    title = _clean_html(row.get("announcementTitle") or "")
    ticker = str(row.get("secCode") or row.get("stockCode") or "").strip()
    adjunct_url = str(row.get("adjunctUrl") or "").lstrip("/")
    published_at = _parse_cninfo_time(row.get("announcementTime"))
    filing_type = _infer_filing_type(title, row.get("columnName"))

    return {
        "market": "CN",
        "source": "cninfo",
        "ticker": ticker,
        "stock_code": ticker,
        "company_name": str(row.get("secName") or row.get("shortName") or ticker).strip(),
        "exchange": infer_ashare_exchange(ticker),
        "announcement_id": str(row.get("announcementId") or row.get("id") or "").strip(),
        "org_id": str(row.get("orgId") or infer_cninfo_org_id(ticker)),
        "announcement_title": title,
        "published_at": published_at,
        "download_url": f"{CNINFO_STATIC_BASE}/{adjunct_url}" if adjunct_url else None,
        "adjunct_url": adjunct_url,
        "disclosure_category": str(row.get("columnName") or "").strip(),
        "filing_type": filing_type,
        "fiscal_year": _extract_fiscal_year(title, published_at),
        "raw": row,
    }


def search_announcements(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
    page_size: int = 30,
) -> list[dict[str, Any]]:
    """Search CNINFO announcements and return normalized rows."""
    code = re.sub(r"\D", "", ticker)
    se_date = ""
    if start_date and end_date:
        se_date = f"{start_date}~{end_date}"
    params = {
        "stock": f"{code},{infer_cninfo_org_id(code)}" if code else "",
        "tabName": "fulltext",
        "pageSize": page_size,
        "pageNum": 1,
        "column": "szse" if infer_ashare_exchange(code) == "SZSE" else "sse",
        "category": category or ("category_ndbg_szsh" if keyword and "年度报告" in keyword else ""),
        "plate": "",
        "seDate": se_date,
        "searchkey": keyword or "",
        "secid": "",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 FinancialRAGWorkbench/0.1",
        "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
    }
    resp = requests.post(CNINFO_QUERY_URL, data=params, headers=headers, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("announcements") or []
    return [normalize_cninfo_announcement(row) for row in rows]


def get_annual_report(ticker: str, fiscal_year: int) -> dict[str, Any] | None:
    keyword = f"{fiscal_year}年年度报告"
    rows = search_announcements(ticker, keyword=keyword, page_size=20)
    annual_rows = [
        row for row in rows
        if row.get("filing_type") == "annual_report" and row.get("fiscal_year") == fiscal_year
    ]
    full_reports = [row for row in annual_rows if _is_full_annual_report(row.get("announcement_title") or "")]
    if full_reports:
        return full_reports[0]
    return annual_rows[0] if annual_rows else None


def download_announcement(announcement: dict[str, Any], output_dir: str | None = None) -> dict[str, Any]:
    url = announcement.get("download_url")
    if not url:
        raise ValueError("公告缺少 download_url")
    base_dir = output_dir or os.path.join(config.PUBLIC_DATA_DIR, "ashare", "cninfo", "filings")
    os.makedirs(base_dir, exist_ok=True)
    suffix = os.path.splitext(url.split("?")[0])[1] or ".pdf"
    filename = f"{announcement.get('stock_code')}_{announcement.get('fiscal_year')}_{announcement.get('announcement_id')}{suffix}"
    stored_path = os.path.join(base_dir, filename)

    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 FinancialRAGWorkbench/0.1"}, timeout=60)
    resp.raise_for_status()
    with open(stored_path, "wb") as fh:
        fh.write(resp.content)

    return {
        "filename": filename,
        "stored_path": stored_path,
        "content_type": "application/pdf",
        "size_bytes": os.path.getsize(stored_path),
        "source_url": url,
    }


def _infer_filing_type(title: str, category: str | None = None) -> str:
    haystack = f"{title} {category or ''}"
    for keyword, filing_type in DISCLOSURE_TYPE_MAP.items():
        if keyword in haystack:
            return filing_type
    return "announcement"


def _is_full_annual_report(title: str) -> bool:
    if "年度报告" not in title and "年报" not in title:
        return False
    excluded = ("摘要", "英文", "取消", "更正", "修订", "补充", "已取消")
    return not any(token in title for token in excluded)


def _extract_fiscal_year(title: str, published_at: datetime | None) -> int:
    match = re.search(r"(20\d{2}|19\d{2})\s*年\s*(?:年度报告|年报)", title)
    if match:
        return int(match.group(1))
    if published_at:
        return published_at.year - 1 if "年度报告" in title or "年报" in title else published_at.year
    return datetime.now(timezone.utc).year


def _parse_cninfo_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _clean_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()
