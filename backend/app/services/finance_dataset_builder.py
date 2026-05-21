"""Finance evaluation dataset builder — FinanceBench import, custom 10-K case generation, dataset freeze."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import config
from app.models import (
    CompanyModel, DocumentModel, EvalCaseModel, EvalDatasetModel,
    FilingModel, FilingSectionModel, FinancialFactModel, SettingsModel,
)
from app.services.embedding_provider import embed_single
from app.services.embedding_provider import get_embeddings
from app.services.splitter import split_text
from app.services.vector_store import add_chunks, delete_document
from app.services.sec_connector import extract_usd_facts, normalize_facts_for_filing
from app.services.vector_store import get_collection, query as vector_query

TASK_RATIOS = {"retrieval": 0.30, "calculation": 0.30, "risk_trend": 0.25, "insufficient_evidence": 0.15}
SECTION_ITEMS = ["1", "1A", "7", "7A", "8"]
FB_SOURCE_URL = "https://huggingface.co/datasets/PatronusAI/financebench"
FINQA_SOURCE_URL = "https://huggingface.co/datasets/ibm-research/finqa"
TATQA_SOURCE_URL = "https://huggingface.co/datasets/next-tat/TAT-QA"
GOLD_RECALL_THRESHOLD = 0.30
PUBLIC_DATA_LICENSES = {
    "finqa": "Apache-2.0 / academic benchmark source",
    "tatqa": "Public academic benchmark source",
    "financebench": "CC BY-NC 4.0",
}


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
    dataset.manifest_json = _public_dataset_manifest("financebench", split="train", rows_imported=added, cases_added=added, skipped=skipped)
    db.commit()
    return {"cases_added": added, "skipped": skipped}


def import_finqa(
    db: Session,
    dataset: EvalDatasetModel,
    split: str = "train",
    limit: int | None = 50,
) -> dict[str, Any]:
    rows = _load_finqa_rows(split=split, limit=limit)
    company = _ensure_public_company(db, dataset.workspace_id, "FINQA", "FinQA public benchmark")
    rows_imported = 0
    cases_added = 0
    skipped = 0
    for idx, row in enumerate(rows):
        rows_imported += 1
        case_specs = _finqa_case_specs(row, split=split, source_row_idx=idx)
        filing = _get_or_create_public_filing(
            db,
            workspace_id=dataset.workspace_id,
            company_id=company.id,
            accession_number=f"finqa-{split}-{idx}",
            fiscal_year=2020,
            source_url=FINQA_SOURCE_URL,
            document_id=None,
            filing_type="PUBLIC-QA",
            metadata={"source_dataset": "finqa", "split": split, "row_uid": str(row.get("id") or idx)},
        )
        doc = _upsert_public_document(
            db,
            dataset.workspace_id,
            company.id,
            source="finqa",
            split=split,
            row_uid=str(row.get("id") or idx),
            filename=f"finqa_{split}_{idx:05d}.txt",
            content=_finqa_row_text(row),
            source_url=FINQA_SOURCE_URL,
            metadata={
                "source_dataset": "finqa",
                "split": split,
                "source_row_idx": idx,
                "filing_id": filing.id,
                "company_ticker": company.ticker,
            },
        )
        admissible = doc is not None and doc.status == "completed"
        if not admissible:
            skipped += 1
        filing.document_id = doc.id if doc else None
        db.commit()
        for spec in case_specs:
            meta = {
                **spec["metadata_json"],
                "source_dataset": "finqa",
                "ticker": company.ticker,
                "filing_id": filing.id,
                "fiscal_year": filing.fiscal_year,
                "public_data_only": True,
                "source_url": FINQA_SOURCE_URL,
                "license_note": PUBLIC_DATA_LICENSES["finqa"],
                "admissible": admissible and spec["admissible"],
                "failure_reason": None if admissible and spec["admissible"] else spec["failure_reason"] or "index_incomplete",
                "quality_flags": {
                    **spec["quality_flags"],
                    "source_url": FINQA_SOURCE_URL,
                    "public_data_only": True,
                    "admissible": admissible and spec["admissible"],
                },
            }
            status = "approved" if meta["admissible"] else "rejected"
            _add(db, dataset.id, spec["case_uid"], spec["task_type"], spec["difficulty"], spec["question"], spec["expected_answer"],
                expected_numeric=spec.get("expected_numeric"),
                expected_evidence=spec.get("expected_evidence"),
                expected_calculation=spec.get("expected_calculation"),
                gold_filing_id=filing.id,
                gold_document_id=doc.id if doc else None,
                status=status,
                meta=meta,
                tolerance=spec.get("tolerance", 0.01),
            )
            cases_added += 1

    dataset.case_count = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset.id).count()
    dataset.manifest_json = _public_dataset_manifest(
        "finqa",
        split=split,
        rows_imported=rows_imported,
        cases_added=cases_added,
        skipped=skipped,
        extra={"company_ticker": company.ticker, "rows_total": len(rows)},
    )
    db.commit()
    return {"rows_imported": rows_imported, "cases_added": cases_added, "skipped": skipped}


def import_tatqa(
    db: Session,
    dataset: EvalDatasetModel,
    split: str = "train",
    limit: int | None = 50,
) -> dict[str, Any]:
    rows = _load_tatqa_rows(split=split, limit=limit)
    company = _ensure_public_company(db, dataset.workspace_id, "TATQA", "TAT-QA public benchmark")
    rows_imported = 0
    cases_added = 0
    skipped = 0
    for idx, row in enumerate(rows):
        rows_imported += 1
        case_specs = _tatqa_case_specs(row, split=split, source_row_idx=idx)
        row_uid = row.get("table", {}).get("uid") or f"{split}-{idx}"
        filing = _get_or_create_public_filing(
            db,
            workspace_id=dataset.workspace_id,
            company_id=company.id,
            accession_number=f"tatqa-{split}-{idx}",
            fiscal_year=2020,
            source_url=TATQA_SOURCE_URL,
            document_id=None,
            filing_type="PUBLIC-QA",
            metadata={"source_dataset": "tatqa", "split": split, "row_uid": row_uid},
        )
        doc = _upsert_public_document(
            db,
            dataset.workspace_id,
            company.id,
            source="tatqa",
            split=split,
            row_uid=row_uid,
            filename=f"tatqa_{split}_{idx:05d}.txt",
            content=_tatqa_row_text(row),
            source_url=TATQA_SOURCE_URL,
            metadata={
                "source_dataset": "tatqa",
                "split": split,
                "source_row_idx": idx,
                "filing_id": filing.id,
                "company_ticker": company.ticker,
            },
        )
        admissible = doc is not None and doc.status == "completed"
        if not admissible:
            skipped += 1
        filing.document_id = doc.id if doc else None
        db.commit()
        for spec in case_specs:
            meta = {
                **spec["metadata_json"],
                "source_dataset": "tatqa",
                "ticker": company.ticker,
                "filing_id": filing.id,
                "fiscal_year": filing.fiscal_year,
                "public_data_only": True,
                "source_url": TATQA_SOURCE_URL,
                "license_note": PUBLIC_DATA_LICENSES["tatqa"],
                "admissible": admissible and spec["admissible"],
                "failure_reason": None if admissible and spec["admissible"] else spec["failure_reason"] or "index_incomplete",
                "quality_flags": {
                    **spec["quality_flags"],
                    "source_url": TATQA_SOURCE_URL,
                    "public_data_only": True,
                    "admissible": admissible and spec["admissible"],
                },
            }
            status = "approved" if meta["admissible"] else "rejected"
            _add(db, dataset.id, spec["case_uid"], spec["task_type"], spec["difficulty"], spec["question"], spec["expected_answer"],
                expected_numeric=spec.get("expected_numeric"),
                expected_evidence=spec.get("expected_evidence"),
                expected_calculation=spec.get("expected_calculation"),
                gold_filing_id=filing.id,
                gold_document_id=doc.id if doc else None,
                status=status,
                meta=meta,
                tolerance=spec.get("tolerance", 0.01),
            )
            cases_added += 1

    dataset.case_count = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset.id).count()
    dataset.manifest_json = _public_dataset_manifest(
        "tatqa",
        split=split,
        rows_imported=rows_imported,
        cases_added=cases_added,
        skipped=skipped,
        extra={"company_ticker": company.ticker, "rows_total": len(rows)},
    )
    db.commit()
    return {"rows_imported": rows_imported, "cases_added": cases_added, "skipped": skipped}


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

    dataset.case_count = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset.id).count()
    dataset.manifest_json = {
        "source": "custom_10k",
        "derived_from": "SEC EDGAR 10-K filings and CompanyFacts",
        "source_url": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        "license_note": "Public domain (SEC EDGAR)",
        "public_data_only": True,
        "method": "template_deterministic",
        "per_filing": per_filing,
        "coverage": audit_custom_10k_coverage(db, dataset.workspace_id),
    }
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
    audit = audit_filing_coverage(db, filing)

    r, c, t, ins = int(count * 0.30), int(count * 0.30), int(count * 0.25), count - int(count * 0.30) * 2 - int(count * 0.25)
    added = 0
    ticker = company.ticker
    fy = filing.fiscal_year

    # Retrieval
    for item_code, sec in list(sections.items())[:r]:
        if sec.content_preview and len(sec.content_preview) > 100:
            uid = f"cust-ret-{filing.id}-{item_code}"
            question = f"{ticker} FY{fy} 10-K Item {item_code}（{sec.title}）的核心内容是什么？"
            expected_evidence = {"section_item": item_code, "text_snippet": sec.content_preview[:500]}
            quality = _case_quality(
                db, audit, "evidence_retrieval", question, expected_evidence, section_item=item_code
            )
            if _add(db, dataset_id, uid, "evidence_retrieval", "easy",
                question,
                sec.content_preview[:500],
                expected_evidence=expected_evidence,
                gold_filing_id=filing.id, gold_document_id=filing.document_id,
                status="approved" if quality["admissible"] else "rejected",
                meta={**_base_case_meta(ticker, fy), "section_item": item_code, **quality},
            ): added += 1

    # Calculations — look up facts by both canonical (CamelCase) and alias (lowercase) names
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
            status="approved" if audit["admissible"] else "rejected",
            meta={**_base_case_meta(ticker, fy), **_quality_from_audit(audit),
                  "metric_group": "net_margin", "input_metrics": ["Revenues", "NetIncomeLoss"]},
        ): added += 1

    # Risk/Trend
    if "1A" in sections and sections["1A"].content_preview:
        uid = f"cust-risk-{filing.id}"
        question = f"列出 {ticker} FY{fy} 10-K Item 1A 中披露的前三个主要风险因素。"
        expected_evidence = {"section_item": "1A", "text_snippet": sections["1A"].content_preview[:600]}
        quality = _case_quality(db, audit, "risk_trend", question, expected_evidence, section_item="1A")
        if _add(db, dataset_id, uid, "risk_trend", "medium",
            question,
            sections["1A"].content_preview[:600],
            expected_evidence=expected_evidence,
            gold_filing_id=filing.id, gold_document_id=filing.document_id,
            status="approved" if quality["admissible"] else "rejected",
            meta={**_base_case_meta(ticker, fy), "section_item": "1A", **quality},
        ): added += 1

    # Insufficient evidence
    for metric in ["EBITDA", "FreeCashFlow"][:ins]:
        uid = f"cust-ins-{filing.id}-{metric}"
        if _add(db, dataset_id, uid, "insufficient_evidence", "hard",
            f"{ticker} FY{fy} 的 {metric} 是多少？",
            "该指标未在 10-K 中直接披露，需间接推算。",
            rubric_json={"expected_behavior": "agent_should_decline", "acceptable": ["insufficient_data", "not_disclosed"]},
            gold_filing_id=filing.id, gold_document_id=filing.document_id,
            status="approved" if audit["admissible"] else "rejected",
            meta={**_base_case_meta(ticker, fy), **_quality_from_audit(audit),
                  "metric_group": metric, "expects_abstain": True},
        ): added += 1

    db.commit()
    return added


def _add(db: Session, dataset_id: int, uid: str, task_type: str, difficulty: str,
         question: str, expected_answer: str, **kw) -> bool:
    existing = db.query(EvalCaseModel).filter(EvalCaseModel.case_uid == uid, EvalCaseModel.dataset_id == dataset_id).first()
    if existing:
        _update_existing_case(existing, task_type, difficulty, question, expected_answer, kw)
        return False
    if "meta" in kw:
        kw["metadata_json"] = kw.pop("meta")
    kw.setdefault("status", "draft")
    kw.setdefault("tolerance", 0.01)
    db.add(EvalCaseModel(dataset_id=dataset_id, case_uid=uid, question=question,
        expected_answer=expected_answer, task_type=task_type, difficulty=difficulty, **kw))
    return True


def _update_existing_case(case: EvalCaseModel, task_type: str, difficulty: str, question: str,
                          expected_answer: str, kw: dict[str, Any]) -> None:
    meta = kw.pop("meta", None)
    case.task_type = task_type
    case.difficulty = difficulty
    case.question = question
    case.expected_answer = expected_answer
    for key, value in kw.items():
        setattr(case, key, value)
    if meta is not None:
        case.metadata_json = meta


def _base_case_meta(ticker: str, fiscal_year: int) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "source_dataset": "custom_10k",
        "derived_from": "SEC EDGAR 10-K",
        "public_data_only": True,
        "license_note": "Public domain (SEC EDGAR)",
    }


def _quality_from_audit(audit: dict[str, Any]) -> dict[str, Any]:
    reason = None if audit["admissible"] else audit["failure_reason"]
    return {
        "admissible": audit["admissible"],
        "failure_reason": reason,
        "quality_flags": {
            "admissible": audit["admissible"],
            "failure_reason": reason,
            "document_status": audit.get("document_status"),
            "document_chunk_count": audit.get("document_chunk_count", 0),
            "chroma_chunk_count": audit.get("chroma_chunk_count", 0),
        },
    }


def _case_quality(
    db: Session,
    audit: dict[str, Any],
    task_type: str,
    question: str,
    expected_evidence: Any,
    section_item: str | None = None,
) -> dict[str, Any]:
    quality = _quality_from_audit(audit)
    if not quality["admissible"]:
        return quality
    if section_item and section_item not in audit.get("sections_present", []):
        return _quality_failure(audit, "missing_section")
    if task_type in {"evidence_retrieval", "risk_trend"}:
        preflight = _gold_recall_preflight(db, audit["filing_id"], question, expected_evidence)
        quality["quality_flags"]["gold_recall_at_8"] = preflight["hit"]
        quality["quality_flags"]["gold_recall_score"] = preflight["score"]
        if not preflight["hit"]:
            return _quality_failure(audit, preflight["failure_reason"], quality["quality_flags"])
    return quality


def _quality_failure(audit: dict[str, Any], reason: str, flags: dict[str, Any] | None = None) -> dict[str, Any]:
    quality = _quality_from_audit({**audit, "admissible": False, "failure_reason": reason})
    if flags:
        quality["quality_flags"].update(flags)
    return quality


def audit_custom_10k_coverage(db: Session, workspace_id: int) -> dict[str, Any]:
    filings = (
        db.query(FilingModel)
        .join(CompanyModel, FilingModel.company_id == CompanyModel.id)
        .filter(FilingModel.workspace_id == workspace_id, FilingModel.document_id.isnot(None))
        .order_by(CompanyModel.ticker.asc(), FilingModel.fiscal_year.desc())
        .all()
    )
    items = [audit_filing_coverage(db, filing) for filing in filings]
    return {
        "total_filings": len(items),
        "admissible_filings": sum(1 for item in items if item["admissible"]),
        "filings": items,
    }


def audit_filing_coverage(db: Session, filing: FilingModel) -> dict[str, Any]:
    doc = filing.document
    sections = [
        s.item_code
        for s in db.query(FilingSectionModel).filter(FilingSectionModel.filing_id == filing.id).all()
    ]
    facts = [
        f.metric
        for f in db.query(FinancialFactModel).filter(FinancialFactModel.filing_id == filing.id).all()
    ]
    settings = db.query(SettingsModel).first()
    embed_provider = (settings.embedding_provider if settings else None) or config.DEFAULT_EMBEDDING_PROVIDER
    embed_model = (settings.embed_model if settings else None) or config.DEFAULT_EMBED_MODEL
    chroma_chunks = _count_chroma_chunks(filing.id, embed_provider, embed_model)
    document_chunk_count = doc.chunk_count if doc else 0
    failure_reason = None
    if not doc:
        failure_reason = "missing_document"
    elif doc.status != "completed":
        failure_reason = "document_not_indexed"
    elif not document_chunk_count:
        failure_reason = "document_not_indexed"
    elif chroma_chunks <= 0:
        failure_reason = "index_incomplete"
    return {
        "filing_id": filing.id,
        "ticker": filing.company.ticker if filing.company else None,
        "fiscal_year": filing.fiscal_year,
        "document_id": filing.document_id,
        "document_status": doc.status if doc else None,
        "document_chunk_count": document_chunk_count,
        "chroma_chunk_count": chroma_chunks,
        "sections_present": sorted(set(sections)),
        "facts_present": sorted(set(facts)),
        "admissible": failure_reason is None,
        "failure_reason": failure_reason,
    }


def _count_chroma_chunks(filing_id: int, embedding_provider: str | None = None, embedding_model: str | None = None) -> int:
    try:
        collection = get_collection(embedding_provider, embedding_model)
        result = collection.get(where={"filing_id": filing_id})
        return len(result["ids"]) if result and result["ids"] else 0
    except Exception:
        return 0


def _gold_recall_preflight(db: Session, filing_id: int, question: str, expected_evidence: Any) -> dict[str, Any]:
    gold_items = _expected_evidence_items(expected_evidence)
    if not gold_items:
        return {"hit": False, "score": 0.0, "failure_reason": "missing_gold_evidence"}
    try:
        settings = db.query(SettingsModel).first()
        embed_provider = (settings.embedding_provider if settings else None) or config.DEFAULT_EMBEDDING_PROVIDER
        embed_model = (settings.embed_model if settings else None) or config.DEFAULT_EMBED_MODEL
        embedding = embed_single(question, model=embed_model, provider=embed_provider)
        citations = vector_query(
            embedding,
            top_k=8,
            embedding_provider=embed_provider,
            embedding_model=embed_model,
            where={"filing_id": filing_id},
        )
    except Exception as exc:
        return {"hit": False, "score": 0.0, "failure_reason": f"preflight_error:{exc}"}
    best = 0.0
    for gold in gold_items:
        for citation in citations:
            best = max(best, _token_overlap(str(gold).lower(), (citation.get("content") or "").lower()))
    return {
        "hit": best >= GOLD_RECALL_THRESHOLD,
        "score": round(best, 4),
        "failure_reason": None if best >= GOLD_RECALL_THRESHOLD else "gold_not_retrievable",
    }


def _expected_evidence_items(expected_evidence: Any) -> list[str]:
    if not expected_evidence:
        return []
    if isinstance(expected_evidence, str):
        return [expected_evidence]
    if isinstance(expected_evidence, dict):
        item = (
            expected_evidence.get("text_snippet")
            or expected_evidence.get("text")
            or expected_evidence.get("evidence")
        )
        return [str(item)] if item else []
    return [str(item) for item in expected_evidence if item]


def _token_overlap(a: str, b: str) -> float:
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b))


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
                              "source_dataset": "sec_10k", "source_tag": data.get("tag"),
                              "source_url": filing.source_url,
                              "license_note": "Public domain (SEC EDGAR)",
                              "public_data_only": True,
                              "admissible": True,
                              "quality_flags": {"public_data_only": True, "admissible": True}},
                    ): cases_added += 1
            results.append({"ticker": ticker, "filings_used": len(filings), "cases_added": cases_added})
        except Exception as exc:
            results.append({"ticker": ticker, "error": str(exc)})

    dataset.case_count = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset.id).count()
    dataset.manifest_json = {
        "source": "sec_edgar_companyfacts",
        "source_url": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
        "license_note": "Public domain (SEC EDGAR)",
        "public_data_only": True,
        "tickers": tickers,
        "latest_years": latest_years,
        "results": results,
    }
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
    _reject_inadmissible_cases(db, dataset_id)
    approved = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset_id, EvalCaseModel.status == "approved").count()
    ds.case_count = approved
    ds.frozen_at = datetime.now(timezone.utc)
    db.commit()
    return ds


def _reject_inadmissible_cases(db: Session, dataset_id: int) -> None:
    cases = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset_id, EvalCaseModel.status == "approved").all()
    for case in cases:
        metadata = case.metadata_json or {}
        flags = metadata.get("quality_flags") or {}
        admissible = metadata.get("admissible", flags.get("admissible"))
        if admissible is not False:
            continue
        metadata["admissible"] = False
        metadata["failure_reason"] = metadata.get("failure_reason") or flags.get("failure_reason") or "quality_not_checked"
        metadata["quality_flags"] = {**flags, "admissible": False, "failure_reason": metadata["failure_reason"]}
        case.metadata_json = metadata
        case.status = "rejected"
    db.commit()


def _hash_q(q: str) -> str:
    import hashlib
    return hashlib.md5(q.encode()).hexdigest()[:12]


def _public_dataset_manifest(source: str, split: str, rows_imported: int, cases_added: int, skipped: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    source_map = {
        "finqa": "huggingface:ibm-research/finqa",
        "tatqa": "huggingface:next-tat/TAT-QA",
        "financebench": "huggingface:PatronusAI/financebench",
    }
    source_url_map = {"finqa": FINQA_SOURCE_URL, "tatqa": TATQA_SOURCE_URL, "financebench": FB_SOURCE_URL}
    manifest = {
        "source": source_map.get(source, source),
        "source_url": source_url_map.get(source),
        "split": split,
        "rows_imported": rows_imported,
        "cases_added": cases_added,
        "skipped": skipped,
        "public_data_only": True,
        "license_note": PUBLIC_DATA_LICENSES.get(source, "public benchmark"),
    }
    if extra:
        manifest.update(extra)
    return manifest


def _public_dataset_text(title: str, table_text: str, paragraphs_text: str, qa_text: str) -> str:
    parts = [title]
    for block in (table_text, paragraphs_text, qa_text):
        block = block.strip()
        if block:
            parts.append(block)
    return "\n\n".join(parts)


def _finqa_row_text(row: dict[str, Any]) -> str:
    table = row.get("table") or []
    pre = "\n".join(str(x) for x in row.get("pre_text") or [])
    post = "\n".join(str(x) for x in row.get("post_text") or [])
    table_text = _table_to_text(table)
    qa = row.get("qa") or {}
    qa_text = f"Question: {qa.get('question', '')}\nAnswer: {qa.get('answer', '')}\nProgram: {qa.get('program', '')}\nGold evidence: {json.dumps(qa.get('gold_inds') or {}, ensure_ascii=False)}"
    return _public_dataset_text(f"FinQA example {row.get('id', '')}", table_text, "\n\n".join(x for x in (pre, post) if x), qa_text)


def _tatqa_row_text(row: dict[str, Any]) -> str:
    table = row.get("table") or {}
    table_text = _table_to_text(table.get("table") or [])
    paragraphs = row.get("paragraphs") or []
    paragraph_text = "\n".join(f"[{p.get('order', '')}] {p.get('text', '')}" for p in paragraphs)
    questions = row.get("questions") or []
    qa_text = "\n".join(
        f"Q: {q.get('question', '')}\nA: {q.get('answer', '')}\nAnswer type: {q.get('answer_type', '')}\nGold paragraphs: {q.get('rel_paragraphs', [])}"
        for q in questions[:5]
    )
    return _public_dataset_text(f"TAT-QA example {table.get('uid', '')}", table_text, paragraph_text, qa_text)


def _table_to_text(table: list[list[Any]]) -> str:
    rows: list[str] = []
    for row in table:
        cells = [str(cell) for cell in row]
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def _load_finqa_rows(split: str, limit: int | None) -> list[dict[str, Any]]:
    import requests

    url = f"https://raw.githubusercontent.com/czyssrs/FinQA/main/dataset/{split}.json"
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    rows = resp.json()
    if limit:
        rows = rows[:limit]
    return rows


def _load_tatqa_rows(split: str, limit: int | None) -> list[dict[str, Any]]:
    from datasets import load_dataset

    ds = load_dataset("next-tat/TAT-QA", split=split)
    if limit:
        ds = ds.select(range(min(limit, len(ds))))
    return [dict(row) for row in ds]


def _finqa_case_specs(row: dict[str, Any], split: str, source_row_idx: int) -> list[dict[str, Any]]:
    qa = row.get("qa") or {}
    question = qa.get("question", "")
    steps = qa.get("steps") or []
    answer = qa.get("answer") or (steps[-1].get("res") if steps and isinstance(steps[-1], dict) else "")
    numeric = _parse_numeric_answer(answer)
    evidence = list((qa.get("gold_inds") or {}).values())
    return [{
        "case_uid": f"finqa-{split}-{row.get('id') or source_row_idx}",
        "question": question,
        "expected_answer": str(answer),
        "expected_numeric": numeric,
        "expected_evidence": evidence,
        "expected_calculation": {
            "program": qa.get("program"),
            "steps": qa.get("steps") or [],
        },
        "task_type": "calculation" if numeric is not None else "evidence_retrieval",
        "difficulty": "medium",
        "tolerance": 0.05,
        "admissible": True,
        "failure_reason": None,
        "metadata_json": {
            "source_dataset": "finqa",
            "source_row_id": str(row.get("id") or source_row_idx),
            "source_row_idx": source_row_idx,
            "split": split,
            "public_data_only": True,
            "question_uid": row.get("id"),
            "answer_type": "numeric" if numeric is not None else "text",
        },
        "quality_flags": {
            "public_data_only": True,
            "source_dataset": "finqa",
            "source_row_idx": source_row_idx,
        },
    }]


def _tatqa_case_specs(row: dict[str, Any], split: str, source_row_idx: int) -> list[dict[str, Any]]:
    paragraphs = row.get("paragraphs") or []
    paragraph_map = {str(p.get("order")): p.get("text", "") for p in paragraphs}
    row_uid = row.get("table", {}).get("uid") or f"{split}-{source_row_idx}"
    specs = []
    for q_idx, question in enumerate(row.get("questions") or []):
        answer = question.get("answer")
        expected_numeric = _parse_numeric_answer(answer)
        answer_type = (question.get("answer_type") or "").lower()
        if answer_type in {"arithmetic", "count"}:
            task_type = "calculation"
        elif answer_type in {"span", "multi-span"}:
            task_type = "evidence_retrieval" if expected_numeric is None else "calculation"
        else:
            task_type = "evidence_retrieval" if expected_numeric is None else "numeric"
        rel_paragraphs = [paragraph_map.get(str(ref), "") for ref in question.get("rel_paragraphs") or [] if paragraph_map.get(str(ref), "")]
        specs.append({
            "case_uid": f"tatqa-{split}-{row_uid}-{question.get('uid') or q_idx}",
            "question": question.get("question", ""),
            "expected_answer": _stringify_answer(answer),
            "expected_numeric": expected_numeric,
            "expected_evidence": rel_paragraphs or [f"Table {row_uid}"],
            "expected_calculation": {
                "answer_type": answer_type,
                "derivation": question.get("derivation"),
                "scale": question.get("scale"),
            },
            "task_type": task_type,
            "difficulty": "medium" if task_type != "calculation" else "hard",
            "tolerance": 0.05,
            "admissible": True,
            "failure_reason": None,
            "metadata_json": {
                "source_dataset": "tatqa",
                "source_row_id": row_uid,
                "source_row_idx": source_row_idx,
                "split": split,
                "public_data_only": True,
                "question_uid": question.get("uid"),
                "answer_type": answer_type,
                "scale": question.get("scale"),
                "rel_paragraphs": question.get("rel_paragraphs") or [],
            },
            "quality_flags": {
                "public_data_only": True,
                "source_dataset": "tatqa",
                "source_row_idx": source_row_idx,
            },
        })
    return specs


def _parse_numeric_answer(answer: Any) -> float | None:
    if isinstance(answer, (int, float)):
        return float(answer)
    if isinstance(answer, list) and answer:
        return _parse_numeric_answer(answer[0])
    if isinstance(answer, str):
        cleaned = answer.strip().replace(",", "")
        m = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
        if m:
            return float(m.group(0))
    return None


def _stringify_answer(answer: Any) -> str:
    if isinstance(answer, list):
        return ", ".join(str(item) for item in answer)
    return str(answer)


def _ensure_public_company(db: Session, workspace_id: int, ticker: str, name: str) -> CompanyModel:
    existing = db.query(CompanyModel).filter(CompanyModel.workspace_id == workspace_id, CompanyModel.ticker == ticker).first()
    if existing:
        return existing
    company = CompanyModel(workspace_id=workspace_id, ticker=ticker, name=name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _get_or_create_public_filing(
    db: Session,
    workspace_id: int,
    company_id: int,
    accession_number: str,
    fiscal_year: int,
    source_url: str,
    document_id: int | None,
    filing_type: str,
    metadata: dict[str, Any],
) -> FilingModel:
    filing = (
        db.query(FilingModel)
        .filter(
            FilingModel.workspace_id == workspace_id,
            FilingModel.company_id == company_id,
            FilingModel.accession_number == accession_number,
        )
        .first()
    )
    if filing:
        filing.document_id = document_id
        filing.fiscal_year = fiscal_year
        filing.source_url = source_url
        filing.filing_type = filing_type
        filing.metadata_json = metadata
        db.commit()
        db.refresh(filing)
        return filing
    filing = FilingModel(
        workspace_id=workspace_id,
        company_id=company_id,
        document_id=document_id,
        accession_number=accession_number,
        filing_type=filing_type,
        fiscal_year=fiscal_year,
        source_url=source_url,
        status="imported",
        metadata_json=metadata,
    )
    db.add(filing)
    db.commit()
    db.refresh(filing)
    return filing


def _upsert_public_document(
    db: Session,
    workspace_id: int,
    company_id: int,
    source: str,
    split: str,
    row_uid: str,
    filename: str,
    content: str,
    source_url: str,
    metadata: dict[str, Any],
) -> DocumentModel | None:
    existing = db.query(DocumentModel).filter(DocumentModel.filename == filename).first()

    from app.config import config as app_config

    os.makedirs(app_config.UPLOAD_DIR, exist_ok=True)
    public_dir = os.path.join(app_config.UPLOAD_DIR, "public_datasets", source, split)
    os.makedirs(public_dir, exist_ok=True)
    stored_path = os.path.join(public_dir, filename)
    with open(stored_path, "w", encoding="utf-8") as f:
        f.write(content)

    doc = existing or DocumentModel(
        filename=filename,
        stored_path=stored_path,
        content_type="text/plain",
        size_bytes=os.path.getsize(stored_path),
        status="pending",
        tags=f"finance,public,{source},{split}",
    )
    if existing:
        doc.stored_path = stored_path
        doc.size_bytes = os.path.getsize(stored_path)
    if not existing:
        db.add(doc)
        db.flush()

    try:
        chunks = split_text(content)
        if not chunks:
            raise ValueError("no chunks")
        settings = db.query(SettingsModel).first()
        embedding_provider = (settings.embedding_provider if settings else None) or config.DEFAULT_EMBEDDING_PROVIDER
        embed_model = (settings.embed_model if settings else None) or config.DEFAULT_EMBED_MODEL
        embeddings = get_embeddings([c["content"] for c in chunks], model=embed_model, provider=embedding_provider)
        delete_document(doc.id, embedding_provider=embedding_provider, embedding_model=embed_model)
        add_chunks(
            chunks,
            embeddings,
            doc.id,
            doc.filename,
            doc.kb_version,
            embedding_provider=embedding_provider,
            embedding_model=embed_model,
            extra_metadata={
                "workspace_id": workspace_id,
                "company_id": company_id,
                "filing_id": metadata.get("filing_id"),
                "company_ticker": metadata.get("company_ticker"),
                "source_dataset": metadata.get("source_dataset"),
                "split": split,
                "row_uid": row_uid,
                "source_url": source_url,
                "public_data_only": True,
            },
        )
        doc.chunk_count = len(chunks)
        doc.status = "completed"
    except Exception as exc:
        doc.status = "failed"
        metadata["failure_reason"] = metadata.get("failure_reason") or f"index_error:{exc}"
    db.commit()
    db.refresh(doc)
    return doc
