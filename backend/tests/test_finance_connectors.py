from app.routers.finance import (
    _build_connector_status_catalog,
    _extract_ashare_financial_facts,
    _next_daily_run_at,
)


def test_connector_status_catalog_contains_public_finance_sources():
    rows = _build_connector_status_catalog()
    names = {row["name"] for row in rows}

    assert {"sec_edgar", "cninfo", "akshare", "finqa", "tatqa"}.issubset(names)
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
