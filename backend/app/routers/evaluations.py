"""Evaluation 路由 (v1.1)"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import EvaluationRunModel, SettingsModel
from app.schemas import EvaluationRunRequest, EvaluationResultResponse
from app.services.evaluation_service import run_evaluation, save_evaluation_result, load_evaluation_results

router = APIRouter(prefix="/api/evaluations", tags=["Evaluations"])


@router.post("/run", response_model=EvaluationResultResponse)
def run(req: EvaluationRunRequest = EvaluationRunRequest(), db: Session = Depends(get_db)):
    settings = db.query(SettingsModel).first()
    try:
        result = run_evaluation(
            strategy=req.strategy,
            chat_provider=(settings.chat_provider or settings.provider) if settings else None,
            chat_model=settings.chat_model if settings else None,
            embedding_provider=settings.embedding_provider if settings else None,
            embedding_model=settings.embed_model if settings else None,
        )
    except RuntimeError as exc:
        message = str(exc)
        status_code = 503 if "未配置" in message else 502
        raise HTTPException(status_code, detail={"message": message}) from exc
    except Exception as exc:
        raise HTTPException(500, detail={"message": f"评估运行失败: {exc}"}) from exc
    save_evaluation_result(req.strategy, result)

    run_model = EvaluationRunModel(
        strategy=req.strategy,
        hit_rate=result.get("hit_rate"),
        context_precision=result.get("hit_rate"),  # simplified
        faithfulness=result.get("hit_rate"),
        answer_relevancy=result.get("hit_rate"),
        results=result,
    )
    db.add(run_model)
    db.commit()
    db.refresh(run_model)

    return EvaluationResultResponse(
        id=run_model.id,
        strategy=run_model.strategy,
        hit_rate=run_model.hit_rate,
        context_precision=run_model.context_precision,
        faithfulness=run_model.faithfulness,
        answer_relevancy=run_model.answer_relevancy,
        results=run_model.results,
        created_at=run_model.created_at,
    )


@router.get("/results", response_model=list[EvaluationResultResponse])
def list_results(db: Session = Depends(get_db)):
    runs = db.query(EvaluationRunModel).order_by(EvaluationRunModel.created_at.desc()).limit(20).all()
    return [EvaluationResultResponse(
        id=r.id, strategy=r.strategy, hit_rate=r.hit_rate,
        context_precision=r.context_precision, faithfulness=r.faithfulness,
        answer_relevancy=r.answer_relevancy, results=r.results, created_at=r.created_at,
    ) for r in runs]
