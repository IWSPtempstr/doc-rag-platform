"""Finance evaluation adapters and metric helpers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import EvalCaseModel, EvalDatasetModel, EvalResultModel, FilingModel
from app.services.finance_agent import run_finance_agent


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
    verifier_passes = 0
    citation_overlaps = 0
    per_task: dict[str, dict] = {}

    for case in cases:
        metadata = case.metadata_json or {}
        ticker = metadata.get("ticker")
        filing_id = case.gold_filing_id or metadata.get("filing_id")
        task_type = case.task_type or "unknown"

        if not ticker:
            details.append({"case_id": case.id, "question": case.question, "skipped": True, "reason": "missing ticker"})
            continue

        try:
            result = run_finance_agent(
                db=db, workspace_id=workspace_id, company_ticker=ticker,
                filing_id=filing_id, question=case.question, mode="eval",
            )
        except Exception as exc:
            details.append({"case_id": case.id, "question": case.question, "error": str(exc)})
            continue

        citations = result.get("citations", [])
        verification = result.get("verification", {})
        evidence_hit = bool(citations)
        numeric_hit = _numeric_hit(result.get("calculations", []), case.expected_numeric, case.tolerance)
        overlap = _evidence_overlap(citations, case.expected_evidence)
        verifier_pass = bool(verification.get("passed"))

        evidence_hits += int(evidence_hit)
        numeric_hits += int(numeric_hit)
        verifier_passes += int(verifier_pass)
        citation_overlaps += overlap

        detail = {
            "case_id": case.id, "question": case.question, "task_type": task_type,
            "answer": result.get("answer"), "evidence_hit": evidence_hit,
            "numeric_hit": numeric_hit, "evidence_overlap": overlap,
            "verification": verification,
        }
        details.append(detail)

        per_task.setdefault(task_type, {"total": 0, "evidence_hits": 0, "numeric_hits": 0, "overlap_total": 0})
        per_task[task_type]["total"] += 1
        per_task[task_type]["evidence_hits"] += int(evidence_hit)
        per_task[task_type]["numeric_hits"] += int(numeric_hit)
        per_task[task_type]["overlap_total"] += overlap

    total = max(len(cases), 1)
    metrics = {
        "retrieval_hit_rate": round(evidence_hits / total, 4),
        "evidence_recall": round(citation_overlaps / total, 4),
        "numeric_accuracy": round(numeric_hits / total, 4),
        "citation_coverage": round(evidence_hits / total, 4),
        "verifier_pass_rate": round(verifier_passes / total, 4),
        "total_cases": len(cases),
        "by_task_type": {
            k: {
                "total": v["total"],
                "retrieval_hit_rate": round(v["evidence_hits"] / max(v["total"], 1), 4),
                "numeric_accuracy": round(v["numeric_hits"] / max(v["total"], 1), 4),
                "evidence_recall": round(v["overlap_total"] / max(v["total"], 1), 4),
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


def _evidence_overlap(citations: list[dict], expected_evidence: list | str | None) -> int:
    """Count how many gold evidence items have some overlap with citation content."""
    if not expected_evidence or not citations:
        return 0
    if isinstance(expected_evidence, str):
        expected_evidence = [expected_evidence]
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


def _numeric_hit(calculations: list[dict], expected: float | None, tolerance: float | None) -> bool:
    if expected is None:
        return bool(calculations)
    tol = tolerance or 0.01
    return any(abs(float(c.get("value", 0)) - expected) <= tol for c in calculations)
