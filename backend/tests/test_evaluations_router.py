import pytest
from fastapi import HTTPException

from app.routers import evaluations
from app.schemas import EvaluationRunRequest


class _FakeQuery:
    def first(self):
        return None


class _FakeDB:
    def query(self, _model):
        return _FakeQuery()


def test_evaluation_route_returns_structured_error_on_runtime_failure(monkeypatch):
    def boom(**_kwargs):
        raise RuntimeError("API 生成失败: bad model")

    monkeypatch.setattr(evaluations, "run_evaluation", boom)

    with pytest.raises(HTTPException) as exc:
        evaluations.run(EvaluationRunRequest(strategy="dense"), _FakeDB())

    assert exc.value.status_code == 502
    assert exc.value.detail == {"message": "API 生成失败: bad model"}
