"""Centralized finance MAS built for LangGraph, with a sequential fallback."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, TypedDict

from sqlalchemy.orm import Session

from app.config import config
from app.models import AgentRunModel, AgentStepModel, CompanyModel, FilingModel, FinancialFactModel, SettingsModel
from app.services.embedding_provider import embed_single
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
    answer: str
    verification: dict
    needs_retrieval_retry: bool
    supervisor_phase: str
    retrieval_count: int


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
    if not filing:
        raise ValueError("No filing available for this company")

    run = AgentRunModel(
        workspace_id=workspace_id,
        company_id=company.id,
        filing_id=filing.id,
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
        "filing_id": filing.id,
        "question": question,
        "mode": mode,
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
    except Exception as exc:
        run.status = "failed"
        run.answer = f"分析失败: {exc}"
        run.verification = {"passed": False, "errors": [str(exc)]}
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
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
    graph.add_node("supervisor", _supervisor_node)

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
        input_json={"question": state.get("question"), "filing_id": state.get("filing_id")},
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
    phase = state.get("supervisor_phase", "retrieval")
    has_citations = bool(state.get("citations"))
    has_facts = bool(state.get("facts"))
    has_calculations = bool(state.get("calculations"))
    has_answer = bool(state.get("answer"))
    verification = state.get("verification") or {}
    verified = verification.get("passed", False)
    retrieval_count = state.get("retrieval_count", 0)

    if phase == "retrieval":
        if not has_citations and retrieval_count < 2:
            state["retrieval_count"] = retrieval_count + 1
            return "retrieval"
        if not has_citations:
            state["supervisor_phase"] = "verifier"
            state["verification"] = {"passed": False, "errors": ["检索未返回结果，已重试 2 次"]}
            return "verifier"
        state["supervisor_phase"] = "facts"
        return "facts" if not has_facts else _next_phase(state)

    if phase == "facts" and has_facts:
        state["supervisor_phase"] = "calculation"
        return "calculation" if not has_calculations else _next_phase(state)

    if phase == "calculation" and has_calculations:
        state["supervisor_phase"] = "analysis"
        return "analysis" if not has_answer else _next_phase(state)

    if phase == "analysis" and has_answer:
        state["supervisor_phase"] = "verifier"
        return "verifier" if not verified else "done"

    if phase == "verifier":
        if verified:
            return "done"
        if retrieval_count < 2:
            state["supervisor_phase"] = "retrieval"
            state["retrieval_count"] = retrieval_count + 1
            state["needs_retrieval_retry"] = True
            return "retrieval"
        return "done"

    return phase


def _next_phase(state: FinanceAgentState) -> str:
    has_calculations = bool(state.get("calculations"))
    has_answer = bool(state.get("answer"))
    verification = state.get("verification") or {}
    verified = verification.get("passed", False)

    if not has_calculations:
        state["supervisor_phase"] = "calculation"
        return "calculation"
    if not has_answer:
        state["supervisor_phase"] = "analysis"
        return "analysis"
    if not verified:
        state["supervisor_phase"] = "verifier"
        return "verifier"
    return "done"


# ── Worker Nodes ────────────────────────────────────────────

def _retrieval_node(db: Session, state: FinanceAgentState) -> FinanceAgentState:
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


def _fact_node(db: Session, state: FinanceAgentState) -> FinanceAgentState:
    facts: list[dict] = []
    text = "\n".join(c.get("content", "") for c in state.get("citations", []))
    patterns = [
        ("revenue", "Revenue", r"(?:revenue|net sales|total revenues)[^\d$]{0,40}\$?\s*([0-9][0-9,\.]+)\s*(million|billion)?"),
        ("net_income", "Net income", r"(?:net income|net earnings)[^\d$]{0,40}\$?\s*([0-9][0-9,\.]+)\s*(million|billion)?"),
        ("cash_flow", "Operating cash flow", r"(?:cash flows? from operating activities|operating cash flow)[^\d$]{0,60}\$?\s*([0-9][0-9,\.]+)\s*(million|billion)?"),
    ]
    for metric, label, pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        value = _normalize_number(match.group(1), match.group(2))
        facts.append({
            "metric": metric,
            "label": label,
            "value": value,
            "unit": "USD",
            "evidence": match.group(0)[:240],
            "confidence": 0.55,
        })
    state["facts"] = facts

    filing_id = state.get("filing_id")
    if filing_id:
        existing = {(f.metric, f.period) for f in
                    db.query(FinancialFactModel).filter(FinancialFactModel.filing_id == filing_id).all()}
        for fact in facts:
            key = (fact["metric"], fact.get("period"))
            if key in existing:
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
    values = {f["metric"]: f.get("value") for f in facts}
    calculations: list[dict] = []
    revenue = values.get("revenue")
    net_income = values.get("net_income")
    if revenue and net_income:
        calculations.append({
            "name": "net_margin",
            "label": "Net margin",
            "value": round(net_income / revenue, 4),
            "formula": "net_income / revenue",
        })
    state["calculations"] = calculations
    return state


def _analysis_node(db: Session, state: FinanceAgentState) -> FinanceAgentState:
    citations = state.get("citations", [])
    facts = state.get("facts", [])
    calculations = state.get("calculations", [])
    lines = [f"针对 {state['company_ticker']} 的 10-K，系统完成了检索、指标抽取和一致性检查。"]
    if facts:
        lines.append("抽取到的关键指标包括：" + "；".join(
            f"{f['label']}={f.get('value')}" for f in facts if f.get("value") is not None
        ) + "。")
    if calculations:
        lines.append("确定性计算结果：" + "；".join(
            f"{c['label']}={c['value']}" for c in calculations
        ) + "。")
    if citations:
        lines.append("回答基于检索到的 10-K 片段，具体证据见 citations。")
    else:
        lines.append("当前没有检索到足够的 10-K 证据，分析可信度较低。")
    state["answer"] = "\n".join(lines)
    return state


def _verifier_node(db: Session, state: FinanceAgentState) -> FinanceAgentState:
    errors: list[str] = []

    if not state.get("citations"):
        errors.append("缺少引用证据")
    if not state.get("answer"):
        errors.append("缺少最终回答")

    for fact in (state.get("facts") or []):
        evidence = fact.get("evidence", "")
        value = fact.get("value")
        if evidence and value is not None:
            numbers_in_evidence = re.findall(r"[\d,]+\.?\d*", evidence)
            unit_words_in_evidence = re.findall(r"(million|billion)", evidence, flags=re.I)
            consistent = False
            for n in numbers_in_evidence:
                ev_value = _normalize_number(n, unit_words_in_evidence[0] if unit_words_in_evidence else None)
                if ev_value > 0 and abs(ev_value - value) < max(0.01 * abs(value), 1):
                    consistent = True
                    break
            if not consistent:
                errors.append(f"{fact['label']} 值与证据文本不一致")

    calculations = state.get("calculations", [])
    calc_results: set[str] = set()
    for calc in calculations:
        if calc.get("value") is not None:
            calc_results.add(str(calc["value"]))
            if calc["name"] == "net_margin":
                if calc["value"] < 0 or calc["value"] > 1:
                    errors.append(f"Net margin {calc['value']} 超出合理范围 [0, 1]")

    answer = state.get("answer", "")
    cited_text = " ".join(c.get("content", "") for c in (state.get("citations") or []))
    answer_numbers = re.findall(r"[\d,]+\.?\d*\s*(?:million|billion|%|percent)?", answer, flags=re.I)
    unsupported = [
        n.strip() for n in answer_numbers
        if n.strip() and n.strip() not in cited_text
        and not any(cr in n for cr in calc_results)
    ]
    if unsupported:
        errors.append(f"报告中包含未在引用中出现的数字: {', '.join(unsupported[:3])}")

    num_citations = len(state.get("citations", []))
    coverage = min(1.0, num_citations / 5)

    state["verification"] = {
        "passed": not errors,
        "errors": errors,
        "citation_coverage": coverage,
        "numeric_checks": len(calculations),
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


def _summarize_state(state: FinanceAgentState) -> dict[str, Any]:
    return {
        "citations": len(state.get("citations", [])),
        "facts": len(state.get("facts", [])),
        "calculations": len(state.get("calculations", [])),
        "verification": state.get("verification"),
        "answer_preview": (state.get("answer") or "")[:240],
    }
