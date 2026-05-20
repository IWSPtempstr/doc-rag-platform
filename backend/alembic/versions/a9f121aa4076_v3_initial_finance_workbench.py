"""v3_initial_finance_workbench

Revision ID: a9f121aa4076
Revises:
Create Date: 2026-05-20 21:29:05.922638

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9f121aa4076'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1"),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_workspaces_id", "workspaces", ["id"])
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=True)

    op.create_table(
        "memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(50), server_default="owner"),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_memberships_id", "memberships", ["id"])

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("cik", sa.String(20)),
        sa.Column("exchange", sa.String(50)),
        sa.Column("industry", sa.String(200)),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_companies_id", "companies", ["id"])
    op.create_index("ix_companies_ticker", "companies", ["ticker"])
    op.create_index("ix_companies_cik", "companies", ["cik"])

    op.create_table(
        "filings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer()),
        sa.Column("accession_number", sa.String(80)),
        sa.Column("filing_type", sa.String(20), server_default="10-K"),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("filed_at", sa.DateTime()),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("status", sa.String(30), server_default="imported"),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_filings_id", "filings", ["id"])
    op.create_index("ix_filings_accession", "filings", ["accession_number"])

    op.create_table(
        "filing_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filing_id", sa.Integer(), nullable=False),
        sa.Column("item_code", sa.String(20), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content_preview", sa.Text()),
        sa.Column("char_start", sa.Integer(), server_default="0"),
        sa.Column("char_end", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_filing_sections_id", "filing_sections", ["id"])

    op.create_table(
        "financial_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filing_id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(120), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("value", sa.Float()),
        sa.Column("unit", sa.String(50)),
        sa.Column("period", sa.String(50)),
        sa.Column("source", sa.String(120), server_default="extracted"),
        sa.Column("evidence", sa.Text()),
        sa.Column("confidence", sa.Float()),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_financial_facts_id", "financial_facts", ["id"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer()),
        sa.Column("filing_id", sa.Integer()),
        sa.Column("user_id", sa.Integer()),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(50), server_default="full"),
        sa.Column("status", sa.String(30), server_default="running"),
        sa.Column("answer", sa.Text()),
        sa.Column("citations", sa.JSON()),
        sa.Column("facts", sa.JSON()),
        sa.Column("calculations", sa.JSON()),
        sa.Column("verification", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("completed_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_agent_runs_id", "agent_runs", ["id"])

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("step_order", sa.Integer(), server_default="0"),
        sa.Column("node_name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), server_default="completed"),
        sa.Column("input_json", sa.JSON()),
        sa.Column("output_json", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_steps_id", "agent_steps", ["id"])

    op.create_table(
        "agent_artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("payload", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_artifacts_id", "agent_artifacts", ["id"])

    op.create_table(
        "eval_datasets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source", sa.String(80), server_default="custom"),
        sa.Column("version", sa.String(80), server_default="v1"),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_eval_datasets_id", "eval_datasets", ["id"])

    op.create_table(
        "eval_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text()),
        sa.Column("expected_evidence", sa.JSON()),
        sa.Column("expected_numeric", sa.Float()),
        sa.Column("tolerance", sa.Float(), server_default="0.01"),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_eval_cases_id", "eval_cases", ["id"])

    op.create_table(
        "eval_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer()),
        sa.Column("strategy", sa.String(80), server_default="finance_agent"),
        sa.Column("metrics", sa.JSON()),
        sa.Column("results", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_eval_results_id", "eval_results", ["id"])


def downgrade() -> None:
    op.drop_table("eval_results")
    op.drop_table("eval_cases")
    op.drop_table("eval_datasets")
    op.drop_table("agent_artifacts")
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")
    op.drop_table("financial_facts")
    op.drop_table("filing_sections")
    op.drop_table("filings")
    op.drop_table("companies")
    op.drop_table("memberships")
    op.drop_table("workspaces")
    op.drop_table("users")
