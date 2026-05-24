"""A-share daily brief assembly and sentiment helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.models import (
    CompanyModel,
    DailyBriefModel,
    FilingModel,
    FinancialFactModel,
    MarketFactModel,
    SentimentFactModel,
    UserWatchlistModel,
)
from app.services.ashare_structured_provider import load_akshare_provider, normalize_financial_value


HotProvider = Callable[[], list[dict]]


def build_daily_brief_payload(
    db: Session,
    workspace_id: int,
    user_id: int | None,
    trade_date: str,
    hot_provider: HotProvider | None = None,
    limit: int = 20,
) -> dict:
    """Build the user-facing daily brief ordering without giving trading advice."""
    hot_rows, hot_source, failure_reason = _load_hot_top20(db, workspace_id, trade_date, hot_provider, limit)
    watchlist = _watchlist_rows(db, workspace_id, user_id)

    items: list[dict] = []
    seen: set[str] = set()
    for row in watchlist:
        ticker = row.ticker.upper()
        seen.add(ticker)
        items.append(_brief_item(
            ticker=ticker,
            name=_company_name(db, workspace_id, ticker),
            section="watchlist",
            source="user_watchlist",
            rank=row.priority,
            trade_date=trade_date,
            coverage_tags=_brief_coverage_tags(db, workspace_id, ticker),
        ))

    hot_added = 0
    for idx, row in enumerate(hot_rows, start=1):
        ticker = str(row.get("ticker") or row.get("代码") or row.get("symbol") or "").upper().strip()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        hot_added += 1
        items.append(_brief_item(
            ticker=ticker,
            name=row.get("name") or row.get("名称") or _company_name(db, workspace_id, ticker),
            section="hot_top20",
            source=row.get("source") or hot_source,
            rank=row.get("rank") or row.get("排名") or idx,
            trade_date=trade_date,
            heat_score=row.get("heat_score") or row.get("人气") or row.get("热度") or row.get("value"),
            coverage_tags=_brief_coverage_tags(db, workspace_id, ticker, has_heat=True),
        ))
        if hot_added >= limit:
            break

    summary = _brief_summary(len(watchlist), hot_added, failure_reason)
    return {
        "trade_date": trade_date,
        "status": "generated",
        "summary": summary,
        "items": items,
        "metadata": {
            "watchlist_count": len(watchlist),
            "hot_count": hot_added,
            "hot_source": hot_source,
            "failure_reason": failure_reason,
            "advice_policy": "research_only_no_trading_advice",
        },
    }


def get_or_create_daily_brief(
    db: Session,
    workspace_id: int,
    user_id: int | None,
    trade_date: str,
    hot_provider: HotProvider | None = None,
) -> dict:
    row = (
        db.query(DailyBriefModel)
        .filter(
            DailyBriefModel.workspace_id == workspace_id,
            DailyBriefModel.user_id == user_id,
            DailyBriefModel.trade_date == trade_date,
        )
        .first()
    )
    if row:
        metadata = row.metadata_json or {}
        if metadata.get("hot_count", 0) == 0 and metadata.get("failure_reason"):
            payload = build_daily_brief_payload(db, workspace_id, user_id, trade_date, hot_provider=hot_provider)
            row.status = payload["status"]
            row.summary = payload["summary"]
            row.items = payload["items"]
            row.metadata_json = payload["metadata"]
            db.commit()
            return payload
        return {
            "trade_date": row.trade_date,
            "status": row.status,
            "summary": row.summary,
            "items": row.items or [],
            "metadata": row.metadata_json or {},
        }

    payload = build_daily_brief_payload(db, workspace_id, user_id, trade_date, hot_provider=hot_provider)
    db.add(DailyBriefModel(
        workspace_id=workspace_id,
        user_id=user_id,
        trade_date=trade_date,
        status=payload["status"],
        summary=payload["summary"],
        items=payload["items"],
        metadata_json=payload["metadata"],
    ))
    db.commit()
    return payload


def sync_market_sentiment(db: Session, workspace_id: int, provider: str = "akshare") -> int:
    """Sync market-level A-share news sentiment if the provider exposes it."""
    if provider != "akshare":
        raise ValueError("第一版仅支持 akshare 情绪数据源")
    ak = load_akshare_provider()
    fn = getattr(ak, "index_news_sentiment_scope", None)
    if not fn:
        return _sync_market_sentiment_fallback(db, workspace_id, "akshare 缺少 index_news_sentiment_scope 接口")
    try:
        frame = fn()
        rows = frame.to_dict(orient="records") if hasattr(frame, "to_dict") else []
    except Exception as exc:
        return _sync_market_sentiment_fallback(db, workspace_id, f"akshare index_news_sentiment_scope 失败: {exc}")
    upserted = 0
    for row in rows[-30:]:
        trade_date = str(row.get("日期") or row.get("date") or row.get("时间") or "")[:10]
        if not trade_date:
            continue
        score = normalize_financial_value(
            row.get("市场情绪指数") or row.get("sentiment") or row.get("情绪指数")
        )
        label = _sentiment_label(score)
        existing = (
            db.query(SentimentFactModel)
            .filter(
                SentimentFactModel.workspace_id == workspace_id,
                SentimentFactModel.ticker.is_(None),
                SentimentFactModel.trade_date == trade_date,
                SentimentFactModel.scope == "market",
                SentimentFactModel.source == provider,
            )
            .first()
        )
        payload = {
            "score": score,
            "label": label,
            "evidence": f"A股市场情绪指数 {trade_date}: {score}",
            "metadata_json": row,
        }
        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
        else:
            db.add(SentimentFactModel(
                workspace_id=workspace_id,
                ticker=None,
                trade_date=trade_date,
                scope="market",
                source=provider,
                **payload,
            ))
        upserted += 1
    db.commit()
    if upserted == 0:
        return _sync_market_sentiment_fallback(db, workspace_id, "akshare index_news_sentiment_scope 返回空数据")
    return upserted


def _sync_market_sentiment_fallback(db: Session, workspace_id: int, failure_reason: str) -> int:
    """Persist a clearly labeled local fallback when the upstream sentiment endpoint is unavailable."""
    latest_brief = (
        db.query(DailyBriefModel)
        .filter(DailyBriefModel.workspace_id == workspace_id)
        .order_by(DailyBriefModel.generated_at.desc())
        .first()
    )
    latest_market_fact = (
        db.query(MarketFactModel)
        .filter(MarketFactModel.workspace_id == workspace_id)
        .order_by(MarketFactModel.trade_date.desc(), MarketFactModel.created_at.desc())
        .first()
    )
    trade_date = (
        latest_market_fact.trade_date
        if latest_market_fact else latest_brief.trade_date
        if latest_brief else datetime.now(timezone.utc).date().isoformat()
    )

    market_rows = (
        db.query(MarketFactModel)
        .filter(MarketFactModel.workspace_id == workspace_id, MarketFactModel.trade_date == trade_date)
        .all()
    )
    pct_values = [
        float(row.value)
        for row in market_rows
        if row.metric in {"pct_change", "change_pct"} and row.value is not None
    ]
    hot_items = latest_brief.items if latest_brief and latest_brief.items else []
    hot_count = len(hot_items)
    if pct_values:
        avg_pct = sum(pct_values) / len(pct_values)
        score = max(0, min(100, 50 + avg_pct * 5))
        evidence = f"本地行情涨跌幅均值 {avg_pct:.2f}%，上游情绪接口不可用：{failure_reason}"
    elif hot_count:
        score = 50.0
        evidence = f"本地简报包含 {hot_count} 条热度公司，上游情绪接口不可用：{failure_reason}"
    else:
        score = 50.0
        evidence = f"本地暂无行情/热榜覆盖，上游情绪接口不可用：{failure_reason}"
    label = _sentiment_label(score)

    existing = (
        db.query(SentimentFactModel)
        .filter(
            SentimentFactModel.workspace_id == workspace_id,
            SentimentFactModel.ticker.is_(None),
            SentimentFactModel.trade_date == trade_date,
            SentimentFactModel.scope == "market",
            SentimentFactModel.source == "local_market_coverage_fallback",
        )
        .first()
    )
    payload = {
        "score": score,
        "label": label,
        "evidence": evidence,
        "metadata_json": {
            "fallback": True,
            "failure_reason": failure_reason,
            "market_fact_count": len(market_rows),
            "hot_count": hot_count,
            "method": "pct_change_mean_or_neutral_hot_coverage",
        },
    }
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
    else:
        db.add(SentimentFactModel(
            workspace_id=workspace_id,
            ticker=None,
            trade_date=trade_date,
            scope="market",
            source="local_market_coverage_fallback",
            **payload,
        ))
    db.commit()
    return 1


def load_akshare_hot_top20() -> list[dict]:
    ak = load_akshare_provider()
    errors: list[str] = []
    providers = [
        ("stock_hot_rank_em", {}, "akshare_hot_rank_em"),
        ("stock_hot_search_baidu", {"symbol": "A股"}, "akshare_hot_search_baidu"),
    ]
    for fn_name, kwargs, source in providers:
        fn = getattr(ak, fn_name, None)
        if not fn:
            errors.append(f"缺少 {fn_name}")
            continue
        try:
            frame = fn(**kwargs)
            rows = frame.to_dict(orient="records") if hasattr(frame, "to_dict") else []
            result = _normalize_hot_rows(rows, source)
            if result:
                return result[:20]
            errors.append(f"{fn_name} 返回空数据")
        except Exception as exc:
            errors.append(f"{fn_name}: {exc}")
    raise RuntimeError("A 股热榜同步失败: " + "；".join(errors))


def _normalize_hot_rows(rows: list[dict], source: str) -> list[dict]:
    result = []
    for idx, row in enumerate(rows[:50], start=1):
        ticker = str(
            row.get("代码")
            or row.get("股票代码")
            or row.get("symbol")
            or row.get("ticker")
            or row.get("证券代码")
            or ""
        ).strip().upper()
        ticker = _normalize_ashare_code(ticker)
        if not ticker or not ticker.isdigit() or len(ticker) != 6:
            continue
        result.append({
            "ticker": ticker,
            "name": row.get("股票名称") or row.get("名称") or row.get("name") or row.get("证券简称") or ticker,
            "rank": row.get("排名") or row.get("rank") or idx,
            "heat_score": row.get("人气") or row.get("热度") or row.get("搜索指数") or row.get("最新价") or row.get("value"),
            "source": source,
            "raw": row,
        })
    return result


def _load_hot_top20(
    db: Session,
    workspace_id: int,
    trade_date: str,
    hot_provider: HotProvider | None,
    limit: int,
) -> tuple[list[dict], str, str | None]:
    provider = hot_provider or load_akshare_hot_top20
    try:
        return provider()[:limit], "akshare_hot_rank", None
    except Exception as exc:
        return _fallback_hot_from_market_facts(db, workspace_id, trade_date, limit), "market_fact_fallback", str(exc)


def _fallback_hot_from_market_facts(db: Session, workspace_id: int, trade_date: str, limit: int) -> list[dict]:
    rows = (
        db.query(MarketFactModel)
        .filter(MarketFactModel.workspace_id == workspace_id, MarketFactModel.trade_date == trade_date)
        .all()
    )
    scores: dict[str, float] = {}
    for row in rows:
        value = float(row.value or 0)
        if row.metric == "amount":
            scores[row.ticker] = max(scores.get(row.ticker, 0), value)
        elif row.metric in {"pct_change", "change_pct"}:
            scores[row.ticker] = max(scores.get(row.ticker, 0), abs(value))
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [
        {
            "ticker": ticker,
            "name": _company_name(db, workspace_id, ticker),
            "rank": idx,
            "heat_score": score,
            "source": "market_fact_fallback",
        }
        for idx, (ticker, score) in enumerate(ranked, start=1)
    ]


def _watchlist_rows(db: Session, workspace_id: int, user_id: int | None) -> list[UserWatchlistModel]:
    if not user_id:
        return []
    return (
        db.query(UserWatchlistModel)
        .filter(UserWatchlistModel.workspace_id == workspace_id, UserWatchlistModel.user_id == user_id)
        .order_by(UserWatchlistModel.priority.asc(), UserWatchlistModel.created_at.asc())
        .all()
    )


def _company_name(db: Session, workspace_id: int, ticker: str) -> str:
    company = (
        db.query(CompanyModel)
        .filter(CompanyModel.workspace_id == workspace_id, CompanyModel.ticker == ticker.upper())
        .first()
    )
    return company.name if company else ticker


def _brief_item(
    ticker: str,
    name: str,
    section: str,
    source: str,
    rank: int | None,
    trade_date: str,
    heat_score=None,
    coverage_tags: list[str] | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "section": section,
        "rank": rank,
        "heat_score": heat_score,
        "source": source,
        "trade_date": trade_date,
        "analysis_scope": ["公告变化", "财务事实变化", "行情/热度/情绪变化解释"],
        "advice_policy": "不提供买卖建议、目标价或交易信号",
        "coverage_tags": coverage_tags or ["数据覆盖不足"],
    }


def _brief_coverage_tags(db: Session, workspace_id: int, ticker: str, has_heat: bool = False) -> list[str]:
    code = _normalize_ashare_code(ticker)
    company = (
        db.query(CompanyModel)
        .filter(CompanyModel.workspace_id == workspace_id, CompanyModel.ticker == code)
        .first()
    )
    tags: list[str] = []
    financial_fact_count = 0
    filing_count = 0
    market_fact_count = 0
    if company:
        filings = (
            db.query(FilingModel.id)
            .filter(FilingModel.workspace_id == workspace_id, FilingModel.company_id == company.id)
            .all()
        )
        filing_ids = [row[0] for row in filings]
        filing_count = len(filing_ids)
        if filing_ids:
            financial_fact_count = db.query(FinancialFactModel).filter(FinancialFactModel.filing_id.in_(filing_ids)).count()
        market_fact_count = (
            db.query(MarketFactModel)
            .filter(MarketFactModel.workspace_id == workspace_id, MarketFactModel.company_id == company.id)
            .count()
        )
    if filing_count:
        tags.append("已有关联公告")
    if financial_fact_count:
        tags.append("已有财务事实")
    if has_heat or market_fact_count:
        tags.append("仅热度信号" if not financial_fact_count else "有热度信号")
    if not filing_count or not financial_fact_count:
        tags.append("缺少基本面验证")
    return tags or ["数据覆盖不足"]


def _brief_summary(watchlist_count: int, hot_count: int, failure_reason: str | None) -> str:
    if watchlist_count:
        base = f"今日先展示 {watchlist_count} 家关注公司，再补充 {hot_count} 家市场热度公司。"
    else:
        base = f"今日未设置关注公司，展示市场热度最高的 {hot_count} 家 A 股公司。"
    if failure_reason:
        base += f" 热度数据源降级：{failure_reason}。"
    return base


def _normalize_ashare_code(value: str) -> str:
    text = str(value or "").upper().strip()
    for prefix in ("SH", "SZ", "BJ"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text[-6:] if len(text) >= 6 else text


def _sentiment_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 60:
        return "positive"
    if score <= 40:
        return "negative"
    return "neutral"
