"""Finance evaluation adapters and metric helpers."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import EvalCaseModel, EvalDatasetModel, EvalResultModel, FilingModel
from app.services.finance_agent import run_finance_agent

_NON_DISCLOSED_KW = {"ebitda", "freecashflow", "free cash flow", "free_cash_flow", "fcf"}
_ABSTAIN_PHRASES = [
    "未直接披露", "未披露", "未列示", "无法给出", "不包含",
    "not disclosed", "not directly reported", "cannot provide",
    "not available", "insufficient", "not present",
]


def ensure_dataset(db: Session, workspace_id: int, dataset_name: str) -> EvalDatasetModel:
    """Find dataset by name first (what frontend passes), then source (legacy), then seed."""
    dataset = (
        db.query(EvalDatasetModel)
        .filter(EvalDatasetModel.workspace_id == workspace_id, EvalDatasetModel.name == dataset_name)
        .first()
    )
    if dataset:
        return dataset

    dataset = (
        db.query(EvalDatasetModel)
        .filter(EvalDatasetModel.workspace_id == workspace_id, EvalDatasetModel.source == dataset_name)
        .first()
    )
    if dataset:
        return dataset

    dataset = EvalDatasetModel(
        workspace_id=workspace_id,
        source=dataset_name,
        name=_dataset_name(dataset_name),
        version="v1",
        description="Seeded finance evaluation set",
    )
    db.add(dataset)
    db.flush()

    filing = db.query(FilingModel).filter(FilingModel.workspace_id == workspace_id).first()
    for case in _seed_cases(dataset_name, filing):
        db.add(EvalCaseModel(dataset_id=dataset.id, **case))
    db.commit()
    db.refresh(dataset)
    return dataset


def run_finance_evaluation(db: Session, workspace_id: int, dataset_name: str, strategy: str) -> EvalResultModel:
    dataset = ensure_dataset(db, workspace_id, dataset_name)

    q = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset.id)
    if dataset.frozen_at:
        q = q.filter(EvalCaseModel.status == "approved")

    cases = q.all()
    details = []
    evidence_hits = 0
    numeric_hits = 0
    numeric_total = 0
    verifier_passes = 0
    citation_overlaps = 0
    abstain_correct = 0
    abstain_total = 0
    fact_groundings = 0
    fact_grounding_total = 0
    evaluated_cases = 0
    skipped_cases = 0
    per_task: dict[str, dict] = {}

    for case in cases:
        metadata = case.metadata_json or {}
        ticker = metadata.get("ticker")
        filing_id = case.gold_filing_id or metadata.get("filing_id")
        task_type = case.task_type or "unknown"
        metric_group = metadata.get("metric_group")

        invalid_reason = _inadmissible_reason(metadata)
        if invalid_reason:
            skipped_cases += 1
            details.append({
                "case_id": case.id,
                "question": case.question,
                "task_type": task_type,
                "skipped": True,
                "failure_type": _dataset_failure_type(invalid_reason),
                "failure_reason": invalid_reason,
            })
            continue

        if not ticker:
            skipped_cases += 1
            details.append({
                "case_id": case.id,
                "question": case.question,
                "task_type": task_type,
                "skipped": True,
                "failure_type": "dataset_invalid",
                "failure_reason": "missing_ticker",
            })
            continue

        evaluated_cases += 1
        try:
            result = run_finance_agent(
                db=db, workspace_id=workspace_id, company_ticker=ticker,
                filing_id=filing_id, question=case.question, mode="eval",
            )
        except Exception as exc:
            details.append({
                "case_id": case.id,
                "question": case.question,
                "task_type": task_type,
                "error": str(exc),
                "failure_type": "agent_failed",
            })
            continue

        citations = result.get("citations", [])
        verification = result.get("verification", {})
        facts = result.get("facts", [])
        calculations = result.get("calculations", [])
        answer = result.get("answer", "")

        # ── basic flags ──
        evidence_hit = bool(citations)
        verifier_pass = bool(verification.get("passed"))

        # ── abstain detection ──
        is_abstain = _check_abstain(answer, verification)
        expects_abstain = (
            task_type == "insufficient_evidence"
            or any(kw in (case.question or "").lower() for kw in _NON_DISCLOSED_KW)
        )

        # ── numeric accuracy ──
        numeric_hit = False
        if case.expected_numeric is not None:
            numeric_total += 1
            numeric_hit = _match_numeric_from_facts(facts, calculations, case.expected_numeric, case.tolerance)
        elif expects_abstain:
            # No expected numeric + abstain expected → correct answer is abstain
            abstain_total += 1
            if is_abstain:
                abstain_correct += 1

        # ── evidence overlap ──
        overlap = _evidence_overlap(citations, case.expected_evidence)

        # ── fact grounding ──
        grounding_applicable = _fact_grounding_applicable(metadata, case.expected_numeric)
        fact_grounded = _check_fact_grounding(facts, calculations, metadata, case.expected_numeric, case.tolerance)
        if grounding_applicable:
            fact_grounding_total += 1
        if grounding_applicable and fact_grounded:
            fact_groundings += 1

        evidence_hits += int(evidence_hit)
        numeric_hits += int(numeric_hit)
        verifier_passes += int(verifier_pass)
        citation_overlaps += overlap

        detail = {
            "case_id": case.id, "question": case.question, "task_type": task_type,
            "answer_preview": answer[:300], "evidence_hit": evidence_hit,
            "numeric_hit": numeric_hit, "evidence_overlap": overlap,
            "fact_grounded": fact_grounded,
            "fact_grounding_applicable": grounding_applicable,
            "is_abstain": is_abstain, "expects_abstain": expects_abstain,
            "failure_type": _result_failure_type(metadata, citations, overlap, verifier_pass, task_type),
            "verification": verification,
        }
        details.append(detail)

        per_task.setdefault(task_type, {
            "total": 0, "evidence_hits": 0, "numeric_hits": 0, "numeric_total": 0, "overlap_total": 0,
            "fact_groundings": 0, "fact_grounding_total": 0, "abstain_correct": 0, "abstain_total": 0,
        })
        per_task[task_type]["total"] += 1
        per_task[task_type]["evidence_hits"] += int(evidence_hit)
        if case.expected_numeric is not None:
            per_task[task_type]["numeric_hits"] += int(numeric_hit)
            per_task[task_type]["numeric_total"] += 1
        per_task[task_type]["overlap_total"] += overlap
        if grounding_applicable:
            per_task[task_type]["fact_grounding_total"] += 1
            per_task[task_type]["fact_groundings"] += int(fact_grounded)
        if expects_abstain:
            per_task[task_type]["abstain_total"] += 1
            if is_abstain:
                per_task[task_type]["abstain_correct"] += 1

    total = max(evaluated_cases, 1)
    metrics = {
        "retrieval_hit_rate": round(evidence_hits / total, 4),
        "evidence_recall": round(citation_overlaps / total, 4),
        "fact_grounding_rate": round(fact_groundings / max(fact_grounding_total, 1), 4) if fact_grounding_total else None,
        "numeric_accuracy": round(numeric_hits / max(numeric_total, 1), 4) if numeric_total else None,
        "citation_coverage": round(evidence_hits / total, 4),
        "verifier_pass_rate": round(verifier_passes / total, 4),
        "abstain_accuracy": round(abstain_correct / max(abstain_total, 1), 4) if abstain_total else None,
        "total_cases": evaluated_cases,
        "skipped_cases": skipped_cases,
        "numeric_cases": numeric_total,
        "fact_grounding_cases": fact_grounding_total,
        "abstain_cases": abstain_total,
        "abstain_correct": abstain_correct,
        "by_task_type": {
            k: {
                "total": v["total"],
                "retrieval_hit_rate": round(v["evidence_hits"] / max(v["total"], 1), 4),
                "numeric_accuracy": round(v["numeric_hits"] / max(v["numeric_total"], 1), 4) if v["numeric_total"] else None,
                "evidence_recall": round(v["overlap_total"] / max(v["total"], 1), 4),
                "fact_grounding_rate": round(v["fact_groundings"] / max(v["fact_grounding_total"], 1), 4) if v["fact_grounding_total"] else None,
                "abstain_accuracy": round(v["abstain_correct"] / max(v["abstain_total"], 1), 4) if v["abstain_total"] else None,
            }
            for k, v in per_task.items()
        },
    }
    row = EvalResultModel(
        workspace_id=workspace_id, dataset_id=dataset.id,
        strategy=strategy, metrics=metrics, results=details,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _inadmissible_reason(metadata: dict) -> str | None:
    flags = metadata.get("quality_flags") or {}
    admissible = metadata.get("admissible", flags.get("admissible"))
    if admissible is False:
        return metadata.get("failure_reason") or flags.get("failure_reason") or "dataset_invalid"
    return None


def _dataset_failure_type(reason: str) -> str:
    if reason in {"document_not_indexed", "index_incomplete"} or reason.startswith("preflight_error"):
        return "index_incomplete"
    return "dataset_invalid"


def _result_failure_type(metadata: dict, citations: list[dict], overlap: int, verifier_pass: bool, task_type: str) -> str | None:
    if not citations:
        flags = metadata.get("quality_flags") or {}
        if (flags.get("chroma_chunk_count") or 0) <= 0:
            return "index_incomplete"
        return "retriever_miss"
    if task_type in {"evidence_retrieval", "risk_trend"} and overlap <= 0:
        return "retriever_miss"
    if not verifier_pass:
        return "agent_verifier_fail"
    return None


def _check_abstain(answer: str, verification: dict) -> bool:
    """Check if the agent is correctly abstaining/declining to answer."""
    if verification.get("is_abstain"):
        return True
    answer_lower = answer.lower()
    return any(phrase in answer_lower for phrase in _ABSTAIN_PHRASES)


def _fact_grounding_applicable(metadata: dict, expected: float | None) -> bool:
    return bool(expected is not None and (metadata.get("metric_group") or metadata.get("input_metrics")))


def _check_fact_grounding(facts: list[dict], calculations: list[dict], metadata: dict,
                          expected: float | None, tolerance: float | None) -> bool:
    """Check that numeric answers are grounded in canonical facts or fact-backed calculations."""
    metric_group = metadata.get("metric_group")
    input_metrics = metadata.get("input_metrics") or []
    if not metric_group and not input_metrics:
        return False
    tol = tolerance or 0.01
    canonical = {
        (fact.get("canonical_metric") or fact.get("metric") or "").upper(): fact
        for fact in facts
    }
    if input_metrics:
        if not all(str(metric).upper() in canonical for metric in input_metrics):
            return False
        if expected is None:
            return True
        return _calculation_matches(calculations, metric_group, expected, tol)

    if not facts:
        return False
    for fact in facts:
        canon = fact.get("canonical_metric") or ""
        if canon.upper() == metric_group.upper():
            val = fact.get("value")
            if val is not None and expected is not None:
                if abs(val - expected) <= max(tol * abs(expected), 1):
                    return True
            elif val is not None:
                return True  # Has the right metric, even if we can't verify value
    return False


def _calculation_matches(calculations: list[dict], name: str | None, expected: float, tolerance: float) -> bool:
    threshold = max(tolerance * abs(expected), 1e-6)
    for calc in calculations:
        if name and str(calc.get("name", "")).upper() != str(name).upper():
            continue
        val = calc.get("value")
        if val is not None and abs(val - expected) <= threshold:
            return True
    return False


def _match_numeric_from_facts(facts: list[dict], calculations: list[dict],
                               expected: float, tolerance: float | None) -> bool:
    """Check if any fact or calculation matches the expected numeric value."""
    tol = tolerance or 0.01
    threshold = max(tol * abs(expected), 1)
    # Check facts first (preferred)
    for fact in facts:
        val = fact.get("value")
        if val is not None and abs(val - expected) <= threshold:
            return True
    # Fallback to calculations
    for calc in calculations:
        val = calc.get("value")
        if val is not None and abs(val - expected) <= threshold:
            return True
    return False


def _evidence_overlap(citations: list[dict], expected_evidence: list | str | dict | None) -> int:
    """Count how many gold evidence items have some overlap with citation content."""
    if not expected_evidence or not citations:
        return 0
    if isinstance(expected_evidence, str):
        expected_evidence = [expected_evidence]
    elif isinstance(expected_evidence, dict):
        expected_evidence = [
            expected_evidence.get("text_snippet")
            or expected_evidence.get("text")
            or expected_evidence.get("evidence")
            or str(expected_evidence)
        ]
    count = 0
    for gold in expected_evidence:
        gold_lower = str(gold).lower()
        for cit in citations:
            content = (cit.get("content") or "").lower()
            if _token_overlap(gold_lower, content) >= 0.3:
                count += 1
                break
    return count


def _token_overlap(a: str, b: str) -> float:
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b))


def _dataset_name(source: str) -> str:
    return {
        "finqa": "FinQA-style seeded cases",
        "tatqa": "TAT-QA-style seeded cases",
        "custom_10k": "Custom 10-K agent tasks",
        "sec_10k": "SEC 10-K numeric benchmark",
        "financebench_sample_all": "FinanceBench sample",
    }.get(source, source)


def _seed_cases(source: str, filing: FilingModel | None) -> list[dict]:
    ticker = filing.company.ticker if filing and filing.company else None
    filing_id = filing.id if filing else None
    base_metadata = {"ticker": ticker, "filing_id": filing_id}
    if source == "finqa":
        return [{"question": "What financial metrics can be extracted from the latest 10-K?",
                  "expected_answer": "revenue and profitability metrics", "metadata_json": base_metadata}]
    if source == "tatqa":
        return [{"question": "Calculate any available margin from the filing evidence.",
                  "expected_answer": "margin calculation", "metadata_json": base_metadata}]
    return [
        {"question": "Summarize revenue trend and key business risks from the 10-K.",
         "expected_answer": "risk and revenue evidence", "metadata_json": base_metadata},
        {"question": "Find evidence for management discussion and financial statements.",
         "expected_answer": "MD&A and financial statements citations", "metadata_json": base_metadata},
    ]
