"""A-share daily sync scheduler."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import DataSyncJobModel, MembershipModel, WorkspaceModel
from app.services.ashare_daily_brief import get_or_create_daily_brief, sync_market_sentiment

_scheduler_task: asyncio.Task | None = None


def next_daily_run_at(hour: int = 3, utc_offset_hours: int = 8) -> datetime:
    tz = timezone(timedelta(hours=utc_offset_hours))
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def run_daily_sync_for_workspace(
    db: Session,
    workspace_id: int,
    trade_date: str | None = None,
    source: str = "scheduled",
) -> dict:
    date_value = trade_date or datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    job = DataSyncJobModel(
        workspace_id=workspace_id,
        job_type="daily_sync",
        source=source,
        status="running",
        metrics={"trade_date": date_value},
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    metrics = {"trade_date": date_value, "brief_items": 0, "brief_users": 0, "sentiment_upserted": 0}
    try:
        user_ids = [
            row[0]
            for row in db.query(distinct(MembershipModel.user_id))
            .filter(MembershipModel.workspace_id == workspace_id)
            .all()
        ]
        if not user_ids:
            payload = get_or_create_daily_brief(db, workspace_id, None, date_value)
            metrics["brief_items"] += len(payload.get("items") or [])
        for user_id in user_ids:
            payload = get_or_create_daily_brief(db, workspace_id, user_id, date_value)
            metrics["brief_users"] += 1
            metrics["brief_items"] += len(payload.get("items") or [])
        try:
            metrics["sentiment_upserted"] = sync_market_sentiment(db, workspace_id)
        except Exception as exc:
            metrics["sentiment_failure_reason"] = str(exc)
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.metrics = metrics
        db.commit()
        return {"id": job.id, "status": job.status, "metrics": metrics}
    except Exception as exc:
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc)
        job.failure_reason = str(exc)
        job.metrics = metrics
        db.commit()
        raise


def run_daily_sync_for_all_workspaces(trade_date: str | None = None) -> list[dict]:
    db = SessionLocal()
    try:
        workspaces = db.query(WorkspaceModel).all()
        return [
            run_daily_sync_for_workspace(db, workspace.id, trade_date=trade_date, source="scheduled:03:00")
            for workspace in workspaces
        ]
    finally:
        db.close()


async def _scheduler_loop(hour: int = 3, utc_offset_hours: int = 8) -> None:
    while True:
        target = next_daily_run_at(hour=hour, utc_offset_hours=utc_offset_hours)
        sleep_seconds = max((target - datetime.now(target.tzinfo)).total_seconds(), 1)
        await asyncio.sleep(sleep_seconds)
        try:
            await asyncio.to_thread(run_daily_sync_for_all_workspaces)
        except Exception as exc:
            print(f"[ashare-daily-sync] failed: {exc}")


def start_ashare_daily_scheduler(hour: int = 3, utc_offset_hours: int = 8) -> asyncio.Task:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop(hour=hour, utc_offset_hours=utc_offset_hours))
    return _scheduler_task
