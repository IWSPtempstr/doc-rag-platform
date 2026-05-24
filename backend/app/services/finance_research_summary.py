"""Company-level research availability summary for A-share pages and agents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    CompanyModel,
    DailyBriefModel,
    DataSyncJobModel,
    FilingModel,
    FinancialFactModel,
    MarketFactModel,
    SentimentFactModel,
    UserWatchlistModel,
)


def build_company_research_summary(
    db: Session,
    workspace_id: int,
    company: CompanyModel,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Summarize what can and cannot be inferred for a company today."""
    filings = (
        db.query(FilingModel)
        .filter(FilingModel.workspace_id == workspace_id, FilingModel.company_id == company.id)
        .order_by(FilingModel.fiscal_year.desc(), FilingModel.created_at.desc())
        .all()
    )
    filing_ids = [row.id for row in filings]
    annual_reports = [row for row in filings if row.filing_type in {"annual_report", "10-K"}]
    financial_fact_count = (
        db.query(FinancialFactModel).filter(FinancialFactModel.filing_id.in_(filing_ids)).count()
        if filing_ids else 0
    )
    market_facts = (
        db.query(MarketFactModel)
        .filter(MarketFactModel.workspace_id == workspace_id, MarketFactModel.company_id == company.id)
        .order_by(MarketFactModel.trade_date.desc(), MarketFactModel.created_at.desc())
        .limit(12)
        .all()
    )
    sentiment = (
        db.query(SentimentFactModel)
        .filter(SentimentFactModel.workspace_id == workspace_id, SentimentFactModel.scope == "market")
        .order_by(SentimentFactModel.trade_date.desc(), SentimentFactModel.created_at.desc())
        .first()
    )
    watch = None
    if user_id:
        watch = (
            db.query(UserWatchlistModel)
            .filter(
                UserWatchlistModel.workspace_id == workspace_id,
                UserWatchlistModel.user_id == user_id,
                UserWatchlistModel.ticker == company.ticker,
            )
            .first()
        )

    hot_item = _latest_brief_item(db, workspace_id, company.ticker, user_id)
    heat_fact = next((row for row in market_facts if row.metric == "heat_score"), None)
    latest_market = market_facts[0] if market_facts else None
    latest_sync_failure = _latest_sync_failure(db, workspace_id)

    missing_items: list[str] = []
    failure_reasons: dict[str, str] = {}
    if not annual_reports:
        missing_items.append("missing_annual_report")
        failure_reasons["missing_annual_report"] = "filing_not_imported"
    if not financial_fact_count:
        missing_items.append("missing_financial_facts")
        failure_reasons["missing_financial_facts"] = "fact_sync_requires_filing" if not filings else "akshare_not_synced"
    if not filings:
        missing_items.append("missing_announcements")
        failure_reasons["missing_announcements"] = "cninfo_not_imported"
    if not market_facts:
        missing_items.append("missing_market_fact")
        failure_reasons["missing_market_fact"] = "market_fact_not_synced"
    if not sentiment:
        missing_items.append("missing_sentiment")
        failure_reasons["missing_sentiment"] = "sentiment_not_synced"
    if latest_sync_failure:
        failure_reasons["latest_daily_sync"] = latest_sync_failure

    available_signals = {
        "watchlisted": bool(watch),
        "watchlist_priority": watch.priority if watch else None,
        "hot_rank": hot_item.get("rank") if hot_item else None,
        "hot_source": hot_item.get("source") if hot_item else None,
        "heat_score": _first_not_none(
            heat_fact.value if heat_fact else None,
            hot_item.get("heat_score") if hot_item else None,
        ),
        "latest_market_fact": _market_fact_payload(latest_market),
        "latest_sentiment": _sentiment_payload(sentiment),
        "filing_count": len(filings),
        "annual_report_count": len(annual_reports),
        "announcement_count": len(filings),
        "financial_fact_count": financial_fact_count,
        "market_fact_count": len(market_facts),
    }

    can_infer = []
    if watch:
        can_infer.append("这家公司在你的关注列表中，应优先进入每日检查。")
    if hot_item or heat_fact:
        can_infer.append("当前可以把市场热度作为关注度变化的弱信号。")
    if sentiment:
        can_infer.append("当前可以参考市场级情绪变化，但不能替代个股公告或财务事实。")
    if financial_fact_count:
        can_infer.append("当前已有结构化财务事实，可以解释收入、利润、资产负债等基本面项目。")
    if filings:
        can_infer.append("当前已有公告或年报资产，可以做公告检索和引用解释。")

    cannot_infer = []
    if not financial_fact_count:
        cannot_infer.append("缺少结构化财务事实，不能判断收入、利润、资产负债等基本面变化。")
    if not filings:
        cannot_infer.append("缺少已导入公告/年报，不能确认今天是否存在可追溯披露变化。")
    if not sentiment:
        cannot_infer.append("缺少市场情绪事实，不能判断整体情绪是否改善或转弱。")
    if not market_facts and not hot_item:
        cannot_infer.append("缺少行情或热榜数据，不能解释市场关注度变化。")

    actions = []
    if not filings:
        actions.append({"key": "import_annual_report", "label": "导入年报", "priority": 1})
        actions.append({"key": "search_announcements", "label": "搜索公告", "priority": 2})
    if filings and not financial_fact_count:
        actions.append({"key": "sync_financial_facts", "label": "同步财务事实", "priority": 1})
    if not market_facts:
        actions.append({"key": "sync_market_facts", "label": "同步行情热度", "priority": 3})
    if not sentiment:
        actions.append({"key": "sync_market_sentiment", "label": "同步市场情绪", "priority": 4})
    actions.append({"key": "check_connectors", "label": "管理端检查数据源", "priority": 9})

    boundary = [
        "数据不足时只能解释关注度、热度、已关注状态和数据覆盖情况。",
        "不会用热度或情绪替代公告/财务事实，也不会生成买卖建议、目标价或交易信号。",
    ]
    if financial_fact_count and filings:
        boundary.insert(0, "已有公告/财务事实时，可以做可追溯的基本面解释。")

    return {
        "company": {
            "id": company.id,
            "ticker": company.ticker,
            "name": company.name,
            "market": company.exchange,
            "industry": company.industry,
            "watchlisted": bool(watch),
        },
        "available_signals": available_signals,
        "missing_items": missing_items,
        "failure_reasons": failure_reasons,
        "can_infer": can_infer or ["当前只有公司基础信息，不能形成业务判断。"],
        "cannot_infer": cannot_infer,
        "next_actions": sorted(actions, key=lambda item: item["priority"]),
        "analysis_boundary": boundary,
        "coverage_tags": coverage_tags_from_summary(available_signals, missing_items),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def coverage_tags_from_summary(available_signals: dict[str, Any], missing_items: list[str]) -> list[str]:
    tags: list[str] = []
    if available_signals.get("annual_report_count") or available_signals.get("announcement_count"):
        tags.append("已有关联公告")
    if available_signals.get("financial_fact_count"):
        tags.append("已有财务事实")
    if available_signals.get("heat_score") is not None or available_signals.get("hot_rank"):
        tags.append("仅热度信号" if "missing_financial_facts" in missing_items else "有热度信号")
    if "missing_financial_facts" in missing_items or "missing_annual_report" in missing_items:
        tags.append("缺少基本面验证")
    if "missing_sentiment" in missing_items:
        tags.append("未同步市场情绪")
    return tags or ["数据覆盖不足"]


def _latest_brief_item(db: Session, workspace_id: int, ticker: str, user_id: int | None) -> dict[str, Any] | None:
    rows = (
        db.query(DailyBriefModel)
        .filter(DailyBriefModel.workspace_id == workspace_id)
        .order_by(DailyBriefModel.generated_at.desc())
        .limit(20)
        .all()
    )
    target = _normalize_ashare_code(ticker)
    best_user_item = None
    best_any_item = None
    for row in rows:
        for item in row.items or []:
            if _normalize_ashare_code(str(item.get("ticker") or item.get("symbol") or item.get("代码") or "")) != target:
                continue
            payload = dict(item)
            payload.setdefault("trade_date", row.trade_date)
            if row.user_id == user_id:
                best_user_item = payload
                break
            if best_any_item is None:
                best_any_item = payload
        if best_user_item:
            break
    return best_user_item or best_any_item


def _latest_sync_failure(db: Session, workspace_id: int) -> str | None:
    row = (
        db.query(DataSyncJobModel)
        .filter(DataSyncJobModel.workspace_id == workspace_id, DataSyncJobModel.failure_reason.isnot(None))
        .order_by(DataSyncJobModel.started_at.desc())
        .first()
    )
    return row.failure_reason if row else None


def _market_fact_payload(row: MarketFactModel | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "trade_date": row.trade_date,
        "metric": row.metric,
        "label": row.label,
        "value": row.value,
        "unit": row.unit,
        "source": row.source,
    }


def _sentiment_payload(row: SentimentFactModel | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "trade_date": row.trade_date,
        "score": row.score,
        "label": row.label,
        "source": row.source,
    }


def _first_not_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _normalize_ashare_code(value: str) -> str:
    text = str(value or "").upper().strip()
    for prefix in ("SH", "SZ", "BJ"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text[-6:] if len(text) >= 6 else text
