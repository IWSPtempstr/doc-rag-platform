from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import AgentRunModel, AgentStepModel, CompanyModel, FilingModel, WorkspaceModel
from app.services.finance_observability import (
    build_alert_events,
    build_agent_run_trace,
    compute_trajectory_detail,
)


def _db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_compute_trajectory_detail_detects_path_tools_and_retries():
    detail = compute_trajectory_detail(
        actual_path=["retrieval", "facts", "calculation", "verifier", "retrieval_retry", "analysis_retry", "verifier_retry"],
        expected_path=["retrieval", "facts", "calculation", "analysis", "verifier"],
        actual_tool_groups=["filing_retrieval", "structured_facts", "calculation", "market_facts"],
        expected_tool_groups=["filing_retrieval", "structured_facts", "calculation"],
    )

    assert detail["path_match"] is False
    assert detail["path_recall"] == 0.8
    assert detail["required_tool_recall"] == 1.0
    assert detail["unexpected_tool_rate"] == 0.25
    assert detail["retry_count"] == 3
    assert detail["verifier_repair"] is True


def test_build_agent_run_trace_includes_latency_tokens_steps_and_failure_type():
    db = _db_session()
    workspace = WorkspaceModel(id=1, name="Demo", slug="demo")
    company = CompanyModel(id=1, workspace_id=1, ticker="AAPL", name="Apple")
    filing = FilingModel(id=1, workspace_id=1, company_id=1, fiscal_year=2024)
    started = datetime.now(timezone.utc) - timedelta(seconds=2)
    completed = datetime.now(timezone.utc)
    run = AgentRunModel(
        id=1,
        workspace_id=1,
        company_id=1,
        filing_id=1,
        question="What is revenue?",
        mode="eval",
        status="completed",
        answer="Revenue was 100.",
        verification={"passed": False, "errors": ["缺少引用证据"]},
        created_at=started,
        completed_at=completed,
    )
    step = AgentStepModel(
        run_id=1,
        step_order=1,
        node_name="facts",
        status="completed",
        input_json={"prompt_tokens": 3},
        output_json={"completion_tokens": 4, "total_tokens": 7, "model": "deterministic"},
        duration_ms=123.4,
    )
    db.add_all([workspace, company, filing, run, step])
    db.commit()

    trace = build_agent_run_trace(db, run_id=1)

    assert trace["run_id"] == 1
    assert trace["end_to_end_duration_ms"] >= 1900
    assert trace["token_usage"]["total_tokens"] == 7
    assert trace["failure_type"] == "verifier_failed"
    assert trace["steps"][0]["duration_ms"] == 123.4


def test_build_alert_events_applies_finance_agent_thresholds():
    metrics = {
        "numeric_accuracy": 0.75,
        "verifier_pass_rate": 0.5,
        "trajectory_match_rate": 0.7,
        "unsupported_claim_rate": 0.1,
        "efficiency": {"p95_latency_ms": 21000},
    }

    alerts = build_alert_events(metrics, source="evaluation", dataset_name="finance_agent_offline")
    alert_types = {alert["alert_type"] for alert in alerts}

    assert {
        "p95_latency_ms",
        "verifier_pass_rate",
        "trajectory_match_rate",
        "numeric_accuracy",
        "unsupported_claim_rate",
    }.issubset(alert_types)
