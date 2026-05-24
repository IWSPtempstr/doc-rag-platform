from app.routers.finance import (
    _build_connector_status_catalog,
    _extract_ashare_financial_facts,
    _filing_response,
    _json_safe,
    _load_akshare_market_rows,
    _next_daily_run_at,
)
from datetime import datetime, timezone
from app.models import CompanyModel, DocumentModel, FilingModel


def test_connector_status_catalog_contains_ashare_finance_sources():
    rows = _build_connector_status_catalog()
    names = {row["name"] for row in rows}

    assert {"cninfo", "akshare", "tushare", "ashare_mcp", "chroma"}.issubset(names)
    assert all(row["capabilities"] for row in rows)


def test_extract_ashare_financial_facts_normalizes_core_metrics():
    rows = [
        {
            "报告日": "2023-12-31",
            "营业总收入": "1500",
            "净利润": "300",
            "资产总计": "5000",
        }
    ]

    facts = _extract_ashare_financial_facts(rows, fiscal_year=2023, ticker="600519")
    by_metric = {fact["metric"]: fact for fact in facts}

    assert by_metric["Revenues"]["value"] == 1500.0
    assert by_metric["NetIncomeLoss"]["value"] == 300.0
    assert by_metric["Assets"]["period"] == "2023-12-31"
    assert by_metric["Revenues"]["source"] == "akshare"


def test_next_daily_run_at_is_scheduled_for_three_am_local_time():
    next_run = _next_daily_run_at(hour=3, utc_offset_hours=8)

    assert next_run.hour == 3
    assert next_run.tzinfo is not None


def test_json_safe_converts_datetime_inside_metadata():
    payload = _json_safe({
        "published_at": datetime(2026, 3, 31, 16, 0, tzinfo=timezone.utc),
        "nested": [{"filed_at": datetime(2026, 4, 1, tzinfo=timezone.utc)}],
    })

    assert payload["published_at"] == "2026-03-31T16:00:00+00:00"
    assert payload["nested"][0]["filed_at"] == "2026-04-01T00:00:00+00:00"


def test_akshare_market_rows_falls_back_to_spot_when_hist_fails():
    class FakeFrame:
        def __init__(self, rows):
            self.rows = rows

        def to_dict(self, orient):
            assert orient == "records"
            return self.rows

    class FakeAk:
        def stock_zh_a_hist(self, **kwargs):
            raise RuntimeError("remote closed")

        def stock_zh_a_spot_em(self):
            return FakeFrame([
                {"代码": "000001", "最新价": "10.5"},
                {"代码": "000725", "最新价": "4.12", "今开": "4.00", "最高": "4.20", "最低": "3.98", "成交量": "100", "成交额": "412"},
            ])

    rows = _load_akshare_market_rows(FakeAk(), "000725")

    assert rows[0]["收盘"] == "4.12"
    assert rows[0]["开盘"] == "4.00"
    assert rows[0]["source_fallback"] == "stock_zh_a_spot_em"


def test_filing_response_serializes_relationship_summaries():
    company = CompanyModel(id=1, ticker="000725", name="京东方A", cik="-", workspace_id=1)
    document = DocumentModel(id=2, filename="annual.pdf", stored_path="/tmp/annual.pdf", status="pending", chunk_count=0)
    filing = FilingModel(
        id=3,
        workspace_id=1,
        company_id=1,
        document_id=2,
        filing_type="annual_report",
        fiscal_year=2025,
        status="queued",
        created_at=datetime(2026, 5, 24, tzinfo=timezone.utc),
        company=company,
        document=document,
    )

    response = _filing_response(filing)

    assert response.company["ticker"] == "000725"
    assert response.document["filename"] == "annual.pdf"
