"""Finance evaluation dataset builder — FinanceBench import, custom 10-K case generation, dataset freeze."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    CompanyModel, DocumentModel, EvalCaseModel, EvalDatasetModel,
    FilingModel, FilingSectionModel, FinancialFactModel,
)
from app.services.sec_connector import extract_usd_facts, normalize_facts_for_filing

TASK_RATIOS = {"retrieval": 0.30, "calculation": 0.30, "risk_trend": 0.25, "insufficient_evidence": 0.15}
SECTION_ITEMS = ["1", "1A", "7", "7A", "8"]
FB_SOURCE_URL = "https://huggingface.co/datasets/PatronusAI/financebench"


# ── FinanceBench import ────────────────────────────────────

def import_financebench(db: Session, dataset: EvalDatasetModel, limit: int | None = 150) -> dict[str, Any]:
    try:
        from datasets import load_dataset
    except ImportError:
        raise RuntimeError("pip install datasets")

    ds = load_dataset("PatronusAI/financebench", split="train", trust_remote_code=True)
    if limit:
        ds = ds.select(range(min(limit, len(ds))))

    companies = {c.name.lower(): c for c in db.query(CompanyModel).filter(CompanyModel.workspace_id == dataset.workspace_id).all()}
    docs = {d.filename.lower(): d for d in db.query(DocumentModel).all()}
    added, skipped = 0, 0

    for row in ds:
        uid = f"fb-{row.get('doc_name','')}-{_hash_q(row.get('question',''))}"
        if db.query(EvalCaseModel).filter(EvalCaseModel.case_uid == uid, EvalCaseModel.dataset_id == dataset.id).first():
            skipped += 1
            continue

        doc_name = (row.get("doc_name") or "").strip()
        doc_type = (row.get("doc_type") or "").strip()
        company = companies.get(doc_name.split("_")[0].lower() if "_" in doc_name else doc_name.lower())
        doc = docs.get(doc_name.lower())

        db.add(EvalCaseModel(
            dataset_id=dataset.id, case_uid=uid,
            question=row.get("question", ""),
            expected_answer=row.get("answer") or "",
            expected_evidence=row.get("evidence") or [],
            task_type="numeric" if row.get("answer_type") == "numeric" else "evidence_retrieval",
            status="draft",
            gold_document_id=doc.id if doc else None,
            metadata_json={
                "ticker": company.ticker if company else None,
                "doc_name": doc_name, "doc_type": doc_type,
                "doc_period": row.get("doc_period"), "doc_link": row.get("doc_link"),
                "is_10k": doc_type.upper() in ("10-K", "10K"),
                "source_dataset": "financebench", "source_row_id": str(row.get("id", "")),
            },
        ))
        added += 1

    dataset.case_count = (dataset.case_count or 0) + added
    dataset.manifest_json = {"source": "huggingface:PatronusAI/financebench", "rows_imported": added, "rows_skipped": skipped}
    db.commit()
    return {"cases_added": added, "skipped": skipped}


# ── Custom 10-K case generation ────────────────────────────

def generate_custom_10k_cases(
    db: Session, dataset: EvalDatasetModel, cases_per_filing: int = 10,
) -> dict[str, Any]:
    companies = db.query(CompanyModel).filter(CompanyModel.workspace_id == dataset.workspace_id).all()
    total = 0
    per_filing: list[dict] = []

    for company in companies:
        filings = (
            db.query(FilingModel)
            .filter(FilingModel.company_id == company.id, FilingModel.document_id.isnot(None))
            .order_by(FilingModel.fiscal_year.desc()).limit(3).all()
        )
        for filing in filings:
            n = _gen_cases_for_filing(db, dataset.id, company, filing, cases_per_filing)
            total += n
            per_filing.append({"ticker": company.ticker, "filing_id": filing.id, "fiscal_year": filing.fiscal_year, "cases": n})

    dataset.case_count = (dataset.case_count or 0) + total
    dataset.manifest_json = {"source": "custom_10k", "method": "template_deterministic", "per_filing": per_filing}
    db.commit()
    return {"cases_added": total, "per_filing": per_filing}


def _gen_cases_for_filing(
    db: Session, dataset_id: int, company, filing, count: int,
) -> int:
    sections = {
        s.item_code: s
        for s in db.query(FilingSectionModel).filter(
            FilingSectionModel.filing_id == filing.id, FilingSectionModel.item_code.in_(SECTION_ITEMS)
        ).all()
    }
    facts = {f.metric: f for f in db.query(FinancialFactModel).filter(FinancialFactModel.filing_id == filing.id).all()}

    r, c, t, ins = int(count * 0.30), int(count * 0.30), int(count * 0.25), count - int(count * 0.30) * 2 - int(count * 0.25)
    added = 0
    ticker = company.ticker
    fy = filing.fiscal_year

    # Retrieval
    for item_code, sec in list(sections.items())[:r]:
        if sec.content_preview and len(sec.content_preview) > 100:
            uid = f"cust-ret-{filing.id}-{item_code}"
            if _add(db, dataset_id, uid, "evidence_retrieval", "easy",
                f"{ticker} FY{fy} 10-K Item {item_code}（{sec.title}）的核心内容是什么？",
                sec.content_preview[:500],
                evidence={"section_item": item_code, "text_snippet": sec.content_preview[:500]},
                gold_filing_id=filing.id, gold_document_id=filing.document_id,
                meta={"ticker": ticker, "fiscal_year": fy, "section_item": item_code, "source_dataset": "custom_10k"},
            ): added += 1

    # Calculations
    rev = facts.get("revenue") or facts.get("Revenues")
    ni = facts.get("net_income") or facts.get("NetIncomeLoss")
    if rev and ni and rev.value and ni.value:
        margin = round(ni.value / rev.value, 4)
        uid = f"cust-calc-{filing.id}-margin"
        if _add(db, dataset_id, uid, "calculation", "medium",
            f"{ticker} FY{fy} 净利润率是多少？（净利润 / 营收）",
            str(margin), expected_numeric=margin, tolerance=0.02,
            expected_calculation={"formula": "net_income/revenue", "inputs": {"revenue": rev.value, "net_income": ni.value}},
            gold_filing_id=filing.id, gold_document_id=filing.document_id,
            meta={"ticker": ticker, "fiscal_year": fy, "source_dataset": "custom_10k"},
        ): added += 1

    # Risk/Trend
    if "1A" in sections and sections["1A"].content_preview:
        uid = f"cust-risk-{filing.id}"
        if _add(db, dataset_id, uid, "risk_trend", "medium",
            f"列出 {ticker} FY{fy} 10-K Item 1A 中披露的前三个主要风险因素。",
            sections["1A"].content_preview[:600],
            evidence={"section_item": "1A", "text_snippet": sections["1A"].content_preview[:600]},
            gold_filing_id=filing.id, gold_document_id=filing.document_id,
            meta={"ticker": ticker, "fiscal_year": fy, "section_item": "1A", "source_dataset": "custom_10k"},
        ): added += 1

    # Insufficient evidence
    for metric in ["EBITDA", "FreeCashFlow"][:ins]:
        uid = f"cust-ins-{filing.id}-{metric}"
        if _add(db, dataset_id, uid, "insufficient_evidence", "hard",
            f"{ticker} FY{fy} 的 {metric} 是多少？",
            "该指标未在 10-K 中直接披露，需间接推算。",
            rubric_json={"expected_behavior": "agent_should_decline", "acceptable": ["insufficient_data", "not_disclosed"]},
            gold_filing_id=filing.id, gold_document_id=filing.document_id,
            meta={"ticker": ticker, "fiscal_year": fy, "source_dataset": "custom_10k"},
        ): added += 1

    if added:
        db.commit()
    return added


def _add(db: Session, dataset_id: int, uid: str, task_type: str, difficulty: str,
         question: str, expected_answer: str, **kw) -> bool:
    if db.query(EvalCaseModel).filter(EvalCaseModel.case_uid == uid, EvalCaseModel.dataset_id == dataset_id).first():
        return False
    kw.setdefault("status", "draft")
    kw.setdefault("tolerance", 0.01)
    db.add(EvalCaseModel(dataset_id=dataset_id, case_uid=uid, question=question,
        expected_answer=expected_answer, task_type=task_type, difficulty=difficulty, **kw))
    return True


# ── SEC 10-K numeric cases (from existing filings) ─────────

def generate_sec_10k_cases(
    db: Session, dataset: EvalDatasetModel, tickers: list[str], latest_years: int = 3,
) -> dict[str, Any]:
    """Generate numeric cases from existing filings + XBRL companyfacts. Requires filings already imported."""
    results: list[dict] = []
    for ticker in tickers:
        try:
            company = db.query(CompanyModel).filter(
                CompanyModel.workspace_id == dataset.workspace_id, CompanyModel.ticker == ticker.upper()
            ).first()
            if not company:
                results.append({"ticker": ticker, "error": "公司未导入"})
                continue

            try:
                xbrl_facts = extract_usd_facts(company.cik)
            except Exception:
                results.append({"ticker": ticker, "error": "无法获取 XBRL facts"})
                continue

            filings = (
                db.query(FilingModel)
                .filter(FilingModel.company_id == company.id)
                .order_by(FilingModel.fiscal_year.desc()).limit(latest_years).all()
            )
            cases_added = 0
            for filing in filings:
                facts = normalize_facts_for_filing(xbrl_facts, filing.fiscal_year)
                _upsert_facts(db, filing.id, facts)
                for metric, data in facts.items():
                    uid = f"sec-{filing.id}-{metric}"
                    value = data.get("value")
                    if _add(db, dataset.id, uid, "numeric", "easy",
                        f"{ticker} FY{filing.fiscal_year} 的 {metric} 是多少？",
                        str(value) if value else "N/A",
                        expected_numeric=value, status="approved",
                        gold_filing_id=filing.id, gold_document_id=filing.document_id,
                        meta={"ticker": ticker, "cik": company.cik, "fiscal_year": filing.fiscal_year,
                              "accession_number": filing.accession_number, "metric_group": metric,
                              "source_dataset": "sec_10k", "source_tag": data.get("tag")},
                    ): cases_added += 1
            results.append({"ticker": ticker, "filings_used": len(filings), "cases_added": cases_added})
        except Exception as exc:
            results.append({"ticker": ticker, "error": str(exc)})

    dataset.case_count = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset.id).count()
    dataset.manifest_json = {"tickers": tickers, "latest_years": latest_years, "results": results}
    db.commit()
    return {"tickers_processed": results}


def _upsert_facts(db: Session, filing_id: int, facts: dict[str, Any]) -> None:
    existing = {f.metric for f in db.query(FinancialFactModel).filter(FinancialFactModel.filing_id == filing_id).all()}
    for metric, data in facts.items():
        if metric in existing:
            continue
        db.add(FinancialFactModel(filing_id=filing_id, metric=metric, label=metric, value=data.get("value"), source="sec_xbrl", confidence=0.95))
    db.commit()


# ── Dataset helpers ────────────────────────────────────────

def _ensure_dataset(db: Session, workspace_id: int, name: str, source: str, **kw) -> EvalDatasetModel:
    ds = db.query(EvalDatasetModel).filter(EvalDatasetModel.workspace_id == workspace_id, EvalDatasetModel.name == name).first()
    if ds:
        for k, v in kw.items():
            if v is not None:
                setattr(ds, k, v)
        db.commit()
        return ds
    ds = EvalDatasetModel(workspace_id=workspace_id, name=name, source=source, **kw)
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


def _next_version(db: Session, name: str) -> str:
    datasets = db.query(EvalDatasetModel).filter(EvalDatasetModel.name.startswith(name)).order_by(EvalDatasetModel.created_at.desc()).all()
    nums = []
    for d in datasets:
        try:
            if d.version.startswith("v"):
                nums.append(int(d.version[1:]))
        except ValueError:
            pass
    return f"v{max(nums) + 1}" if nums else "v1"


def freeze_dataset(db: Session, dataset_id: int) -> EvalDatasetModel:
    ds = db.query(EvalDatasetModel).filter(EvalDatasetModel.id == dataset_id).first()
    if not ds:
        raise ValueError("Dataset not found")
    approved = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset_id, EvalCaseModel.status == "approved").count()
    ds.case_count = approved
    ds.frozen_at = datetime.now(timezone.utc)
    db.commit()
    return ds


def _hash_q(q: str) -> str:
    import hashlib
    return hashlib.md5(q.encode()).hexdigest()[:12]
