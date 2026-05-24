"""Centralized finance MAS built for LangGraph, with a sequential fallback."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from app.config import config
from app.models import AgentRunModel, AgentStepModel, CompanyModel, FilingModel, FinancialFactModel, MarketFactModel, SentimentFactModel, SettingsModel
from app.services.embedding_provider import embed_single
from app.services.finance_research_summary import build_company_research_summary
from app.services.vector_store import query as vector_query


class FinanceAgentState(TypedDict, total=False):
    workspace_id: int
    company_ticker: str
    filing_id: int | None
    question: str
    mode: str
    citations: list[dict]
    facts: list[dict]
    calculations: list[dict]
    research_summary: dict
    answer: str
    verification: dict
    needs_retrieval_retry: bool
    supervisor_phase: str
    retrieval_count: int
    facts_done: bool
    calculation_done: bool
    analysis_done: bool
    tool_groups: list[str]


def run_finance_agent(
    db: Session,
    workspace_id: int,
    company_ticker: str,
    filing_id: int | None,
    question: str,
    mode: str = "full",
    user_id: int | None = None,
) -> dict:
    company = (
        db.query(CompanyModel)
        .filter(CompanyModel.workspace_id == workspace_id, CompanyModel.ticker == company_ticker.upper())
        .first()
    )
    if not company:
        raise ValueError(f"Company not found: {company_ticker}")

    if filing_id is None:
        filing = (
            db.query(FilingModel)
            .filter(FilingModel.company_id == company.id)
            .order_by(FilingModel.fiscal_year.desc(), FilingModel.created_at.desc())
            .first()
        )
    else:
        filing = db.query(FilingModel).filter(FilingModel.id == filing_id).first()
    if filing_id is not None and not filing:
        raise ValueError("Filing not found for this company")

    research_summary = build_company_research_summary(db, workspace_id, company, user_id)

    run = AgentRunModel(
        workspace_id=workspace_id,
        company_id=company.id,
        filing_id=filing.id if filing else None,
        user_id=user_id,
        question=question,
        mode=mode,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    state: FinanceAgentState = {
        "workspace_id": workspace_id,
        "company_ticker": company.ticker,
        "filing_id": filing.id if filing else None,
        "question": question,
        "mode": mode,
        "research_summary": research_summary,
        "tool_groups": classify_finance_tool_groups(question),
        "supervisor_phase": "retrieval",
        "retrieval_count": 0,
    }

    try:
        state = _run_graph_or_fallback(db, run.id, state)
        run.status = "completed"
        run.answer = state.get("answer", "")
        run.citations = state.get("citations", [])
        run.facts = state.get("facts", [])
        run.calculations = state.get("calculations", [])
        run.verification = state.get("verification", {})
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        _safe_write_finance_trace(db, run.id)
    except Exception as exc:
        run.status = "failed"
        run.answer = f"分析失败: {exc}"
        run.verification = {"passed": False, "errors": [str(exc)]}
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        _safe_write_finance_trace(db, run.id)
        raise

    steps = (
        db.query(AgentStepModel)
        .filter(AgentStepModel.run_id == run.id)
        .order_by(AgentStepModel.step_order.asc())
        .all()
    )
    return {
        "answer": run.answer or "",
        "citations": run.citations or [],
        "facts": run.facts or [],
        "calculations": run.calculations or [],
        "agent_run_id": run.id,
        "steps": [
            {
                "id": s.id,
                "node_name": s.node_name,
                "status": s.status,
                "output_json": s.output_json,
                "duration_ms": s.duration_ms,
            }
            for s in steps
        ],
        "verification": run.verification or {},
    }


def _run_graph_or_fallback(db: Session, run_id: int, state: FinanceAgentState) -> FinanceAgentState:
    try:
        from langgraph.graph import END, StateGraph
    except Exception:
        return _run_sequential(db, run_id, state)

    graph = StateGraph(FinanceAgentState)

    def make_node(name, fn):
        return lambda s: _recorded(db, run_id, name, fn, s)

    graph.add_node("retrieval", make_node("retrieval", _retrieval_node))
    graph.add_node("facts", make_node("facts", _fact_node))
    graph.add_node("calculation", make_node("calculation", _calculation_node))
    graph.add_node("analysis", make_node("analysis", _analysis_node))
    graph.add_node("verifier", make_node("verifier", _verifier_node))
    graph.add_node("supervisor", lambda s: _supervisor_node(db, s))

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges(
        "supervisor",
        _supervisor_router,
        {
            "retrieval": "retrieval",
            "facts": "facts",
            "calculation": "calculation",
            "analysis": "analysis",
            "verifier": "verifier",
            "done": END,
        },
    )

    for node in ("retrieval", "facts", "calculation", "analysis", "verifier"):
        graph.add_edge(node, "supervisor")

    return graph.compile().invoke(state)


def _run_sequential(db: Session, run_id: int, state: FinanceAgentState) -> FinanceAgentState:
    max_retries = 2
    for name, fn in [
        ("retrieval", _retrieval_node),
        ("facts", _fact_node),
        ("calculation", _calculation_node),
        ("analysis", _analysis_node),
        ("verifier", _verifier_node),
    ]:
        state = _recorded(db, run_id, name, fn, state)
        if name == "retrieval" and not state.get("citations"):
            retries = state.get("retrieval_count", 0)
            while not state.get("citations") and retries < max_retries:
                retries += 1
                state["retrieval_count"] = retries
                state = _recorded(db, run_id, f"retrieval_retry_{retries}", _retrieval_node, state)
        if name == "verifier" and not state.get("verification", {}).get("passed") and state.get("retrieval_count", 0) < 2:
            state["retrieval_count"] = state.get("retrieval_count", 0) + 1
            state = _recorded(db, run_id, "retrieval_retry", _retrieval_node, state)
            state = _recorded(db, run_id, "analysis_retry", _analysis_node, state)
            state = _recorded(db, run_id, "verifier_retry", _verifier_node, state)
    return state


def _recorded(db: Session, run_id: int, name: str, fn, state: FinanceAgentState) -> FinanceAgentState:
    step_order = db.query(AgentStepModel).filter(AgentStepModel.run_id == run_id).count() + 1
    t0 = time.time()
    step = AgentStepModel(
        run_id=run_id,
        step_order=step_order,
        node_name=name,
        status="running",
        input_json={
            "question": state.get("question"),
            "filing_id": state.get("filing_id"),
            "tool_groups": state.get("tool_groups", []),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_tokens": False,
            "provider": "deterministic",
            "model": f"finance_mas:{name}",
            "cache_hit": False,
        },
    )
    db.add(step)
    db.commit()
    try:
        next_state = fn(db, state)
        step.status = "completed"
        step.output_json = _summarize_state(next_state)
        return next_state
    except Exception as exc:
        step.status = "failed"
        step.error = str(exc)
        raise
    finally:
        step.duration_ms = round((time.time() - t0) * 1000, 2)
        db.commit()


# ── Supervisor ──────────────────────────────────────────────

def _supervisor_node(db: Session, state: FinanceAgentState) -> FinanceAgentState:
    return state


def _supervisor_router(state: FinanceAgentState) -> str:
    if state.get("verification") is not None:
        return "done"
    groups = set(state.get("tool_groups", []))
    needs_document_retrieval = bool(groups & {"filing_retrieval", "announcement_search"}) and bool(state.get("filing_id"))
    if needs_document_retrieval and not state.get("citations") and state.get("retrieval_count", 0) < _MAX_RETRIEVAL_ATTEMPTS:
        return "retrieval"
    if not state.get("facts_done"):
        return "facts"
    if not state.get("calculation_done"):
        return "calculation"
    if not state.get("analysis_done"):
        return "analysis"
    return "verifier"


# ── Worker Nodes ────────────────────────────────────────────

def _retrieval_node(db: Session, state: FinanceAgentState) -> FinanceAgentState:
    state["retrieval_count"] = state.get("retrieval_count", 0) + 1
    settings = db.query(SettingsModel).first()
    embed_provider = (settings.embedding_provider if settings else None) or config.DEFAULT_EMBEDDING_PROVIDER
    embed_model = (settings.embed_model if settings else None) or config.DEFAULT_EMBED_MODEL
    embedding = embed_single(state["question"], model=embed_model, provider=embed_provider)
    where = {"filing_id": state["filing_id"]} if state.get("filing_id") else {"company_ticker": state["company_ticker"]}
    citations = vector_query(
        embedding,
        top_k=8,
        embedding_provider=embed_provider,
        embedding_model=embed_model,
        where=where,
    )
    state["citations"] = citations
    return state


def classify_finance_tool_groups(question: str) -> list[str]:
    """Route finance questions to a small, explicit tool group set."""
    q = question.lower()
    groups: set[str] = set()
    if any(term in q for term in ("公告", "年报", "披露", "announcement", "filing", "annual report")):
        groups.add("announcement_search")
        groups.add("filing_retrieval")
    if any(term in q for term in ("风险", "risk", "item 1a", "摘要", "summary", "章节", "section", "引用", "证据")):
        groups.add("filing_retrieval")
    if any(term in q for term in ("营收", "收入", "净利润", "利润", "资产", "负债", "现金流", "revenue", "income", "assets", "liabilities", "cash flow")):
        groups.add("structured_facts")
    if any(term in q for term in ("率", "margin", "ratio", "growth", "同比", "增速", "计算", "compare", "对比")):
        groups.add("calculation")
        groups.add("structured_facts")
    if any(term in q for term in ("股价", "收盘", "开盘", "最高", "最低", "成交量", "市值", "行情", "price", "close", "open", "volume", "market cap")):
        groups.add("market_facts")
    if any(term in q for term in ("情绪", "sentiment", "热度", "人气", "关注")):
        groups.add("market_facts")
        groups.add("market_sentiment")
    if any(term in q for term in ("评估", "benchmark", "dataset", "case", "命中率", "evidence_recall")):
        groups.add("evaluation")
    if not groups:
        groups.update({"filing_retrieval", "structured_facts"})
    return sorted(groups)


# Metric alias map — user-facing names → canonical XBRL metric names
_METRIC_ALIAS = {
    "revenue": "Revenues",
    "net_income": "NetIncomeLoss",
    "operating_income": "OperatingIncomeLoss",
    "total_assets": "Assets",
    "total_liabilities": "Liabilities",
    "operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities",
}
# Reverse: canonical → preferred alias
_CANONICAL_TO_ALIAS = {v: k for k, v in _METRIC_ALIAS.items()}

# Metrics not directly disclosed in standard annual reports; the agent should decline.
_NON_DISCLOSED_METRICS = {"ebitda", "freecashflow", "free cash flow", "free_cash_flow", "fcf"}
_MAX_RETRIEVAL_ATTEMPTS = 2


def _fact_node(db: Session, state: FinanceAgentState) -> FinanceAgentState:
    filing_id = state.get("filing_id")
    facts: list[dict] = []
    groups = set(state.get("tool_groups", []))

    # ── 1) Load canonical/structured facts from DB ──
    canonical: dict[str, FinancialFactModel] = {}
    if filing_id:
        rows = (
            db.query(FinancialFactModel)
            .filter(FinancialFactModel.filing_id == filing_id)
            .all()
        )
        source_rank = {"sec_xbrl": 3, "akshare": 2, "structured": 1, "agent_extracted": 0}
        for row in rows:
            current = canonical.get(row.metric)
            if not current or source_rank.get(row.source or "", 0) > source_rank.get(current.source or "", 0):
                canonical[row.metric] = row

    if "market_facts" in groups:
        company = (
            db.query(CompanyModel)
            .filter(CompanyModel.workspace_id == state["workspace_id"], CompanyModel.ticker == state["company_ticker"])
            .first()
        )
        if company:
            market_rows = (
                db.query(MarketFactModel)
                .filter(MarketFactModel.workspace_id == state["workspace_id"], MarketFactModel.company_id == company.id)
                .order_by(MarketFactModel.trade_date.desc(), MarketFactModel.metric.asc())
                .limit(12)
                .all()
            )
            for row in market_rows:
                facts.append({
                    "metric": row.metric,
                    "canonical_metric": row.metric,
                    "label": row.label,
                    "value": row.value,
                    "unit": row.unit,
                    "period": row.trade_date,
                    "source": "market_fact",
                    "confidence": row.confidence or 1.0,
                    "evidence": f"{row.ticker} {row.trade_date} {row.label}={row.value}",
                })

    if "market_sentiment" in groups:
        sentiment_rows = (
            db.query(SentimentFactModel)
            .filter(
                SentimentFactModel.workspace_id == state["workspace_id"],
                SentimentFactModel.scope == "market",
            )
            .order_by(SentimentFactModel.trade_date.desc(), SentimentFactModel.created_at.desc())
            .limit(2)
            .all()
        )
        for row in sentiment_rows:
            facts.append({
                "metric": "market_sentiment",
                "canonical_metric": "market_sentiment",
                "label": "市场情绪",
                "value": row.score,
                "unit": "score",
                "period": row.trade_date,
                "source": "sentiment_fact",
                "confidence": 1.0,
                "evidence": f"{row.trade_date} 市场情绪={row.score} {row.label or ''}".strip(),
                "metadata": {"label": row.label, "scope": row.scope, "source": row.source},
            })

    # ── 2) Build fact list from canonical XBRL ──
    for alias, canon_metric in _METRIC_ALIAS.items():
        candidate_metrics = [canon_metric]
        if alias == "operating_cash_flow":
            candidate_metrics.append("OperatingCashFlow")
        metric = next((m for m in candidate_metrics if m in canonical), None)
        if metric:
            row = canonical[metric]
            facts.append({
                "metric": alias,
                "canonical_metric": metric,
                "label": metric,
                "value": row.value,
                "unit": row.unit or ("CNY" if row.source == "akshare" else "USD"),
                "period": row.period,
                "source": row.source,
                "confidence": row.confidence or 0.95,
                "evidence": row.evidence or f"{row.source} {metric} = {row.value}",
            })

    # Also include any canonical metrics not in the alias map
    seen_canonical = {f["canonical_metric"] for f in facts}
    for metric, row in canonical.items():
        if metric not in seen_canonical:
            alias = _CANONICAL_TO_ALIAS.get(metric, metric.lower())
            facts.append({
                "metric": alias,
                "canonical_metric": metric,
                "label": metric,
                "value": row.value,
                "unit": row.unit or "USD",
                "source": "sec_xbrl",
                "confidence": row.confidence or 0.95,
                "evidence": f"XBRL {metric} = {row.value}",
            })

    # ── 3) Text regex fallback — only for metrics NOT already covered ──
    covered_aliases = {f["metric"] for f in facts}
    text = "\n".join(c.get("content", "") for c in state.get("citations", []))
    patterns = [
        ("revenue", "Revenue", r"(?:revenue|net sales|total revenues)[^\d$]{0,40}\$?\s*([0-9][0-9,\.]+)\s*(million|billion)?"),
        ("net_income", "Net income", r"(?:net income|net earnings|net loss)[^\d$]{0,40}\$?\s*([0-9][0-9,\.]+)\s*(million|billion)?"),
        ("operating_cash_flow", "Operating cash flow", r"(?:cash flows? from operating activities|operating cash flow)[^\d$]{0,60}\$?\s*([0-9][0-9,\.]+)\s*(million|billion)?"),
    ]
    for metric, label, pattern in patterns:
        if metric in covered_aliases:
            continue
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        value = _normalize_number(match.group(1), match.group(2))
        facts.append({
            "metric": metric,
            "label": label,
            "value": value,
            "unit": "USD",
            "source": "text_regex",
            "evidence": match.group(0)[:240],
            "confidence": 0.45,
        })

    state["facts"] = facts
    state["facts_done"] = True

    # ── 4) Persist new facts without overwriting canonical ──
    if filing_id:
        existing_canonical = {
            f.metric
            for f in db.query(FinancialFactModel).filter(
                FinancialFactModel.filing_id == filing_id, FinancialFactModel.source == "sec_xbrl"
            ).all()
        }
        existing_agent = {
            (f.metric, f.source)
            for f in db.query(FinancialFactModel).filter(
                FinancialFactModel.filing_id == filing_id, FinancialFactModel.source == "agent_extracted"
            ).all()
        }
        for fact in facts:
            if fact.get("source") in {"market_fact", "sentiment_fact"}:
                continue
            canon = fact.get("canonical_metric") or fact["metric"]
            if canon in existing_canonical:
                continue
            key = (fact["metric"], "agent_extracted")
            if key in existing_agent:
                continue
            db.add(FinancialFactModel(
                filing_id=filing_id,
                metric=fact["metric"],
                label=fact["label"],
                value=fact.get("value"),
                unit=fact.get("unit", "USD"),
                source="agent_extracted",
                evidence=fact.get("evidence"),
                confidence=fact.get("confidence"),
            ))
        db.commit()

    return state


def _calculation_node(db: Session, state: FinanceAgentState) -> FinanceAgentState:
    facts = state.get("facts", [])
    values = {f["metric"]: f.get("value") for f in facts if f.get("value") is not None}
    source = {f["metric"]: f.get("source") for f in facts}
    calculations: list[dict] = []

    revenue = values.get("revenue")
    net_income = values.get("net_income")
    if revenue and net_income:
        rev_src = source.get("revenue", "unknown")
        ni_src = source.get("net_income", "unknown")
        confidence = 0.95 if (rev_src == "sec_xbrl" and ni_src == "sec_xbrl") else 0.55
        calculations.append({
            "name": "net_margin",
            "label": "Net margin (净利润率)",
            "value": round(net_income / revenue, 4),
            "formula": "net_income / revenue",
            "inputs": {"revenue": revenue, "net_income": net_income},
            "source": f"revenue={rev_src}, net_income={ni_src}",
            "confidence": confidence,
        })

    state["calculations"] = calculations
    state["calculation_done"] = True
    return state


def _analysis_node(db: Session, state: FinanceAgentState) -> FinanceAgentState:
    citations = state.get("citations", [])
    facts = state.get("facts", [])
    calculations = state.get("calculations", [])

    question = state.get("question", "").lower()
    ticker = state["company_ticker"]
    intent = _question_intent(question)

    # Check if question is asking for non-disclosed metrics
    asking_non_disclosed = any(
        kw in question for kw in _NON_DISCLOSED_METRICS
    )

    if asking_non_disclosed:
        # Build abstain answer
        metric_hint = next((kw for kw in _NON_DISCLOSED_METRICS if kw in question), "该指标")
        lines = [
            f"{ticker} 已入库的公告/财报事实未直接披露 {metric_hint}。",
            "EBITDA 和 Free Cash Flow 通常需要由多个报表项目间接推算。",
            "当前基于已入库公告、财务事实和行情事实无法给出可追溯数值。",
        ]
    elif intent == "risk":
        lines = [f"{ticker} 风险因素摘要："]
        lines.extend(_citation_bullets(citations, max_items=3, preferred_terms=("risk", "risks", "may", "could", "competition", "regulatory", "风险")))
        if citations:
            lines.append("依据以上公告/财报引用片段。")
        else:
            lines.append("当前没有检索到可引用的风险因素片段。")
    elif intent == "evidence":
        lines = [f"{ticker} 公告/财报证据摘要："]
        lines.extend(_citation_bullets(citations, max_items=3))
        if citations:
            lines.append("依据以上公告/财报引用片段。")
        else:
            lines.append("当前没有检索到足够的公告/财报证据。")
    elif facts or calculations:
        if _is_daily_attention_question(question):
            lines = _daily_attention_answer(ticker, facts, calculations, state.get("research_summary") or {})
        else:
            lines = [f"{ticker} 公告/财报分析结果："]
            structured_facts = [
                f for f in facts
                if f.get("source") in {"sec_xbrl", "akshare", "structured", "market_fact", "sentiment_fact"}
            ]
            if structured_facts:
                value_strs = []
                for f in structured_facts:
                    display = _display_fact(f)
                    if display:
                        value_strs.append(display)
                if value_strs:
                    lines.append("已入库的结构化数据：" + "；".join(value_strs))
            if calculations:
                for c in calculations:
                    lines.append(_display_calculation(c))
            if not structured_facts and citations:
                lines.extend(_citation_bullets(citations, max_items=3))
            elif not structured_facts:
                lines.append("当前没有检索到足够的公告/财报证据，分析可信度较低。")
    else:
        lines = _insufficient_research_answer(ticker, state.get("research_summary") or {})

    state["answer"] = "\n".join(lines)
    state["analysis_done"] = True
    return state


def _is_daily_attention_question(question: str) -> bool:
    terms = ("今天", "今日", "需要关注", "变化", "情绪", "热度", "行情")
    return any(term in question for term in terms)


def _daily_attention_answer(ticker: str, facts: list[dict], calculations: list[dict], summary: dict | None = None) -> list[str]:
    summary = summary or {}
    fact_by_metric = {f.get("metric"): f for f in facts}
    revenue = fact_by_metric.get("revenue")
    net_income = fact_by_metric.get("net_income")
    heat = fact_by_metric.get("heat_score")
    sentiment = fact_by_metric.get("market_sentiment")
    margin = next((c for c in calculations if c.get("name") == "net_margin"), None)

    conclusion_bits: list[str] = []
    if heat and heat.get("value") is not None:
        conclusion_bits.append(f"市场热度为 {_format_plain_number(heat.get('value'))}，说明今天有一定关注度。")
    elif (summary.get("available_signals") or {}).get("heat_score") is not None:
        conclusion_bits.append(
            f"市场热度为 {_format_plain_number((summary.get('available_signals') or {}).get('heat_score'))}，说明今天有一定关注度。"
        )
    if margin and margin.get("value") is not None:
        margin_pct = margin["value"] * 100
        if margin_pct < 3:
            conclusion_bits.append(f"净利率约 {margin_pct:.2f}%，盈利弹性偏薄。")
        elif margin_pct < 10:
            conclusion_bits.append(f"净利率约 {margin_pct:.2f}%，盈利能力处于中等水平。")
        else:
            conclusion_bits.append(f"净利率约 {margin_pct:.2f}%，盈利能力相对较强。")
    if sentiment and sentiment.get("value") is not None:
        label = (sentiment.get("metadata") or {}).get("label") or sentiment.get("label") or "未标注"
        conclusion_bits.append(f"市场情绪最新标签为{label}，分数 {_format_plain_number(sentiment.get('value'))}。")

    lines = ["今日结论"]
    if conclusion_bits:
        lines.append(" ".join(conclusion_bits))
    else:
        lines.append("当前可用数据有限，暂时不能判断是否出现明显变化。")

    lines.append("")
    lines.append("主要原因")
    reason_lines = []
    if revenue and revenue.get("value") is not None:
        reason_lines.append(f"营业收入约 {_format_money(revenue.get('value'), revenue.get('unit'))}，反映公司业务规模。")
    if net_income and net_income.get("value") is not None:
        reason_lines.append(f"净利润约 {_format_money(net_income.get('value'), net_income.get('unit'))}，需要结合收入规模看盈利质量。")
    if heat and heat.get("value") is not None:
        reason_lines.append("市场热度可作为今天市场关注度的辅助信号。")
    if not sentiment:
        reason_lines.append("当前未同步市场情绪数据，因此不能判断整体情绪是否正在改善或转弱。")
    for text in (summary.get("cannot_infer") or [])[:2]:
        if text not in reason_lines:
            reason_lines.append(text)
    lines.extend(reason_lines or ["已入库财务、热度和情绪数据不足，无法形成充分解释。"])

    lines.append("")
    lines.append("需要继续跟踪")
    follow = ["后续公告是否出现业绩、重大合同、资产减值或监管问询等变化。"]
    if heat:
        follow.append("热度升高后是否伴随真实公告或成交变化。")
    if not sentiment:
        follow.append("补充市场情绪同步后，再判断这家公司是否受整体情绪影响。")
    lines.extend(follow)
    return lines


def _insufficient_research_answer(ticker: str, summary: dict) -> list[str]:
    can_infer = summary.get("can_infer") or []
    cannot_infer = summary.get("cannot_infer") or []
    actions = summary.get("next_actions") or []
    signals = summary.get("available_signals") or {}

    lines = ["今日结论"]
    if signals.get("heat_score") is not None or signals.get("hot_rank") is not None:
        heat_part = f"热度 {_format_plain_number(signals.get('heat_score'))}" if signals.get("heat_score") is not None else "热榜记录"
        lines.append(f"{ticker} 当前只能基于{heat_part}做有限说明，不能确认基本面是否发生变化。")
    else:
        lines.append(f"{ticker} 当前入库数据不足，暂时无法形成可靠的公告、财务或情绪判断。")

    lines.append("")
    lines.append("主要原因")
    lines.extend(cannot_infer[:3] or ["缺少公告/年报、结构化财务事实、行情热度或市场情绪数据。"])
    for text in can_infer[:2]:
        lines.append(text)

    lines.append("")
    lines.append("需要继续跟踪")
    action_labels = [str(item.get("label")) for item in actions if item.get("label")]
    lines.extend(action_labels[:4] or ["导入年报", "同步财务事实", "同步行情热度", "同步市场情绪"])
    return lines


_DISPLAY_LABELS = {
    "Revenues": "营业收入",
    "NetIncomeLoss": "净利润",
    "OperatingIncomeLoss": "营业利润",
    "Assets": "资产总计",
    "Liabilities": "负债合计",
    "OperatingCashFlow": "经营现金流",
    "NetCashProvidedByUsedInOperatingActivities": "经营现金流",
    "heat_score": "市场热度",
    "market_sentiment": "市场情绪",
    "revenue": "营业收入",
    "net_income": "净利润",
    "operating_income": "营业利润",
    "total_assets": "资产总计",
    "total_liabilities": "负债合计",
    "operating_cash_flow": "经营现金流",
}


def _display_fact(fact: dict) -> str:
    value = fact.get("value")
    if value is None:
        return ""
    metric = fact.get("canonical_metric") or fact.get("metric") or ""
    label = _DISPLAY_LABELS.get(metric) or _DISPLAY_LABELS.get(fact.get("metric")) or fact.get("label") or metric
    if fact.get("metric") == "market_sentiment":
        text_label = (fact.get("metadata") or {}).get("label") or "未标注"
        return f"{label}={text_label}，分数 {_format_plain_number(value)}"
    if fact.get("metric") == "heat_score":
        return f"{label}={_format_plain_number(value)}"
    return f"{label}={_format_money(value, fact.get('unit'))}"


def _display_calculation(calc: dict) -> str:
    if calc.get("name") == "net_margin" and calc.get("value") is not None:
        return f"净利率约 {calc['value'] * 100:.2f}%，由净利润除以营业收入得到。"
    return f"{calc.get('label') or '计算结果'}={calc.get('value')}"


def _format_money(value: Any, unit: str | None) -> str:
    try:
        num = float(value)
    except Exception:
        return str(value)
    suffix = "元" if unit == "CNY" else (unit or "")
    if abs(num) >= 1_0000_0000:
        return f"{num / 1_0000_0000:.2f}亿{suffix}"
    if abs(num) >= 1_0000:
        return f"{num / 1_0000:.2f}万{suffix}"
    return f"{num:.2f}{suffix}"


def _format_plain_number(value: Any) -> str:
    try:
        num = float(value)
    except Exception:
        return str(value)
    return f"{num:.2f}".rstrip("0").rstrip(".")


def _verifier_node(db: Session, state: FinanceAgentState) -> FinanceAgentState:
    errors: list[str] = []
    facts = state.get("facts", [])
    citations = state.get("citations", [])
    answer = state.get("answer", "")
    question = state.get("question", "").lower()

    # ── 1) Basic checks ──
    groups = set(state.get("tool_groups", []))
    has_structured_grounding = any(
        fact.get("source") in {"sec_xbrl", "akshare", "market_fact", "sentiment_fact", "structured"}
        for fact in facts
    ) or bool(state.get("calculations"))
    citation_required = bool(groups & {"filing_retrieval", "announcement_search"}) or not has_structured_grounding
    if citation_required and not citations:
        errors.append("缺少引用证据")
    if not answer:
        errors.append("缺少最终回答")

    # ── 2) Fact consistency — trust canonical/structured facts, verify regex ──
    for fact in facts:
        source = fact.get("source", "")
        if source in {"sec_xbrl", "akshare", "market_fact", "sentiment_fact", "structured"}:
            continue
        # Text regex facts: check evidence consistency
        evidence = fact.get("evidence", "")
        value = fact.get("value")
        if evidence and value is not None and source != "sec_xbrl":
            numbers_in_evidence = re.findall(r"[\d,]+\.?\d*", evidence)
            unit_words_in_evidence = re.findall(r"(million|billion)", evidence, flags=re.I)
            consistent = False
            for n in numbers_in_evidence:
                if not n or not any(ch.isdigit() for ch in n):
                    continue
                ev_value = _normalize_number(n, unit_words_in_evidence[0] if unit_words_in_evidence else None)
                if ev_value > 0 and abs(ev_value - value) < max(0.01 * abs(value), 1):
                    consistent = True
                    break
            if not consistent:
                errors.append(f"{fact['label']} 值与证据文本不一致")

    # ── 3) Abstain detection for non-disclosed metrics ──
    asking_non_disclosed = any(kw in question for kw in _NON_DISCLOSED_METRICS)
    abstain_phrases = [
        "未直接披露", "未披露", "未列示", "无法给出", "不包含",
        "not disclosed", "not directly reported", "cannot provide",
        "not available", "insufficient", "not present",
    ]
    is_abstaining = any(phrase in answer.lower() for phrase in abstain_phrases)

    if asking_non_disclosed and is_abstaining:
        pass  # Correct behavior for non-disclosed metrics
    elif asking_non_disclosed and not is_abstaining:
        # Agent fabricated numbers for undisclosed metrics
        answer_numbers = re.findall(r"[\d,]+\.?\d+", answer)
        if answer_numbers:
            errors.append("对未披露指标不应提供具体数值")

    # ── 4) Calculation range check ──
    calculations = state.get("calculations", [])
    calc_results: set[float] = set()
    for calc in calculations:
        if calc.get("value") is not None:
            calc_results.add(calc["value"])
            if calc["name"] == "net_margin":
                if calc["value"] < 0 or calc["value"] > 1:
                    errors.append(f"Net margin {calc['value']} 超出合理范围 [0, 1]")
            if calc.get("confidence", 1.0) < 0.5:
                errors.append(f"{calc['label']} 数据源置信度不足")

    # ── 5) Unsupported claims in answer — only for non-canonical numbers ──
    cited_text = " ".join(c.get("content", "") for c in citations)
    answer_numbers = re.findall(r"[\d,]+\.?\d*\s*(?:million|billion|%|percent)?", answer, flags=re.I)
    ignored_numbers = set()
    ticker_digits = re.sub(r"\D", "", state.get("company_ticker", ""))
    if ticker_digits:
        ignored_numbers.add(ticker_digits)
    for year in re.findall(r"(19\d{2}|20\d{2})", question):
        ignored_numbers.add(year)
    # Collect all canonical fact values as "supported"
    supported_numbers: set[str] = set()
    for fact in facts:
        if fact.get("source") in {"sec_xbrl", "akshare", "market_fact", "sentiment_fact", "structured"} and fact.get("value") is not None:
            v = fact["value"]
            supported_numbers.add(str(v))
            supported_numbers.add(str(round(v)))
            if v >= 1e9:
                supported_numbers.add(f"{v/1e9:.2f}")
            if v >= 1e6:
                supported_numbers.add(f"{v/1e6:.1f}")
    for cr in calc_results:
        supported_numbers.add(str(cr))
        supported_numbers.add(str(round(cr, 4)))
        supported_numbers.add(f"{cr * 100:.2f}")

    unsupported = [
        n.strip() for n in answer_numbers
        if n.strip() and any(ch.isdigit() for ch in n)
        and re.sub(r"[^0-9.]", "", n.strip()) not in ignored_numbers
        and n.strip() not in cited_text
        and not any(str(sn) in n for sn in supported_numbers if sn)
    ]
    if unsupported and not (asking_non_disclosed and is_abstaining):
        errors.append(f"报告中包含未在引用中出现的数字: {', '.join(unsupported[:3])}")

    # ── 6) Coverage ──
    num_citations = len(citations)
    coverage = min(1.0, num_citations / 5)

    state["verification"] = {
        "passed": not errors,
        "errors": errors,
        "citation_coverage": coverage,
        "numeric_checks": len(calculations),
        "canonical_facts_used": len([f for f in facts if f.get("source") == "sec_xbrl"]),
        "structured_facts_used": len([f for f in facts if f.get("source") in {"sec_xbrl", "akshare", "structured"}]),
        "market_facts_used": len([f for f in facts if f.get("source") == "market_fact"]),
        "tool_groups": state.get("tool_groups", []),
        "is_abstain": is_abstaining,
        "asking_non_disclosed": asking_non_disclosed,
    }
    state["needs_retrieval_retry"] = False
    return state


# ── Helpers ─────────────────────────────────────────────────

def _normalize_number(raw: str, unit_word: str | None) -> float:
    value = float(raw.replace(",", ""))
    if unit_word and unit_word.lower().startswith("b"):
        return value * 1_000_000_000
    if unit_word and unit_word.lower().startswith("m"):
        return value * 1_000_000
    return value


def _question_intent(question: str) -> str:
    risk_terms = ("risk", "risks", "risk factor", "item 1a", "风险")
    evidence_terms = ("item ", "section", "summarize", "summary", "describe", "evidence", "核心内容", "摘要", "披露")
    numeric_terms = ("how much", "多少", "margin", "ratio", "rate", "growth", "revenue", "income", "assets", "liabilities", "利润率")
    if any(term in question for term in risk_terms):
        return "risk"
    if any(term in question for term in numeric_terms):
        return "numeric"
    if any(term in question for term in evidence_terms):
        return "evidence"
    return "numeric"


def _citation_bullets(citations: list[dict], max_items: int = 3, preferred_terms: tuple[str, ...] = ()) -> list[str]:
    snippets: list[str] = []
    for citation in citations:
        content = (citation.get("content") or "").replace("\n", " ").strip()
        if not content:
            continue
        sentences = [s.strip() for s in re.split(r"(?<=[.!?。！？])\s+", content) if len(s.strip()) > 20]
        candidates = sentences or [content]
        if preferred_terms:
            preferred = [
                s for s in candidates
                if any(term.lower() in s.lower() for term in preferred_terms)
            ]
            candidates = preferred or candidates
        for sentence in candidates:
            cleaned = sentence[:260].strip()
            if cleaned and cleaned not in snippets:
                snippets.append(cleaned)
                break
        if len(snippets) >= max_items:
            break
    if not snippets:
        return ["未检索到足够可引用内容。"]
    return [f"- {snippet}" for snippet in snippets]


def _summarize_state(state: FinanceAgentState) -> dict[str, Any]:
    return {
        "citations": len(state.get("citations", [])),
        "facts": len(state.get("facts", [])),
        "calculations": len(state.get("calculations", [])),
        "verification": state.get("verification"),
        "answer_preview": (state.get("answer") or "")[:240],
        "tool_groups": state.get("tool_groups", []),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_tokens": False,
        "provider": "deterministic",
        "model": "finance_mas",
        "cache_hit": False,
    }


def _safe_write_finance_trace(db: Session, run_id: int) -> None:
    try:
        from app.services.finance_observability import write_finance_agent_trace

        write_finance_agent_trace(db, run_id)
    except Exception:
        pass
