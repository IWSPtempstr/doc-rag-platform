"""Finance evaluation adapters and metric helpers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import EvalCaseModel, EvalDatasetModel, EvalResultModel, FilingModel
from app.services.finance_agent import run_finance_agent


def ensure_dataset(db: Session, workspace_id: int, source: str) -> EvalDatasetModel:
    dataset = (
        db.query(EvalDatasetModel)
        .filter(EvalDatasetModel.workspace_id == workspace_id, EvalDatasetModel.source == source)
        .first()
    )
    if dataset:
        return dataset

    dataset = EvalDatasetModel(
        workspace_id=workspace_id,
        source=source,
        name=_dataset_name(source),
        version="v1",
        description="Seeded finance evaluation set",
    )
    db.add(dataset)
    db.flush()

    filing = db.query(FilingModel).filter(FilingModel.workspace_id == workspace_id).first()
    cases = _seed_cases(source, filing)
    for case in cases:
        db.add(EvalCaseModel(dataset_id=dataset.id, **case))
    db.commit()
    db.refresh(dataset)
    return dataset


def run_finance_evaluation(db: Session, workspace_id: int, source: str, strategy: str) -> EvalResultModel:
    dataset = ensure_dataset(db, workspace_id, source)
    cases = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset.id).all()
    details = []
    evidence_hits = 0
    numeric_hits = 0
    verifier_passes = 0

    for case in cases:
        metadata = case.metadata_json or {}
        ticker = metadata.get("ticker")
        filing_id = metadata.get("filing_id")
        if not ticker:
            details.append({"case_id": case.id, "question": case.question, "skipped": True, "reason": "missing ticker"})
            continue
        try:
            result = run_finance_agent(
                db=db,
                workspace_id=workspace_id,
                company_ticker=ticker,
                filing_id=filing_id,
                question=case.question,
                mode="eval",
            )
        except Exception as exc:
            details.append({"case_id": case.id, "question": case.question, "error": str(exc)})
            continue

        citations = result.get("citations", [])
        verification = result.get("verification", {})
        evidence_hit = bool(citations)
        numeric_hit = _numeric_hit(result.get("calculations", []), case.expected_numeric, case.tolerance)
        evidence_hits += int(evidence_hit)
        numeric_hits += int(numeric_hit)
        verifier_passes += int(bool(verification.get("passed")))
        details.append({
            "case_id": case.id,
            "question": case.question,
            "answer": result.get("answer"),
            "evidence_hit": evidence_hit,
            "numeric_hit": numeric_hit,
            "verification": verification,
        })

    total = max(len(cases), 1)
    metrics = {
        "retrieval_hit_rate": round(evidence_hits / total, 4),
        "evidence_recall": round(evidence_hits / total, 4),
        "numeric_accuracy": round(numeric_hits / total, 4),
        "citation_coverage": round(evidence_hits / total, 4),
        "verifier_pass_rate": round(verifier_passes / total, 4),
        "total_cases": len(cases),
    }
    row = EvalResultModel(
        workspace_id=workspace_id,
        dataset_id=dataset.id,
        strategy=strategy,
        metrics=metrics,
        results=details,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _dataset_name(source: str) -> str:
    return {
        "finqa": "FinQA-style seeded cases",
        "tatqa": "TAT-QA-style seeded cases",
        "custom_10k": "Custom 10-K agent tasks",
    }.get(source, source)


def _seed_cases(source: str, filing: FilingModel | None) -> list[dict]:
    ticker = filing.company.ticker if filing and filing.company else None
    filing_id = filing.id if filing else None
    base_metadata = {"ticker": ticker, "filing_id": filing_id}
    if source == "finqa":
        return [{
            "question": "What financial metrics can be extracted from the latest 10-K?",
            "expected_answer": "revenue and profitability metrics",
            "metadata_json": base_metadata,
        }]
    if source == "tatqa":
        return [{
            "question": "Calculate any available margin from the filing evidence.",
            "expected_answer": "margin calculation",
            "metadata_json": base_metadata,
        }]
    return [
        {
            "question": "Summarize revenue trend and key business risks from the 10-K.",
            "expected_answer": "risk and revenue evidence",
            "metadata_json": base_metadata,
        },
        {
            "question": "Find evidence for management discussion and financial statements.",
            "expected_answer": "MD&A and financial statements citations",
            "metadata_json": base_metadata,
        },
    ]


def _numeric_hit(calculations: list[dict], expected: float | None, tolerance: float | None) -> bool:
    if expected is None:
        return bool(calculations)
    tol = tolerance or 0.01
    return any(abs(float(c.get("value", 0)) - expected) <= tol for c in calculations)

