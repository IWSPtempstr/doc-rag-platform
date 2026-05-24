"""Finance evaluation adapters and metric helpers."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import EvalCaseModel, EvalDatasetModel, EvalResultModel, FilingModel
from app.services.finance_agent import run_finance_agent
from app.services.finance_observability import compute_trajectory_detail, record_finance_alerts

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
    answer_score_sum = 0.0
    answer_score_total = 0
    evidence_score_sum = 0.0
    evidence_score_total = 0
    unsupported_claims = 0
    calculation_consistency_hits = 0
    calculation_consistency_total = 0
    trajectory_matches = 0
    trajectory_total = 0
    path_recall_sum = 0.0
    path_recall_total = 0
    tool_recall_sum = 0.0
    tool_recall_total = 0
    unexpected_tool_sum = 0.0
    unexpected_tool_total = 0
    retry_cases = 0
    verifier_repair_cases = 0
    latency_values: list[float] = []
    total_tokens_values: list[int] = []
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
        steps = result.get("steps", [])

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

        # ── response quality / judge-style deterministic scores ──
        answer_score = None
        if case.expected_answer and case.expected_numeric is None:
            answer_score = _judge_text_score(answer, case.expected_answer)
            answer_score_sum += answer_score
            answer_score_total += 1

        evidence_score = _judge_evidence_score(citations, case.expected_evidence)
        if evidence_score is not None:
            evidence_score_sum += evidence_score
            evidence_score_total += 1

        unsupported_claim = _has_unsupported_claims(verification)
        unsupported_claims += int(unsupported_claim)

        calculation_consistent = None
        if case.expected_numeric is not None or calculations or metadata.get("input_metrics"):
            calculation_consistent = _calculation_consistent(
                facts, calculations, metadata, numeric_hit, fact_grounded, case.expected_numeric
            )
            calculation_consistency_total += 1
            calculation_consistency_hits += int(calculation_consistent)

        # ── trajectory / tool-group / efficiency ──
        actual_path = [step.get("node_name") for step in steps if step.get("node_name")]
        actual_tool_groups = verification.get("tool_groups") or []
        expected_path = metadata.get("expected_path") or []
        expected_tool_groups = metadata.get("expected_tool_groups") or []
        trajectory = compute_trajectory_detail(actual_path, expected_path, actual_tool_groups, expected_tool_groups)
        if expected_path:
            trajectory_total += 1
            trajectory_matches += int(trajectory["path_match"])
        if trajectory.get("path_recall") is not None:
            path_recall_sum += trajectory["path_recall"]
            path_recall_total += 1
        if trajectory.get("required_tool_recall") is not None:
            tool_recall_sum += trajectory["required_tool_recall"]
            tool_recall_total += 1
        if actual_tool_groups:
            unexpected_tool_sum += trajectory.get("unexpected_tool_rate") or 0
            unexpected_tool_total += 1
        retry_cases += int((trajectory.get("retry_count") or 0) > 0)
        verifier_repair_cases += int(bool(trajectory.get("verifier_repair")))

        latency = _case_latency_ms(steps)
        if latency is not None:
            latency_values.append(latency)
        total_tokens_values.append(_case_total_tokens(steps))

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
            "answer_judge_score": answer_score,
            "evidence_judge_score": evidence_score,
            "unsupported_claim": unsupported_claim,
            "calculation_consistent": calculation_consistent,
            "trajectory": trajectory,
            "latency_ms": latency,
            "total_tokens": total_tokens_values[-1] if total_tokens_values else 0,
            "failure_type": _result_failure_type(metadata, citations, overlap, verifier_pass, task_type),
            "verification": verification,
        }
        details.append(detail)

        per_task.setdefault(task_type, {
            "total": 0, "evidence_hits": 0, "numeric_hits": 0, "numeric_total": 0, "overlap_total": 0,
            "fact_groundings": 0, "fact_grounding_total": 0, "abstain_correct": 0, "abstain_total": 0,
            "answer_score_sum": 0.0, "answer_score_total": 0, "evidence_score_sum": 0.0, "evidence_score_total": 0,
            "unsupported_claims": 0, "calculation_consistency_hits": 0, "calculation_consistency_total": 0,
            "trajectory_matches": 0, "trajectory_total": 0, "tool_recall_sum": 0.0, "tool_recall_total": 0,
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
        if answer_score is not None:
            per_task[task_type]["answer_score_sum"] += answer_score
            per_task[task_type]["answer_score_total"] += 1
        if evidence_score is not None:
            per_task[task_type]["evidence_score_sum"] += evidence_score
            per_task[task_type]["evidence_score_total"] += 1
        per_task[task_type]["unsupported_claims"] += int(unsupported_claim)
        if calculation_consistent is not None:
            per_task[task_type]["calculation_consistency_total"] += 1
            per_task[task_type]["calculation_consistency_hits"] += int(calculation_consistent)
        if expected_path:
            per_task[task_type]["trajectory_total"] += 1
            per_task[task_type]["trajectory_matches"] += int(trajectory["path_match"])
        if trajectory.get("required_tool_recall") is not None:
            per_task[task_type]["tool_recall_sum"] += trajectory["required_tool_recall"]
            per_task[task_type]["tool_recall_total"] += 1

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
        "answer_judge_score": round(answer_score_sum / max(answer_score_total, 1), 4) if answer_score_total else None,
        "evidence_judge_score": round(evidence_score_sum / max(evidence_score_total, 1), 4) if evidence_score_total else None,
        "unsupported_claim_rate": round(unsupported_claims / total, 4),
        "calculation_consistency_rate": round(calculation_consistency_hits / max(calculation_consistency_total, 1), 4) if calculation_consistency_total else None,
        "trajectory_match_rate": round(trajectory_matches / max(trajectory_total, 1), 4) if trajectory_total else None,
        "path_recall": round(path_recall_sum / max(path_recall_total, 1), 4) if path_recall_total else None,
        "required_tool_recall": round(tool_recall_sum / max(tool_recall_total, 1), 4) if tool_recall_total else None,
        "unexpected_tool_rate": round(unexpected_tool_sum / max(unexpected_tool_total, 1), 4) if unexpected_tool_total else None,
        "retry_rate": round(retry_cases / total, 4),
        "verifier_repair_rate": round(verifier_repair_cases / total, 4),
        "efficiency": {
            "avg_latency_ms": round(sum(latency_values) / max(len(latency_values), 1), 2) if latency_values else None,
            "p95_latency_ms": _p95(latency_values),
            "max_latency_ms": round(max(latency_values), 2) if latency_values else None,
            "total_tokens": sum(total_tokens_values),
            "avg_total_tokens": round(sum(total_tokens_values) / max(len(total_tokens_values), 1), 2) if total_tokens_values else 0,
            "estimated_tokens": True,
        },
        "by_task_type": {
            k: {
                "total": v["total"],
                "retrieval_hit_rate": round(v["evidence_hits"] / max(v["total"], 1), 4),
                "numeric_accuracy": round(v["numeric_hits"] / max(v["numeric_total"], 1), 4) if v["numeric_total"] else None,
                "evidence_recall": round(v["overlap_total"] / max(v["total"], 1), 4),
                "fact_grounding_rate": round(v["fact_groundings"] / max(v["fact_grounding_total"], 1), 4) if v["fact_grounding_total"] else None,
                "abstain_accuracy": round(v["abstain_correct"] / max(v["abstain_total"], 1), 4) if v["abstain_total"] else None,
                "answer_judge_score": round(v["answer_score_sum"] / max(v["answer_score_total"], 1), 4) if v["answer_score_total"] else None,
                "evidence_judge_score": round(v["evidence_score_sum"] / max(v["evidence_score_total"], 1), 4) if v["evidence_score_total"] else None,
                "unsupported_claim_rate": round(v["unsupported_claims"] / max(v["total"], 1), 4),
                "calculation_consistency_rate": round(v["calculation_consistency_hits"] / max(v["calculation_consistency_total"], 1), 4) if v["calculation_consistency_total"] else None,
                "trajectory_match_rate": round(v["trajectory_matches"] / max(v["trajectory_total"], 1), 4) if v["trajectory_total"] else None,
                "required_tool_recall": round(v["tool_recall_sum"] / max(v["tool_recall_total"], 1), 4) if v["tool_recall_total"] else None,
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
    record_finance_alerts(metrics, source="evaluation", dataset_name=dataset.name, result_id=row.id)
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


def _judge_text_score(answer: str, expected_answer: str | None) -> float:
    if not expected_answer:
        return 0.0
    if expected_answer.lower() in (answer or "").lower():
        return 1.0
    return round(_token_jaccard(answer or "", expected_answer), 4)


def _judge_evidence_score(citations: list[dict], expected_evidence: list | str | dict | None) -> float | None:
    expected_items = _evidence_items(expected_evidence)
    if not expected_items:
        return None
    hits = _evidence_overlap(citations, expected_items)
    return round(hits / max(len(expected_items), 1), 4)


def _has_unsupported_claims(verification: dict) -> bool:
    errors = verification.get("errors") or []
    return any(
        "未在引用" in str(error)
        or "unsupported" in str(error).lower()
        or "不应提供具体数值" in str(error)
        for error in errors
    )


def _calculation_consistent(
    facts: list[dict],
    calculations: list[dict],
    metadata: dict,
    numeric_hit: bool,
    fact_grounded: bool,
    expected_numeric: float | None,
) -> bool:
    if expected_numeric is not None:
        return bool(numeric_hit and (fact_grounded or not metadata.get("input_metrics")))
    if metadata.get("input_metrics"):
        return bool(fact_grounded)
    if not calculations:
        return True
    for calc in calculations:
        if calc.get("value") is None:
            return False
        if calc.get("confidence", 1.0) < 0.5:
            return False
        inputs = calc.get("inputs") or {}
        if any(value is None for value in inputs.values()):
            return False
    return bool(facts)


def _case_latency_ms(steps: list[dict]) -> float | None:
    durations = [step.get("duration_ms") for step in steps if step.get("duration_ms") is not None]
    if not durations:
        return None
    return round(sum(float(duration) for duration in durations), 2)


def _case_total_tokens(steps: list[dict]) -> int:
    total = 0
    for step in steps:
        output = step.get("output_json") or {}
        input_json = step.get("input_json") or {}
        total += _usage_value(output, "total_tokens")
        total += _usage_value(input_json, "total_tokens")
    return total


def _usage_value(payload: dict, key: str) -> int:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    value = payload.get(key) if isinstance(payload, dict) else None
    if value is None and isinstance(usage, dict):
        value = usage.get(key)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(0.95 * (len(ordered) - 1))))
    return round(ordered[idx], 2)


def _evidence_items(expected_evidence: list | str | dict | None) -> list[str]:
    if not expected_evidence:
        return []
    if isinstance(expected_evidence, str):
        return [expected_evidence]
    if isinstance(expected_evidence, dict):
        return [
            expected_evidence.get("text_snippet")
            or expected_evidence.get("text")
            or expected_evidence.get("evidence")
            or str(expected_evidence)
        ]
    return [str(item) for item in expected_evidence if item is not None]


def _token_jaccard(a: str, b: str) -> float:
    tokens_a = set(_judge_tokens(a))
    tokens_b = set(_judge_tokens(b))
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def _judge_tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", text.lower())


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
        "ashare_daily_brief": "A 股每日简报评估集",
        "ashare_announcement": "A 股公告检索评估集",
        "ashare_financial_fact": "A 股财务事实评估集",
        "ashare_market_sentiment": "A 股行情与情绪评估集",
        "finance_agent_offline": "A 股 Agent 离线回归集",
    }.get(source, source)


def _seed_cases(source: str, filing: FilingModel | None) -> list[dict]:
    ticker = filing.company.ticker if filing and filing.company else None
    filing_id = filing.id if filing else None
    base_metadata = {
        "ticker": ticker,
        "filing_id": filing_id,
        "source_dataset": source,
        "admissible": bool(ticker),
        "failure_reason": None if ticker else "missing_ashare_company",
    }
    status = "approved" if ticker else "draft"
    if source == "ashare_financial_fact":
        return [{
            "question": "提取该公司的营业总收入、净利润、资产总计等核心财务事实。",
            "task_type": "financial_fact",
            "expected_answer": "营业总收入 净利润 资产总计",
            "metadata_json": {**base_metadata, "expected_tool_groups": ["structured_facts"]},
            "status": status,
        }]
    if source == "ashare_announcement":
        return [{
            "question": "总结该公司最新年报公告中管理层讨论与风险相关内容。",
            "task_type": "announcement_retrieval",
            "expected_answer": "管理层讨论 风险 公告引用",
            "metadata_json": {**base_metadata, "expected_tool_groups": ["filing_retrieval"]},
            "status": status,
        }]
    if source == "ashare_market_sentiment":
        return [{
            "question": "结合行情事实和市场情绪，解释该公司今日热度变化，避免输出交易建议。",
            "task_type": "market_sentiment",
            "expected_answer": "行情 热度 情绪 不提供交易建议",
            "metadata_json": {**base_metadata, "expected_tool_groups": ["market_facts"]},
            "status": status,
        }]
    return [
        {
            "question": "生成该公司的每日简报，包含公告变化、财务事实变化、行情/热度/情绪变化解释。",
            "task_type": "daily_brief",
            "expected_answer": "公告变化 财务事实 行情 热度 情绪",
            "metadata_json": {**base_metadata, "expected_tool_groups": ["filing_retrieval", "structured_facts", "market_facts"]},
            "status": status,
        },
        {
            "question": "如果公告或结构化事实不足，请说明缺失原因，不要编造数值或交易信号。",
            "task_type": "abstain",
            "expected_answer": "缺失原因 不提供交易建议",
            "metadata_json": {**base_metadata, "expects_abstain": True},
            "status": status,
        },
    ]
