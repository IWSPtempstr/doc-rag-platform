"""v32_ashare_market_facts

Revision ID: c2d4e5f60819
Revises: b1f2a3c4077
Create Date: 2026-05-21 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d4e5f60819"
down_revision: Union[str, Sequence[str], None] = "b1f2a3c4077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("trade_date", sa.String(length=20), nullable=False),
        sa.Column("metric", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=300), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=120), server_default="akshare"),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_facts_id", "market_facts", ["id"])
    op.create_index("ix_market_facts_ticker", "market_facts", ["ticker"])
    op.create_index("ix_market_facts_trade_date", "market_facts", ["trade_date"])


def downgrade() -> None:
    op.drop_index("ix_market_facts_trade_date", table_name="market_facts")
    op.drop_index("ix_market_facts_ticker", table_name="market_facts")
    op.drop_index("ix_market_facts_id", table_name="market_facts")
    op.drop_table("market_facts")
