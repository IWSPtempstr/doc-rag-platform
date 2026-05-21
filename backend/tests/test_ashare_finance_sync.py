from app.routers.finance import _report_period_from_row


def test_report_period_from_akshare_report_date():
    row = {"报告日": "2023-12-31", "营业总收入": "100"}

    assert _report_period_from_row(row, fallback_year=2023) == "2023-12-31"


def test_report_period_falls_back_to_fiscal_year():
    assert _report_period_from_row({}, fallback_year=2022) == "2022"
