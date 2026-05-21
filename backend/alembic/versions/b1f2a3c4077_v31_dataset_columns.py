"""v31_dataset_columns

Revision ID: b1f2a3c4077
Revises: a9f121aa4076
Create Date: 2026-05-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1f2a3c4077'
down_revision: Union[str, Sequence[str], None] = 'a9f121aa4076'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("eval_datasets", sa.Column("manifest_json", sa.JSON(), nullable=True))
    op.add_column("eval_datasets", sa.Column("case_count", sa.Integer(), server_default="0"))
    op.add_column("eval_datasets", sa.Column("frozen_at", sa.DateTime(), nullable=True))
    op.add_column("eval_datasets", sa.Column("source_url", sa.String(1000), nullable=True))
    op.add_column("eval_datasets", sa.Column("license_note", sa.String(500), nullable=True))

    op.add_column("eval_cases", sa.Column("case_uid", sa.String(200), nullable=True))
    op.create_index("ix_eval_cases_case_uid", "eval_cases", ["case_uid"])
    op.add_column("eval_cases", sa.Column("task_type", sa.String(40), nullable=True))
    op.add_column("eval_cases", sa.Column("difficulty", sa.String(20), server_default="medium"))
    op.add_column("eval_cases", sa.Column("status", sa.String(20), server_default="draft"))
    op.add_column("eval_cases", sa.Column("gold_filing_id", sa.Integer(), nullable=True))
    op.add_column("eval_cases", sa.Column("gold_document_id", sa.Integer(), nullable=True))
    op.add_column("eval_cases", sa.Column("expected_calculation", sa.JSON(), nullable=True))
    op.add_column("eval_cases", sa.Column("rubric_json", sa.JSON(), nullable=True))

    op.create_foreign_key(
        "fk_eval_cases_gold_filing", "eval_cases", "filings",
        ["gold_filing_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_eval_cases_gold_document", "eval_cases", "documents",
        ["gold_document_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_eval_cases_gold_document", "eval_cases", type_="foreignkey")
    op.drop_constraint("fk_eval_cases_gold_filing", "eval_cases", type_="foreignkey")

    op.drop_column("eval_cases", "rubric_json")
    op.drop_column("eval_cases", "expected_calculation")
    op.drop_column("eval_cases", "gold_document_id")
    op.drop_column("eval_cases", "gold_filing_id")
    op.drop_column("eval_cases", "status")
    op.drop_column("eval_cases", "difficulty")
    op.drop_column("eval_cases", "task_type")
    op.drop_index("ix_eval_cases_case_uid", "eval_cases")
    op.drop_column("eval_cases", "case_uid")

    op.drop_column("eval_datasets", "license_note")
    op.drop_column("eval_datasets", "source_url")
    op.drop_column("eval_datasets", "frozen_at")
    op.drop_column("eval_datasets", "case_count")
    op.drop_column("eval_datasets", "manifest_json")
