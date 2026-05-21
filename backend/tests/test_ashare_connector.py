from app.services.ashare_connector import (
    get_annual_report,
    infer_ashare_exchange,
    normalize_cninfo_announcement,
)
import app.services.ashare_connector as ashare_connector


def test_infer_ashare_exchange_from_ticker_prefix():
    assert infer_ashare_exchange("600519") == "SSE"
    assert infer_ashare_exchange("000001") == "SZSE"
    assert infer_ashare_exchange("300750") == "SZSE"
    assert infer_ashare_exchange("688981") == "SSE"


def test_normalize_cninfo_announcement_extracts_annual_report_metadata():
    row = {
        "secCode": "600519",
        "secName": "贵州茅台",
        "announcementId": "1212345678",
        "announcementTitle": "2023年年度报告",
        "announcementTime": 1711929600000,
        "adjunctUrl": "finalpage/2024-04-01/1212345678.PDF",
        "columnName": "年度报告",
    }

    item = normalize_cninfo_announcement(row)

    assert item["ticker"] == "600519"
    assert item["company_name"] == "贵州茅台"
    assert item["market"] == "CN"
    assert item["source"] == "cninfo"
    assert item["exchange"] == "SSE"
    assert item["filing_type"] == "annual_report"
    assert item["fiscal_year"] == 2023
    assert item["announcement_id"] == "1212345678"
    assert item["download_url"].endswith("/finalpage/2024-04-01/1212345678.PDF")


def test_normalize_cninfo_announcement_keeps_semi_annual_report_distinct():
    row = {
        "secCode": "000001",
        "secName": "平安银行",
        "announcementId": "semi-1",
        "announcementTitle": "2024年半年度报告",
        "announcementTime": 1722470400000,
        "adjunctUrl": "finalpage/2024-08-01/semi-1.PDF",
        "columnName": "半年度报告",
    }

    item = normalize_cninfo_announcement(row)

    assert item["filing_type"] == "semi_annual_report"


def test_get_annual_report_prefers_full_report_over_summary_and_revision(monkeypatch):
    rows = [
        {"filing_type": "annual_report", "fiscal_year": 2023, "announcement_title": "贵州茅台2023年年度报告摘要"},
        {"filing_type": "annual_report", "fiscal_year": 2023, "announcement_title": "贵州茅台2023年年度报告（英文版）"},
        {"filing_type": "annual_report", "fiscal_year": 2023, "announcement_title": "贵州茅台2023年年度报告"},
    ]
    monkeypatch.setattr(ashare_connector, "search_announcements", lambda *_args, **_kwargs: rows)

    report = get_annual_report("600519", 2023)

    assert report["announcement_title"] == "贵州茅台2023年年度报告"
