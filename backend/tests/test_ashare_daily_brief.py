from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import CompanyModel, DailyBriefModel, FilingModel, FinancialFactModel, MarketFactModel, UserModel, UserWatchlistModel, WorkspaceModel
from app.services.ashare_daily_brief import build_daily_brief_payload, get_or_create_daily_brief


def _db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(WorkspaceModel(id=1, name="A股研究", slug="ashare"))
    db.add(UserModel(id=1, email="u@example.com", name="User", password_hash="x"))
    for idx, ticker in enumerate(["600519", "000001", "300750", "601318"], start=1):
        db.add(CompanyModel(id=idx, workspace_id=1, ticker=ticker, name=f"公司{ticker}", exchange="A-share"))
    db.commit()
    return db


def _hot_rows():
    return [
        {"ticker": "600519", "name": "贵州茅台", "heat_score": 100, "rank": 1, "source": "akshare_hot_rank"},
        {"ticker": "000001", "name": "平安银行", "heat_score": 90, "rank": 2, "source": "akshare_hot_rank"},
        {"ticker": "300750", "name": "宁德时代", "heat_score": 80, "rank": 3, "source": "akshare_hot_rank"},
    ]


def test_daily_brief_uses_hot_top20_when_user_has_no_watchlist():
    db = _db_session()

    payload = build_daily_brief_payload(db, workspace_id=1, user_id=1, trade_date="2026-05-23", hot_provider=_hot_rows)

    assert [item["ticker"] for item in payload["items"]] == ["600519", "000001", "300750"]
    assert {item["section"] for item in payload["items"]} == {"hot_top20"}
    assert payload["metadata"]["watchlist_count"] == 0
    assert payload["items"][0]["coverage_tags"] == ["仅热度信号", "缺少基本面验证"]


def test_daily_brief_marks_existing_filing_and_financial_facts():
    db = _db_session()
    filing = FilingModel(workspace_id=1, company_id=1, filing_type="annual_report", fiscal_year=2023, status="imported")
    db.add(filing)
    db.flush()
    db.add(FinancialFactModel(filing_id=filing.id, metric="Revenues", label="营业总收入", value=100.0, unit="CNY", source="akshare"))
    db.commit()

    payload = build_daily_brief_payload(db, workspace_id=1, user_id=1, trade_date="2026-05-23", hot_provider=_hot_rows)

    first = payload["items"][0]
    assert first["ticker"] == "600519"
    assert "已有关联公告" in first["coverage_tags"]
    assert "已有财务事实" in first["coverage_tags"]
    assert "缺少基本面验证" not in first["coverage_tags"]


def test_daily_brief_orders_watchlist_before_hot_top20_and_deduplicates():
    db = _db_session()
    db.add(UserWatchlistModel(user_id=1, workspace_id=1, ticker="300750", priority=1))
    db.add(UserWatchlistModel(user_id=1, workspace_id=1, ticker="601318", priority=2))
    db.commit()

    payload = build_daily_brief_payload(db, workspace_id=1, user_id=1, trade_date="2026-05-23", hot_provider=_hot_rows)

    assert [item["ticker"] for item in payload["items"]] == ["300750", "601318", "600519", "000001"]
    assert [item["section"] for item in payload["items"][:2]] == ["watchlist", "watchlist"]
    assert payload["metadata"]["hot_count"] == 2


def test_daily_brief_falls_back_to_market_facts_when_hot_provider_fails():
    db = _db_session()
    for ticker, amount in [("000001", 1000), ("600519", 2000), ("300750", 1500)]:
        company = db.query(CompanyModel).filter(CompanyModel.ticker == ticker).first()
        db.add(MarketFactModel(
            workspace_id=1,
            company_id=company.id,
            ticker=ticker,
            trade_date="2026-05-23",
            metric="amount",
            label="成交额",
            value=amount,
            unit="CNY",
        ))
    db.commit()

    def failing_provider():
        raise RuntimeError("hot rank unavailable")

    payload = build_daily_brief_payload(db, workspace_id=1, user_id=1, trade_date="2026-05-23", hot_provider=failing_provider)

    assert [item["ticker"] for item in payload["items"]] == ["600519", "300750", "000001"]
    assert payload["metadata"]["failure_reason"] == "hot rank unavailable"
    assert payload["metadata"]["hot_source"] == "market_fact_fallback"


def test_failed_empty_daily_brief_is_regenerated_when_provider_recovers():
    db = _db_session()
    db.add(DailyBriefModel(
        workspace_id=1,
        user_id=1,
        trade_date="2026-05-23",
        status="generated",
        summary="今日未设置关注公司，展示市场热度最高的 0 家 A 股公司。",
        items=[],
        metadata_json={
            "watchlist_count": 0,
            "hot_count": 0,
            "hot_source": "market_fact_fallback",
            "failure_reason": "akshare 未安装，无法同步 A 股结构化事实",
        },
    ))
    db.commit()

    payload = get_or_create_daily_brief(
        db,
        workspace_id=1,
        user_id=1,
        trade_date="2026-05-23",
        hot_provider=_hot_rows,
    )

    assert [item["ticker"] for item in payload["items"]] == ["600519", "000001", "300750"]
    assert payload["metadata"]["hot_count"] == 3
    assert payload["metadata"]["failure_reason"] is None
