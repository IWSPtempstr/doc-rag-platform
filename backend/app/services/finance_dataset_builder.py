"""A-share finance evaluation dataset governance."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import EvalCaseModel, EvalDatasetModel


def freeze_dataset(db: Session, dataset_id: int) -> EvalDatasetModel:
    """Freeze an evaluation set after rejecting inadmissible approved cases."""
    dataset = db.query(EvalDatasetModel).filter(EvalDatasetModel.id == dataset_id).first()
    if not dataset:
        raise ValueError("Dataset not found")

    _reject_inadmissible_cases(db, dataset_id)
    approved = (
        db.query(EvalCaseModel)
        .filter(EvalCaseModel.dataset_id == dataset_id, EvalCaseModel.status == "approved")
        .count()
    )
    dataset.case_count = approved
    dataset.frozen_at = datetime.now(timezone.utc)
    db.commit()
    return dataset


def _reject_inadmissible_cases(db: Session, dataset_id: int) -> None:
    cases = (
        db.query(EvalCaseModel)
        .filter(EvalCaseModel.dataset_id == dataset_id, EvalCaseModel.status == "approved")
        .all()
    )
    for case in cases:
        metadata = case.metadata_json or {}
        flags = metadata.get("quality_flags") or {}
        admissible = metadata.get("admissible", flags.get("admissible"))
        if admissible is not False:
            continue
        reason = metadata.get("failure_reason") or flags.get("failure_reason") or "quality_not_checked"
        metadata["admissible"] = False
        metadata["failure_reason"] = reason
        metadata["quality_flags"] = {**flags, "admissible": False, "failure_reason": reason}
        case.metadata_json = metadata
        case.status = "rejected"
    db.commit()
