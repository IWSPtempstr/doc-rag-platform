"""Finance agent offline benchmark and observability helpers."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import config
from app.models import AgentRunModel, AgentStepModel, EvalCaseModel, EvalDatasetModel


FINANCE_AGENT_DATA_DIR = Path(config.DATA_DIR) / "evaluations" / "finance_agent"
FINANCE_AGENT_TRACE_LOG = Path(config.TRACE_DIR) / "finance_agent.jsonl"
FINANCE_AGENT_ALERT_LOG = Path(config.TRACE_DIR) / "finance_agent_alerts.jsonl"

_ALERT_THRESHOLDS = {
    "p95_latency_ms": (15000, "gt"),
    "verifier_pass_rate": (0.85, "lt"),
    "trajectory_match_rate": (0.85, "lt"),
    "numeric_accuracy": (0.90, "lt"),
    "unsupported_claim_rate": (0.05, "gt"),
}


def parse_finance_agent_cases(file_path: str) -> list[dict]:
    """Parse JSON/JSONL finance agent benchmark cases into EvalCase-compatible dicts."""
    path = Path(file_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"benchmark file not found: {file_path}")

    raw_cases = _load_json_or_jsonl(path)
    cases: list[dict] = []
    seen: set[str] = set()
    for idx, raw in enumerate(raw_cases, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"line {idx}: case must be a JSON object")
        question = str(raw.get("question") or "").strip()
        if not question:
            raise ValueError(f"line {idx}: missing required field question")

        case_uid = str(raw.get("case_uid") or f"{path.stem}-{idx}").strip()
        if case_uid in seen:
            raise ValueError(f"line {idx}: duplicate case_uid {case_uid}")
        seen.add(case_uid)

        metadata = dict(raw.get("metadata_json") or raw.get("metadata") or {})
        ticker = raw.get("company_ticker") or raw.get("ticker") or metadata.get("ticker")
        if ticker:
            metadata["ticker"] = str(ticker).upper()
        filing_id = raw.get("filing_id") or raw.get("gold_filing_id") or metadata.get("filing_id")
        if filing_id is not None:
            metadata["filing_id"] = filing_id

        for key in (
            "expected_path",
            "expected_tool_groups",
            "expected_facts",
            "expects_abstain",
            "metric_group",
            "input_metrics",
            "quality_flags",
            "failure_reason",
            "admissible",
        ):
            if key in raw:
                metadata[key] = raw[key]
        metadata["source_format"] = "finance_agent_jsonl"

        cases.append({
            "case_uid": case_uid,
            "question": question,
            "expected_answer": raw.get("expected_answer"),
            "expected_evidence": raw.get("expected_evidence"),
            "expected_numeric": _float_or_none(raw.get("expected_numeric")),
            "expected_calculation": raw.get("expected_calculation"),
            "tolerance": _float_or_default(raw.get("tolerance"), 0.01),
            "task_type": raw.get("task_type") or "finance_agent",
            "difficulty": raw.get("difficulty") or "medium",
            "status": raw.get("status") or ("rejected" if metadata.get("admissible") is False else "approved"),
            "gold_filing_id": _int_or_none(raw.get("gold_filing_id") or raw.get("filing_id")),
            "gold_document_id": _int_or_none(raw.get("gold_document_id") or raw.get("document_id")),
            "rubric_json": raw.get("rubric_json") or raw.get("rubric"),
            "metadata_json": metadata,
        })
    return cases


def import_finance_agent_jsonl(db: Session, workspace_id: int, dataset_name: str, file_path: str) -> dict:
    """Import or upsert finance agent benchmark cases from JSON/JSONL."""
    cases = parse_finance_agent_cases(file_path)
    dataset = _get_or_create_offline_dataset(db, workspace_id, dataset_name, file_path)

    created = 0
    updated = 0
    for case in cases:
        row = (
            db.query(EvalCaseModel)
            .filter(EvalCaseModel.dataset_id == dataset.id, EvalCaseModel.case_uid == case["case_uid"])
            .first()
        )
        if row:
            for key, value in case.items():
                setattr(row, key, value)
            updated += 1
        else:
            db.add(EvalCaseModel(dataset_id=dataset.id, **case))
            created += 1

    db.flush()
    dataset.case_count = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset.id).count()
    manifest = dict(dataset.manifest_json or {})
    manifest.update({
        "source_format": "finance_agent_jsonl",
        "last_import_file": str(Path(file_path).expanduser()),
        "last_imported_at": datetime.now(timezone.utc).isoformat(),
        "public_data_only": True,
    })
    dataset.manifest_json = manifest
    db.commit()
    db.refresh(dataset)
    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "case_count": dataset.case_count,
        "created": created,
        "updated": updated,
    }


def export_finance_agent_jsonl(db: Session, workspace_id: int, dataset_name: str) -> dict:
    """Export a finance EvalDataset to the standard JSONL case format."""
    dataset = _find_dataset(db, workspace_id, dataset_name)
    if not dataset:
        raise ValueError(f"dataset not found: {dataset_name}")
    rows = (
        db.query(EvalCaseModel)
        .filter(EvalCaseModel.dataset_id == dataset.id)
        .order_by(EvalCaseModel.id.asc())
        .all()
    )

    FINANCE_AGENT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FINANCE_AGENT_DATA_DIR / f"{_safe_filename(dataset_name)}.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for case in rows:
            payload = _case_to_jsonl_payload(case)
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return {"dataset_id": dataset.id, "dataset_name": dataset.name, "file_path": str(out_path), "case_count": len(rows)}


def compute_trajectory_detail(
    actual_path: list[str] | None,
    expected_path: list[str] | None,
    actual_tool_groups: list[str] | None,
    expected_tool_groups: list[str] | None,
) -> dict:
    """Compare actual AgentStep nodes/tool groups with benchmark expectations."""
    actual = [str(item) for item in (actual_path or []) if item]
    expected = _filter_path(expected_path or [])
    actual_for_path = _filter_path(actual)
    matched = sum(1 for node in expected if node in actual_for_path)
    path_recall = round(matched / len(expected), 4) if expected else None
    path_match = bool(expected) and actual_for_path == expected

    actual_tools = set(actual_tool_groups or [])
    expected_tools = set(expected_tool_groups or [])
    required_tool_recall = (
        round(len(actual_tools & expected_tools) / len(expected_tools), 4)
        if expected_tools else None
    )
    unexpected_tool_rate = (
        round(len(actual_tools - expected_tools) / len(actual_tools), 4)
        if actual_tools else 0.0
    )
    retry_count = sum(1 for node in actual if "retry" in node)
    retry_rate = round(retry_count / len(actual), 4) if actual else 0.0
    verifier_index = next((i for i, node in enumerate(actual) if _base_node(node) == "verifier"), None)
    verifier_repair = verifier_index is not None and any("retry" in node for node in actual[verifier_index + 1:])

    return {
        "actual_path": actual,
        "expected_path": expected,
        "path_match": path_match,
        "path_recall": path_recall,
        "required_tool_recall": required_tool_recall,
        "unexpected_tool_rate": unexpected_tool_rate,
        "retry_count": retry_count,
        "retry_rate": retry_rate,
        "verifier_repair": verifier_repair,
    }


def build_agent_run_trace(db: Session, run_id: int) -> dict:
    """Build a trace payload for one AgentRun from DB rows."""
    run = db.query(AgentRunModel).filter(AgentRunModel.id == run_id).first()
    if not run:
        raise ValueError(f"agent run not found: {run_id}")
    steps = (
        db.query(AgentStepModel)
        .filter(AgentStepModel.run_id == run_id)
        .order_by(AgentStepModel.step_order.asc())
        .all()
    )
    step_payloads = [_step_trace_payload(step) for step in steps]
    token_usage = {
        "prompt_tokens": sum(item["token_usage"]["prompt_tokens"] for item in step_payloads),
        "completion_tokens": sum(item["token_usage"]["completion_tokens"] for item in step_payloads),
        "total_tokens": sum(item["token_usage"]["total_tokens"] for item in step_payloads),
        "estimated_tokens": any(item["token_usage"].get("estimated_tokens") for item in step_payloads),
    }
    duration_ms = _duration_between(run.created_at, run.completed_at)
    if duration_ms is None:
        duration_ms = round(sum(step.duration_ms or 0 for step in steps), 2)

    verification = run.verification or {}
    failure_type = None
    if run.status == "failed":
        failure_type = "agent_failed"
    elif verification and not verification.get("passed", True):
        failure_type = "verifier_failed"

    return {
        "type": "finance_agent_run",
        "run_id": run.id,
        "workspace_id": run.workspace_id,
        "company_id": run.company_id,
        "filing_id": run.filing_id,
        "question": run.question,
        "mode": run.mode,
        "status": run.status,
        "answer_preview": (run.answer or "")[:500],
        "end_to_end_duration_ms": duration_ms,
        "token_usage": token_usage,
        "model": _first_step_value(step_payloads, "model"),
        "provider": _first_step_value(step_payloads, "provider"),
        "cache_hit": any(item.get("cache_hit") for item in step_payloads),
        "failure_type": failure_type,
        "verification": verification,
        "created_at": _dt_to_iso(run.created_at),
        "completed_at": _dt_to_iso(run.completed_at),
        "timestamp": time.time(),
        "steps": step_payloads,
    }


def write_finance_agent_trace(db: Session, run_id: int) -> dict:
    trace = build_agent_run_trace(db, run_id)
    _append_jsonl(FINANCE_AGENT_TRACE_LOG, trace)
    alerts = build_alert_events(
        {"efficiency": {"p95_latency_ms": trace.get("end_to_end_duration_ms") or 0}},
        source="agent_run",
        dataset_name=None,
        run_id=run_id,
    )
    for alert in alerts:
        _append_jsonl(FINANCE_AGENT_ALERT_LOG, alert)
    return trace


def get_agent_run_trace(db: Session, workspace_id: int, run_id: int) -> dict | None:
    run = (
        db.query(AgentRunModel)
        .filter(AgentRunModel.id == run_id, AgentRunModel.workspace_id == workspace_id)
        .first()
    )
    if not run:
        return None
    return build_agent_run_trace(db, run_id)


def build_alert_events(
    metrics: dict,
    source: str,
    dataset_name: str | None = None,
    result_id: int | None = None,
    run_id: int | None = None,
) -> list[dict]:
    """Build local alert events from threshold rules."""
    events: list[dict] = []
    flat_metrics = dict(metrics or {})
    efficiency = flat_metrics.get("efficiency") or {}
    if isinstance(efficiency, dict) and "p95_latency_ms" in efficiency:
        flat_metrics["p95_latency_ms"] = efficiency["p95_latency_ms"]

    for metric, (threshold, direction) in _ALERT_THRESHOLDS.items():
        value = flat_metrics.get(metric)
        if value is None:
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        triggered = numeric_value > threshold if direction == "gt" else numeric_value < threshold
        if not triggered:
            continue
        events.append({
            "type": "finance_agent_alert",
            "alert_type": metric,
            "source": source,
            "dataset_name": dataset_name,
            "result_id": result_id,
            "run_id": run_id,
            "metric_value": numeric_value,
            "threshold": threshold,
            "direction": direction,
            "severity": "critical" if metric in {"numeric_accuracy", "unsupported_claim_rate"} else "warning",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "message": f"{metric}={numeric_value} triggered threshold {direction} {threshold}",
        })
    return events


def record_finance_alerts(metrics: dict, source: str, dataset_name: str | None = None,
                          result_id: int | None = None, run_id: int | None = None) -> list[dict]:
    alerts = build_alert_events(metrics, source=source, dataset_name=dataset_name, result_id=result_id, run_id=run_id)
    for alert in alerts:
        _append_jsonl(FINANCE_AGENT_ALERT_LOG, alert)
    return alerts


def get_finance_observability_alerts(limit: int = 50) -> list[dict]:
    return _read_tail(FINANCE_AGENT_ALERT_LOG, limit)


def estimate_tokens(text: str | None) -> int:
    """Cheap local fallback for providers that do not return usage."""
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def _load_json_or_jsonl(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, dict):
            payload = payload.get("cases") or payload.get("data") or [payload]
        if not isinstance(payload, list):
            raise ValueError("JSON benchmark file must contain a list or {cases: [...]}")
        return payload
    rows = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_no}: invalid JSONL row: {exc}") from exc
    return rows


def _get_or_create_offline_dataset(db: Session, workspace_id: int, dataset_name: str, file_path: str) -> EvalDatasetModel:
    dataset = _find_dataset(db, workspace_id, dataset_name)
    if dataset:
        return dataset
    dataset = EvalDatasetModel(
        workspace_id=workspace_id,
        name=dataset_name,
        source="finance_agent_offline",
        version="v1",
        description="Finance agent offline JSONL regression benchmark",
        source_url=str(Path(file_path).expanduser()),
        license_note="Derived from public filings/public benchmark data",
        manifest_json={"public_data_only": True, "source_format": "finance_agent_jsonl"},
    )
    db.add(dataset)
    db.flush()
    return dataset


def _find_dataset(db: Session, workspace_id: int, dataset_name: str) -> EvalDatasetModel | None:
    return (
        db.query(EvalDatasetModel)
        .filter(EvalDatasetModel.workspace_id == workspace_id, EvalDatasetModel.name == dataset_name)
        .first()
        or db.query(EvalDatasetModel)
        .filter(EvalDatasetModel.workspace_id == workspace_id, EvalDatasetModel.source == dataset_name)
        .first()
    )


def _case_to_jsonl_payload(case: EvalCaseModel) -> dict:
    metadata = case.metadata_json or {}
    payload = {
        "case_uid": case.case_uid,
        "question": case.question,
        "company_ticker": metadata.get("ticker"),
        "filing_id": case.gold_filing_id or metadata.get("filing_id"),
        "task_type": case.task_type,
        "expected_answer": case.expected_answer,
        "expected_evidence": case.expected_evidence,
        "expected_numeric": case.expected_numeric,
        "expected_calculation": case.expected_calculation,
        "tolerance": case.tolerance,
        "expected_path": metadata.get("expected_path"),
        "expected_tool_groups": metadata.get("expected_tool_groups"),
        "expected_facts": metadata.get("expected_facts"),
        "expects_abstain": metadata.get("expects_abstain"),
        "status": case.status,
        "difficulty": case.difficulty,
        "rubric_json": case.rubric_json,
        "metadata_json": metadata,
    }
    return {key: value for key, value in payload.items() if value is not None}


def _filter_path(path: list[str]) -> list[str]:
    return [str(node) for node in path if str(node) not in {"supervisor", "done", "END"}]


def _base_node(node: str) -> str:
    if "_retry" in node:
        return node.split("_retry", 1)[0]
    if node.startswith("retrieval_retry"):
        return "retrieval"
    return node


def _step_trace_payload(step: AgentStepModel) -> dict:
    input_json = step.input_json or {}
    output_json = step.output_json or {}
    prompt_tokens = _usage_value(input_json, "prompt_tokens") + _usage_value(output_json, "prompt_tokens")
    completion_tokens = _usage_value(input_json, "completion_tokens") + _usage_value(output_json, "completion_tokens")
    total_tokens = _usage_value(input_json, "total_tokens") + _usage_value(output_json, "total_tokens")
    if total_tokens == 0 and (prompt_tokens or completion_tokens):
        total_tokens = prompt_tokens + completion_tokens
    estimated_tokens = bool(input_json.get("estimated_tokens") or output_json.get("estimated_tokens"))
    if total_tokens == 0 and output_json.get("answer_preview"):
        completion_tokens = estimate_tokens(output_json.get("answer_preview"))
        total_tokens = completion_tokens
        estimated_tokens = True
    return {
        "id": step.id,
        "step_order": step.step_order,
        "node_name": step.node_name,
        "status": step.status,
        "duration_ms": step.duration_ms or 0,
        "error": step.error,
        "model": output_json.get("model") or input_json.get("model"),
        "provider": output_json.get("provider") or input_json.get("provider"),
        "cache_hit": bool(output_json.get("cache_hit") or input_json.get("cache_hit")),
        "failure_type": output_json.get("failure_type") or ("node_failed" if step.status == "failed" else None),
        "token_usage": {
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "total_tokens": int(total_tokens),
            "estimated_tokens": estimated_tokens,
        },
        "input_json": input_json,
        "output_json": output_json,
        "created_at": _dt_to_iso(step.created_at),
    }


def _usage_value(payload: dict, key: str) -> int:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    value = payload.get(key) if isinstance(payload, dict) else None
    if value is None and isinstance(usage, dict):
        value = usage.get(key)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _first_step_value(step_payloads: list[dict], key: str) -> Any:
    for step in step_payloads:
        if step.get(key):
            return step[key]
    return None


def _duration_between(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return round((end - start).total_seconds() * 1000, 2)


def _dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _append_jsonl(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _read_tail(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[-limit:]


def _safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in value)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _float_or_default(value: Any, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
