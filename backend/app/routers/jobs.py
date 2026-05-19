"""任务管理路由"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import JobModel
from app.schemas import JobResponse
from app.redis_client import get_job_progress

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(JobModel).filter(JobModel.id == job_id).first()
    if not job:
        raise HTTPException(404, "任务不存在")

    progress = get_job_progress(job_id)

    return JobResponse(
        id=job.id,
        document_id=job.document_id,
        type=job.type,
        status=job.status,
        error=job.error,
        retry_count=job.retry_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
        progress=progress,
    )
