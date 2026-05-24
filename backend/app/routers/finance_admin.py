"""Admin-only A-share finance operations."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import EvalResultModel, UserModel, WorkspaceModel
from app.routers.auth import get_current_admin_workspace
from app.routers.finance import _build_ashare_daily_job_status, _build_connector_status_rows, _test_connector_by_name
from app.services.ashare_daily_scheduler import run_daily_sync_for_workspace

router = APIRouter(prefix="/api/admin/finance", tags=["Finance Admin"])


@router.get("/connectors/status", response_model=dict)
def admin_connector_status(
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    return {
        "connectors": _build_connector_status_rows(db, workspace.id),
        "daily_jobs": [_build_ashare_daily_job_status(db, workspace.id)],
    }


@router.post("/connectors/{name}/test", response_model=dict)
def admin_test_connector(
    name: str,
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
):
    return _test_connector_by_name(name)


@router.post("/jobs/daily-sync/run", response_model=dict)
def run_daily_sync(
    date: str | None = Query(default=None),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    _user, workspace = ws
    trade_date = date or datetime.now(timezone.utc).date().isoformat()
    try:
        result = run_daily_sync_for_workspace(db, workspace.id, trade_date=trade_date, source="manual_admin")
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc
    return result


@router.get("/jobs/daily-sync/history", response_model=list[dict])
def daily_sync_history(
    limit: int = Query(default=30, ge=1, le=200),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    rows = (
        db.query(DataSyncJobModel)
        .filter(DataSyncJobModel.workspace_id == workspace.id, DataSyncJobModel.job_type == "daily_sync")
        .order_by(DataSyncJobModel.started_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "job_type": row.job_type,
            "source": row.source,
            "status": row.status,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "failure_reason": row.failure_reason,
            "metrics": row.metrics or {},
        }
        for row in rows
    ]


@router.get("/evaluations/results", response_model=list[dict])
def admin_eval_results(
    limit: int = Query(default=30, ge=1, le=100),
    ws: tuple[UserModel, WorkspaceModel] = Depends(get_current_admin_workspace),
    db: Session = Depends(get_db),
):
    _, workspace = ws
    rows = (
        db.query(EvalResultModel)
        .filter(EvalResultModel.workspace_id == workspace.id)
        .order_by(EvalResultModel.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "dataset_id": row.dataset_id,
            "strategy": row.strategy,
            "metrics": row.metrics or {},
            "created_at": row.created_at,
        }
        for row in rows
    ]
