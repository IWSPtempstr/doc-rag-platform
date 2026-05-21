#!/usr/bin/env python
"""Generate a reproducible finance benchmark report from the local SQLite state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db import SessionLocal  # noqa: E402
from app.models import EvalCaseModel, EvalDatasetModel, EvalResultModel  # noqa: E402


def build_report(workspace_id: int) -> dict:
    db = SessionLocal()
    try:
        datasets = (
            db.query(EvalDatasetModel)
            .filter(EvalDatasetModel.workspace_id == workspace_id)
            .order_by(EvalDatasetModel.created_at.desc())
            .all()
        )
        latest_results = (
            db.query(EvalResultModel)
            .filter(EvalResultModel.workspace_id == workspace_id)
            .order_by(EvalResultModel.created_at.desc())
            .limit(10)
            .all()
        )
        dataset_rows = []
        for dataset in datasets:
            cases = db.query(EvalCaseModel).filter(EvalCaseModel.dataset_id == dataset.id).all()
            failure_counts: dict[str, int] = {}
            status_counts: dict[str, int] = {}
            for case in cases:
                status_counts[case.status] = status_counts.get(case.status, 0) + 1
                metadata = case.metadata_json or {}
                reason = metadata.get("failure_reason") or (metadata.get("quality_flags") or {}).get("failure_reason")
                if reason:
                    failure_counts[reason] = failure_counts.get(reason, 0) + 1
            dataset_rows.append({
                "id": dataset.id,
                "name": dataset.name,
                "source": dataset.source,
                "version": dataset.version,
                "case_count": dataset.case_count,
                "frozen": bool(dataset.frozen_at),
                "source_url": dataset.source_url,
                "license_note": dataset.license_note,
                "manifest": dataset.manifest_json or {},
                "status_counts": status_counts,
                "failure_counts": failure_counts,
            })
        return {
            "workspace_id": workspace_id,
            "datasets": dataset_rows,
            "latest_results": [
                {
                    "id": row.id,
                    "dataset_id": row.dataset_id,
                    "strategy": row.strategy,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "metrics": row.metrics or {},
                }
                for row in latest_results
            ],
        }
    finally:
        db.close()


def print_markdown(report: dict) -> None:
    print("# Finance Benchmark Report")
    print()
    print(f"Workspace: `{report['workspace_id']}`")
    print()
    print("## Public Datasets")
    for ds in report["datasets"]:
        print(f"- `{ds['name']}` ({ds['source']} {ds['version']}): cases={ds['case_count']}, frozen={ds['frozen']}")
        if ds.get("source_url"):
            print(f"  source: {ds['source_url']}")
        if ds.get("license_note"):
            print(f"  license: {ds['license_note']}")
        if ds["failure_counts"]:
            print(f"  failures: {json.dumps(ds['failure_counts'], ensure_ascii=False)}")
    print()
    print("## Latest Results")
    for result in report["latest_results"]:
        print(f"- result #{result['id']} dataset={result['dataset_id']} strategy={result['strategy']}")
        print(f"  metrics: {json.dumps(result['metrics'], ensure_ascii=False)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-id", type=int, default=1)
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()
    report = build_report(args.workspace_id)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_markdown(report)


if __name__ == "__main__":
    main()
