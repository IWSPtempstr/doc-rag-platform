import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import EvalCaseModel, WorkspaceModel
from app.services import finance_observability
from app.services.finance_observability import (
    export_finance_agent_jsonl,
    import_finance_agent_jsonl,
    parse_finance_agent_cases,
)


def _db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(WorkspaceModel(id=1, name="Demo", slug="demo"))
    db.commit()
    return db


def test_parse_finance_agent_cases_accepts_jsonl_and_validates_required_fields(tmp_path):
    path = tmp_path / "finance_agent_offline.jsonl"
    rows = [
        {
            "case_uid": "aapl-revenue-2024",
            "question": "What was AAPL revenue?",
            "company_ticker": "AAPL",
            "filing_id": 42,
            "task_type": "numeric",
            "expected_numeric": 100.0,
            "expected_path": ["facts", "calculation", "analysis", "verifier"],
            "expected_tool_groups": ["structured_facts", "calculation"],
            "expected_facts": [{"metric": "Revenues", "value": 100.0}],
        },
        {
            "case_uid": "aapl-risk-2024",
            "question": "Summarize risks.",
            "company_ticker": "AAPL",
            "task_type": "risk_trend",
            "expected_answer": "risk summary",
            "expected_evidence": ["risk factors"],
            "expects_abstain": False,
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    cases = parse_finance_agent_cases(str(path))

    assert [case["case_uid"] for case in cases] == ["aapl-revenue-2024", "aapl-risk-2024"]
    assert cases[0]["metadata_json"]["ticker"] == "AAPL"
    assert cases[0]["metadata_json"]["expected_tool_groups"] == ["structured_facts", "calculation"]


def test_import_finance_agent_jsonl_upserts_cases_and_exports_standard_file(tmp_path, monkeypatch):
    db = _db_session()
    monkeypatch.setattr(finance_observability, "FINANCE_AGENT_DATA_DIR", tmp_path / "exports")
    input_path = tmp_path / "cases.jsonl"
    input_path.write_text(
        json.dumps({
            "case_uid": "case-1",
            "question": "What was revenue?",
            "company_ticker": "MSFT",
            "task_type": "numeric",
            "expected_numeric": 212.0,
            "expected_path": ["facts", "calculation", "analysis", "verifier"],
            "expected_tool_groups": ["structured_facts", "calculation"],
            "status": "approved",
        }) + "\n",
        encoding="utf-8",
    )

    result = import_finance_agent_jsonl(db, workspace_id=1, dataset_name="finance_agent_offline", file_path=str(input_path))
    result_again = import_finance_agent_jsonl(db, workspace_id=1, dataset_name="finance_agent_offline", file_path=str(input_path))
    case_count = db.query(EvalCaseModel).count()
    export = export_finance_agent_jsonl(db, workspace_id=1, dataset_name="finance_agent_offline")

    assert result["case_count"] == 1
    assert result_again["updated"] == 1
    assert case_count == 1
    assert export["case_count"] == 1
    assert export["file_path"].endswith("/exports/finance_agent_offline.jsonl")
